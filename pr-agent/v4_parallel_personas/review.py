"""v4 - parallel-personas + skeptic PR review.

The demo's "we got greedy" moment. v3 concatenated the team's four reviewer
personas into ONE prompt and made a single call. v4 stops bundling: it runs

    Stage 1 - one agent per persona, in parallel
        Four separate `shared.call(...)`s, each on `specialist_reasoning`
        (sonnet). Each agent's system prompt contains ONLY that one persona's
        profile + the output contract, so it reviews the full PR diff through a
        single lens and tags every finding `source=<persona_id>`. The four calls
        run concurrently (threads — `shared.call` is a blocking subprocess).
        Their findings are pooled; duplicates / overlaps / false positives are
        EXPECTED here and are the skeptic's problem, not stage 1's.

    Stage 2 - skeptic pass, one call
        A single `shared.call(...)` on `skeptic` (opus). It gets the diff plus
        the full pooled stage-1 findings as JSON (each tagged with its `source`
        persona) and is asked to: drop false positives / over-broad pattern
        matches, merge duplicates that several personas raised into one finding,
        and — when multiple personas independently flagged the same thing — KEEP
        it and record the agreement (high confidence) in
        `extra.raised_by` + `extra.skeptic`. Its filtered/merged list is what
        v4 returns.

This is deliberately the powerful-but-expensive shape (5 real calls: 4 sonnet +
1 opus). v5 is the one that makes it cheap via tiering — v4 does NOT
cost-optimize.

The axis v4 isolates over v3: architecture (parallel agents + skeptic) rather
than the prompt. Same diff-only / no-tools shape; the agentic/repo dimension was
v2's.

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
DEFAULT_SOURCE = "v4_parallel_personas"

# Retry behavior for the parallel persona calls. Concurrent subprocess launches
# can trip transient socket errors (EADDRNOTAVAIL, connection reset) under the
# shared rate limit; back off and retry a couple of times before giving up.
_MAX_ATTEMPTS = 3
_TRANSIENT_MARKERS = ("EADDRNOTAVAIL", "ECONNRESET", "reset", "address", "rate", "429", "529")
_TRANSIENT_BACKOFF_SECONDS = 30.0
_DEFAULT_BACKOFF_SECONDS = 5.0

# The personas live in `pr-agent/personas/*.md`. This file is at
# `pr-agent/v4_parallel_personas/review.py`, so the pr-agent root is two up.
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


# --- Stage 1: per-persona agent prompts -----------------------------------

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


# --- Stage 2: skeptic prompt ----------------------------------------------

_SKEPTIC_SYSTEM = """\
You are the most senior, most skeptical reviewer on the team — the final gate. A
panel of four specialist reviewers (security_hawk, perf_skeptic, kiss_zealot,
quality_critic) each reviewed this pull request independently and through their
own narrow lens. Their pooled raw findings are handed to you as JSON, each tagged
with the `source` persona that raised it.

Specialists running in isolation are noisy: they raise false positives, match
patterns too broadly, and several of them often flag the SAME underlying issue
from different angles. Your job is to turn that noisy pool into the crisp list a
staff engineer would actually post on the PR.

Do this:
1. DROP false positives and over-broad pattern matches — anything that isn't
   actually true of THIS diff, or that no reasonable reviewer would block on.
   Verify each claim against the diff before keeping it.
2. MERGE duplicates: when multiple personas flagged the same underlying issue
   (same file + same code, even if worded differently), collapse them into ONE
   finding. Pick the clearest title/message; set `source` to the most relevant
   persona (or the first that raised it).
3. RECORD AGREEMENT: every finding you keep MUST include an `extra` object with:
     - "raised_by": [list of every persona id that flagged this issue]
     - "skeptic": "kept"   for a single-persona finding you validated, or
                  "merged" for a finding you collapsed from several personas.
   When more than one persona independently raised the same issue, KEEP it —
   independent agreement is a strong signal — and note all of them in
   `raised_by` (this is your high-confidence set).
4. Keep severity honest: a real secret / RCE / auth bypass is `must`; a
   defense-in-depth nit is `should` or `suggestion`.

Preserve the original persona in each finding's `source`. Do not invent new
persona ids. Do not add issues the panel did not raise.

Output format - REQUIRED.

