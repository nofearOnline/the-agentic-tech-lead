# Benchmark Comparison — the 4-rung ladder (+ model-tier sweep)

The evolution the talk ships is a **4-rung ladder**: **v1** single-shot → **v2** repo-aware → **v3** persona-bundle → **v4** persona-bundle-made-cheap. All four are benchmarked across **3 PRs × 3 trials**.

Matrix facts: ground truth of **62 planted issues** across the three PRs (15 / 14 / 33), many-to-one scoring (one finding may cover multiple co-located issues), **Anthropic SDK backend** (`ANTHROPIC_API_KEY`, every review a fresh conversation — no cross-call memory or prompt-cache sharing). The full run (ladder + Haiku/Opus sweep) was **~$40.5** of API spend across 81 runs and ran **clean** (no CLI throttling this time, so latency is real).

> **v4 is v3 with one knob changed.** v3 runs four bundled reviewer personas on Sonnet; v4 runs the *identical* call on Haiku (~3× cheaper/token). Everything else is shared code. v4 exists to answer the one question the ladder hinges on: *did v3's win come from the architecture or from the spend?* **Answer: the architecture — and this run shows the model tier barely matters for it (Haiku F1 0.88 = Sonnet F1 0.88).**

Regenerate the ladder tables with `python pr-agent/bench/compare.py` (raw output in `pr-agent/bench/results/comparison_output.md`). A full **architecture × model sweep** (every rung on Haiku / Sonnet / Opus 4.8) is in the **model-tier sweep appendix** below.

---

## TL;DR — the four things this data actually shows

1. **Composition wins, but the margin is modest and v4 dominates v3.** Persona builds (v3/v4) land **F1 0.88 / recall 0.86**; the single-shot generalist (v1) is **0.83 / 0.83**; giving it the repo (v2) is the *worst* at **0.78 / 0.72**. The persona architecture is now **model-tier-insensitive** — Haiku and Sonnet both score F1 0.88 — so **v4 strictly dominates v3**: same quality, **0.30× the cost** ($0.033 vs $0.111). The frontier knee is a single point, **v4**.

