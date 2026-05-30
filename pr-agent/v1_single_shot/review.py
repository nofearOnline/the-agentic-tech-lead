"""v1 - single-shot PR review.

The simplest possible reviewer: fetch the PR diff via the `gh` CLI, hand
the whole thing to one LLM call with a tool that forces structured output,
and return the resulting findings.

No tools beyond `report_findings` (used purely for output shaping).
No loop. No access to the rest of the repo beyond the diff. This is the
baseline that the rest of the evolutions improve on.

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

# Allow `python review.py ...` from inside the v1 folder to find `shared/`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import Anthropic  # noqa: E402

from shared import (  # noqa: E402
    Config,
    Finding,
    PullRequest,
    Usage,
    compute_cost,
    fetch_pull_request,
    load_config,
    parse_pr_arg,
)
from shared.config import require_anthropic_api_key  # noqa: E402
from shared.cost import usage_from_anthropic  # noqa: E402


SYSTEM_PROMPT = """\
You are an experienced engineering tech lead reviewing a pull request.

You will be given the PR title, description, author, and the unified diff of
the changes. Your job is to find every issue that matters and report it via
the `report_findings` tool.

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

Always emit through the `report_findings` tool. If the PR looks clean overall,
return an empty `findings` list and say so in `summary`. Be concrete about
file paths and line numbers from the diff. Do NOT fabricate line numbers you
cannot point to in the diff."""


REPORT_FINDINGS_TOOL = {
    "name": "report_findings",
    "description": "Report all issues found in the PR. Call this exactly once at the end.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One short paragraph summarizing the review.",
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "Path of the affected file as it appears in the diff.",
                        },
                        "line_start": {"type": "integer"},
                        "line_end": {"type": "integer"},
                        "category": {
                            "type": "string",
                            "enum": [
                                "security",
                                "performance",
                                "correctness",
                                "dry",
                                "kiss",
                                "test",
                                "standards",
                                "quality",
                            ],
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["must", "should", "suggestion"],
                        },
                        "title": {
                            "type": "string",
                            "description": "Short headline, <= 80 chars.",
                        },
                        "message": {
                            "type": "string",
                            "description": "Full explanation: what is wrong, why it matters, suggested fix.",
                        },
                    },
                    "required": [
                        "file",
                        "line_start",
                        "line_end",
                        "category",
                        "severity",
                        "title",
                        "message",
                    ],
                },
            },
        },
        "required": ["summary", "findings"],
    },
}


@dataclass
class ReviewResult:
    findings: list[Finding]
    usage: Usage
    cost_usd: float
    summary: str
    raw_tool_input: dict | None = None


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


def review(pr: PullRequest, config: Config) -> ReviewResult:
    """Run a single-shot review. Returns structured findings and token usage."""
    require_anthropic_api_key()
    model = config.model_for("generalist")
    pricing = config.pricing_for(model)

    client = Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[REPORT_FINDINGS_TOOL],
        tool_choice={"type": "tool", "name": "report_findings"},
        messages=[{"role": "user", "content": _build_user_message(pr)}],
    )

    tool_input: dict | None = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "report_findings":
            tool_input = dict(block.input)
            break

    if tool_input is None:
        # Model refused to call the tool. Treat as zero findings; record raw text.
        text = "\n".join(
            getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text"
        )
        return ReviewResult(
            findings=[],
            usage=usage_from_anthropic(response.usage),
            cost_usd=compute_cost(usage_from_anthropic(response.usage), pricing),
            summary=text or "(no tool call returned)",
            raw_tool_input=None,
        )

    findings: list[Finding] = []
    for raw in tool_input.get("findings", []) or []:
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

    usage = usage_from_anthropic(response.usage)
    return ReviewResult(
        findings=findings,
        usage=usage,
        cost_usd=compute_cost(usage, pricing),
        summary=str(tool_input.get("summary", "")),
        raw_tool_input=tool_input,
    )


def _render_for_cli(result: ReviewResult) -> str:
    lines: list[str] = []
    lines.append(result.summary or "(no summary)")
    lines.append("")
    if not result.findings:
        lines.append("No findings.")
    else:
        for i, f in enumerate(result.findings, start=1):
            lines.append(
                f"[{i}] {f.severity.upper()} {f.category} - {f.file}:{f.line_start}-{f.line_end}"
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
        }
        print(json.dumps(out, indent=2))
    else:
        print(_render_for_cli(result))
        sys.stderr.write(
            f"\nTokens: in={result.usage.input_tokens} "
            f"cache_w={result.usage.cache_creation_input_tokens} "
            f"cache_r={result.usage.cache_read_input_tokens} "
            f"out={result.usage.output_tokens}  "
            f"Cost: ${result.cost_usd:.4f}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
