"""Score a list of findings against a planted-issue ground-truth file.

A finding F matches an issue I when:
  1. F.file normalized == I.file normalized
  2. F.line range overlaps I.line_range +/- I.match_tolerance_lines
  3. At least one of I.match_keywords appears (case-insensitive) somewhere
     in F.title or F.message.

Matching is greedy: each finding can claim at most one issue (the first
candidate it satisfies, in YAML order), and each issue can be claimed
exactly once. Findings that claim nothing are false positives; issues
nobody claimed are false negatives.

FP note: in a controlled demo some FPs are not actually wrong - the agent
may have caught real issues we forgot to plant. The scorer flags every FP
for manual review; the headline precision number assumes "not planted =
false". Update ground truth and re-score to fix.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@dataclass
class GroundTruthIssue:
    id: str
    category: str
    severity: str
    file: str
    line_start: int
    line_end: int
    description: str
    match_keywords: list[str]


@dataclass
class GroundTruth:
    pr: int
    title: str
    size: str
    match_tolerance_lines: int
    issues: list[GroundTruthIssue]


def load_ground_truth(path: Path | str) -> GroundTruth:
    raw = yaml.safe_load(Path(path).read_text())
    issues_raw = raw.get("issues") or []
    issues = []
    for r in issues_raw:
        lr = r["line_range"]
        issues.append(
            GroundTruthIssue(
                id=str(r["id"]),
                category=str(r["category"]),
                severity=str(r["severity"]),
                file=str(r["file"]),
                line_start=int(lr[0]),
                line_end=int(lr[1]),
                description=str(r.get("description", "")).strip(),
                match_keywords=[str(k) for k in (r.get("match_keywords") or [])],
            )
        )
    return GroundTruth(
        pr=int(raw["pr"]),
        title=str(raw.get("title", "")),
        size=str(raw.get("size", "unknown")),
        match_tolerance_lines=int(raw.get("match_tolerance_lines", 5)),
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _normalize_path(p: str) -> str:
    p = (p or "").strip().lstrip("./")
    # Some agents strip the leading `a/` `b/` from git diff paths; tolerate.
    for prefix in ("a/", "b/"):
        if p.startswith(prefix):
            p = p[len(prefix) :]
    return p


def _ranges_overlap(a_lo: int, a_hi: int, b_lo: int, b_hi: int, tol: int) -> bool:
    return max(a_lo, b_lo - tol) <= min(a_hi, b_hi + tol)


def _finding_text(f: dict[str, Any]) -> str:
    parts = [
        str(f.get("title") or ""),
        str(f.get("message") or ""),
        str(f.get("category") or ""),
    ]
    return " ".join(parts).lower()


def _keyword_hit(text: str, keywords: list[str]) -> str | None:
    for kw in keywords:
        if kw and kw.lower() in text:
            return kw
    return None


@dataclass
class MatchEdge:
    finding_index: int
    issue_id: str
    matched_keyword: str


@dataclass
class ScoreResult:
    pr: int
    total_findings: int
    total_issues: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    matches: list[MatchEdge] = field(default_factory=list)
    covered_issue_ids: list[str] = field(default_factory=list)   # deduped issues with >=1 matching finding
    matched_finding_count: int = 0                               # findings that matched >=1 issue
    unmatched_findings: list[int] = field(default_factory=list)
    unmatched_issue_ids: list[str] = field(default_factory=list)
    per_category: dict[str, dict[str, int]] = field(default_factory=dict)
    per_severity: dict[str, dict[str, int]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pr": self.pr,
            "totals": {
                "findings": self.total_findings,
                "issues": self.total_issues,
                "true_positives": self.true_positives,        # issues covered (recall numerator)
                "matched_findings": self.matched_finding_count,  # findings that hit something (precision numerator)
                "false_positives": self.false_positives,
                "false_negatives": self.false_negatives,
            },
            "metrics": {
                "precision": self.precision,
                "recall": self.recall,
                "f1": self.f1,
            },
            "matches": [
                {
                    "finding_index": m.finding_index,
                    "issue_id": m.issue_id,
                    "matched_keyword": m.matched_keyword,
                }
                for m in self.matches
            ],
            "covered_issue_ids": self.covered_issue_ids,
            "unmatched_findings": self.unmatched_findings,
            "unmatched_issue_ids": self.unmatched_issue_ids,
            "per_category": self.per_category,
            "per_severity": self.per_severity,
        }


def score(findings: list[dict[str, Any]], gt: GroundTruth) -> ScoreResult:
    """Match findings against ground-truth issues (many-to-one).

    A finding may cover EVERY issue it localizes to (same file, overlapping
    line range, and a keyword hit), and an issue is "covered" if ANY finding
    matches it. This decouples recall from how granularly a version chooses
    to report: a reviewer that folds three nits into one comment is not
    penalized, and a reviewer that splits one issue into three findings is
    not rewarded.

    - recall    = covered issues / total issues
    - precision = findings that matched >=1 issue / total findings
    - a "false positive" is a finding that localizes to no planted issue
      (review these manually -- it may be a real issue we never planted)
    - a "false negative" is a planted issue no finding localized to

    The per-issue keyword + line-range gate still applies, so a vague
    "this PR has problems" finding cannot vacuum up credit for issues it
    does not actually point at.
    """

    matches: list[MatchEdge] = []
    matched_finding_indices: set[int] = set()
    covered_issue_ids: set[str] = set()

    for fi, f in enumerate(findings):
        f_file = _normalize_path(str(f.get("file", "")))
        try:
            f_lo = int(f.get("line_start", 0))
            f_hi = int(f.get("line_end", f_lo))
        except (TypeError, ValueError):
            f_lo = f_hi = 0
        f_text = _finding_text(f)

        for issue in gt.issues:
            if _normalize_path(issue.file) != f_file:
                continue
            if not _ranges_overlap(
                f_lo, f_hi, issue.line_start, issue.line_end, gt.match_tolerance_lines
            ):
                continue
            kw = _keyword_hit(f_text, issue.match_keywords)
            if kw is None:
                continue

            # many-to-one: this finding covers this issue; keep scanning so
            # the same finding can also cover other issues it localizes to.
            matches.append(MatchEdge(finding_index=fi, issue_id=issue.id, matched_keyword=kw))
            matched_finding_indices.add(fi)
            covered_issue_ids.add(issue.id)

    covered = len(covered_issue_ids)
    matched_findings = len(matched_finding_indices)
    fp = len(findings) - matched_findings
    fn = len(gt.issues) - covered

    precision = matched_findings / len(findings) if findings else 0.0
    recall = covered / len(gt.issues) if gt.issues else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    per_category: dict[str, dict[str, int]] = {}
    per_severity: dict[str, dict[str, int]] = {}
    for issue in gt.issues:
        for bucket, key in (("per_category", issue.category), ("per_severity", issue.severity)):
            target = per_category if bucket == "per_category" else per_severity
            slot = target.setdefault(key, {"total": 0, "found": 0})
            slot["total"] += 1
            if issue.id in covered_issue_ids:
                slot["found"] += 1

    # preserve YAML order for readable output
    ordered_covered = [i.id for i in gt.issues if i.id in covered_issue_ids]

    return ScoreResult(
        pr=gt.pr,
        total_findings=len(findings),
        total_issues=len(gt.issues),
        true_positives=covered,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        matches=matches,
        covered_issue_ids=ordered_covered,
        matched_finding_count=matched_findings,
        unmatched_findings=[i for i in range(len(findings)) if i not in matched_finding_indices],
        unmatched_issue_ids=[i.id for i in gt.issues if i.id not in covered_issue_ids],
        per_category=per_category,
        per_severity=per_severity,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _ground_truth_path_for_pr(pr_number: int) -> Path:
    here = Path(__file__).resolve().parent
    gt_dir = here / "ground_truth"
    # filename pattern: pr-{N}-*.yaml
    for candidate in sorted(gt_dir.glob(f"pr-{pr_number}-*.yaml")):
        return candidate
    raise FileNotFoundError(f"No ground-truth file for PR #{pr_number} in {gt_dir}")


def _short_finding(f: dict[str, Any], idx: int) -> str:
    return (
        f"  [{idx}] {f.get('severity', '?')}/{f.get('category', '?')}  "
        f"{f.get('file', '?')}:{f.get('line_start', '?')}-{f.get('line_end', '?')}\n"
        f"      {(f.get('title') or '').strip()[:120]}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score findings against ground truth")
    parser.add_argument(
        "result_json",
        help="Path to a JSON file produced by run_eval (or any object with `findings: [...]`)",
    )
    parser.add_argument("--pr", type=int, help="Override PR number (default: read from result)")
    parser.add_argument(
        "--ground-truth",
        default=None,
        help="Path to ground-truth YAML (default: derived from PR number)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print unmatched findings and missed issues"
    )
    args = parser.parse_args(argv)

    result = json.loads(Path(args.result_json).read_text())
    findings = result.get("findings") or []
    pr_number = args.pr or int(result.get("pr") or 0)
    if not pr_number:
        raise SystemExit("PR number not found in result; pass --pr.")

    gt_path = Path(args.ground_truth) if args.ground_truth else _ground_truth_path_for_pr(pr_number)
    gt = load_ground_truth(gt_path)

    s = score(findings, gt)

    print(
        f"PR #{s.pr}  findings={s.total_findings}  issues={s.total_issues}  "
        f"TP={s.true_positives}  FP={s.false_positives}  FN={s.false_negatives}  "
        f"P={s.precision:.2f}  R={s.recall:.2f}  F1={s.f1:.2f}"
    )

    if args.verbose:
        print("\nUnmatched issues (false negatives):")
        for issue in gt.issues:
            if issue.id in s.unmatched_issue_ids:
                print(f"  - {issue.id}  [{issue.severity}/{issue.category}]  {issue.file}:{issue.line_start}-{issue.line_end}")
                print(f"      {issue.description.splitlines()[0] if issue.description else ''}")

        print("\nUnmatched findings (possible false positives - review manually):")
        for idx in s.unmatched_findings:
            print(_short_finding(findings[idx], idx))

    return 0


if __name__ == "__main__":
    sys.exit(main())
