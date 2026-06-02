"""v5 - tiered parallel-personas + skeptic PR review.

The demo's punchline: v4's shape, ~7x cheaper, same quality. v4 ran four Sonnet
persona agents in parallel + one Opus skeptic and cost ~$2.31 on PR#3. v5 keeps
the multi-agent architecture intact and attacks cost on two axes from the blog,
WITHOUT throwing the personas or the skeptic away.

    Phase 0 - deterministic pre-phase (ZERO inference, runs in <1s)
        Pure Python over the PR's changed paths + diff text, before any model
        runs. Two reductions:
          * Persona gating - decide which personas have any surface area in
            this diff. If the diff touches no auth/crypto/secret/network/SQL/
            eval/PII code, `security_hawk` adds nothing; if it touches no
            data-access/loops/queries/IO, `perf_skeptic` adds nothing; etc.
            Dropping a persona removes a whole LLM call. (On a broad PR like #3
            most personas apply, so the saving is honest-but-small there; it
            pays off on narrow PRs.)
          * Skeptic-input pre-clustering - after stage 1, collapse findings that
            point at the same (file, line_start, category) into a single
            representative entry carrying every persona that raised it, so the
            expensive Opus call reads a smaller pool.
        Every decision is logged to stderr.

    Stage 1 - per-persona breadth agents, in parallel  ->  TIER: haiku
        Same as v4 (one agent per kept persona, diff-only, ThreadPoolExecutor),
        but on `specialist_narrow` (haiku) instead of `specialist_reasoning`
        (sonnet). Breadth work doesn't need a frontier model — this is the big
        per-token saving (~3x cheaper input/output than sonnet).

    Stage 2 - skeptic pass, one call  ->  TIER: opus (kept)
        Same Opus skeptic as v4 ("let the smartest agent prune"), but fed the
        pre-clustered pool instead of the raw union, so it processes fewer
        entries. It still prunes false positives, merges cross-cluster
        duplicates, and records agreement in `extra.raised_by`/`extra.skeptic`.

Public API:
    review(pr, config) -> ReviewResult            # used by the eval harness

CLI:
    python review.py <pr-url-or-number> [--repo OWNER/REPO]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

# Make `shared/` importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (  # noqa: E402
    Config,
    Finding,
    PullRequest,
    Usage,
    call,
    extract_fenced_json,
    fetch_pull_request,
    load_config,
    parse_pr_arg,
)
from shared.cost import sum_usage  # noqa: E402
from shared.llm import CallResult  # noqa: E402

# Fallback source when the model omits / mangles the persona tag on a finding.
DEFAULT_SOURCE = "v5_tiered"

# Retry behavior for the parallel persona calls. Concurrent subprocess launches
# can trip transient socket errors (EADDRNOTAVAIL, connection reset) under the
# shared rate limit; back off and retry a couple of times before giving up.
_MAX_ATTEMPTS = 3  # 1 initial + 2 retries
_TRANSIENT_MARKERS = ("EADDRNOTAVAIL", "ECONNRESET", "reset", "address", "rate", "429", "529")
_TRANSIENT_BACKOFF_SECONDS = 30.0
_DEFAULT_BACKOFF_SECONDS = 5.0

# The personas live in `pr-agent/personas/*.md`. This file is at
# `pr-agent/v5_tiered/review.py`, so the pr-agent root is two up.
_PR_AGENT_ROOT = Path(__file__).resolve().parent.parent
_PERSONAS_DIR = _PR_AGENT_ROOT / "personas"


def _load_personas() -> list[tuple[str, str]]:
    """Read every persona profile under `pr-agent/personas/`.

    Returns a list of (persona_id, markdown_body) sorted by id for a stable,
    deterministic prompt. `persona_id` is the filename stem (e.g.
    "security_hawk"); it is also the value each agent stamps on its findings'
    `source`, so attribution survives the round trip.
    """
    if not _PERSONAS_DIR.is_dir():
        raise FileNotFoundError(f"Personas directory not found: {_PERSONAS_DIR}")
    personas: list[tuple[str, str]] = []
    for path in sorted(_PERSONAS_DIR.glob("*.md")):
        personas.append((path.stem, path.read_text(encoding="utf-8")))
    if not personas:
        raise FileNotFoundError(f"No persona files (*.md) found in {_PERSONAS_DIR}")
    return personas


# --- Phase 0: deterministic pre-phase (no inference) -----------------------

# Per-persona trigger vocabulary. A persona is kept iff the lowercased diff
# signal (changed file paths + added/removed code lines) contains at least one
# of its triggers. These are intentionally broad: the goal is to drop a persona
# only when the diff genuinely has NO surface for its lens, never to risk recall
# on a PR the persona could speak to. `security_hawk` and `perf_skeptic` are the
# ones that actually gate (a pure-IO-free or pure-auth-free diff), while
# `kiss_zealot`/`quality_critic` are general code-structure lenses that fire on
# almost any executable change and drop only on pure data/config/doc diffs.
_PERSONA_TRIGGERS: dict[str, tuple[str, ...]] = {
    "security_hawk": (
        ".env", ".gitignore", "auth", "jwt", "login", "logout", "password",
        "passwd", "secret", "token", "crypto", "webhook", "admin", "cors",
        "session", "cookie", "eval(", "new function", "bcrypt", "md5", "sha1",
        "createhash", "math.random", "randombytes", "fetch(", "http://",
        "https://", "req.query", "req.body", "req.headers", "req.params",
        "process.env", "select ", "insert ", "update ", "delete ", "query(",
        "card", "cvc", "pan", "api_key", "apikey", "authorization", "role",
        "ssrf", "redirect", "encrypt", "decrypt", "hash", "privilege", "bypass",
    ),
    "perf_skeptic": (
        "findall", "findby", ".find(", ".filter(", ".map(", ".foreach(",
        "for (", "for(", "while (", "while(", "await ", "promise.all",
        "query(", "fetch(", ".save(", "findmany", "repo.", "repository",
        "limit", "offset", "cursor", "paginat", "csv", "stream",
        "express.json", "json({", "json.stringify", ".reduce(", ".join(",
        ".sort(", "n+1", "cache", "index", "scan", "batch", "loop",
    ),
    "kiss_zealot": (
        "abstract class", "abstract ", "interface ", "class ", "factory",
        "strategy", "manager", " extends ", " implements ", "@ts-nocheck",
        "@ts-ignore", "eslint-disable", "as any", ": any", "new ", "singleton",
        "export const", "function ", "=> {", "enum ", "decorator", "config",
        "flag", "// ", "/*", "abstractbase", "wrapper", "helper",
    ),
    "quality_critic": (
        "catch", "try {", "try{", "console.", "res.status", "res.json",
        "res.send", "z.", "zod", "test(", "it(", "describe(", "expect(",
        "var ", " == ", "!=", "throw", "logger", "function ", "=>",
        "req.body", "req.query", "return ", "async ", "interface ", ".test.",
        ".spec.", "schema", "validate", "status(",
    ),
}


def _diff_signal(pr: PullRequest) -> tuple[list[str], str]:
    """Extract the deterministic matching surface from the PR diff.

    Returns (changed_paths, lowered_blob) where `blob` is the concatenation of
    changed file paths + every added/removed code line, lowercased. This is the
    only thing the prefilter inspects — pure text, no model.
    """
    paths: list[str] = []
    parts: list[str] = []
    for line in pr.diff.splitlines():
        if line.startswith("diff --git"):
            parts.append(line)
        elif line.startswith("+++ ") or line.startswith("--- "):
            p = line[4:].strip()
            if p and p != "/dev/null":
                if p.startswith(("a/", "b/")):
                    p = p[2:]
                paths.append(p)
                parts.append(p)
        elif line.startswith(("+", "-")):
            parts.append(line[1:])
    blob = "\n".join(parts).lower()
    return sorted(set(paths)), blob


@dataclass
class PrefilterDecision:
    persona_id: str
    kept: bool
    reason: str


def _prefilter(
    pr: PullRequest, personas: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], list[PrefilterDecision], list[str]]:
    """Decide which personas to run, deterministically, with no LLM call.

    Keeps a persona iff its lens has any surface in the diff. Falls back to
    keeping every persona if the prefilter would otherwise drop them all (an
    empty/odd diff shouldn't silently produce an empty review).
    """
    paths, blob = _diff_signal(pr)
    kept: list[tuple[str, str]] = []
    decisions: list[PrefilterDecision] = []
    for pid, body in personas:
        triggers = _PERSONA_TRIGGERS.get(pid)
        if triggers is None:
            kept.append((pid, body))
            decisions.append(PrefilterDecision(pid, True, "no trigger profile; kept by default"))
            continue
        hits = sorted({kw.strip() for kw in triggers if kw in blob})
        if hits:
            sample = ", ".join(hits[:6])
            more = f" (+{len(hits) - 6} more)" if len(hits) > 6 else ""
            kept.append((pid, body))
            decisions.append(
                PrefilterDecision(pid, True, f"{len(hits)} signal(s): {sample}{more}")
            )
        else:
            decisions.append(PrefilterDecision(pid, False, "no relevant surface in diff"))

    if not kept:
        kept = list(personas)
        decisions = [
            PrefilterDecision(pid, True, "fallback: prefilter matched nothing, keeping all")
            for pid, _ in personas
        ]
    return kept, decisions, paths


# --- Stage 1: per-persona agent prompts (identical contract to v4) ---------

_PERSONA_PREAMBLE = """\
You are a single, opinionated senior reviewer doing a focused pass over a pull
request. Your full profile is below. Review ONLY through your own lens — your
taste, your pet issues, your bar for what blocks a merge. Do NOT try to be a
balanced, generic "senior reviewer"; another teammate covers the concerns you
don't. A finding only you would care about is still a finding worth raising.

It is fine — expected, even — to surface issues another reviewer might also
catch; a later skeptic pass deduplicates across the team, so err toward
reporting what you see rather than self-censoring for fear of overlap. Do not,
however, pad the list with issues outside your lens.

ATTRIBUTION - REQUIRED. Every finding MUST carry a `source` field set to
EXACTLY this persona id (no other value):
{persona_id}
"""


_OUTPUT_CONTRACT = """\
Categories you should look for:
- security      secrets in code, injection, broken auth, SSRF, PII / PCI leaks
- performance   N+1, unbounded work, sync I/O on hot paths, missing pagination
- correctness   bugs, regressions, race conditions, broken edge cases
- dry           duplicated logic that should be shared
- kiss          over-engineering, unnecessary abstractions, dead code
- test          missing tests, tests that pass for the wrong reason
- standards     naming, formatting, inconsistency with the rest of the diff
- quality       anything else a senior reviewer would flag

Severity:
- must         CI / security / data-loss / would block merge
- should       quality issues a reviewer would normally request changes for
- suggestion   nits and improvements that aren't blocking

Output format - REQUIRED.

Reply with a single ```json fenced block. Do not include any other prose
before or after the block. The block must parse as JSON with this shape:

```json
{
  "summary": "one short paragraph summarizing what you found through your lens",
  "findings": [
    {
      "file": "path/as/it/appears/in/the/diff",
      "line_start": 12,
      "line_end": 18,
      "category": "security",
      "severity": "must",
      "title": "short headline, <= 80 chars",
      "message": "what is wrong, why it matters, suggested fix",
      "source": "PERSONA_ID"
    }
  ]
}
```

If you find nothing through your lens, return an empty `findings` list and say
so in `summary`. Use only the file paths that appear in the diff (do not
fabricate paths). Use line numbers that appear in the diff hunks; if you cannot
point to a specific line, use the start of the relevant hunk."""


def _build_persona_system(persona_id: str, body: str) -> str:
    """System prompt for ONE persona agent: only that persona + the contract."""
    preamble = _PERSONA_PREAMBLE.format(persona_id=persona_id)
    profile = f"### PERSONA: {persona_id}\n\n{body.strip()}"
    contract = _OUTPUT_CONTRACT.replace("PERSONA_ID", persona_id)
    return "\n\n".join([preamble, profile, contract])


def _build_user_message(pr: PullRequest) -> str:
    return (
        f"Repository: {pr.repo}\n"
        f"PR #{pr.number}: {pr.title}\n"
        f"Author:     {pr.author}\n"
        f"Size:       +{pr.additions} / -{pr.deletions} across {pr.changed_files} files\n"
        f"\n"
        f"Description:\n{pr.body or '(no description)'}\n"
        f"\n"
        f"Diff:\n"
        f"```diff\n"
        f"{pr.diff}\n"
        f"```\n"
    )


