# v4 — parallel personas + skeptic

The "we got greedy" multi-agent version. Where [v3](../v3_persona_bundle/) put all
four reviewer personas in one prompt and made a single call, v4 gives **each
persona its own agent** and runs them in parallel, then adds a **skeptic** pass
to prune the noise.

This mirrors the moment in the HoneyBook blog where they stopped concatenating
personas and ran one agent per reviewer, then let the smartest model prune false
positives. v4 is intentionally the *powerful but expensive* shape — it sets up
v5, which makes the same idea cheap via tiering. **v4 does not cost-optimize.**

## Pipeline

```
                   ┌────────────────────────────┐
  PR diff ───┬────▶│ security_hawk   (sonnet)    │──┐
             ├────▶│ perf_skeptic    (sonnet)    │──┤
             ├────▶│ kiss_zealot     (sonnet)    │──┤  pooled findings
             └────▶│ quality_critic  (sonnet)    │──┘  (dupes + FPs OK)
                   └────────────────────────────┘     │
                        Stage 1 — parallel            ▼
                                              ┌──────────────────┐
                                              │ skeptic  (opus)  │  filter + merge
                                              └──────────────────┘
                                                       │
                                                       ▼
                                           final findings + agreement tags
                                                  Stage 2 — 1 call
```

### Stage 1 — parallel persona agents (4 concurrent calls)

- One `shared.call(...)` **per persona**, each on `specialist_reasoning` (sonnet).
- Each agent's system prompt contains **only that one persona's profile** + the
  output contract — it reviews the full PR diff through a single lens and stamps
  every finding `source=<persona_id>`.
- The four calls run concurrently via `ThreadPoolExecutor(max_workers=4)`
  (`shared.call` is a blocking subprocess, so threads parallelize cleanly).
- `tools_enabled=False` — diff-only, same axis as v1/v3. (Repo/agentic access
  was v2's dimension.)
- All findings are pooled. Duplicates, overlaps, and false positives are
  **expected** here — that's the skeptic's job.

### Stage 2 — skeptic pass (1 call)

- One `shared.call(...)` on `skeptic` (opus).
- Gets the diff + the full pooled stage-1 findings as JSON (each tagged with its
  `source` persona).
- It drops false positives / over-broad matches, **merges** duplicates that
  several personas raised into one finding, and — when multiple personas
  independently flagged the same thing — **keeps** it as high-confidence.
- Agreement is recorded on each surviving finding in `extra`:
  - `extra.raised_by`: every persona id that flagged the issue.
  - `extra.skeptic`: `"kept"` (single-persona, validated) or `"merged"`
    (collapsed from several personas).
- `source` always preserves the originating persona (for a merged finding, the
  most relevant / first one; the rest live in `extra.raised_by`).

The skeptic's filtered/merged list is what v4 returns.

## Errors & resilience

- **A persona agent errors** → skip it, still run the skeptic on whatever came
  back.
- **The skeptic errors** → fall back to returning the de-duplicated stage-1 pool
  (`extra.skeptic = "fallback-dedup"`).
- **Transient socket / rate errors** (EADDRNOTAVAIL, connection reset, 429/529)
  → short backoff + retry, up to 3 attempts per call.
- **All four agents fail in parallel** → retry once sequentially before giving
  up (concurrent subprocess launches are the usual culprit).

## Reported metrics

For this multi-call version:

- `num_turns` = total calls made (≤ 4 persona agents + 1 skeptic).
- `cost_usd` = **sum** across every call actually made.
- `usage` = summed `Usage` via `shared.cost.sum_usage`.
- `duration_ms` = wall-clock for the whole review (parallel stage included).

## Run it

```bash
cd pr-agent && source .venv/bin/activate

# via the eval harness (scored against ground truth)
python -m bench.run_eval --version v4_parallel_personas --pr 3 --trials 1

# standalone CLI
python v4_parallel_personas/review.py 3
python v4_parallel_personas/review.py 3 --json
```

> One PR #3 run makes ~5 real `claude` calls (4 sonnet + 1 opus) on a ~700-line
> diff — the most expensive version so far (~$1–2). That cost is the point: it's
> the setup for v5's savings.
