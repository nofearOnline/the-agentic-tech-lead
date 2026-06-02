"""v2 - repo-aware PR review.

v1 saw only the diff. v2 closes the "I can't see the rest of the repo" gap:
it checks out a git worktree at the PR's head commit, hands the `claude` CLI
its built-in read tools (Read/Grep/Glob/LS) plus that worktree, and lets the
model run an agentic loop. The model can now open sibling endpoints, the
shared logger, helper modules, and any unchanged file to ground its findings.

The miss bucket this targets (issues v1 structurally cannot see):
  - "this response uses snake_case but the rest of the API is camelCase"
  - "this uses console.log but the codebase has a pino logger"
  - "this re-implements a helper that already exists elsewhere"
  - contract mismatches with files that the diff never touched.

Pipeline:
    PR  ->  git worktree @ head_sha  ->  agentic claude call (tools)  ->  findings

Public API:
    review(pr, config) -> ReviewResult            # used by the eval harness

CLI:
    python review.py <pr-url-or-number> [--repo OWNER/REPO]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Make `shared/` importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (  # noqa: E402
    Config,
    Finding,
    PullRequest,
    Usage,
    call,
    extract_fenced_json,
    fetch_pull_request,
    load_config,
    parse_pr_arg,
)

SOURCE = "v2_repo_aware"


SYSTEM_PROMPT = """\
You are an experienced engineering tech lead reviewing a pull request.

You will be given the PR title, description, author, and the unified diff
of the changes. Unlike a diff-only review, you ALSO have a full working copy
of the repository checked out at the state AFTER this PR is applied. Your
current working directory IS the repository root, and you have these tools:

- Read   open any file to see code the diff does not show
- Grep   search the whole repo for patterns, callers, conventions
- Glob   find files by name/path
- LS     list directories

USE THESE TOOLS. The whole point of this review is to ground your findings in
the rest of the codebase, not just the diff. Before you finalize, actively
investigate:

- Conventions: do the changed files match how the rest of the repo does
  things? Read sibling endpoints/handlers and shared modules. Flag drift such
  as snake_case response fields where the rest of the API uses camelCase, or
  raw console.log where the codebase has a real logger (e.g. pino) it should
  use instead.
- Duplication: Grep for helpers/utilities the new code re-implements instead
  of reusing.
- Contracts: does the change agree with un-changed callers, types, schemas,
  and tests elsewhere? Open those files and check.
- The usual lenses below still apply.

Categories you should look for:
- security      secrets in code, injection, broken auth, SSRF, PII / PCI leaks
- performance   N+1, unbounded work, sync I/O on hot paths, missing pagination
- correctness   bugs, regressions, race conditions, broken edge cases
- dry           duplicated logic that should be shared
- kiss          over-engineering, unnecessary abstractions, dead code
- test          missing tests, tests that pass for the wrong reason
- standards     naming, formatting, inconsistency with the rest of the codebase
- quality       anything else a senior reviewer would flag

Severity:
- must         CI / security / data-loss / would block merge
- should       quality issues a reviewer would normally request changes for
- suggestion   nits and improvements that aren't blocking

Output format - REQUIRED.

After you have finished investigating, your FINAL message must be a single
```json fenced block and nothing else - no prose before or after it. The
block must parse as JSON with this shape:

```json
{
  "summary": "one short paragraph summarizing your review",
  "findings": [
    {
      "file": "path/as/it/appears/in/the/diff",
      "line_start": 12,
      "line_end": 18,
      "category": "security",
      "severity": "must",
      "title": "short headline, <= 80 chars",
      "message": "what is wrong, why it matters, suggested fix"
    }
  ]
}
```

If the PR is clean overall, return an empty `findings` list and say so in
`summary`. Use the file paths exactly as they appear in the diff (relative to
the repo root). Use line numbers from the diff hunks or from the files you
read; if you cannot point to a specific line, use the start of the relevant
hunk."""


# Read-only tool surface. We deliberately do NOT expose Bash/Edit/Write so the
# agent can explore but cannot mutate the worktree or run arbitrary commands.
_ALLOWED_TOOLS = ["Read", "Grep", "Glob", "LS"]


@dataclass
class ReviewResult:
    findings: list[Finding]
    usage: Usage
    cost_usd: float
    summary: str
    raw_response: str = ""
    resolved_model: str = ""
    num_turns: int = 0
    duration_ms: int = 0
    error: str | None = None


def _build_user_message(pr: PullRequest) -> str:
    return (
        f"Repository: {pr.repo}\n"
        f"PR #{pr.number}: {pr.title}\n"
        f"Author:     {pr.author}\n"
        f"Size:       +{pr.additions} / -{pr.deletions} across {pr.changed_files} files\n"
        f"\n"
        f"A working copy of this repository at the PR's head commit is checked\n"
        f"out in your current working directory. Read/Grep/Glob freely to\n"
        f"ground your review in the surrounding code.\n"
        f"\n"
        f"Description:\n{pr.body or '(no description)'}\n"
        f"\n"
        f"Diff:\n"
        f"```diff\n"
        f"{pr.diff}\n"
        f"```\n"
    )