Reply with a single ```json fenced block, no prose before or after. Shape:

```json
{
  "summary": "one short paragraph: what survived, what you pruned, where the panel agreed",
  "findings": [
    {
      "file": "path/as/it/appears/in/the/diff",
      "line_start": 12,
      "line_end": 18,
      "category": "security",
      "severity": "must",
      "title": "short headline, <= 80 chars",
      "message": "what is wrong, why it matters, suggested fix",
      "source": "security_hawk",
      "extra": { "raised_by": ["security_hawk", "quality_critic"], "skeptic": "merged" }
    }
  ]
}
```

If after pruning nothing survives, return an empty `findings` list and say so in
`summary`. Use only file paths and line numbers that appear in the diff."""


def _build_skeptic_user(pr: PullRequest, pooled: list[Finding]) -> str:
    pool_json = json.dumps(
        [
            {
                "file": f.file,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "category": f.category,
                "severity": f.severity,
                "title": f.title,
                "message": f.message,
                "source": f.source,
            }
            for f in pooled
        ],
        indent=2,
    )
    return (
        f"{_build_user_message(pr)}\n"
        f"The four persona agents raised {len(pooled)} findings in total. "
        f"Here is the full pool (each tagged with the persona that raised it):\n"
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


# --- Finding coercion ------------------------------------------------------


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


def _coerce_skeptic_findings(
    raw_obj: dict | None, valid_sources: set[str]
) -> tuple[str, list[Finding]]:
    """Parse the skeptic's JSON into (summary, findings), preserving `extra`.

    The skeptic stamps each finding with the originating persona in `source`
    and the agreement metadata (`raised_by`, `skeptic`) in `extra`.
    """
    if not raw_obj:
        return "", []
    summary = str(raw_obj.get("summary") or "")
    findings: list[Finding] = []
    for raw in raw_obj.get("findings") or []:
        if not isinstance(raw, dict):
            continue
        try:
            source = str(raw.get("source") or "").strip()
            if source not in valid_sources:
                source = DEFAULT_SOURCE
            extra_in = raw.get("extra")
            extra: dict = dict(extra_in) if isinstance(extra_in, dict) else {}
            raised_by = extra.get("raised_by")
            if isinstance(raised_by, list):
                extra["raised_by"] = [str(r) for r in raised_by]
            elif source != DEFAULT_SOURCE:
                extra.setdefault("raised_by", [source])
            findings.append(
                Finding(
                    file=str(raw["file"]),
                    line_start=int(raw["line_start"]),
                    line_end=int(raw["line_end"]),
                    category=str(raw["category"]),
                    severity=str(raw["severity"]),  # type: ignore[arg-type]
                    title=str(raw["title"]),
                    message=str(raw["message"]),
                    source=source,
                    extra=extra,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            sys.stderr.write(f"warning: dropped malformed finding ({exc}): {raw!r}\n")
    return summary, findings


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


# --- Retry wrapper ---------------------------------------------------------


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
        sys.stderr.write(f"  [stage1] persona agent: {pid}\n")
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
    """Run v4: parallel persona agents + an opus skeptic pass."""
    started = time.monotonic()

    personas = _load_personas()
    valid_sources = {pid for pid, _ in personas}
    persona_model = config.model_for("specialist_reasoning")
    skeptic_model = config.model_for("skeptic")

    # --- Stage 1: parallel persona agents ---
    persona_results = _run_persona_agents(pr, personas, persona_model, parallel=True)

    # If EVERY persona agent failed under parallel load, retry once sequentially
    # before giving up — concurrent subprocess launches are the usual culprit.
    if persona_results and all(r.is_error for r in persona_results.values()):
        sys.stderr.write(
            "warning: all persona agents errored in parallel; retrying sequentially\n"
        )
        persona_results = _run_persona_agents(
            pr, personas, persona_model, parallel=False
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

    # --- Stage 2: skeptic pass ---
    skeptic_res: CallResult | None = None
    skeptic_summary = ""
    final_findings: list[Finding] = []

    if pooled:
        skeptic_res = _call_with_retry(
            system=_SKEPTIC_SYSTEM,
            user=_build_skeptic_user(pr, pooled),
            model=skeptic_model,
            label="skeptic",
        )
        all_calls.append(skeptic_res)
        if skeptic_res.is_error:
            sys.stderr.write(
                f"warning: skeptic failed ({skeptic_res.error}); "
                f"falling back to de-duplicated stage-1 pool\n"
            )
            final_findings = _dedup_pool(pooled)
            skeptic_summary = (
                "Skeptic pass failed; returning the de-duplicated union of the "
                "four persona agents' findings (unfiltered)."
            )
        else:
            skeptic_summary, final_findings = _coerce_skeptic_findings(
                extract_fenced_json(skeptic_res.text), valid_sources
            )
    else:
        skeptic_summary = "No persona agent produced any findings."

    # --- Aggregate usage / cost across every call actually made ---
    total_usage = sum_usage(c.usage for c in all_calls)
    total_cost = sum(c.cost_usd for c in all_calls)
    num_calls = len(all_calls)
    duration_ms = int((time.monotonic() - started) * 1000)

    skeptic_cost = skeptic_res.cost_usd if skeptic_res is not None else 0.0
    sys.stderr.write(
        f"  [cost] stage1 personas (4x sonnet)=${stage1_cost:.4f}  "
        f"stage2 skeptic (1x opus)=${skeptic_cost:.4f}  "
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
        description="v4 parallel-personas + skeptic PR reviewer"
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
