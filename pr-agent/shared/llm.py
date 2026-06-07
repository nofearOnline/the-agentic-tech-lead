"""Single entry point for every LLM call across every version of the
reviewer.

Today this shells out to the `claude` CLI in non-interactive mode and
parses the JSON envelope. Tomorrow it might call the Anthropic SDK
directly when an API key is available; the public signature here is
designed to make that swap a 30-minute change instead of a refactor.

Every version of the agent (v1..v5) MUST go through this module to make
an LLM call. The bench harness depends on:
  - consistent token-usage accounting
  - consistent cost reporting (in USD)
  - consistent retry / timeout behavior
  - the ability to swap backends without touching version code
"""

from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import config as _config_mod
from .cost import Usage, add_usage, compute_cost, usage_from_anthropic


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass
class CallResult:
    """One LLM call's result. Identical shape regardless of backend."""

    text: str                       # the model's text response (post-tool-loop if applicable)
    usage: Usage                    # input/output/cache tokens
    cost_usd: float                 # what this call actually cost (or hypothetical cost)
    duration_ms: int                # wall-clock time inside the LLM call
    resolved_model: str             # the dated snapshot the alias resolved to
    num_turns: int                  # how many turns the agent ran (1 for single-shot)
    is_error: bool = False
    error: str | None = None
    raw: dict | None = field(default=None, repr=False)  # full envelope for forensic dumps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def call(
    *,
    system: str,
    user: str,
    model: str = "haiku",
    tools_enabled: bool = False,
    max_turns: int | None = None,
    timeout_seconds: int = 600,
    extra_args: Iterable[str] | None = None,
    add_dirs: Iterable[str] | None = None,
    cwd: str | None = None,
) -> CallResult:
    """Run one non-interactive Claude call through the configured backend.

    Backend is chosen by config.yaml `backend:` (overridable with the
    PR_AGENT_BACKEND env var):
      - "sdk": Anthropic Python SDK. Single-shot when `tools_enabled` is
        False; otherwise an in-process Read/Grep/Glob/LS tool loop scoped to
        `cwd` + `add_dirs` (mirrors what the CLI exposed to v2).
      - "cli": shell out to the `claude` CLI (the original backend).

    The CallResult shape is identical regardless of backend, so version code
    never needs to know which one ran.
    """
    if _select_backend() == "sdk":
        return _call_sdk(
            system=system,
            user=user,
            model=model,
            tools_enabled=tools_enabled,
            max_turns=max_turns,
            timeout_seconds=timeout_seconds,
            add_dirs=add_dirs,
            cwd=cwd,
        )
    return _call_cli(
        system=system,
        user=user,
        model=model,
        tools_enabled=tools_enabled,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds,
        extra_args=extra_args,
        add_dirs=add_dirs,
        cwd=cwd,
    )


