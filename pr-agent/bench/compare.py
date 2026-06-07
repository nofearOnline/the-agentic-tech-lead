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
        issues_total = max(issues_total, int((s.get("totals") or {}).get("issues", 0)))
        # Use the deduped covered_issue_ids (one count per issue per trial).
        # Falls back to deriving a deduped set from `matches` for older
        # result files written before covered_issue_ids existed.
        covered = s.get("covered_issue_ids")
        if covered is None:
            covered = {m["issue_id"] for m in (s.get("matches") or [])}
        for issue_id in set(covered):
            issue_hit_count[issue_id] += 1

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


# Exploratory builds kept on disk for evidence but out of the 4-rung ladder.
# Excluded from default discovery; still reachable via explicit --version.
ARCHIVED_VERSIONS = {"v4_parallel_personas", "v5_tiered"}

# (architecture, model) -> results label. The model sweep benchmarks each
# architecture across tiers. Note the v3 persona-bundle architecture's haiku
# cell is the shipped v4 (v4_persona_lite); its sonnet cell is v3 itself.
MODEL_MATRIX: dict[str, dict[str, str]] = {
    "v1 single-shot": {
        "haiku": "v1_single_shot__haiku",
        "sonnet": "v1_single_shot",
        "opus": "v1_single_shot__opus",
    },
    "v2 repo-aware": {
        "haiku": "v2_repo_aware__haiku",
        "sonnet": "v2_repo_aware",
        "opus": "v2_repo_aware__opus",
    },
    "v3 persona-bundle": {
        "haiku": "v4_persona_lite",
        "sonnet": "v3_persona_bundle",
        "opus": "v3_persona_bundle__opus",
    },
}


def _discover_versions(results_dir: Path) -> list[str]:
    """Versions for the default ladder view. Excludes archived builds and
    model-sweep variants (labels containing '__'); those render in the
    dedicated model matrix instead.
    """
    if not results_dir.exists():
        return []
    return sorted(
        p.name
        for p in results_dir.iterdir()
        if p.is_dir() and p.name not in ARCHIVED_VERSIONS and "__" not in p.name
    )


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


def _markdown_version_rollup(rows: list[Aggregate]) -> str:
    """Per-version summary, averaged across all PRs/trials. This is the
    'one slide' view: each version as a single row of mean cost / recall / F1
    so the Teach -> Compose -> Govern arc reads top-to-bottom.
    """
    by_version: dict[str, list[Aggregate]] = defaultdict(list)
    for r in rows:
        by_version[r.version].append(r)

    # Stable order matching the evolution narrative. The ladder is four rungs;
    # v4_persona_lite (the v3 bundle on a cheap model) is the punchline the talk
    # ends on. The parallel-agents / tiered experiments are archived out of the
    # ladder (see ARCHIVED_VERSIONS) and are not shown by default.
    order = [
        "v1_single_shot",
        "v2_repo_aware",
        "v3_persona_bundle",
        "v4_persona_lite",
    ]
    versions = [v for v in order if v in by_version] + [
        v for v in sorted(by_version) if v not in order
    ]

    header = (
        "| version | mean cost | mean latency | precision | recall | F1 | "
        "vs v1 cost | vs v3 cost |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
    )

    # Weight each (version, PR) aggregate by its trial count so the mean is a
    # true per-trial mean, not a mean-of-means.
    def _wmean(aggs: list[Aggregate], attr: str) -> float:
        num = sum(getattr(a, attr) * a.trials for a in aggs)
        den = sum(a.trials for a in aggs)
        return num / den if den else 0.0

    summaries: dict[str, dict[str, float]] = {}
    for v in versions:
        aggs = by_version[v]
        summaries[v] = {
            "cost": _wmean(aggs, "cost_mean"),
            "latency": _wmean(aggs, "elapsed_mean"),
            "precision": _wmean(aggs, "precision_mean"),
            "recall": _wmean(aggs, "recall_mean"),
            "f1": _wmean(aggs, "f1_mean"),
        }

    v1_cost = summaries.get("v1_single_shot", {}).get("cost", 0.0)
    v3_cost = summaries.get("v3_persona_bundle", {}).get("cost", 0.0)

    body = []
    for v in versions:
        s = summaries[v]
        v1x = f"{s['cost'] / v1_cost:.1f}x" if v1_cost else "-"
        v3x = f"{s['cost'] / v3_cost:.2f}x" if v3_cost else "-"
        body.append(
            f"| {v} | ${s['cost']:.3f} | {s['latency']:.0f}s | "
            f"{s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.2f} | "
            f"{v1x} | {v3x} |"
        )
    return "## Per-version rollup (mean across all PRs/trials)\n\n" + header + "\n".join(body)


