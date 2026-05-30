"""Pull-request fetching via `gh` CLI. Shared so every version (and the
eval harness) gets the same PR shape.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PullRequest:
    repo: str            # OWNER/NAME
    number: str          # PR number as string (for CLI compatibility)
    title: str
    body: str
    author: str
    additions: int
    deletions: int
    changed_files: int
    head_sha: str
    base_sha: str
    diff: str            # unified diff


def parse_pr_arg(arg: str) -> tuple[str | None, str]:
    """Accept either a full GitHub PR URL or a bare PR number."""
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
        raise SystemExit(
            "`gh` CLI not found on PATH. Install it from https://cli.github.com/"
        ) from exc
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or "")
        raise SystemExit(
            f"`gh {' '.join(args)}` failed with exit code {exc.returncode}"
        )
    return result.stdout


def fetch_pull_request(repo: str | None, number: str) -> PullRequest:
    meta_args = [
        "pr", "view", number,
        "--json", "title,body,author,additions,deletions,changedFiles,url,headRefOid,baseRefOid",
    ]
    diff_args = ["pr", "diff", number]
    if repo:
        meta_args += ["--repo", repo]
        diff_args += ["--repo", repo]

    meta = json.loads(_run_gh(meta_args))
    diff = _run_gh(diff_args)

    resolved_repo = repo
    if not resolved_repo:
        url_match = re.match(
            r"https?://github\.com/([^/]+/[^/]+)/pull/\d+",
            meta.get("url", ""),
        )
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
        head_sha=meta.get("headRefOid") or "",
        base_sha=meta.get("baseRefOid") or "",
        diff=diff,
    )
