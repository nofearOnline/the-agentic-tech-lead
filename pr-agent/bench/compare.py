"""Aggregate trial results into a comparison table.

Reads `bench/results/<version>/pr-<N>/trial-*.json` and prints a markdown
table for the slide deck plus per-category coverage and per-issue hit/miss
heatmaps.

Usage:
    python compare.py                              # all versions, all PRs
    python compare.py --version v1_single_shot     # one version
    python compare.py --json                       # raw JSON instead of markdown
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PR_AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PR_AGENT_ROOT))

from shared import load_config  # noqa: E402

from bench.score import load_ground_truth  # noqa: E402


@dataclass
class Aggregate:
    version: str
    pr: int
    trials: int = 0
    cost_mean: float = 0.0
    cost_total: float = 0.0
    elapsed_mean: float = 0.0
    precision_mean: float = 0.0
    recall_mean: float = 0.0
    f1_mean: float = 0.0
    f1_stdev: float = 0.0
    findings_mean: float = 0.0
    tp_mean: float = 0.0
    issues_total: int = 0
    issue_hit_count: dict[str, int] = field(default_factory=dict)
    category_coverage: dict[str, tuple[int, int]] = field(default_factory=dict)
    errors: int = 0


def _load_trials(results_dir: Path, version: str, pr: int) -> list[dict[str, Any]]:
    trial_dir = results_dir / version / f"pr-{pr}"
    if not trial_dir.exists():
        return []
    out = []
    for f in sorted(trial_dir.glob("trial-*.json")):
        out.append(json.loads(f.read_text()))
    return out


def aggregate(results_dir: Path, version: str, pr: int) -> Aggregate | None:
    trials = _load_trials(results_dir, version, pr)
    if not trials:
        return None

    successful = [t for t in trials if not t.get("error")]
    errors = len(trials) - len(successful)

    def _mean(values: list[float]) -> float:
        return statistics.fmean(values) if values else 0.0

    def _stdev(values: list[float]) -> float:
        return statistics.stdev(values) if len(values) > 1 else 0.0

    costs = [float(t["cost_usd"]) for t in successful]
    elapsed = [float(t["elapsed_seconds"]) for t in successful]
    findings_counts = [float(len(t.get("findings") or [])) for t in successful]
    precision = []
    recall = []
    f1 = []
    tp = []
    for t in successful:
        s = t.get("score") or {}
        m = s.get("metrics") or {}
        totals = s.get("totals") or {}
        precision.append(float(m.get("precision", 0.0)))
        recall.append(float(m.get("recall", 0.0)))
        f1.append(float(m.get("f1", 0.0)))
        tp.append(float(totals.get("true_positives", 0)))

    # Per-issue hit rate (how often did this issue get caught across trials)
    issue_hit_count: dict[str, int] = defaultdict(int)
    issues_total = 0
    for t in successful:
        s = t.get("score") or {}
        matches = s.get("matches") or []
        issues_total = max(issues_total, int((s.get("totals") or {}).get("issues", 0)))
        for m in matches:
            issue_hit_count[m["issue_id"]] += 1

    category_coverage_acc: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for t in successful:
        s = t.get("score") or {}
        for cat, slot in (s.get("per_category") or {}).items():
            category_coverage_acc[cat].append((int(slot.get("found", 0)), int(slot.get("total", 0))))

    category_coverage: dict[str, tuple[int, int]] = {}
    for cat, items in category_coverage_acc.items():
        # average found across trials, total stays constant
        avg_found = int(round(_mean([float(f) for f, _ in items])))
        total = items[0][1] if items else 0
        category_coverage[cat] = (avg_found, total)

    return Aggregate(
        version=version,
        pr=pr,
        trials=len(successful),
        cost_mean=_mean(costs),
        cost_total=sum(costs),
        elapsed_mean=_mean(elapsed),
        precision_mean=_mean(precision),
        recall_mean=_mean(recall),
        f1_mean=_mean(f1),
        f1_stdev=_stdev(f1),
        findings_mean=_mean(findings_counts),
        tp_mean=_mean(tp),
        issues_total=issues_total,
        issue_hit_count=dict(issue_hit_count),
        category_coverage=category_coverage,
        errors=errors,
    )


def _discover_versions(results_dir: Path) -> list[str]:
    if not results_dir.exists():
        return []
    return sorted(p.name for p in results_dir.iterdir() if p.is_dir())


def _discover_prs(results_dir: Path, version: str) -> list[int]:
    vdir = results_dir / version
    if not vdir.exists():
        return []
    prs = []
    for p in vdir.iterdir():
        if p.is_dir() and p.name.startswith("pr-"):
            try:
                prs.append(int(p.name[3:]))
            except ValueError:
                continue
    return sorted(prs)


def _markdown_summary(rows: list[Aggregate]) -> str:
    if not rows:
        return "(no results found)"

    header = (
        "| version | PR | trials | cost (mean) | latency (mean) | findings | "
        "TP | precision | recall | F1 (mean +/- sd) |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    )
    body_lines = []
    for r in rows:
        body_lines.append(
            f"| {r.version} | #{r.pr} | {r.trials} | "
            f"${r.cost_mean:.4f} | {r.elapsed_mean:.1f}s | "
            f"{r.findings_mean:.1f} | "
            f"{r.tp_mean:.1f}/{r.issues_total} | "
            f"{r.precision_mean:.2f} | {r.recall_mean:.2f} | "
            f"{r.f1_mean:.2f} +/- {r.f1_stdev:.2f} |"
        )
    return header + "\n".join(body_lines)


def _markdown_issue_heatmap(
    rows: list[Aggregate], results_dir: Path
) -> str:
    """For each PR: list every planted issue and whether each version found it
    (X/N where X = trials that found it, N = total trials).
    """
    cfg = load_config()
    gt_dir = PR_AGENT_ROOT / "bench" / "ground_truth"

    # Group rows by PR
    by_pr: dict[int, list[Aggregate]] = defaultdict(list)
    for r in rows:
        by_pr[r.pr].append(r)

    out: list[str] = []
    for pr in sorted(by_pr.keys()):
        gt_path = next(gt_dir.glob(f"pr-{pr}-*.yaml"), None)
        if gt_path is None:
            continue
        gt = load_ground_truth(gt_path)

        # column per version
        versions_for_pr = [r.version for r in by_pr[pr]]
        trials_for_pr = {r.version: r.trials for r in by_pr[pr]}

        out.append(f"\n### PR #{pr} - issue hit rate (per version, X/trials)\n")
        header = "| issue id | severity | category | " + " | ".join(versions_for_pr) + " |"
        sep = "| --- | --- | --- | " + " | ".join("---" for _ in versions_for_pr) + " |"
        out.append(header)
        out.append(sep)
        for issue in gt.issues:
            cells = []
            for v in versions_for_pr:
                agg = next(r for r in by_pr[pr] if r.version == v)
                hits = agg.issue_hit_count.get(issue.id, 0)
                n = trials_for_pr[v] or 1
                marker = f"{hits}/{n}"
                cells.append(marker)
            out.append(
                f"| {issue.id} | {issue.severity} | {issue.category} | " + " | ".join(cells) + " |"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare versions across runs")
    parser.add_argument(
        "--version",
        action="append",
        help="Limit to specific version(s); default: all under bench/results/",
    )
    parser.add_argument(
        "--pr",
        action="append",
        type=int,
        help="Limit to specific PR number(s); default: all found",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit raw JSON instead of markdown"
    )
    args = parser.parse_args(argv)

    config = load_config()
    results_dir = config.output_dir

    versions = args.version or _discover_versions(results_dir)
    if not versions:
        print("(no results yet -- run run_eval.py first)")
        return 0

    aggregates: list[Aggregate] = []
    for v in versions:
        prs = args.pr or _discover_prs(results_dir, v)
        for pr in prs:
            agg = aggregate(results_dir, v, pr)
            if agg:
                aggregates.append(agg)

    if args.json:
        print(
            json.dumps(
                [a.__dict__ for a in aggregates],
                indent=2,
                default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o),
            )
        )
        return 0

    print("## Run comparison\n")
    print(_markdown_summary(aggregates))
    print(_markdown_issue_heatmap(aggregates, results_dir))

    # Cost roll-up
    total_cost = sum(a.cost_total for a in aggregates)
    total_trials = sum(a.trials for a in aggregates)
    print(f"\nTotal API cost across {total_trials} successful trials: ${total_cost:.4f}")
    return 0


_ = math  # reserved for future per-issue confidence intervals


if __name__ == "__main__":
    sys.exit(main())