def _label_rollup(results_dir: Path, label: str) -> dict[str, float] | None:
    """Trial-weighted means across all of a single label's PRs. Used by the
    model matrix, which keys on raw results labels (incl. '__model' sweeps).
    """
    prs = _discover_prs(results_dir, label)
    aggs = [a for a in (aggregate(results_dir, label, pr) for pr in prs) if a]
    den = sum(a.trials for a in aggs)
    if den == 0:
        return None

    def _w(attr: str) -> float:
        return sum(getattr(a, attr) * a.trials for a in aggs) / den

    return {
        "f1": _w("f1_mean"),
        "recall": _w("recall_mean"),
        "precision": _w("precision_mean"),
        "cost": _w("cost_mean"),
        "latency": _w("elapsed_mean"),
        "trials": float(den),
    }


def _markdown_model_matrix(results_dir: Path) -> str:
    """Architecture x model-tier matrix. Each cell is one architecture run
    end-to-end on one tier, summarized as F1 / recall / mean cost (weighted
    across all PRs). Answers: 'for a given architecture, what does dialing the
    model up or down buy?'
    """
    models = ["haiku", "sonnet", "opus"]
    out = [
        "## Model-tier matrix (F1 / recall / mean cost, weighted across all PRs)\n",
        "Each cell = one architecture on one tier. '-' = not benchmarked. The "
        "v3 persona-bundle row's haiku cell is the shipped v4 (v4_persona_lite); "
        "its sonnet cell is v3 itself.\n",
    ]
    header = "| architecture | " + " | ".join(models) + " |"
    sep = "| --- | " + " | ".join("---" for _ in models) + " |"
    out.append(header)
    out.append(sep)
    for arch, mapping in MODEL_MATRIX.items():
        cells = []
        for m in models:
            label = mapping.get(m)
            summ = _label_rollup(results_dir, label) if label else None
            if summ:
                cells.append(
                    f"F1 {summ['f1']:.2f} / R {summ['recall']:.2f} / ${summ['cost']:.3f}"
                )
            else:
                cells.append("-")
        out.append(f"| {arch} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def _markdown_cost_recall_data(rows: list[Aggregate]) -> str:
    """Plottable cost-vs-recall points, one per (version, PR). Drop straight
    into a scatter / bubble chart for the deck.
    """
    out = ["## Cost vs. recall (per version x PR -- chart data)\n"]
    out.append("| version | PR | mean cost | mean recall | mean F1 |")
    out.append("| --- | --- | --- | --- | --- |")
    for r in sorted(rows, key=lambda a: (a.version, a.pr)):
        out.append(
            f"| {r.version} | #{r.pr} | {r.cost_mean:.3f} | "
            f"{r.recall_mean:.2f} | {r.f1_mean:.2f} |"
        )
    return "\n".join(out)


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
    print(_markdown_version_rollup(aggregates))
    print("\n")
    print(_markdown_model_matrix(results_dir))
    print("\n")
    print(_markdown_summary(aggregates))
    print("\n")
    print(_markdown_cost_recall_data(aggregates))
    print(_markdown_issue_heatmap(aggregates, results_dir))

    # Cost roll-up
    total_cost = sum(a.cost_total for a in aggregates)
    total_trials = sum(a.trials for a in aggregates)
    print(f"\nTotal API cost across {total_trials} successful trials: ${total_cost:.4f}")
    return 0


_ = math  # reserved for future per-issue confidence intervals


if __name__ == "__main__":
    sys.exit(main())
