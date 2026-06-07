"""Per-issue coverage analysis for the newly-planted "hard" issues.

Loads the trial results for a set of version labels, scores each trial against
the current ground truth, and reports, for every NEW issue, the fraction of
trials in which it was caught -- broken down by version. This is the
discrimination check: the new issues should be MISSED by v1/v2 and CAUGHT by
the persona-bundled v3, even when every version runs on the same model.

Usage:
    python bench/analyze_new_issues.py                 # default opus labels
    python bench/analyze_new_issues.py --labels v1_single_shot v2_repo_aware v3_persona_bundle
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from score import _ground_truth_path_for_pr, load_ground_truth, score

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

# The 7 issues planted in this round (id -> short label).
NEW_ISSUES = {
    "pr1-security-coupon-redos": "PR1 ReDoS coupon regex",
    "pr2-security-idor-no-ownership-check": "PR2 IDOR (no ownership check)",
    "pr2-correctness-idempotency-key-ignored": "PR2 idempotency key ignored",
    "pr3-security-timing-unsafe-apikey": "PR3 timing-unsafe key compare",
    "pr3-security-webhook-no-hmac": "PR3 unsigned webhook (no HMAC)",
    "pr3-perf-webhook-sequential-await": "PR3 sequential webhook await",
    "pr3-quality-webhook-floating-promise": "PR3 floating promise",
}

ISSUE_PR = {
    "pr1-security-coupon-redos": 1,
    "pr2-security-idor-no-ownership-check": 2,
    "pr2-correctness-idempotency-key-ignored": 2,
    "pr3-security-timing-unsafe-apikey": 3,
    "pr3-security-webhook-no-hmac": 3,
    "pr3-perf-webhook-sequential-await": 3,
    "pr3-quality-webhook-floating-promise": 3,
}


def analyze(labels: list[str]) -> None:
    gt_by_pr = {pr: load_ground_truth(_ground_truth_path_for_pr(pr)) for pr in (1, 2, 3)}

    # label -> issue_id -> (hits, trials)
    coverage: dict[str, dict[str, list[int]]] = {
        lbl: {iid: [0, 0] for iid in NEW_ISSUES} for lbl in labels
    }
    # also overall recall per label per pr for context
    overall: dict[str, dict[int, list[float]]] = {lbl: defaultdict(list) for lbl in labels}

    for lbl in labels:
        for pr in (1, 2, 3):
            gt = gt_by_pr[pr]
            for tf in sorted((RESULTS / lbl / f"pr-{pr}").glob("trial-*.json")):
                result = json.loads(tf.read_text())
                findings = result.get("findings") or []
                s = score(findings, gt)
                overall[lbl][pr].append(s.recall)
                covered = set(s.covered_issue_ids)
                for iid in NEW_ISSUES:
                    if ISSUE_PR[iid] != pr:
                        continue
                    coverage[lbl][iid][1] += 1
                    if iid in covered:
                        coverage[lbl][iid][0] += 1

    # ---- per-issue table ----
    name_w = max(len(v) for v in NEW_ISSUES.values())
    header = f"{'NEW ISSUE':<{name_w}}  " + "  ".join(f"{lbl:>26}" for lbl in labels)
    print(header)
    print("-" * len(header))
    for iid, name in NEW_ISSUES.items():
        cells = []
        for lbl in labels:
            hits, trials = coverage[lbl][iid]
            cells.append(f"{hits}/{trials}".rjust(26))
        print(f"{name:<{name_w}}  " + "  ".join(cells))

    # ---- overall recall per pr ----
    print("\nOverall recall (mean across trials), per PR:")
    sub = f"{'':<{name_w}}  " + "  ".join(f"{lbl:>26}" for lbl in labels)
    print(sub)
    print("-" * len(sub))
    for pr in (1, 2, 3):
        cells = []
        for lbl in labels:
            vals = overall[lbl][pr]
            m = sum(vals) / len(vals) if vals else 0.0
            cells.append(f"{m:.2f}".rjust(26))
        print(f"{('PR ' + str(pr)):<{name_w}}  " + "  ".join(cells))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--labels",
        nargs="+",
        default=["v1_single_shot__opus", "v2_repo_aware__opus", "v3_persona_bundle__opus"],
    )
    args = ap.parse_args()
    analyze(args.labels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