# --- Stage 2: skeptic prompt (edit-list over a pre-clustered pool) ----------
#
# Cost note: v4's opus skeptic RE-AUTHORED every surviving finding (full prose),
# which is the single most expensive thing in the pipeline at $75/1M output. v5
# keeps opus as the arbiter but only asks it for an EDIT LIST — which clusters to
# drop, which to merge, which to re-severity. The final prose is reused verbatim
# from the (cheap) haiku findings. Opus still does all the judging; it just stops
# paying frontier output rates to retype text the panel already wrote.

# How long a cluster's message is shown to opus. Full haiku messages are ~150
# tokens each; truncating roughly halves the pool's input footprint while leaving
# opus enough of the claim to verify it against the diff.
_SKEPTIC_MSG_PREVIEW_CHARS = 280

_SKEPTIC_SYSTEM = """\
You are the most senior, most skeptical reviewer on the team — the final gate. A
panel of specialist reviewers (some subset of security_hawk, perf_skeptic,
kiss_zealot, quality_critic) each reviewed this pull request independently and
through their own narrow lens. Their findings have already been
DETERMINISTICALLY PRE-CLUSTERED for you: findings that pointed at the same file,
line, and category were collapsed into one entry with a stable `id` (c0, c1, …)
and a `raised_by` array listing every persona that flagged it. You are handed
that clustered pool as JSON.

Pre-clustering only merged EXACT file+line+category matches. Across clusters the
panel is still noisy: false positives, over-broad pattern matches, and several
clusters that are really the SAME underlying issue at slightly different lines or
under different categories.

You will NOT rewrite findings. The panel's wording is kept as-is. Your job is to
return a small EDIT LIST that turns the clustered pool into the crisp list a
staff engineer would actually post. By default every cluster is KEPT; you only
report the exceptions:

1. drops   — cluster ids that are false positives / over-broad / not actually
             true of THIS diff / not worth blocking on. Verify against the diff
             before dropping a real issue. Be conservative: when in doubt, keep.
2. merges  — when several clusters are the same underlying issue, name ONE id to
             keep and the ids to fold into it. The kept finding inherits the
             union of all their personas (high-confidence agreement). Merge
             aggressively across slightly-different lines / categories so the
             final list has no near-duplicates.
3. severities — cluster ids whose severity you want to correct, with the new
             value. A real secret / RCE / auth bypass is `must`; a
             defense-in-depth nit is `should` or `suggestion`.

Do not invent ids that aren't in the pool. Do not add issues the panel did not
raise.

Output format - REQUIRED.

Reply with a single ```json fenced block, no prose before or after. Shape:

```json
{
  "summary": "one short paragraph: what survived, what you pruned/merged, where the panel agreed",
  "drops": ["c7", "c19"],
  "merges": [
    { "keep": "c2", "fold": ["c11", "c30"] }
  ],
  "severities": [
    { "id": "c5", "severity": "must" }
  ]
}
```

Every cluster you do NOT list in `drops` or as a folded id is kept with its
original wording. If you have nothing to prune or merge, return empty arrays."""


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _build_skeptic_user(pr: PullRequest, clusters: list[tuple[Finding, list[str]]]) -> str:
    pool_json = json.dumps(
        [
            {
                "id": f"c{i}",
                "file": rep.file,
                "line_start": rep.line_start,
                "line_end": rep.line_end,
                "category": rep.category,
                "severity": rep.severity,
                "title": rep.title,
                "message": _truncate(rep.message, _SKEPTIC_MSG_PREVIEW_CHARS),
                "raised_by": raised_by,
            }
            for i, (rep, raised_by) in enumerate(clusters)
        ],
        indent=2,
    )
    return (
        f"{_build_user_message(pr)}\n"
        f"The persona agents' findings pre-clustered to {len(clusters)} entries "
        f"(identical file+line+category already merged; `raised_by` lists every "
        f"persona behind each; messages are truncated previews). Return your edit "
        f"list over these cluster ids:\n"
        f"```json\n{pool_json}\n```\n"
    )