def _call_cli(
    *,
    system: str,
    user: str,
    model: str = "haiku",
    tools_enabled: bool = False,
    max_turns: int | None = None,
    timeout_seconds: int = 600,
    extra_args: Iterable[str] | None = None,
    add_dirs: Iterable[str] | None = None,
    cwd: str | None = None,
) -> CallResult:
    """Run a single non-interactive Claude call via the `claude` CLI.

    Args:
        system: System prompt. Replaces Claude Code's default prompt (which
            saves ~70k tokens of scaffolding overhead per call). Use this
            for every version's "you are a reviewer" framing.
        user: User message (the diff, the question, etc.).
        model: One of {"haiku", "sonnet", "opus"} aliases or a full dated
            snapshot ID. Aliases resolve to whatever Claude Code thinks is
            current; the resolved ID comes back in `CallResult.resolved_model`.
        tools_enabled: If False (default), pass `--tools ""` so the model
            cannot read files, search, etc. Use this for single-shot
            versions. For agentic versions (v2+), pass True and the model
            will have access to Claude Code's built-in Read/Grep/Glob/etc.
        max_turns: Currently not enforced by the CLI; reserved for when we
            switch to the SDK.
        timeout_seconds: Subprocess timeout. PR3 on Opus can take ~2 min;
            default 10 min leaves a wide safety margin.
        extra_args: Anything else to pass to `claude`. Use sparingly.
        add_dirs: Extra directories the agent is allowed to Read/Grep within,
            passed as `--add-dir <dir>` (repeatable). Used by repo-aware
            versions (v2+) to expose a worktree checked out at the PR head.
        cwd: Working directory for the `claude` subprocess. When set, the
            agent's relative paths resolve against this directory (e.g. a
            git worktree root). Defaults to the caller's cwd.

    Returns:
        CallResult. Even on a non-zero exit we return a populated result
        with `is_error=True`; callers can decide whether to raise.
    """

    # User message goes on stdin so `--tools` (variadic) can't eat it as a
    # positional argument. Empty `--tools` is unreliable; instead we omit
    # `--tools` entirely when tools are disabled and rely on the system
    # prompt + the model's tool_choice behavior to keep it from invoking
    # anything. The single-shot prompt asks for a JSON-only response, so
    # the model has no reason to reach for a tool.
    cmd = [
        "claude",
        "-p",
        "--output-format", "json",
        "--input-format", "text",
        "--model", model,
        "--system-prompt", system,
        "--strict-mcp-config",          # don't pull in user-level MCP servers
        "--disable-slash-commands",     # no skill auto-trigger
    ]
    if not tools_enabled:
        # Allow nothing. The CLI doesn't accept an empty `--tools` reliably
        # when followed by other args, but `--disallowedTools` with the
        # full built-in set is unambiguous.
        cmd += [
            "--disallowedTools",
            "Bash",
            "Edit",
            "Glob",
            "Grep",
            "LS",
            "MultiEdit",
            "NotebookEdit",
            "Read",
            "Task",
            "TodoWrite",
            "WebFetch",
            "WebSearch",
            "Write",
        ]
    if add_dirs:
        for d in add_dirs:
            cmd += ["--add-dir", d]
    if extra_args:
        cmd += list(extra_args)

    started = time.monotonic()
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            input=user,                 # user message on stdin
            timeout=timeout_seconds,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        return CallResult(
            text="",
            usage=Usage(),
            cost_usd=0.0,
            duration_ms=int((time.monotonic() - started) * 1000),
            resolved_model=model,
            num_turns=0,
            is_error=True,
            error=f"claude CLI timed out after {timeout_seconds}s",
        )

    if completed.returncode != 0:
        return CallResult(
            text="",
            usage=Usage(),
            cost_usd=0.0,
            duration_ms=int((time.monotonic() - started) * 1000),
            resolved_model=model,
            num_turns=0,
            is_error=True,
            error=(completed.stderr or completed.stdout or "non-zero exit").strip(),
        )

    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return CallResult(
            text=completed.stdout,
            usage=Usage(),
            cost_usd=0.0,
            duration_ms=int((time.monotonic() - started) * 1000),
            resolved_model=model,
            num_turns=0,
            is_error=True,
            error=f"could not parse claude CLI output as JSON: {exc}",
        )

    return _envelope_to_result(envelope, model_alias=model)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _pick_resolved_model(model_usage: dict, alias: str) -> str:
    """Pick the *main* model from the CLI's `modelUsage` map.

    Claude Code often reports more than one model per call — a tiny `haiku`
    auxiliary (e.g. for housekeeping) alongside the model you actually asked
    for. The first key is therefore unreliable. Prefer the key that matches
    the requested alias/family; fall back to the model that did the most work.
    """
    keys = list(model_usage.keys())
    if not keys:
        return alias
    al = (alias or "").lower()
    # 1. Full-alias substring (handles full snapshot ids passed as the alias).
    for k in keys:
        if al and al in k.lower():
            return k
    # 2. Family word ("opus"/"sonnet"/"haiku"), skipping the generic prefix.
    family = al.split("-")[0]
    if family and family != "claude":
        for k in keys:
            if family in k.lower():
                return k

    # 3. Otherwise the model with the most token activity.
    def _tokens(v: object) -> float:
        if isinstance(v, dict):
            return sum(x for x in v.values() if isinstance(x, (int, float)))
        return 0.0

    return max(keys, key=lambda k: _tokens(model_usage[k]))


