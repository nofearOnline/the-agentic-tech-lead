# v2 - repo-aware reviewer

v1 reviewed the diff in isolation. v2 gives the reviewer the rest of the
repository.

```
PR number  ->  gh pr diff  +  git worktree @ head_sha  ->  agentic claude call  ->  findings
                                          (Read / Grep / Glob / LS, multi-turn loop)
```

## What changed from v1

| | v1 | v2 |
|---|---|---|
| Input | diff only | diff **+** working copy of the repo at the PR head |
| Tools | none (`tools_enabled=False`) | Read / Grep / Glob / LS (`tools_enabled=True`) |
| Turns | 1 (single shot) | agentic loop (multiple turns) |
| Sees | the diff | the diff **and any file it chooses to open** |

Everything else (the `Finding` shape, the JSON output contract, the model
from `config.model_for("generalist")`, the `ReviewResult` fields) is identical
to v1 so the bench harness scores both the same way.

## Why a worktree

The PR's changes live on a feature branch, not on `main`. If the agent read
files from the normal checkout it would see **stale** `main` code and its
"the rest of the repo does X" reasoning would be wrong.

So before the call, v2 runs:

```bash
git worktree add --detach <tmpdir>/tree <pr.head_sha>
```

This materializes the repository exactly as it looks *after* the PR, in a
throwaway directory. The `claude` subprocess runs with that directory as its
working directory (and it is also passed via `--add-dir`), so:

- relative paths the agent emits match the diff paths (repo-root-relative), and
- every file the agent opens reflects the post-change state.

The worktree is always torn down in a `finally` (`git worktree remove --force`
plus an `rmtree` backstop), so repeated/parallel runs don't leak worktrees.

## The agentic loop

`shared.call(..., tools_enabled=True)` drops the `--disallowedTools` wall and
lets the `claude` CLI run its built-in agent loop. v2 restricts the surface to
read-only tools (`--allowedTools Read Grep Glob LS`) — the agent can explore
but cannot edit the worktree or run shell commands. The system prompt directs
it to investigate conventions, duplication, and cross-file contracts before
emitting findings, then end with a single ```json fenced block (parsed by
`shared.extract_fenced_json`, same as v1).

## The miss bucket v2 targets

Issues v1 *structurally* cannot see because they require the rest of the repo:

- snake_case response fields where the rest of the API uses camelCase
- `console.log` where the codebase has a real (pino) logger
- re-implementing a helper that already exists elsewhere
- contract mismatches with un-changed callers / types / tests

## Usage

From `pr-agent/v2_repo_aware/`:

```bash
python review.py <pr-url-or-number> [--repo OWNER/REPO] [--config PATH] [--json]
```

Or via the bench harness, from `pr-agent/`:

```bash
python -m bench.run_eval --version v2_repo_aware --pr 1 --trials 1
```

Requires a **local clone** of the target repo (the one whose PRs are being
reviewed) with the PR's head commit fetched locally — the worktree is created
from that clone. `gh` must be authenticated for diff/metadata fetching.

## Cost / latency

A repo-aware run is an agentic loop: expect several turns, a few minutes of
wall-clock, and up to ~$0.50 on Sonnet — materially more than v1's single
shot. The payoff is the cross-file findings v1 can't reach.