def _coerce_findings(raw_obj: dict | None) -> tuple[str, list[Finding]]:
    """Turn a parsed JSON object into (summary, findings)."""
    if not raw_obj:
        return "", []
    summary = str(raw_obj.get("summary") or "")
    findings: list[Finding] = []
    for raw in raw_obj.get("findings") or []:
        if not isinstance(raw, dict):
            continue
        try:
            findings.append(
                Finding(
                    file=str(raw["file"]),
                    line_start=int(raw["line_start"]),
                    line_end=int(raw["line_end"]),
                    category=str(raw["category"]),
                    severity=str(raw["severity"]),  # type: ignore[arg-type]
                    title=str(raw["title"]),
                    message=str(raw["message"]),
                    source=SOURCE,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            sys.stderr.write(f"warning: dropped malformed finding ({exc}): {raw!r}\n")
    return summary, findings


# ---------------------------------------------------------------------------
# Git worktree lifecycle
# ---------------------------------------------------------------------------


def _repo_root(config: Config) -> Path:
    """Local clone whose PRs we review. The config file lives at
    pr-agent/config.yaml inside that clone, so the repo root is two levels up.
    Confirm via `git rev-parse` so a moved checkout still resolves correctly.
    """
    pr_agent_dir = config.source_path.parent
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=pr_agent_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return pr_agent_dir.parent


def _add_worktree(repo_root: Path, sha: str) -> Path:
    """Check out `sha` into a fresh temp worktree. Raises on failure."""
    tmp = Path(tempfile.mkdtemp(prefix="v2-worktree-"))
    # mkdtemp creates the dir; `git worktree add` wants to create it itself.
    target = tmp / "tree"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(target), sha],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return target


def _remove_worktree(repo_root: Path, target: Path) -> None:
    """Best-effort cleanup; never raises."""
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(target)],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        pass
    # Remove the mkdtemp parent regardless of git's view of things.
    shutil.rmtree(target.parent, ignore_errors=True)


def review(pr: PullRequest, config: Config) -> ReviewResult:
    """Run a repo-aware agentic review. Returns structured findings + usage."""
    model = config.model_for("generalist")
    repo_root = _repo_root(config)

    sha = pr.head_sha
    if not sha:
        return ReviewResult(
            findings=[],
            usage=Usage(),
            cost_usd=0.0,
            summary="",
            resolved_model=model,
            error="PR has no head_sha; cannot create a worktree at the PR head.",
        )

    worktree: Path | None = None
    try:
        try:
            worktree = _add_worktree(repo_root, sha)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            return ReviewResult(
                findings=[],
                usage=Usage(),
                cost_usd=0.0,
                summary="",
                resolved_model=model,
                error=f"git worktree add failed for {sha}: {detail}",
            )

        result = call(
            system=SYSTEM_PROMPT,
            user=_build_user_message(pr),
            model=model,
            tools_enabled=True,
            cwd=str(worktree),
            add_dirs=[str(worktree)],
            extra_args=["--allowedTools", *_ALLOWED_TOOLS],
        )

        if result.is_error:
            return ReviewResult(
                findings=[],
                usage=result.usage,
                cost_usd=result.cost_usd,
                summary="",
                raw_response=result.text,
                resolved_model=result.resolved_model,
                num_turns=result.num_turns,
                duration_ms=result.duration_ms,
                error=result.error,
            )

        parsed = extract_fenced_json(result.text)
        summary, findings = _coerce_findings(parsed)

        return ReviewResult(
            findings=findings,
            usage=result.usage,
            cost_usd=result.cost_usd,
            summary=summary,
            raw_response=result.text,
            resolved_model=result.resolved_model,
            num_turns=result.num_turns,
            duration_ms=result.duration_ms,
        )
    finally:
        if worktree is not None:
            _remove_worktree(repo_root, worktree)


def _render_for_cli(result: ReviewResult) -> str:
    lines: list[str] = []
    if result.error:
        lines.append(f"ERROR: {result.error}")
        return "\n".join(lines)

    lines.append(result.summary or "(no summary)")
    lines.append("")
    if not result.findings:
        lines.append("No findings.")
    else:
        for i, f in enumerate(result.findings, start=1):
            lines.append(
                f"[{i}] {f.severity.upper()} {f.category} - "
                f"{f.file}:{f.line_start}-{f.line_end}"
            )
            lines.append(f"    {f.title}")
            for body_line in f.message.splitlines():
                lines.append(f"    {body_line}")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v2 repo-aware PR reviewer")
    parser.add_argument("pr", help="PR URL or number")
    parser.add_argument(
        "--repo",
        default=None,
        help="OWNER/REPO when 'pr' is a bare number (defaults to config.yaml repo)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (defaults to pr-agent/config.yaml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw findings + usage as JSON instead of human prose",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    repo, number = parse_pr_arg(args.pr)
    if args.repo:
        repo = args.repo
    if repo is None:
        repo = config.repo.slug

    pr = fetch_pull_request(repo, number)
    sys.stderr.write(
        f"Reviewing {pr.repo}#{pr.number} ({pr.title!r}, "
        f"+{pr.additions}/-{pr.deletions}, {pr.changed_files} files)...\n"
    )

    result = review(pr, config)

    if args.json:
        out = {
            "summary": result.summary,
            "findings": [f.as_dict() for f in result.findings],
            "usage": {
                "input_tokens": result.usage.input_tokens,
                "cache_creation_input_tokens": result.usage.cache_creation_input_tokens,
                "cache_read_input_tokens": result.usage.cache_read_input_tokens,
                "output_tokens": result.usage.output_tokens,
            },
            "cost_usd": result.cost_usd,
            "resolved_model": result.resolved_model,
            "num_turns": result.num_turns,
            "duration_ms": result.duration_ms,
            "error": result.error,
        }
        print(json.dumps(out, indent=2))
    else:
        print(_render_for_cli(result))
        sys.stderr.write(
            f"\nmodel={result.resolved_model} turns={result.num_turns}\n"
            f"tokens: in={result.usage.input_tokens} "
            f"cache_w={result.usage.cache_creation_input_tokens} "
            f"cache_r={result.usage.cache_read_input_tokens} "
            f"out={result.usage.output_tokens}\n"
            f"cost=${result.cost_usd:.4f}  duration={result.duration_ms}ms\n"
        )
    return 0 if not result.error else 1


if __name__ == "__main__":
    sys.exit(main())
