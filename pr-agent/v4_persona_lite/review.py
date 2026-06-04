"""v4 - the persona bundle, made cheap. The version the talk lands on.

The matrix's punchline: v3 (four reviewer personas bundled into ONE call) is
the quality winner. The governance move isn't "add more agents" - it's "take
the thing that already won and make it cheaper." v4 is that move.

v4 is *exactly* v3 - same personas, same system prompt, same single-shot /
no-tools / diff-only shape, same JSON contract and parsing - with ONE knob
changed: the model tier. v3 runs the bundled-persona call on the `generalist`
model (Sonnet); v4 runs the identical call on `tier1` (Haiku), ~20x cheaper per
token. Everything else is imported verbatim from `v3_persona_bundle`, so the
ONLY variable between v3 and v4 is the model. That makes a v3-vs-v4 comparison a
clean read on the question the talk closes on: "did the win come from the
architecture or from the spend?" (Answer: the architecture - v4 on Haiku still
catches the JWT/SSRF security class the diff-only generalist never sees.)

The lesson: find the knee of the curve (personas, one call), then dial the
MODEL down, not the agent count. The cost/quality frontier collapses to two
points - this v4 (cheap) and v3 (premium) - and they are the same architecture.

(Exploratory builds that spent the other direction - parallel persona agents +
an Opus skeptic, and a tiered variant of that - live under the archived
`v4_parallel_personas` / `v5_tiered` dirs. They cost more and scored lower; kept
on disk as evidence, out of the ladder.)

Public API:
    review(pr, config) -> ReviewResult            # used by the eval harness

CLI:
    python review.py <pr-url-or-number> [--repo OWNER/REPO]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `shared/` and sibling version packages importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (  # noqa: E402
    Config,
    PullRequest,
    call,
    extract_fenced_json,
    fetch_pull_request,
    load_config,
    parse_pr_arg,
)

# Reuse v3's machinery verbatim - v4 changes only the model tier.
from v3_persona_bundle.review import (  # noqa: E402
    ReviewResult,
    _build_system_prompt,
    _build_user_message,
    _coerce_findings,
    _load_personas,
    _render_for_cli,
)

# The single knob that separates v4 from v3. v3 uses "generalist" (Sonnet);
# v4 uses "tier1" (Haiku) - same prompt, same call, cheaper model.
MODEL_ROLE = "tier1"


def review(pr: PullRequest, config: Config) -> ReviewResult:
    """Run v3's persona-bundled review on the cheaper `tier1` model (v4)."""
    model = config.model_for(MODEL_ROLE)

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v4 persona-bundle reviewer (cheap tier)")
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
        f"+{pr.additions}/-{pr.deletions}, {pr.changed_files} files) "
        f"on the cheap tier...\n"
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
            f"cost=${result.cost_usd:.4f}  duration={result.duration_ms}ms\n"
        )
    return 0 if not result.error else 1


if __name__ == "__main__":
    sys.exit(main())
