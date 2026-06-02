# v5 — tiered personas + skeptic (the cheap one)

The demo's punchline. [v4](../v4_parallel_personas/) proved the multi-agent shape
(four parallel persona agents + an Opus skeptic) but cost **~$2.31** on PR #3 —
a cost ceiling. v5 keeps that architecture **unchanged in shape** and matches its
quality at a fraction of the cost, using two ideas straight from the HoneyBook
blog — *without* throwing the personas or the skeptic away.

## The two cost levers

### A. A deterministic pre-phase (zero inference, <1s)

Plain Python over the PR's changed paths + diff text, before any model runs:

- **Persona gating.** Each persona has a trigger vocabulary describing the
  surface its lens needs. `security_hawk` needs auth/crypto/secret/network/
  SQL/eval/PII signal; `perf_skeptic` needs data-access/loops/queries/IO;
  `kiss_zealot`/`quality_critic` are general code-structure lenses that fire on
  any executable change. A persona with **no** matching signal is **dropped** —
  that removes a whole LLM call. Broad PRs keep everyone; narrow PRs (a pure
  `.env` change, a CSS-only diff) drop most of the panel. A safety net keeps all
  four if the prefilter would otherwise drop everyone. Every keep/drop decision
  is logged to stderr.

- **Skeptic-input pre-clustering.** After stage 1, findings that share
  `(file, line_start, category)` are collapsed into one representative entry
  (longest message wins) carrying a `raised_by` list of every persona behind it.
  The expensive Opus skeptic then reads the **clustered** pool (with each
  message truncated to a preview) instead of the raw union, and merges further
  across clusters.

- **Edit-list skeptic (the big Opus lever).** v4's Opus skeptic *re-authored*
  every surviving finding in full prose — the single most expensive thing in the
  pipeline at `$75/1M` output. v5 keeps Opus as the arbiter but asks it only for
  an **edit list**: which cluster ids to `drop`, which to `merge`, which to
  re-`severity`. Every other cluster is kept by default, and the final finding
  text is reused **verbatim from the cheap Haiku findings**. Opus still does all
  the judging (pruning false positives, collapsing duplicates, fixing severity);
  it just stops paying frontier output rates to retype text the panel already
  wrote. Reconstruction happens deterministically in Python, with a fallback to
  the de-duplicated pool if the edit list is unusable.

### B. Tier the models by job

The blog's rule — *"Haiku for breadth, Sonnet for synthesis, Opus only as the
skeptic"*:

| Stage | v4 | v5 | Why |
|-------|----|----|-----|
| Stage 1 — persona breadth agents | `specialist_reasoning` (sonnet) | **`specialist_narrow` (haiku)** | Breadth/pattern work doesn't need a frontier model; ~3× cheaper per token. The dominant per-call saving. |
| Stage 2 — skeptic | `skeptic` (opus) | `skeptic` (opus) — **kept** | Pruning/arbitration is where frontier capability pays off ("let the smartest agent prune"). Fed the pre-clustered pool *and* asked only for an edit list, so it reads and writes far less. |

## Pipeline

```
            Phase 0 — deterministic prefilter (no inference)
            ├─ gate personas on trigger signal in the diff
PR diff ───▶├─ keep:  security_hawk, perf_skeptic, kiss_zealot, quality_critic
            └─ drop:  any persona with no surface for its lens
                 │
                 ▼ (kept personas only)
        ┌────────────────────────────┐
   ┌───▶│ security_hawk   (haiku)    │──┐
   ├───▶│ perf_skeptic    (haiku)    │──┤
   ├───▶│ kiss_zealot     (haiku)    │──┤  pooled findings
   └───▶│ quality_critic  (haiku)    │──┘  (dupes + FPs OK)
        └────────────────────────────┘     │
             Stage 1 — parallel            ▼
                                  ┌───────────────────────┐
                                  │ pre-cluster pool       │ (no inference)
                                  │ same file+line+cat → 1 │
                                  └───────────────────────┘
                                            │ smaller pool
                                            ▼
                                  ┌──────────────────────────┐
                                  │ skeptic (opus)           │  emits EDIT LIST
                                  │ drops / merges / severity │  (not re-authored prose)
                                  └──────────────────────────┘
                                            │ apply edits in Python
                                            ▼  (final text reused from haiku)
                                 final findings + agreement tags
```

`tools_enabled=False` throughout — diff-only, same axis as v1/v3/v4. Persona
attribution (`source`) and the skeptic's `extra.raised_by` / `extra.skeptic`
agreement metadata are preserved exactly as in v4.

## Errors & resilience (inherited from v4)

- A persona agent errors → skip it, still run the skeptic on what came back.
- The skeptic errors → fall back to the de-duplicated stage-1 pool
  (`extra.skeptic = "fallback-dedup"`).
- Transient socket / rate errors (EADDRNOTAVAIL, reset, 429/529) → ~30s backoff,
  up to 2 retries per call.
- All kept agents fail in parallel → retry once sequentially.

## Reported metrics

- `num_turns` = total calls actually made (≤ kept personas + 1 skeptic).
- `cost_usd` = **sum** across every call.
- `usage` = summed `Usage` via `shared.cost.sum_usage`.
- `duration_ms` = wall-clock for the whole review.

A `[cost] prefilter(personas kept) stage1 stage2 total` line is written to
stderr at the end of every run.

## Run it

```bash
cd pr-agent && source .venv/bin/activate

# via the eval harness (scored against ground truth)
python -m bench.run_eval --version v5_tiered --pr 3 --trials 1

# standalone CLI
python v5_tiered/review.py 3
python v5_tiered/review.py 3 --json
```

> On a broad PR like #3 the prefilter honestly keeps all four personas (auth +
> admin + webhooks touches every lens), so v5's saving there comes from the
> Haiku tiering and the leaner Opus skeptic (edit list + terse pool) — not the
> gating. The gating's payoff shows on narrow PRs, where it deletes whole calls.
>
> Note on the cache seam: `shared.call` shells out to the `claude` CLI once per
> agent, so the diff is paid as cache-*write* input on all five calls (there is
> no cross-call prompt-cache prefix sharing). That is a structural floor on how
> cheap this CLI-backed pipeline can get; an SDK backend that shares a cached
> diff prefix across specialists would push the multiple higher still.