def _envelope_to_result(envelope: dict, *, model_alias: str) -> CallResult:
    usage_raw = envelope.get("usage") or {}
    usage = Usage(
        input_tokens=int(usage_raw.get("input_tokens") or 0),
        cache_creation_input_tokens=int(usage_raw.get("cache_creation_input_tokens") or 0),
        cache_read_input_tokens=int(usage_raw.get("cache_read_input_tokens") or 0),
        output_tokens=int(usage_raw.get("output_tokens") or 0),
    )
    model_usage = envelope.get("modelUsage") or {}
    resolved_model = _pick_resolved_model(model_usage, model_alias)

    is_error = bool(envelope.get("is_error"))
    error: str | None = None
    if is_error:
        error = (
            envelope.get("api_error_status")
            or envelope.get("subtype")
            or envelope.get("terminal_reason")
            or "claude CLI returned is_error=true"
        )

    return CallResult(
        text=str(envelope.get("result") or ""),
        usage=usage,
        cost_usd=float(envelope.get("total_cost_usd") or 0.0),
        duration_ms=int(envelope.get("duration_ms") or 0),
        resolved_model=resolved_model,
        num_turns=int(envelope.get("num_turns") or 0),
        is_error=is_error,
        error=error,
        raw=envelope,
    )


# ---------------------------------------------------------------------------
# Anthropic SDK backend
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _cfg():
    return _config_mod.load_config()


def _select_backend() -> str:
    """Resolve the active backend: env override > config > auto-detect."""
    override = os.environ.get("PR_AGENT_BACKEND")
    backend = (override or _safe_cfg_backend()).strip().lower()
    if backend == "auto":
        _config_mod.load_dotenv()
        return "sdk" if os.environ.get("ANTHROPIC_API_KEY") else "cli"
    return backend


def _safe_cfg_backend() -> str:
    try:
        return _cfg().backend or "auto"
    except Exception:  # noqa: BLE001
        return "auto"


_FAMILIES = ("opus", "sonnet", "haiku")

_DEFAULT_MODEL_IDS = {
    "opus": "claude-opus-4-1",
    "sonnet": "claude-sonnet-4-5",
    "haiku": "claude-haiku-4-5",
}

_model_id_cache: dict[str, str] = {}


def _family(model: str) -> str:
    s = (model or "").lower()
    for fam in _FAMILIES:
        if fam in s:
            return fam
    return s


def _resolve_model_id(model: str) -> str:
    """Map an alias ("opus"/"sonnet"/"haiku") to a concrete API model id.

    Precedence: a string that already looks like a concrete id is passed
    through; otherwise config `model_ids` (when not "auto"); otherwise the
    newest snapshot in the family via the models API; otherwise a default.
    """
    fam = _family(model)
    if fam not in _FAMILIES:
        return model
    if model not in _FAMILIES and any(ch.isdigit() for ch in model):
        return model
    if fam in _model_id_cache:
        return _model_id_cache[fam]

    try:
        configured = (_cfg().model_ids or {}).get(fam, "auto")
    except Exception:  # noqa: BLE001
        configured = "auto"
    if configured and configured != "auto":
        _model_id_cache[fam] = configured
        return configured

    resolved = _DEFAULT_MODEL_IDS.get(fam, model)
    try:
        client = _anthropic_client()
        models = list(client.models.list(limit=100).data)
        cands = [m for m in models if fam in m.id.lower()]
        if cands:
            cands.sort(key=lambda m: str(getattr(m, "created_at", "")), reverse=True)
            resolved = cands[0].id
    except Exception:  # noqa: BLE001
        pass
    _model_id_cache[fam] = resolved
    return resolved


def _max_output_tokens(family: str) -> int:
    return 8192 if family == "haiku" else 16000


def _anthropic_client(timeout_seconds: int = 600):
    from anthropic import Anthropic

    _config_mod.load_dotenv()
    return Anthropic(max_retries=4, timeout=float(timeout_seconds))


# -- in-process tools (Read/Grep/Glob/LS) scoped to the worktree -----------

