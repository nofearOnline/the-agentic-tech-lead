# pr-agent

This directory holds successive versions of a PR-reviewing agent, used as the
demo subject for **The Agentic Tech Lead**.

The goal across versions is to walk from the most naive thing that could work
("dump the diff into an LLM and hope") all the way to a real agentic reviewer
that uses tools, plans, and iterates. Each version lives in its own folder so
the diff between two versions is the talk-track for that step.

## Versions

| Folder                | What it is                                                   |
|-----------------------|--------------------------------------------------------------|
| `v1_single_shot/`     | One LLM call. Diff in, review out. No tools, no loop.        |
| _(future)_            | Add PR metadata, file-level context, repo conventions, ...   |
| _(future)_            | Add tools (read file, search, run tests) and an agent loop.  |

Each version's folder contains its own `README.md` with how to run it and
what it can and can't do.

## Demo target

All versions are pointed at the `payments-service/` sibling directory in this
repo, and at three intentionally-flawed PRs opened against it on GitHub.
