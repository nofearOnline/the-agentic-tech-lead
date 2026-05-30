"""v1 — single-shot PR review.

The simplest possible reviewer: fetch the PR diff via the `gh` CLI, hand
the whole thing to an LLM with a one-paragraph system prompt, and print
whatever comes back.

No tools. No loop. No access to the rest of the repo, the PR comments,
the linked issue, the CI status, or anything else a human reviewer would
look at. This is the baseline that the rest of the evolutions will
improve on.

Usage:
    export ANTHROPIC_API_KEY=...
    python review.py <pr-url-or-number> [--repo OWNER/REPO]

Examples:
    python review.py https://github.com/nofearOnline/the-agentic-tech-lead/pull/1
    python review.py 1 --repo nofearOnline/the-agentic-tech-lead
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass

from anthropic import Anthropic

MODEL = "claude-sonnet-4-5"
MAX_OUTPUT_TOKENS = 4096

SYSTEM_PROMPT = """\
You are an experienced engineering tech lead reviewing a pull request.

You will be given the PR title, description, and the unified diff of the
changes. Your job is to find the issues that actually matter and explain
each one concisely.

Look for:
- Correctness bugs and regressions
- Security issues (secrets in code, injection, broken auth, SSRF, PII / PCI
  leaks, etc.)
- Performance problems (N+1, unbounded work, sync I/O on hot paths)
- DRY / KISS violations, dead code, and over-engineering
- Test quality (missing tests, tests that pass for the wrong reason)
- Coding standards and consistency with the surrounding code in the diff
- Anything else a senior reviewer would flag before approving

For each issue, give:
- Where (file and roughly which lines)
- What is wrong
- Why it matters
- A suggested fix (one line is fine)

If the PR is clean overall, say so plainly. Don't pad."""


@dataclass
class PullRequest:
    repo: str
    number: str
    title: str
    body: str
    author: str
    additions: int
    deletions: int
    changed_files: int
    diff: str


def parse_pr_arg(arg: str) -> tuple[str | None, str]:
    """Accept either a full GitHub PR URL or a bare number."""
    url_match = re.match(r"https?://github\.com/([^/]+/[^/]+)/pull/(\d+)", arg)
    if url_match:
        return url_match.group(1), url_match.group(2)
    if arg.isdigit():
        return None, arg
    raise SystemExit(f"Cannot parse PR identifier: {arg!r}")


def _run_gh(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit("`gh` CLI not found on PATH. Install it from https://cli.github.com/") from exc
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or "")
        raise SystemExit(f"`gh {' '.join(args)}` failed with exit code {exc.returncode}")
    return result.stdout


def fetch_pull_request(repo: str | None, number: str) -> PullRequest:
    meta_args = [
        "pr", "view", number,
        "--json", "title,body,author,additions,deletions,changedFiles,url",
    ]
    diff_args = ["pr", "diff", number]
    if repo:
        meta_args += ["--repo", repo]
        diff_args += ["--repo", repo]

    meta = json.loads(_run_gh(meta_args))
    diff = _run_gh(diff_args)

    resolved_repo = repo
    if not resolved_repo:
        url_match = re.match(r"https?://github\.com/([^/]+/[^/]+)/pull/\d+", meta.get("url", ""))
        if url_match:
            resolved_repo = url_match.group(1)

    return PullRequest(
        repo=resolved_repo or "<unknown>",
        number=number,
        title=meta.get("title") or "",
        body=meta.get("body") or "",
        author=(meta.get("author") or {}).get("login") or "<unknown>",
        additions=int(meta.get("additions") or 0),
        deletions=int(meta.get("deletions") or 0),
        changed_files=int(meta.get("changedFiles") or 0),
        diff=diff,
    )


def build_user_message(pr: PullRequest) -> str:
    return (
        f"Repository: {pr.repo}\n"
        f"PR #{pr.number}: {pr.title}\n"
        f"Author:     {pr.author}\n"
        f"Size:       +{pr.additions} / -{pr.deletions} across {pr.changed_files} files\n"
        f"\n"
        f"Description:\n{pr.body or '(no description)'}\n"
        f"\n"
        f"Diff:\n"
        f"```diff\n"
        f"{pr.diff}\n"
        f"```\n"
    )


def review(pr: PullRequest, *, model: str = MODEL) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set in the environment.")

    client = Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(pr)}],
    )

    chunks: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            chunks.append(block.text)
    return "\n".join(chunks).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v1 single-shot PR reviewer")
    parser.add_argument("pr", help="PR URL or number")
    parser.add_argument(
        "--repo",
        default=None,
        help="OWNER/REPO when 'pr' is a bare number (defaults to gh's current repo)",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help=f"Anthropic model to use (default: {MODEL})",
    )
    args = parser.parse_args(argv)

    repo, number = parse_pr_arg(args.pr)
    if args.repo:
        repo = args.repo

    pr = fetch_pull_request(repo, number)
    sys.stderr.write(
        f"Reviewing {pr.repo}#{pr.number} ({pr.title!r}, "
        f"+{pr.additions}/-{pr.deletions}, {pr.changed_files} files)...\n"
    )

    output = review(pr, model=args.model)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
