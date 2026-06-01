"""v1 - single-shot PR review.

The simplest possible reviewer: fetch the PR diff via `gh`, hand the whole
thing to one Claude call with no tools and no loop, and parse a structured
list of findings out of the response.

No tools. No agentic loop. No access to the repository beyond the diff.
This is the baseline that the rest of the evolutions improve on.

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


SYSTEM_PROMPT = """\
You are an experienced engineering tech lead reviewing a pull request.

You will be given the PR title, description, author, and the unified diff
of the changes. Your job is to find every issue that matters.

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
  "summary": "one short paragraph summarizing your review",
  "findings": [
    {
      "file": "path/as/it/appears/in/the/diff",
      "line_start": 12,
      "line_end": 18,
      "category": "security",
      "severity": "must",
      "title": "short headline, <= 80 chars",
      "message": "what is wrong, why it matters, suggested fix"
    }
  ]
}
```

If the PR is clean overall, return an empty `findings` list and say so
in `summary`. Use only the file paths that appear in the diff (do not
fabricate paths). Use line numbers that appear in the diff hunks; if you
cannot point to a specific line, use the start of the relevant hunk."""


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


def _coerce_findings(raw_obj: dict | None) -> tuple[str, list[Finding]]:
    """Turn a parsed JSON object into (summary, findings)."""
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
                    source="v1_generalist",
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            sys.stderr.write(f"warning: dropped malformed finding ({exc}): {raw!r}\n")
    return summary, findings


def review(pr: PullRequest, config: Config) -> ReviewResult:
    """Run a single-shot review. Returns structured findings + token usage."""
    model = config.model_for("generalist")

    result = call(
        system=SYSTEM_PROMPT,
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
    summary, findings = _coerce_findings(parsed)

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
                f"[{i}] {f.severity.upper()} {f.category} - "
                f"{f.file}:{f.line_start}-{f.line_end}"
            )
            lines.append(f"    {f.title}")
            for body_line in f.message.splitlines():
                lines.append(f"    {body_line}")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v1 single-shot PR reviewer")
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
