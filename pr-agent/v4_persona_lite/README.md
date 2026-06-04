# v4 — the persona bundle, made cheap

**The version the talk lands on.** The benchmark matrix showed **v3** (four
reviewer personas bundled into one call) is the quality winner. So the
governance move is not "add more agents." It's: **take the architecture that
already won and make it cheaper.** v4 is that move.

## What it is

v4 is *exactly* v3 with **one knob changed: the model tier.**

| | v3 (`v3_persona_bundle`) | v4 (`v4_persona_lite`) |
| --- | --- | --- |
| personas | 4, bundled into one system prompt | same (imported verbatim) |
| architecture | single call, no tools, diff-only | same |
| JSON contract + parsing | shared | same (imported verbatim) |
| **model** | **`generalist` (Sonnet)** | **`tier1` (Haiku)** |

Everything except the model is imported directly from `v3_persona_bundle`, so a
v3-vs-v4 comparison is a clean read on the closing question: *did the win come
from the architecture or from the spend?*

## Why it's the ending

- **Frontier of two, same design.** Plot cost vs. F1 across every version and
  only v4 (cheap: ~$0.066, F1 0.88) and v3 (premium: $0.29, F1 0.96) survive on
  the frontier — the *same* persona architecture, twice. You pick by budget.
- **Composition is the value, not the spend.** On Haiku, v4 still goes 3/3 on
  `jwt-secret-fallback` (the diff-only generalist: 0/3) and 3/3 on the webhook
  SSRF issue v3-on-Sonnet mostly misses. The personas surface the issue class;
  the expensive model is not what's doing the work.
- **The right cost lever.** Dial the *model* down, not the agent count.
- **Honest tax:** Haiku is more stochastic on small diffs (PR#1 swung F1
  0.62↔0.97). A real budget deploy pairs v4 with best-of-n voting (still cheaper
  than one v3 call) or a deterministic false-positive guard.

## Run it

```bash
# single PR
python v4_persona_lite/review.py 1 --json

# in the eval matrix
python bench/run_eval.py --version v4_persona_lite
```

Tune the model in `config.yaml` (`models.tier1`). See `bench/results/` and
`presentation/comparison.md` for how v4 lands against v1–v3.

## Archived experiments

The other direction — *spend up*: parallel persona agents + an Opus skeptic
(`v4_parallel_personas`) and a tiered variant of it (`v5_tiered`) — is kept on
disk but **out of the ladder**. Those builds cost more and scored lower; they're
retained as evidence for the "complexity must earn its cost" point, not as rungs.
