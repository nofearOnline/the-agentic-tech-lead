"""v3 - persona-bundle PR review.

The demo's pivot from "generic senior reviewer" to "reviews like OUR team."

v1 handed the diff to one generic "you are a senior engineer" prompt. v3 keeps
the exact same machinery as v1 - a single LLM call, no tools, diff-only - but
swaps the generic framing for a *bundle* of the team's four reviewer personas
(security_hawk, perf_skeptic, kiss_zealot, quality_critic). The four persona
profiles are concatenated into one system prompt and the model reviews the diff
through all of them at once, tagging each finding with the persona (`source`)
that raised it.

This is deliberately the SIMPLE bundling approach: one call, all personas in a
single prompt. One-agent-per-persona is a later version's job, not this one.

The axis v3 isolates: same model as v1/v2 (`generalist`), same single-shot /
no-tools shape as v1. The only delta over v1 is the persona-driven prompt, so a
v1-vs-v3 comparison measures the *personas*, not the architecture.

Public API:
    review(pr, config) -> ReviewResult            # used by the eval harness

CLI:
    python review.py <pr-url-or-number> [--repo OWNER/REPO]
"""

from __future__ import annotations

import argparse
import json
import sys
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

# Fallback source when the model omits the persona tag on a finding.
DEFAULT_SOURCE = "v3_persona_bundle"

# The personas live in `pr-agent/personas/*.md`. This file is at
# `pr-agent/v3_persona_bundle/review.py`, so the pr-agent root is two levels up.
_PR_AGENT_ROOT = Path(__file__).resolve().parent.parent
_PERSONAS_DIR = _PR_AGENT_ROOT / "personas"


def _load_personas() -> list[tuple[str, str]]:
    """Read every persona profile under `pr-agent/personas/`.

    Returns a list of (persona_id, markdown_body) sorted by id for a stable,
    deterministic prompt. `persona_id` is the filename stem (e.g.
    "security_hawk"); it is also the value the model must put in each finding's
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


_PERSONA_PREAMBLE = """\
You are not one reviewer - you are a TEAM of distinct senior reviewers doing a
single pass over a pull request together. Each teammate has their own taste,
their own pet issues, and their own bar for what blocks a merge. Their full
profiles are bundled below, each under a `### PERSONA: <id>` header.

Review the PR the way this team would: apply every persona's lens, and when a
teammate would raise an issue, raise it in their voice and at their severity.
Do not water the personas down into a generic "senior reviewer" - keep their
individual instincts. A finding only one persona cares about is still a finding.

ATTRIBUTION - REQUIRED. Every finding MUST carry a `source` field set to the id
of the persona who raised it. Use EXACTLY one of these ids:
{persona_ids}

If two personas would flag the same line for different reasons, emit one finding
per persona. Do not invent persona ids; use only the ids listed above.
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
  "summary": "one short paragraph summarizing the team's review",
  "findings": [
    {
      "file": "path/as/it/appears/in/the/diff",
      "line_start": 12,
      "line_end": 18,
      "category": "security",
      "severity": "must",
      "title": "short headline, <= 80 chars",
      "message": "what is wrong, why it matters, suggested fix",
      "source": "security_hawk"
    }
  ]
}
```

If the PR is clean overall, return an empty `findings` list and say so in
`summary`. Use only the file paths that appear in the diff (do not fabricate
paths). Use line numbers that appear in the diff hunks; if you cannot point to a
specific line, use the start of the relevant hunk."""


def _build_system_prompt(personas: list[tuple[str, str]]) -> str:
    persona_ids = ", ".join(pid for pid, _ in personas)
    blocks: list[str] = [_PERSONA_PREAMBLE.format(persona_ids=persona_ids)]
    for pid, body in personas:
        blocks.append(f"### PERSONA: {pid}\n\n{body.strip()}")
    blocks.append(_OUTPUT_CONTRACT)
    return "\n\n".join(blocks)


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


def _coerce_findings(
    raw_obj: dict | None, valid_sources: set[str]
) -> tuple[str, list[Finding]]:
    """Turn a parsed JSON object into (summary, findings).

    Each finding's `source` is the persona that raised it. We trust the model's
    `source` only if it matches a known persona id; otherwise we fall back to
    DEFAULT_SOURCE so attribution never silently points at a made-up persona.
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
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            sys.stderr.write(f"warning: dropped malformed finding ({exc}): {raw!r}\n")
    return summary, findings


def review(pr: PullRequest, config: Config) -> ReviewResult:
    """Run a single-shot, persona-bundled review. Returns findings + usage."""
    model = config.model_for("generalist")

    personas = _load_personas()
    valid_sources = {pid for pid, _ in personas}
    system_prompt = _build_system_prompt(personas)

    result = call(
        system=system_prompt,
        user=_build_user_message(pr),
        model=model,
        tools_enabled=False,
    )

    if result.is_error:
        return ReviewResult(
            findings=[],
            usage=result.usage,
            cost_usd=result.cost_usd,
            summary="",
            raw_response=result.text,
            resolved_model=result.resolved_model,
            num_turns=result.num_turns,
            duration_ms=result.duration_ms,
            error=result.error,
        )

    parsed = extract_fenced_json(result.text)
    summary, findings = _coerce_findings(parsed, valid_sources)

    return ReviewResult(
        findings=findings,
        usage=result.usage,
        cost_usd=result.cost_usd,
        summary=summary,
        raw_response=result.text,
        resolved_model=result.resolved_model,
        num_turns=result.num_turns,
        duration_ms=result.duration_ms,
    )


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
            lines.append(
                f"[{i}] {f.severity.upper()} {f.category} ({f.source}) - "
                f"{f.file}:{f.line_start}-{f.line_end}"
            )
            lines.append(f"    {f.title}")
            for body_line in f.message.splitlines():
                lines.append(f"    {body_line}")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v3 persona-bundle PR reviewer")
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
            f"\nmodel={result.resolved_model} turns={result.num_turns}\n"
            f"tokens: in={result.usage.input_tokens} "
            f"cache_w={result.usage.cache_creation_input_tokens} "
            f"cache_r={result.usage.cache_read_input_tokens} "
            f"out={result.usage.output_tokens}\n"
            f"cost=${result.cost_usd:.4f}  duration={result.duration_ms}ms\n"
        )
    return 0 if not result.error else 1


if __name__ == "__main__":
    sys.exit(main())
