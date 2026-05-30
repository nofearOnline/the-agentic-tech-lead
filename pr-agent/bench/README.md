# Eval harness

How we measure each version of the reviewer agent. Same PRs, same ground
truth, same metrics; the only thing that changes is the agent under test.

## Layout

```
bench/
  ground_truth/        planted-issue catalogs per PR (YAML)
    pr-1-coupon.yaml
    pr-2-refunds.yaml
    pr-3-auth-admin.yaml
  results/             written by run_eval.py
    <version>/
      pr-<N>/
        trial-<T>.json
  score.py             match findings against ground truth
  run_eval.py          run a version across the eval matrix
  compare.py           aggregate results into a markdown table
```

## Setup

From `pr-agent/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...

gh auth status   # must be logged in
```

## Run a version

```bash
cd pr-agent
python -m bench.run_eval --version v1_single_shot
```

That executes `trials_per_pr * |prs|` trials for the version, per
`config.yaml`. Each run produces one JSON file under
`bench/results/v1_single_shot/pr-<N>/trial-<T>.json` containing:

- The structured findings the agent emitted
- Token usage broken down for cache accounting
- Cost in USD
- Elapsed wall-clock seconds
- The scored result (TP / FP / FN, precision / recall / F1, per-category
  coverage, list of matched and unmatched issues)

Common flags:

```bash
python -m bench.run_eval --version v1_single_shot --pr 1 --trials 1
python -m bench.run_eval --version v1_single_shot --version v2_repo_aware
```

## Score a single result file

```bash
python -m bench.score bench/results/v1_single_shot/pr-1/trial-0.json --verbose
```

## Compare across versions

```bash
python -m bench.compare                              # everything
python -m bench.compare --version v1_single_shot     # one version
python -m bench.compare --json                       # raw aggregates
```

The output is markdown so you can paste it straight into the deck.

## Scoring rules

A finding F matches a planted issue I when:

1. `F.file == I.file` (paths normalized: leading `./`, `a/`, `b/` stripped)
2. `F` line range overlaps `I.line_range` +/- `match_tolerance_lines`
3. At least one of `I.match_keywords` appears (case-insensitive) somewhere
   in `F.title` or `F.message`

Matching is greedy, in YAML order: each finding can claim at most one
issue; each issue can be claimed once.

- **True positive**: finding matched an issue
- **False positive**: finding matched nothing
- **False negative**: issue went unclaimed

Precision = TP / (TP + FP), Recall = TP / (TP + FN), F1 = harmonic mean.

### False positives caveat

In a controlled-demo setup, "FP" is overloaded - a finding may flag a
real problem that we simply didn't bother to plant. The scorer reports
every FP for manual review (`--verbose`); if any are real, update the
matching ground-truth YAML and re-score. The headline precision number
assumes "not planted -> false."

## Adding a new version

A version is any folder `pr-agent/<name>/` whose `review.py` exposes:

```python
def review(pr: PullRequest, config: Config) -> ReviewResult: ...
```

where `ReviewResult` has at least `.findings: list[Finding]`,
`.usage: Usage`, `.cost_usd: float`, and `.summary: str`. Then:

```bash
python -m bench.run_eval --version <name>
```

is all you need.

## Adding or updating ground truth

Each `bench/ground_truth/pr-<N>-*.yaml` is the single source of truth
for what counts as a "right answer" on that PR. Edit it freely; the next
`bench.compare` will rescore based on it.

When adding a new issue, include:

- A stable `id` slug (used in the heatmap)
- `file` and `line_range` matching the PR diff (paths must include the
  `payments-service/` prefix because the diff does)
- `match_keywords` - phrases the agent is likely to use when describing
  this issue. Err on the side of generous; the scorer requires only one.