# --- Result shape ----------------------------------------------------------


@dataclass
class ReviewResult:
    findings: list[Finding]
    usage: Usage
    cost_usd: float
    summary: str
    raw_response: str = ""
    resolved_model: str = ""
    num_turns: int = 0
    duration_ms: int = 0
    error: str | None = None


# --- Finding coercion (identical to v4) ------------------------------------


def _coerce_persona_findings(
    raw_obj: dict | None, persona_id: str
) -> tuple[str, list[Finding]]:
    """Parse one persona agent's JSON into (summary, findings).

    Every finding is force-tagged with this agent's `persona_id` regardless of
    what the model put in `source` — a single-persona agent can only speak for
    itself, so attribution can't drift.
    """
    if not raw_obj:
        return "", []
    summary = str(raw_obj.get("summary") or "")
    findings: list[Finding] = []
    for raw in raw_obj.get("findings") or []:
        if not isinstance(raw, dict):
            continue
        try:
            findings.append(
                Finding(
                    file=str(raw["file"]),
                    line_start=int(raw["line_start"]),
                    line_end=int(raw["line_end"]),
                    category=str(raw["category"]),
                    severity=str(raw["severity"]),  # type: ignore[arg-type]
                    title=str(raw["title"]),
                    message=str(raw["message"]),
                    source=persona_id,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            sys.stderr.write(f"warning: dropped malformed finding ({exc}): {raw!r}\n")
    return summary, findings


_SKEPTIC_KEYS = ("drops", "merges", "severities")


def _apply_skeptic_edits(
    raw_obj: dict | None,
    clusters: list[tuple[Finding, list[str]]],
    valid_sources: set[str],
) -> tuple[str, list[Finding]] | None:
    """Apply the opus skeptic's EDIT LIST to the clustered pool.

    The skeptic returns only exceptions (drops / merges / severity overrides);
    every other cluster is kept with its original (haiku-authored) wording. The
    final findings are reconstructed here, so opus never pays output tokens to
    retype prose the panel already wrote.

    Returns (summary, findings), or None if the response is unusable (no
    recognized edit keys / nothing parses) so the caller can fall back to the
    de-duplicated pool.
    """
    if not isinstance(raw_obj, dict) or not any(k in raw_obj for k in _SKEPTIC_KEYS):
        return None

    summary = str(raw_obj.get("summary") or "")
    ids = [f"c{i}" for i in range(len(clusters))]
    valid_ids = set(ids)
    rep_by = {ids[i]: clusters[i][0] for i in range(len(clusters))}
    raised_by: dict[str, list[str]] = {ids[i]: list(clusters[i][1]) for i in range(len(clusters))}

    drops = {str(x) for x in (raw_obj.get("drops") or []) if str(x) in valid_ids}

    severity_override: dict[str, str] = {}
    for s in raw_obj.get("severities") or []:
        if isinstance(s, dict) and str(s.get("id")) in valid_ids:
            sev = str(s.get("severity") or "").strip()
            if sev:
                severity_override[str(s["id"])] = sev

    folded: set[str] = set()
    for m in raw_obj.get("merges") or []:
        if not isinstance(m, dict):
            continue
        keep = str(m.get("keep") or "")
        if keep not in valid_ids:
            continue
        for fid in m.get("fold") or []:
            fid = str(fid)
            if fid in valid_ids and fid != keep:
                folded.add(fid)
                for src in raised_by.get(fid, []):
                    if src not in raised_by[keep]:
                        raised_by[keep].append(src)

    removed = drops | folded
    findings: list[Finding] = []
    for cid in ids:
        if cid in removed:
            continue
        rep = rep_by[cid]
        raised = raised_by[cid]
        source = rep.source if rep.source in valid_sources else DEFAULT_SOURCE
        findings.append(
            Finding(
                file=rep.file,
                line_start=rep.line_start,
                line_end=rep.line_end,
                category=rep.category,
                severity=severity_override.get(cid, rep.severity),  # type: ignore[arg-type]
                title=rep.title,
                message=rep.message,
                source=source,
                extra={
                    "raised_by": raised,
                    "skeptic": "merged" if len(raised) > 1 else "kept",
                },
            )
        )

    if not findings:
        return None
    return summary, findings


# --- Skeptic-input pre-clustering (deterministic, no inference) ------------


def _cluster_pool(pool: list[Finding]) -> tuple[list[tuple[Finding, list[str]]], int]:
    """Collapse findings that share (file, line_start, category) into clusters.

    Returns (clusters, dropped) where each cluster is (representative_finding,
    raised_by_personas) and `dropped` is how many raw findings were folded away.
    The representative keeps the longest message (most detailed wording). This
    shrinks the pool the expensive Opus skeptic must read while preserving the
    agreement signal in `raised_by` — the skeptic merges further across clusters.
    """
    reps: dict[tuple[str, int, str], Finding] = {}
    raised: dict[tuple[str, int, str], list[str]] = {}
    order: list[tuple[str, int, str]] = []
    folded = 0
    for f in pool:
        key = (f.file, f.line_start, f.category)
        if key not in reps:
            reps[key] = f
            raised[key] = [f.source]
            order.append(key)
        else:
            folded += 1
            if f.source not in raised[key]:
                raised[key].append(f.source)
            if len(f.message) > len(reps[key].message):
                reps[key] = f
    clusters = [(reps[k], raised[k]) for k in order]
    return clusters, folded


def _dedup_pool(pool: list[Finding]) -> list[Finding]:
    """Fallback dedup used when the skeptic call fails.

    Collapses findings that point at the same (file, line_start, category) and
    records the personas that raised each in `extra.raised_by`.
    """
    merged: dict[tuple[str, int, str], Finding] = {}
    order: list[tuple[str, int, str]] = []
    for f in pool:
        key = (f.file, f.line_start, f.category)
        if key not in merged:
            kept = Finding(
                file=f.file,
                line_start=f.line_start,
                line_end=f.line_end,
                category=f.category,
                severity=f.severity,
                title=f.title,
                message=f.message,
                source=f.source,
                extra={"raised_by": [f.source], "skeptic": "fallback-dedup"},
            )
            merged[key] = kept
            order.append(key)
        else:
            raised_by = merged[key].extra.setdefault("raised_by", [])
            if f.source not in raised_by:
                raised_by.append(f.source)
    return [merged[k] for k in order]


# --- Retry wrapper (identical to v4) ---------------------------------------


def _is_transient(error: str | None) -> bool:
    if not error:
        return False
    low = error.lower()
    return any(m.lower() in low for m in _TRANSIENT_MARKERS)


def _call_with_retry(*, system: str, user: str, model: str, label: str) -> CallResult:
    """`shared.call` with a small backoff/retry on transient socket/rate errors."""
    last: CallResult | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        result = call(system=system, user=user, model=model, tools_enabled=False)
        if not result.is_error:
            return result
        last = result
        if attempt < _MAX_ATTEMPTS and _is_transient(result.error):
            backoff = (
                _TRANSIENT_BACKOFF_SECONDS
                if _is_transient(result.error)
                else _DEFAULT_BACKOFF_SECONDS
            )
            sys.stderr.write(
                f"warning: {label} transient error (attempt {attempt}/{_MAX_ATTEMPTS}): "
                f"{result.error}; retrying in {backoff:.0f}s\n"
            )
            time.sleep(backoff)
            continue
        break
    return last  # type: ignore[return-value]


# --- Stages ----------------------------------------------------------------


def _run_persona_agents(
    pr: PullRequest,
    personas: list[tuple[str, str]],
    model: str,
    *,
    parallel: bool = True,
) -> dict[str, CallResult]:
    """Run one agent per persona. Returns {persona_id: CallResult}."""
    user = _build_user_message(pr)

    def _one(item: tuple[str, str]) -> tuple[str, CallResult]:
        pid, body = item
        sys.stderr.write(f"  [stage1] persona agent: {pid} (haiku)\n")
        res = _call_with_retry(
            system=_build_persona_system(pid, body),
            user=user,
            model=model,
            label=f"persona {pid}",
        )
        return pid, res

    results: dict[str, CallResult] = {}
    if parallel:
        with ThreadPoolExecutor(max_workers=len(personas)) as pool:
            for pid, res in pool.map(_one, personas):
                results[pid] = res
    else:
        for item in personas:
            pid, res = _one(item)
            results[pid] = res
    return results


def review(pr: PullRequest, config: Config) -> ReviewResult:
    """Run v5: deterministic prefilter -> parallel haiku personas -> opus skeptic."""
    started = time.monotonic()

    all_personas = _load_personas()
    valid_sources = {pid for pid, _ in all_personas}
    # TIER: stage-1 breadth agents on haiku (specialist_narrow), not sonnet.
    persona_model = config.model_for("specialist_narrow")
    skeptic_model = config.model_for("skeptic")

    # --- Phase 0: deterministic pre-phase (no inference) ---
    kept_personas, decisions, changed_paths = _prefilter(pr, all_personas)
    sys.stderr.write(
        f"  [prefilter] {len(changed_paths)} changed file(s); "
        f"{len(kept_personas)}/{len(all_personas)} personas kept\n"
    )
    for d in decisions:
        verb = "KEEP" if d.kept else "DROP"
        sys.stderr.write(f"    [prefilter] {verb} {d.persona_id}: {d.reason}\n")

    # --- Stage 1: parallel persona agents (haiku) ---
    persona_results = _run_persona_agents(pr, kept_personas, persona_model, parallel=True)

    # If EVERY kept persona agent failed under parallel load, retry once
    # sequentially before giving up — concurrent subprocess launches are the
    # usual culprit under the shared rate limit.
    if persona_results and all(r.is_error for r in persona_results.values()):
        sys.stderr.write(
            "warning: all persona agents errored in parallel; retrying sequentially\n"
        )
        persona_results = _run_persona_agents(
            pr, kept_personas, persona_model, parallel=False
        )

    pooled: list[Finding] = []
    all_calls: list[CallResult] = []
    stage1_cost = 0.0
    for pid, res in persona_results.items():
        all_calls.append(res)
        stage1_cost += res.cost_usd
        if res.is_error:
            sys.stderr.write(f"warning: persona agent {pid} failed: {res.error}\n")
            continue
        _, found = _coerce_persona_findings(extract_fenced_json(res.text), pid)
        pooled.extend(found)
        sys.stderr.write(
            f"  [stage1] {pid}: {len(found)} finding(s)  cost=${res.cost_usd:.4f}\n"
        )

    # --- Phase 0 (cont.): pre-cluster the pool before the expensive opus call ---
    clusters, folded = _cluster_pool(pooled)
    if pooled:
        sys.stderr.write(
            f"  [precluster] {len(pooled)} raw -> {len(clusters)} clusters "
            f"({folded} exact file+line+category dupes folded before skeptic)\n"
        )

    # --- Stage 2: skeptic pass (opus) ---
    skeptic_res: CallResult | None = None
    skeptic_summary = ""
    final_findings: list[Finding] = []

    if clusters:
        skeptic_res = _call_with_retry(
            system=_SKEPTIC_SYSTEM,
            user=_build_skeptic_user(pr, clusters),
            model=skeptic_model,
            label="skeptic",
        )
        all_calls.append(skeptic_res)
        edited = (
            None
            if skeptic_res.is_error
            else _apply_skeptic_edits(
                extract_fenced_json(skeptic_res.text), clusters, valid_sources
            )
        )
        if edited is None:
            why = skeptic_res.error if skeptic_res.is_error else "unusable edit list"
            sys.stderr.write(
                f"warning: skeptic unusable ({why}); "
                f"falling back to de-duplicated stage-1 pool\n"
            )
            final_findings = _dedup_pool(pooled)
            skeptic_summary = (
                "Skeptic pass failed; returning the de-duplicated union of the "
                "persona agents' findings (unfiltered)."
            )
        else:
            skeptic_summary, final_findings = edited
            sys.stderr.write(
                f"  [stage2] skeptic edit: {len(clusters)} clusters -> "
                f"{len(final_findings)} findings  cost=${skeptic_res.cost_usd:.4f}\n"
            )
    else:
        skeptic_summary = "No persona agent produced any findings."

    # --- Aggregate usage / cost across every call actually made ---
    total_usage = sum_usage(c.usage for c in all_calls)
    total_cost = sum(c.cost_usd for c in all_calls)
    num_calls = len(all_calls)
    duration_ms = int((time.monotonic() - started) * 1000)

    skeptic_cost = skeptic_res.cost_usd if skeptic_res is not None else 0.0
    kept_ids = ",".join(pid for pid, _ in kept_personas) or "none"
    sys.stderr.write(
        f"  [cost] prefilter(kept {len(kept_personas)}/{len(all_personas)}: {kept_ids})  "
        f"stage1 ({len(kept_personas)}x haiku)=${stage1_cost:.4f}  "
        f"stage2 (1x opus)=${skeptic_cost:.4f}  "
        f"total=${total_cost:.4f}\n"
    )

    resolved_model = ""
    if skeptic_res is not None and not skeptic_res.is_error:
        resolved_model = skeptic_res.resolved_model
    elif all_calls:
        resolved_model = next(
            (c.resolved_model for c in all_calls if c.resolved_model), persona_model
        )

    error: str | None = None
    if not all_calls:
        error = "no calls were made"
    elif all(c.is_error for c in all_calls):
        error = "all persona agents and the skeptic failed"

    return ReviewResult(
        findings=final_findings,
        usage=total_usage,
        cost_usd=total_cost,
        summary=skeptic_summary,
        raw_response=skeptic_res.text if skeptic_res is not None else "",
        resolved_model=resolved_model,
        num_turns=num_calls,
        duration_ms=duration_ms,
        error=error,
    )


# --- CLI -------------------------------------------------------------------


def _render_for_cli(result: ReviewResult) -> str:
    lines: list[str] = []
    if result.error:
        lines.append(f"ERROR: {result.error}")
        return "\n".join(lines)

    lines.append(result.summary or "(no summary)")
    lines.append("")
    if not result.findings:
        lines.append("No findings.")
    else:
        for i, f in enumerate(result.findings, start=1):
            raised_by = f.extra.get("raised_by") if isinstance(f.extra, dict) else None
            tag = f.source
            if isinstance(raised_by, list) and len(raised_by) > 1:
                tag = f"{f.source} +{len(raised_by) - 1} (agreement)"
            lines.append(
                f"[{i}] {f.severity.upper()} {f.category} ({tag}) - "
                f"{f.file}:{f.line_start}-{f.line_end}"
            )
            lines.append(f"    {f.title}")
            for body_line in f.message.splitlines():
                lines.append(f"    {body_line}")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="v5 tiered parallel-personas + skeptic PR reviewer"
    )
    parser.add_argument("pr", help="PR URL or number")
    parser.add_argument(
        "--repo",
        default=None,
        help="OWNER/REPO when 'pr' is a bare number (defaults to config.yaml repo)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (defaults to pr-agent/config.yaml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw findings + usage as JSON instead of human prose",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    repo, number = parse_pr_arg(args.pr)
    if args.repo:
        repo = args.repo
    if repo is None:
        repo = config.repo.slug

    pr = fetch_pull_request(repo, number)
    sys.stderr.write(
        f"Reviewing {pr.repo}#{pr.number} ({pr.title!r}, "
        f"+{pr.additions}/-{pr.deletions}, {pr.changed_files} files)...\n"
    )

    result = review(pr, config)

    if args.json:
        out = {
            "summary": result.summary,
            "findings": [f.as_dict() for f in result.findings],
            "usage": {
                "input_tokens": result.usage.input_tokens,
                "cache_creation_input_tokens": result.usage.cache_creation_input_tokens,
                "cache_read_input_tokens": result.usage.cache_read_input_tokens,
                "output_tokens": result.usage.output_tokens,
            },
            "cost_usd": result.cost_usd,
            "resolved_model": result.resolved_model,
            "num_turns": result.num_turns,
            "duration_ms": result.duration_ms,
            "error": result.error,
        }
        print(json.dumps(out, indent=2))
    else:
        print(_render_for_cli(result))
        sys.stderr.write(
            f"\nmodel={result.resolved_model} calls={result.num_turns}\n"
            f"tokens: in={result.usage.input_tokens} "
            f"cache_w={result.usage.cache_creation_input_tokens} "
            f"cache_r={result.usage.cache_read_input_tokens} "
            f"out={result.usage.output_tokens}\n"
            f"cost=${result.cost_usd:.4f}  duration={result.duration_ms}ms\n"
        )
    return 0 if not result.error else 1


if __name__ == "__main__":
    sys.exit(main())
