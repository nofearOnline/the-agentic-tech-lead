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

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Iterable

from .cost import Usage


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
) -> CallResult:
    """Run a single non-interactive Claude call.

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


def _envelope_to_result(envelope: dict, *, model_alias: str) -> CallResult:
    usage_raw = envelope.get("usage") or {}
    usage = Usage(
        input_tokens=int(usage_raw.get("input_tokens") or 0),
        cache_creation_input_tokens=int(usage_raw.get("cache_creation_input_tokens") or 0),
        cache_read_input_tokens=int(usage_raw.get("cache_read_input_tokens") or 0),
        output_tokens=int(usage_raw.get("output_tokens") or 0),
    )
    model_usage = envelope.get("modelUsage") or {}
    resolved_model = next(iter(model_usage.keys()), model_alias)

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
