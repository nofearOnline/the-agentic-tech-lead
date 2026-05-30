"""Run one or more reviewer versions against the configured PRs and save
raw findings + scores to disk.

Usage:
    # Whole matrix from config.yaml
    python run_eval.py --version v1_single_shot

    # Subset
    python run_eval.py --version v1_single_shot --pr 1 --trials 1

    # Multiple versions
    python run_eval.py --version v1_single_shot --version v2_repo_aware

Outputs land under `pr-agent/bench/results/<version>/pr-<N>/trial-<T>.json`
with the raw findings, token usage, cost, and a `score` block.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

# Make `shared`, `bench`, `v1_single_shot`, ... importable when running from anywhere.
PR_AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PR_AGENT_ROOT))

from shared import (  # noqa: E402
    Config,
    PullRequest,
    fetch_pull_request,
    load_config,
)
from shared.cost import Usage  # noqa: E402

from bench.score import load_ground_truth, score  # noqa: E402


# ---------------------------------------------------------------------------
# Version registry
# ---------------------------------------------------------------------------


@dataclass
class VersionSpec:
    name: str          # folder name under pr-agent/
    review_fn: Callable[[PullRequest, Config], Any]


def load_version(name: str) -> VersionSpec:
    """Import `pr-agent/<name>/review.py` and grab its `review` function."""
    try:
        module = importlib.import_module(f"{name}.review")
    except ImportError as exc:
        raise SystemExit(f"Could not import {name}.review: {exc}") from exc
    review_fn = getattr(module, "review", None)
    if review_fn is None:
        raise SystemExit(f"{name}.review has no `review(pr, config)` function")
    return VersionSpec(name=name, review_fn=review_fn)


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass
class TrialResult:
    version: str
    pr: int
    trial: int
    title: str
    elapsed_seconds: float
    cost_usd: float
    usage: dict[str, int]
    summary: str
    findings: list[dict[str, Any]]
    score: dict[str, Any] | None
    error: str | None = None


def _usage_dict(u: Usage) -> dict[str, int]:
    return {
        "input_tokens": u.input_tokens,
        "cache_creation_input_tokens": u.cache_creation_input_tokens,
        "cache_read_input_tokens": u.cache_read_input_tokens,
        "output_tokens": u.output_tokens,
    }


def _ground_truth_for_pr(pr_number: int) -> Path | None:
    gt_dir = PR_AGENT_ROOT / "bench" / "ground_truth"
    for candidate in sorted(gt_dir.glob(f"pr-{pr_number}-*.yaml")):
        return candidate
    return None


def run_single(
    version: VersionSpec,
    pr: PullRequest,
    trial: int,
    config: Config,
) -> TrialResult:
    """Run one trial of one version against one PR. Score and return."""

    started = time.time()
    try:
        result = version.review_fn(pr, config)
    except Exception as exc:  # noqa: BLE001
        return TrialResult(
            version=version.name,
            pr=int(pr.number),
            trial=trial,
            title=pr.title,
            elapsed_seconds=time.time() - started,
            cost_usd=0.0,
            usage=_usage_dict(Usage()),
            summary="",
            findings=[],
            score=None,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        )
    elapsed = time.time() - started

    findings = [f.as_dict() for f in result.findings]

    gt_path = _ground_truth_for_pr(int(pr.number))
    score_dict: dict[str, Any] | None = None
    if gt_path is not None:
        gt = load_ground_truth(gt_path)
        score_dict = score(findings, gt).as_dict()
    else:
        sys.stderr.write(
            f"warning: no ground truth file for PR #{pr.number}; skipping score.\n"
        )

    return TrialResult(
        version=version.name,
        pr=int(pr.number),
        trial=trial,
        title=pr.title,
        elapsed_seconds=elapsed,
        cost_usd=float(result.cost_usd),
        usage=_usage_dict(result.usage),
        summary=str(getattr(result, "summary", "") or ""),
        findings=findings,
        score=score_dict,
        error=None,
    )


def _save(result: TrialResult, output_dir: Path) -> Path:
    target_dir = output_dir / result.version / f"pr-{result.pr}"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"trial-{result.trial}.json"
    path.write_text(json.dumps(asdict(result), indent=2))
    return path


def _summarize_line(r: TrialResult) -> str:
    if r.error:
        return f"  ! pr={r.pr} trial={r.trial} ERROR: {r.error.splitlines()[0]}"
    if r.score is None:
        return (
            f"  pr={r.pr} trial={r.trial}  findings={len(r.findings)}  "
            f"cost=${r.cost_usd:.4f}  t={r.elapsed_seconds:.1f}s  (no ground truth)"
        )
    m = r.score["metrics"]
    t = r.score["totals"]
    return (
        f"  pr={r.pr} trial={r.trial}  "
        f"findings={t['findings']}  TP={t['true_positives']}/{t['issues']}  "
        f"P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f}  "
        f"cost=${r.cost_usd:.4f}  t={r.elapsed_seconds:.1f}s"
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a reviewer version against the eval matrix")
    parser.add_argument(
        "--version",
        action="append",
        required=True,
        help="Folder name of a version to run (repeatable)",
    )
    parser.add_argument(
        "--pr",
        action="append",
        type=int,
        help="PR number(s) to run against (default: pr-agent/config.yaml `eval.prs`)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=None,
        help="Number of trials per (version, PR) (default: pr-agent/config.yaml `eval.trials_per_pr`)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to pr-agent/config.yaml (default: auto-detect)",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    prs = list(args.pr) if args.pr else list(config.eval.prs)
    trials = args.trials if args.trials is not None else config.eval.trials_per_pr

    versions = [load_version(v) for v in args.version]

    # Fetch each PR once; reuse the same PullRequest object across trials.
    sys.stderr.write(f"Fetching {len(prs)} PR(s) from {config.repo.slug}...\n")
    pr_cache: dict[int, PullRequest] = {}
    for n in prs:
        pr_cache[n] = fetch_pull_request(config.repo.slug, str(n))
        sys.stderr.write(
            f"  PR #{n}: {pr_cache[n].title!r}  "
            f"+{pr_cache[n].additions}/-{pr_cache[n].deletions}, "
            f"{pr_cache[n].changed_files} files\n"
        )

    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    total_runs = len(versions) * len(prs) * trials
    sys.stderr.write(
        f"\nRunning {len(versions)} version(s) x {len(prs)} PR(s) x {trials} trial(s) = {total_runs} runs.\n"
    )
    sys.stderr.write(f"Results under {output_dir}\n\n")

    total_cost = 0.0
    for version in versions:
        sys.stderr.write(f"--- {version.name} ---\n")
        for pr_n in prs:
            pr = pr_cache[pr_n]
            for trial in range(trials):
                result = run_single(version, pr, trial, config)
                _save(result, output_dir)
                total_cost += result.cost_usd
                sys.stderr.write(_summarize_line(result) + "\n")
                if result.cost_usd > config.eval.max_cost_per_run_usd:
                    sys.stderr.write(
                        f"  !! single run exceeded cost cap "
                        f"(${result.cost_usd:.2f} > ${config.eval.max_cost_per_run_usd:.2f})\n"
                    )
        sys.stderr.write("\n")

    sys.stderr.write(f"Total cost across all runs: ${total_cost:.4f}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