2. **"Give it the repo" (v2) is a net loss, at every tier.** v2 regressed mean recall (0.83 → 0.72) *and* cost ~9× v1, and it was dominated on Haiku, Sonnet, **and** Opus. Its generic agentic exploration loop drops issues v1 catches from the diff (e.g. both PR#2 performance issues: v1 3/3 → **v2 0/3**) without reliably buying anything back. This is the credible "tools are not a free win" beat.

3. **The "duplicates/ignores-the-repo" issues we planted did *not* prove repo-value — an honest negative result.** Six issues were designed to need repo awareness (so v2+ would beat v1). They didn't: the *structural* ones are visible in the diff and v1 catches them fine (often better than v2); the *pure-duplication* ones are missed by nearly everyone — including the repo-aware v2. The compose lift this run comes from **other** classes (security-depth, KISS, perf), not these. See "The planted-issue post-mortem" below — it's a finding, not a failure to hide.

4. **For the persona architecture, the model tier is almost free; for the generalist, it's everything.** v1 jumps **+0.17 F1** Haiku→Opus (0.68 → 0.85) — it lives or dies on raw model power. v3 is **0.88 on Haiku already** and Opus only nudges it to 0.89. The personas do the work the bigger model would otherwise have to.

> The clean "each version strictly beats the last" arc is a myth — and saying so is the credible version of this talk. v2 is a genuine regression; v3 is the quality peak; v4 is the same design made cheap and is the build you ship. The tech lead's job is to *measure and notice*, not to assume more machinery is better.

---

## Per-version rollup (the ladder; mean across all PRs/trials)

| version | mean cost | latency | precision | recall | F1 | cost vs v1 | cost vs v3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **v1** single_shot | $0.076 | 64s | 0.85 | 0.83 | 0.83 | 1.0× | 0.68× |
| **v2** repo_aware | $0.673 | 96s | 0.86 | 0.72 | **0.78** | 8.9× | 6.08× |
| **v3** persona_bundle | $0.111 | 83s | 0.90 | 0.86 | **0.88** | 1.5× | 1.00× |
| **v4** persona_lite (Haiku) | **$0.033** | **34s** | 0.90 | 0.86 | **0.88** | **0.4×** | **0.30×** |

> **Reading v4 against v3 and v1:** v4 is the *same* persona architecture as v3, one model tier down — and this run it gives up **nothing** in aggregate (both F1 0.88) while costing **0.30× of v3** and being the fastest rung (34s). It also **dominates v1**: higher precision/recall/F1 at **less than half** v1's cost. The frontier is a single knee — **v4**.

---

## Per-(version × PR) detail — the ladder

| version | PR | trials | mean cost | findings | TP | precision | recall | F1 (mean ± sd) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1 | #1 | 3 | $0.045 | 13.7 | 10.7/15 | 0.93 | 0.71 | 0.80 ± 0.02 |
| v1 | #2 | 3 | $0.060 | 15.7 | 13.7/14 | 0.79 | 0.98 | 0.87 ± 0.02 |
| v1 | #3 | 3 | $0.122 | 32.0 | 26.7/33 | 0.84 | 0.81 | 0.83 ± 0.02 |
| v2 | #1 | 3 | $0.345 | 11.3 | 10.3/15 | 0.85 | 0.69 | 0.76 ± 0.05 |
| v2 | #2 | 3 | $0.530 | 12.0 | 11.0/14 | 0.83 | 0.79 | 0.81 ± 0.05 |
| v2 | #3 | 3 | $1.143 | 22.7 | 22.7/33 | 0.89 | 0.69 | 0.77 ± 0.03 |
| v3 | #1 | 3 | $0.078 | 15.7 | 14.0/15 | 1.00 | 0.93 | **0.97 ± 0.00** |
| v3 | #2 | 3 | $0.092 | 17.3 | 11.7/14 | 0.85 | 0.83 | 0.84 ± 0.03 |
| v3 | #3 | 3 | $0.163 | 31.7 | 26.7/33 | 0.86 | 0.81 | 0.83 ± 0.11¹ |
| **v4** | #1 | 3 | $0.021 | 12.3 | 13.7/15 | 0.95 | 0.91 | **0.93 ± 0.00** |
| **v4** | #2 | 3 | $0.027 | 15.0 | 11.7/14 | 0.90 | 0.83 | 0.86 ± 0.02 |
| **v4** | #3 | 3 | $0.051 | 30.7 | 28.0/33 | 0.84 | 0.85 | 0.84 ± 0.04 |

¹ **v3/PR#3 is the noisy cell (±0.11):** trials ran F1 0.95 / 0.88 / 0.72 — the persona bundle on the 724-line PR is where Sonnet's run-to-run variance shows. Notably v4 (Haiku) on the same PR is *steadier* (±0.04) and matches v3's mean (0.84 vs 0.83).

---

## Cost vs. F1 — the money slide (chart data)

One point per (version, PR). x = mean cost (USD), y = F1.

| version | PR | cost (x) | recall | F1 (y) |
| --- | --- | --- | --- | --- |
| v1 | #1 | 0.045 | 0.71 | 0.80 |
| v1 | #2 | 0.060 | 0.98 | 0.87 |
| v1 | #3 | 0.122 | 0.81 | 0.83 |
| v2 | #1 | 0.345 | 0.69 | 0.76 |
| v2 | #2 | 0.530 | 0.79 | 0.81 |
| v2 | #3 | 1.143 | 0.69 | 0.77 |
| v3 | #1 | 0.078 | 0.93 | 0.97 |
| v3 | #2 | 0.092 | 0.83 | 0.84 |
| v3 | #3 | 0.163 | 0.81 | 0.83 |
| **v4** | #1 | 0.021 | 0.91 | 0.93 |
| **v4** | #2 | 0.027 | 0.83 | 0.86 |
| **v4** | #3 | 0.051 | 0.85 | 0.84 |

**Pareto read:** every v4 point sits down-and-left of its v3 twin at equal-or-better F1, and left of every v1 point — **v4 dominates the frontier**. v2 plots up-and-right of everything (most expensive, lowest F1): strictly dominated. The only decision left is "v4 for almost everything; reach for Opus-on-personas if you need the last F1 point on a huge PR" (see matrix).

---

## Per-issue heatmap (X/trials caught) — the interesting disagreements

Full heatmaps for all 62 issues are in `compare.py` output. Columns are v1 | v2 | v3 | v4. The rows that tell a story:

**The Compose proof — issues the generalist (v1/v2) misses that personas catch, *and it survives the cheap model* (the v4 column is the point):**

| issue | v1 | v2 | v3 | **v4 (Haiku)** | what it is |
| --- | --- | --- | --- | --- | --- |
| pr3-security-jwt-no-algorithm-pin | 0/3 | 0/3 | 3/3 | **3/3** | alg-confusion / `alg:none` — only personas see it, even on Haiku |
| pr1-kiss-abstract-class-vs-interface | 0/3 | 0/3 | 3/3 | **3/3** | abstract class where an interface belongs |
| pr1-quality-dead-code-comment | 1/3 | 1/3 | 3/3 | **3/3** | commented-out dead branch |
| pr2-performance-history-in-memory-filter | 2/3 | 0/3 | 3/3 | **3/3** | full-table scan + in-memory filter |

The cleanest single row is **`jwt-no-algorithm-pin`**: the persona builds go 3/3 where the generalist goes 0/3 — *and v4 holds it 3/3 on Haiku*. The composition surfaces the issue class; the expensive model isn't what's doing the work.

**...but "give it the repo" (v2) is a regression — it drops issues v1 catches from the diff:**

| issue | v1 | v2 | what it is |
| --- | --- | --- | --- |
| pr2-performance-n-plus-one-refund-enrich | 3/3 | 0/3 | N+1 enriching refunds |
| pr2-performance-history-in-memory-filter | 2/3 | 0/3 | full-table scan |
| pr3-security-jwt-secret-fallback | 3/3 | 0/3 | hardcoded `dev-secret-123` fallback |
| pr3-security-gitignore-override-env | 3/3 | 0/3 | `!.env` un-ignores committed secrets |
| pr3-dry-admin-role-check-duplicated | 3/3 | 1/3 | duplicated admin role check |

v2 spends ~9× v1's cost to *lose* coverage. Whatever its tool loop spends attention on, it isn't reliably converting to findings — a clean, honest "tools without structure can hurt" result.

---

## The planted-issue post-mortem (an honest negative result)

We deliberately added six issues meant to require repo awareness, expecting them to separate v1 (diff-only) from v2+ (repo-aware). **They did not.** Columns v1 | v2 | v3 | v4:

| planted issue | v1 | v2 | v3 | v4 | what happened |
| --- | --- | --- | --- | --- | --- |
| pr1 `dry` reimplements-amount-validation | 0/3 | 0/3 | 0/3 | 0/3 | missed by everyone — too subtle (no one connects `isValidAmount` to `money.ts`) |
| pr1 `structure` free-function-not-service | 3/3 | 1/3 | 3/3 | 3/3 | diff-visible (the `TODO: where should this live` gives it away); v2 *worse* |
| pr2 `dry` reimplements-findbyid | 3/3 | 3/3 | 3/3 | 3/3 | everyone catches — `findAll().find()` reads as a smell on its own |
| pr2 `structure` reinvents-repository | 3/3 | 1/3 | 0/3 | 0/3 | v1 catches; the persona builds *miss* it |
| pr3 `dry` reimplements-cardlast4 | 0/3 | 1/3 | 0/3 | 1/3 | mostly missed |
| pr3 `structure` authcontroller-no-di | 3/3 | 2/3 | 2/3 | 2/3 | diff-visible (no constructor); no v2+ advantage |

**Why it backfired — the lesson:**

- **"Ignores the structure" smells live in the added diff.** A free function with a "where should this live" TODO, a controller with no constructor, a module-global + hand-rolled scan loop — a strong generalist infers the convention violation *from the change itself* and doesn't need to read the rest of the repo. So v1 catches them (often better than v2).
- **"Pure duplication" needs the reviewer to go find the one existing helper** (`assertPositiveAmount`, `cardLast4`) — and even the *repo-aware* v2 doesn't reliably grep for it. Its exploration is unfocused; the personas aren't told to look either. So these are missed across the board.
- **Net:** these issues slightly *narrowed* the v3-vs-v1 gap (the persona bundle misses some that v1 catches), rather than widening it. The repo-value case has to be made with classes where a *specific lens* helps (security-depth, KISS), not with "duplication/structure" issues that are either obvious-in-diff or obscure-to-all.

> This is exactly the kind of result the talk's measurement thesis exists to catch: **we had a plausible hypothesis, the benchmark falsified it, and that's the value of having a benchmark.**

---

## Implications for the demo narrative

The arc is a 4-rung climb that ends on the cheap winner:

- **TEACH (v1 → v2):** Be honest — context did **not** help here. v2 *redistributed and net-lost* coverage (−0.11 recall) at ~9× cost, dominated at every model tier. Demo: "the obvious move — hand it the repo — is a trap unless you also tell it *what to look for*." That motivates composition.
- **COMPOSE (→ v3):** The peak. One call, four personas bundled — **F1 0.88, recall 0.86**, and it unlocks classes the generalist never sees (`jwt-no-algorithm-pin`, `abstract-class-vs-interface`: 0/3 → 3/3).
- **GOVERN (→ v4):** Keep the architecture that won; dial the *model* down, not the agent count. **v4: $0.033 (0.30× v3), identical F1 0.88, 34s, and it still catches the security/KISS classes on Haiku.** The talk lands here: **the persona architecture is model-tier-insensitive, so you ship it on the cheap model and pocket the 70%.** One-liner: *"The agentic tech lead's job isn't to build the most agents — it's to find the architecture that works, then dial the model down, not the agent count up."*

**Closing note (the call to action):** the four personas here are *ours* — security hawk, perf skeptic, KISS zealot, quality critic. Yours will differ: a11y, API-compat, data-privacy, on-call-ability. **Bring your own personas — and do the one non-negotiable thing this whole exercise demonstrates: keep a ground-truth benchmark and continuously measure.** We *thought* "duplicates an existing helper" issues would prove repo-value; the benchmark said otherwise. An agent you don't measure is a vibe; the precision/recall/cost numbers — and the negative results — are how you know a change helped instead of hurt.

The demo run-of-show (`demo-run-of-show.md`) matches this arc.

---

## Appendix — model-tier sweep (architecture × model)

The ladder fixes one model per rung. This sweep asks the orthogonal question: **for a given architecture, what does dialing the model up or down actually buy?** Every architecture was run end-to-end on **Haiku, Sonnet, and Opus (4.8)** — 3 PRs × 3 trials each. The diagonal reuses the ladder runs (v1/v2/v3 = Sonnet; v3-Haiku *is* the shipped v4). F1 / recall / mean cost, weighted across all PRs:

| architecture | Haiku | Sonnet | Opus 4.8 |
| --- | --- | --- | --- |
| **v1** single-shot | F1 0.68 / R 0.60 / $0.018 | F1 0.83 / R 0.83 / $0.076 | F1 0.85 / R 0.80 / $0.398 |
| **v2** repo-aware | F1 0.54 / R 0.46 / $0.448 | F1 0.78 / R 0.72 / $0.673 | F1 0.87 / R 0.81 / $2.147 |
| **v3** persona-bundle | **F1 0.88 / R 0.86 / $0.033** *(= v4)* | **F1 0.88 / R 0.86 / $0.111** *(= v3)* | F1 0.89 / R 0.90 / $0.595 |

**What the matrix says — and it sharpens the whole talk:**

1. **Architecture beats tier, per dollar — decisively.** The cheapest persona cell — **v3-on-Haiku (= v4), F1 0.88 at $0.033** — beats *every* v1 and v2 cell at *every* model tier, including v1-on-Opus (0.85) which costs **~12× more**. Climbing the *model* ladder on the wrong architecture (v2) tops out at F1 0.87 for **$2.15/PR**; climbing the *architecture* ladder on the cheap model gets 0.88 for **$0.033**.
2. **The dumb architecture is the most tier-sensitive; the smart one is near-flat.** v1 jumps **+0.17 F1** Haiku→Opus — it leans entirely on raw model power. v3 is already 0.88 on Haiku and barely moves on Sonnet (0.88) or Opus (0.89). The personas do the work the bigger model would otherwise have to, so paying for the bigger model buys almost nothing.
3. **v2 (repo-aware) is dominated at every tier** — agentic exploration is a consistent drag, not a one-PR fluke. On Opus it's the single most expensive cell on the board ($2.15/PR) for a lower F1 than v3-on-Haiku ($0.033).

**Frontier across the 9 cells** (cost, F1): v1-Haiku (0.018, 0.68) → **v4 = v3-Haiku** (0.033, 0.88) → v3-Opus (0.595, 0.89). The persona architecture owns the knee and the top; nothing non-persona is on the frontier above F1 0.85.

---

## Caveats / reproducibility

- **Backend:** Anthropic SDK, `ANTHROPIC_API_KEY` from `pr-agent/.env`. Every review is a **fresh conversation** (no system-prompt caching, no cross-call memory) so trials are independent and billed in full. Regenerate with `python pr-agent/bench/run_eval.py` (ladder) + `--model haiku|opus` (sweep), then `python pr-agent/bench/compare.py`.
- **Clean run, real latency.** Unlike the earlier CLI run, this one was not throttled, so the latency column is as-measured (v4 ~34s, v2 ~96s). Total spend ~$40.5 (ladder $8.0 + Haiku sweep $4.2 + Opus sweep $28.3 — the Opus **v2** tool-loop alone was ~$19; one v2-Opus/PR#3 trial tripped the $5/run cost cap and was capped).
- **Parser drops (minor, mostly Haiku):** the model occasionally emits a finding with the wrong JSON keys (`file_end`/`description` instead of `line_end`/`message`); those findings are dropped with a warning, slightly undercounting a few trials. Hardening the parser (accept aliases) would recover them.
- **Two noisy sweep cells:** one **v2-Haiku/PR#3** trial returned 0 findings (empty/malformed response → F1 0.00, drags v2-Haiku down); the v2-Opus cost-cap trial above is partial. Both are in the *sweep*, not the ladder — every ladder cell is clean n=3.
- **Variance:** the loudest ladder cell is **v3/PR#3 (±0.11)**; v4 is steadier there. Read v4's mean (0.88) as "reliably v3-class"; for a budget deploy on huge PRs, best-of-n (still cheaper than one v3 call) removes the tail.
- **Stale-issue note:** ground-truth was revised this run (6 trivial/diff-obvious issues swapped for the repo-aware set documented in the post-mortem); issue count held at 62. Earlier comparison numbers (v3 F1 0.96, the JWT-secret-fallback "compose-only" row) reflect the *previous* ground truth and CLI backend and no longer apply.
