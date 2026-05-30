# v1 — single-shot reviewer

The most naive thing that could plausibly work.

```
PR number  ─►  gh pr diff  ─►  one LLM call  ─►  text to stdout
```

That's the whole pipeline. No tools, no loop, no access to the repository
beyond the diff itself.

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

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...

gh auth status   # must be logged in
```

## Usage

```bash
python review.py <pr-url-or-number> [--repo OWNER/REPO] [--model MODEL]
```

Examples:

```bash
python review.py https://github.com/nofearOnline/the-agentic-tech-lead/pull/1
python review.py 2 --repo nofearOnline/the-agentic-tech-lead
```

The review is written to stdout; a one-line status header is written to
stderr so you can pipe the review somewhere clean.

## Known limitations (on purpose)

- Big PRs blow past the context window — there is no chunking, no
  prioritization, no per-file review.
- Hallucinated line numbers — the model only sees the diff and is asked
  to "roughly" point at lines. It will sometimes miss.
- No grounding — the model can't open a file or run a test, so
  cross-file regressions and "this looks fine in isolation but conflicts
  with X over there" issues will slip through.
- One-shot — if the first answer is mediocre, that's the answer. There
  is no reflection or critique step.

These are all the things v2+ exists to fix.