_SDK_TOOLS = [
    {
        "name": "Read",
        "description": (
            "Read a UTF-8 text file from the repository. Returns the file "
            "content with 1-based line numbers. Use offset/limit for large files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path, absolute or relative to the repo root."},
                "offset": {"type": "integer", "description": "1-based first line to read."},
                "limit": {"type": "integer", "description": "Maximum number of lines to read."},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "Grep",
        "description": "Search file contents with a regular expression (ripgrep).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "File or directory to search; defaults to repo root."},
                "glob": {"type": "string", "description": "Filter files, e.g. '*.ts'."},
                "ignore_case": {"type": "boolean"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "Glob",
        "description": "Find files matching a glob pattern, recursively.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "e.g. '**/*.ts'"},
                "path": {"type": "string", "description": "Base directory; defaults to repo root."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "LS",
        "description": "List the entries of a directory.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]

_TOOL_OUTPUT_CAP = 30000  # characters per tool result


def _roots(cwd: str | None, add_dirs: Iterable[str] | None) -> list[Path]:
    out: list[Path] = []
    for d in [cwd, *(add_dirs or [])]:
        if d:
            try:
                out.append(Path(d).resolve())
            except Exception:  # noqa: BLE001
                pass
    if not out:
        out.append(Path.cwd().resolve())
    # de-dupe, preserve order
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        if str(p) not in seen:
            seen.add(str(p))
            uniq.append(p)
    return uniq


def _safe_path(p: str, roots: list[Path]) -> Path:
    raw = Path(p)
    candidates = [raw] if raw.is_absolute() else [root / raw for root in roots]
    for cand in candidates:
        try:
            rp = cand.resolve()
        except Exception:  # noqa: BLE001
            continue
        for root in roots:
            try:
                rp.relative_to(root)
                return rp
            except ValueError:
                continue
    raise PermissionError(f"path {p!r} is outside the allowed roots")


def _truncate(s: str) -> str:
    if len(s) > _TOOL_OUTPUT_CAP:
        return s[:_TOOL_OUTPUT_CAP] + f"\n... [truncated {len(s) - _TOOL_OUTPUT_CAP} chars]"
    return s


def _tool_read(inp: dict, roots: list[Path]) -> str:
    fp = _safe_path(str(inp["file_path"]), roots)
    if not fp.is_file():
        return f"Error: not a file: {inp['file_path']}"
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    offset = int(inp.get("offset") or 1)
    limit = int(inp.get("limit") or len(lines))
    start = max(offset, 1)
    chunk = lines[start - 1 : start - 1 + max(limit, 0)]
    return _truncate("\n".join(f"{start + i:6d}|{ln}" for i, ln in enumerate(chunk)))


def _tool_grep(inp: dict, roots: list[Path]) -> str:
    base = roots[0]
    target = _safe_path(str(inp.get("path") or base), roots)
    cmd = ["rg", "--no-heading", "-n"]
    if inp.get("ignore_case"):
        cmd.append("-i")
    if inp.get("glob"):
        cmd += ["-g", str(inp["glob"])]
    cmd += ["-e", str(inp["pattern"]), str(target)]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return "Error: ripgrep (rg) not available."
    except subprocess.TimeoutExpired:
        return "Error: grep timed out."
    out = cp.stdout or cp.stderr or "(no matches)"
    out = out.replace(str(base) + os.sep, "")
    return _truncate(out)


def _tool_glob(inp: dict, roots: list[Path]) -> str:
    base = _safe_path(str(inp.get("path") or "."), roots)
    matches = sorted(
        str(p.relative_to(base)) for p in base.glob(str(inp["pattern"])) if p.is_file()
    )
    return _truncate("\n".join(matches[:500])) if matches else "(no files)"


def _tool_ls(inp: dict, roots: list[Path]) -> str:
    d = _safe_path(str(inp["path"]), roots)
    if not d.is_dir():
        return f"Error: not a directory: {inp['path']}"
    entries = sorted(e.name + ("/" if e.is_dir() else "") for e in d.iterdir())
    return _truncate("\n".join(entries))


_TOOL_FUNCS = {
    "Read": _tool_read,
    "Grep": _tool_grep,
    "Glob": _tool_glob,
    "LS": _tool_ls,
}


def _run_tool(name: str, inp: dict | None, roots: list[Path]) -> str:
    fn = _TOOL_FUNCS.get(name)
    if fn is None:
        return f"Error: unknown tool {name!r}"
    try:
        return fn(inp or {}, roots)
    except PermissionError as e:
        return f"Error: {e}"
    except Exception as e:  # noqa: BLE001
        return f"Error: {type(e).__name__}: {e}"


def _assistant_content(blocks) -> list[dict]:
    out: list[dict] = []
    for b in blocks:
        if getattr(b, "type", "") == "text":
            out.append({"type": "text", "text": b.text})
        elif getattr(b, "type", "") == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


def _call_sdk(
    *,
    system: str,
    user: str,
    model: str,
    tools_enabled: bool,
    max_turns: int | None,
    timeout_seconds: int,
    add_dirs: Iterable[str] | None,
    cwd: str | None,
) -> CallResult:
    started = time.monotonic()
    family = _family(model)

    def _ms() -> int:
        return int((time.monotonic() - started) * 1000)

    def _cost(u: Usage) -> float:
        try:
            return compute_cost(u, _cfg().pricing_for(family))
        except Exception:  # noqa: BLE001
            return 0.0

    try:
        client = _anthropic_client(timeout_seconds)
        model_id = _resolve_model_id(model)
    except Exception as exc:  # noqa: BLE001
        return CallResult(
            text="", usage=Usage(), cost_usd=0.0, duration_ms=_ms(),
            resolved_model=model, num_turns=0, is_error=True,
            error=f"SDK init failed: {type(exc).__name__}: {exc}",
        )

    # Every review is a brand-new conversation: a fresh client, a fresh
    # message list, no prompt caching, no server-side session. Nothing from a
    # previous review (or a previous trial) can influence this one.
    messages: list[dict] = [{"role": "user", "content": user}]
    roots = _roots(cwd, add_dirs)
    tools = _SDK_TOOLS if tools_enabled else None
    max_turns_eff = max_turns if max_turns else (40 if tools_enabled else 1)

    total = Usage()
    turns = 0
    last_text = ""
    resolved = model_id

    try:
        while True:
            turns += 1
            kwargs: dict[str, Any] = {
                "model": model_id,
                "system": system,
                "messages": messages,
                "max_tokens": _max_output_tokens(family),
            }
            if tools:
                kwargs["tools"] = tools
            resp = client.messages.create(**kwargs)
            total = add_usage(total, usage_from_anthropic(resp.usage))
            resolved = getattr(resp, "model", None) or resolved
            texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            if texts:
                last_text = "\n".join(texts)

            if tools and resp.stop_reason == "tool_use" and turns < max_turns_eff:
                messages.append({"role": "assistant", "content": _assistant_content(resp.content)})
                tool_results = [
                    {
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": _run_tool(b.name, b.input, roots),
                    }
                    for b in resp.content
                    if getattr(b, "type", "") == "tool_use"
                ]
                messages.append({"role": "user", "content": tool_results})
                continue
            break
    except Exception as exc:  # noqa: BLE001
        return CallResult(
            text=last_text, usage=total, cost_usd=_cost(total), duration_ms=_ms(),
            resolved_model=resolved, num_turns=turns, is_error=True,
            error=f"{type(exc).__name__}: {exc}",
        )

    return CallResult(
        text=last_text, usage=total, cost_usd=_cost(total), duration_ms=_ms(),
        resolved_model=resolved, num_turns=turns, is_error=False,
    )


# ---------------------------------------------------------------------------
# Fenced JSON extraction (used by single-shot versions)
# ---------------------------------------------------------------------------


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def extract_fenced_json(text: str) -> dict | None:
    """Pull a JSON object out of a model response.

    Tries, in order:
      1. The last ```json ... ``` fenced block
      2. The last ``` ... ``` fenced block (anything)
      3. The whole response, if it parses
      4. The longest brace-balanced substring

    Returns the parsed object, or None if nothing parses.
    """

    text = text or ""
    candidates: list[str] = []

    blocks = _FENCED_JSON_RE.findall(text)
    candidates.extend(reversed(blocks))   # prefer the LAST fenced block
    candidates.append(text.strip())       # bare JSON case

    for raw in candidates:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    # Brace-balanced fallback
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        pass
                    break
        start = text.find("{", start + 1)

    return None


# ---------------------------------------------------------------------------
# CLI for quick smoke tests
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Smoke-test the claude CLI wrapper")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Reply with the JSON {\"ok\":true} inside a ```json fenced block.",
    )
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--system", default="You are a helpful assistant. Reply concisely.")
    parser.add_argument("--tools", action="store_true")
    args = parser.parse_args(argv)

    result = call(
        system=args.system,
        user=args.prompt,
        model=args.model,
        tools_enabled=args.tools,
    )

    sys.stderr.write(
        f"model={result.resolved_model} turns={result.num_turns} "
        f"in={result.usage.input_tokens} cache_w={result.usage.cache_creation_input_tokens} "
        f"cache_r={result.usage.cache_read_input_tokens} out={result.usage.output_tokens} "
        f"cost=${result.cost_usd:.4f} t={result.duration_ms}ms\n"
    )
    if result.is_error:
        sys.stderr.write(f"ERROR: {result.error}\n")
        return 1

    print(result.text)
    fenced = extract_fenced_json(result.text)
    if fenced is not None:
        sys.stderr.write(f"\nExtracted JSON: {json.dumps(fenced)[:200]}\n")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
