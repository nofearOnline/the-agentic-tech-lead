# v1 - single-shot reviewer

The most naive thing that could plausibly work.

```
PR number  ->  gh pr diff  ->  one LLM call  ->  structured findings
```

That's the whole pipeline. No agentic loop, no tools beyond a single
output-shaping tool, no access to the repository beyond the diff itself.

## What it knows

- The PR title, body, author, and size
- The unified diff

## What it does *not* know

- The rest of the repository (other files, conventions, neighboring code)
- The linked issue or design doc
- CI status, lint output, or test results
- Prior PRs by the same author
- Anything that didn't fit in the diff

This list is exactly the gap that later versions will close.

## Setup

From `pr-agent/` (one level up):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...

gh auth status   # must be logged in
```

## Usage

From `pr-agent/v1_single_shot/`:

```bash
python review.py <pr-url-or-number> [--repo OWNER/REPO] [--config PATH] [--json]
```

Examples:

```bash
python review.py 1                          # uses repo from pr-agent/config.yaml
python review.py 2 --json                   # raw JSON output for tooling
python review.py https://github.com/nofearOnline/the-agentic-tech-lead/pull/3
```

The model, pricing, and target repo all come from `pr-agent/config.yaml`.
Change them there once; every version reads from the same file.

## Output shape

Findings come back through the `report_findings` tool with this schema:

```python
Finding(
    file=str,           # path as it appears in the PR diff
    line_start=int,
    line_end=int,
    category=str,       # security | performance | correctness | dry | kiss | test | standards | quality
    severity=str,       # must | should | suggestion
    title=str,          # one-line headline
    message=str,        # full reasoning and suggested fix
    source="v1_generalist",
)
```

The CLI also prints a token-usage and cost line to stderr so you can
spot-check what each review actually cost.

## Known limitations (on purpose)

- Big PRs blow past the context window. There is no chunking, no
  prioritization, no per-file review.
- Hallucinated line numbers. The model only sees the diff and is asked
  to point at line ranges. It will sometimes miss.
- No grounding. The model can't open a file or run a test, so cross-file
  regressions and "this looks fine in isolation but conflicts with X
  over there" issues will slip through.
- One-shot. If the first answer is mediocre, that's the answer. There
  is no reflection or critique step.

These are all the things v2+ exists to fix.
