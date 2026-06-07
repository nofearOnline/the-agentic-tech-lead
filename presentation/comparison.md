# Benchmark Comparison — the 4-rung ladder (+ archived experiments)

The evolution the talk ships is a **4-rung ladder**: **v1** single-shot → **v2** repo-aware → **v3** persona-bundle → **v4** persona-bundle-made-cheap. All four are benchmarked across **3 PRs × 3 trials**. Two earlier experiments that spent *up* the complexity curve (parallel persona agents + an Opus skeptic, and a tiered variant of it) are **archived out of the ladder** — kept on disk as evidence, summarized in the appendix.

Matrix facts: 53 trials counted across all six builds (one archived-parallel/PR#3 trial excluded as a throttle casualty — see appendix), ground truth of **62 planted issues** across the three PRs (15 / 14 / 33), many-to-one scoring (one finding may cover multiple co-located issues), `claude` CLI backend, total counted spend **$16.72**.

> **v4 is v3 with one knob changed.** v3 runs four bundled reviewer personas on Sonnet; v4 runs the *identical* call on Haiku (~20× cheaper/token). Everything else is shared code. v4 exists to answer the one question the ladder hinges on: *did v3's win come from the architecture or from the spend?* **Answer: the architecture.**

Regenerate the ladder tables with: `python pr-agent/bench/compare.py` (archived builds are excluded by default; pass `--version v4_parallel_personas` etc. to see them). A full **architecture × model sweep** (every rung on Haiku / Sonnet / Opus 4.8, +$8.3) is in the **model-tier sweep appendix** below — it confirms the headline: composition is the cheaper lever, and reaches an issue class even Opus alone misses.

---

## TL;DR — the three things this data actually shows

1. **The cost/quality frontier is exactly two points — and they're the same architecture.** Plot cost vs. F1 and only **v3** (personas on Sonnet: **F1 0.96 for $0.29**) and **v4** (the *same* personas on Haiku: **F1 0.88 for $0.066**) survive on the frontier. Everything else is dominated — including v1, which v4 beats on cost at equal F1. The headline: **composition is the frontier; the model tier is just where you choose to sit on it.**
2. **Composition is the value, not the spend.** v4 proves it: the persona *architecture* on a ~20×-cheaper model still unlocks the security class the generalist never sees (`jwt-secret-fallback` **0/3 for v1/v2 → 3/3 for v4**), and on the *hardest* PR (#3) it nearly ties v3 (0.89 vs 0.91) at **1/6 the cost**. The right cost lever is **dial the model down (v3 → v4)**, not add agents up (see appendix — that direction cost ~2.5× more and scored *lower*).
3. **"Give it the repo" (v2) is not a free win, and cheap has a variance tax.** v2 *redistributed* coverage (caught context-dependent issues v1 missed) but **regressed mean recall 0.84 → 0.79** — context is a trade. And v4's Haiku tier buys its low price with **variance** (PR#1 F1 ±0.20: one false-positive-storm trial), which is why a budget deploy wants n>1 / a cheap guard.

> The clean "each version strictly beats the last" arc is a myth — and saying so is the credible version of this talk. v3 is the quality peak; v4 is the same design made cheap; the fancier builds we tried (appendix) lost. The tech lead's job is to *notice*.

---

## Per-version rollup (the ladder; mean across all PRs/trials)

| version | mean cost | repr. latency¹ | precision | recall | F1 | cost vs v1 | cost vs v3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **v1** single_shot | $0.145 | ~140s | 0.94 | 0.84 | 0.88 | 1.0× | 0.50× |
| **v2** repo_aware | $0.295 | ~190s | 0.92 | 0.79 | 0.85 | 2.0× | 1.02× |
| **v3** persona_bundle | $0.289 | ~305s | 0.95 | **0.97** | **0.96** | 2.0× | 1.00× |
| **v4** persona_lite (Haiku) | **$0.066** | **~81s** | 0.91 | 0.85 | 0.88 | **0.5×** | **0.23×** |

> **Reading v4 against v3 and v1:** same persona architecture as v3, one model tier down. It gives up F1 0.96 → 0.88 (back to v1's quality band) but costs **0.23× of v3**. Crucially it **dominates v1** — equal F1 (0.88) at *half* v1's cost — and does so with the architecture that scales to the JWT/security class v1 can't see. The frontier is {v4, v3}; pick by budget.

¹ **Latency caveat:** the overnight run was heavily rate-limited by the Claude CLI usage window, so raw mean latency is contaminated by *waiting*. Figures above are **representative latencies from the unthrottled trials**. Cost and P/R/F1 are unaffected by throttling and are reported as-measured. v4 is the fastest rung (~81s, single Haiku call, no throttle exposure).

---

## Per-(version × PR) detail — the ladder

| version | PR | trials | mean cost | findings | TP | precision | recall | F1 (mean ± sd) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1 | #1 | 3 | $0.128 | 13.7 | 12.7/15 | 0.98 | 0.84 | 0.90 ± 0.02 |
| v1 | #2 | 3 | $0.108 | 14.3 | 13.3/14 | 0.91 | 0.95 | 0.93 ± 0.03 |
| v1 | #3 | 3 | $0.198 | 23.7 | 24.0/33 | 0.93 | 0.73 | 0.82 ± 0.02 |
| v2 | #1 | 3 | $0.208 | 9.7 | 11.7/15 | 0.89 | 0.78 | 0.83 ± 0.07 |
| v2 | #2 | 3 | $0.288 | 13.3 | 12.0/14 | 0.92 | 0.86 | 0.89 ± 0.00 |
| v2 | #3 | 3 | $0.388 | 21.3 | 24.3/33 | 0.94 | 0.74 | 0.82 ± 0.04 |
| v3 | #1 | 3 | $0.199 | 14.3 | 14.7/15 | 1.00 | 0.98 | **0.99 ± 0.02** |
| v3 | #2 | 3 | $0.253 | 16.7 | 14.0/14 | 0.94 | 1.00 | 0.97 ± 0.00 |
| v3 | #3 | 3 | $0.413 | 33.3 | 30.3/33 | 0.90 | 0.92 | 0.91 ± 0.02 |
| **v4** | #1 | 3 | $0.073 | 14.7 | 12.7/15 | 0.86 | 0.84 | 0.85 ± 0.20² |
| **v4** | #2 | 3 | $0.056 | 15.3 | 11.3/14 | 0.98 | 0.81 | 0.89 ± 0.06 |
| **v4** | #3 | 3 | $0.069 | 35.3 | 29.3/33 | 0.90 | 0.89 | **0.89 ± 0.00** |

² **v4/PR#1 variance is the Haiku tax made visible.** Two trials hit F1 0.97 (essentially v3); one collapsed to F1 0.62 in a false-positive storm (17 findings, P 0.59). The cheaper model is more stochastic on small diffs — the mean (0.85) understates the *typical* run (0.97). On the large PR#3 the variance vanishes (±0.00) and it nearly ties v3 (0.89 vs 0.91) at 1/6 the cost. Mitigation for a budget deploy: best-of-n voting (still cheaper than one v3 call) or a deterministic FP guard.

---

## Cost vs. F1 — the money slide (chart data)

One point per (version, PR). x = mean cost (USD), y = F1.

| version | PR | cost (x) | recall | F1 (y) |
| --- | --- | --- | --- | --- |
| v1 | #1 | 0.128 | 0.84 | 0.90 |
| v1 | #2 | 0.108 | 0.95 | 0.93 |
| v1 | #3 | 0.198 | 0.73 | 0.82 |
| v2 | #1 | 0.208 | 0.78 | 0.83 |
| v2 | #2 | 0.288 | 0.86 | 0.89 |
| v2 | #3 | 0.388 | 0.74 | 0.82 |
| v3 | #1 | 0.199 | 0.98 | 0.99 |
| v3 | #2 | 0.253 | 1.00 | 0.97 |
| v3 | #3 | 0.413 | 0.92 | 0.91 |
| **v4** | #1 | 0.073 | 0.84 | 0.85 |
| **v4** | #2 | 0.056 | 0.81 | 0.89 |
| **v4** | #3 | 0.069 | 0.89 | 0.89 |

**Pareto read:** the frontier collapses to **two points, both the persona architecture** — **v4** (cheap corner: ~$0.066, F1 0.88) and **v3** (quality knee: $0.29, F1 0.96). **v1** is beaten by v4 (same F1, ~2× the cost and no path to the security class). The only real decision is *where on the persona frontier your budget sits.* (The archived parallel/tiered builds plot up-and-right of v3 — dominated; see appendix.)

---

## Per-issue heatmap (X/trials caught) — the interesting disagreements

Full heatmaps for all 62 issues are in `compare.py` output. The rows that tell a story:

**Where giving the agent the repo (v2) flipped a miss into a catch (Teach):**

| issue | v1 | v2 | what it is |
| --- | --- | --- | --- |
| pr1-standards-snake-case-response | 0/3 | 3/3 | response field naming vs repo convention |
| pr2-quality-console-log-business-events | 1/3 | 3/3 | `console.log` where repo standardized on pino |
| pr3-security-admin-by-email-suffix | 0/3 | 3/3 | admin granted by email suffix |
| pr3-perf-webhook-sync-in-charge | 0/3 | 3/3 | synchronous webhook in the charge path |
| pr3-perf-admin-no-pagination | 0/3 | 3/3 | unbounded admin list query |

**...but v2 also regressed (the honest cost of context):**

| issue | v1 | v2 | what it is |
| --- | --- | --- | --- |
| pr2-performance-history-in-memory-filter | 3/3 | 0/3 | in-memory filter over full history |
| pr2-performance-n-plus-one-refund-enrich | 3/3 | 0/3 | N+1 query enriching refunds |
| pr3-dry-admin-role-check-duplicated | 3/3 | 0/3 | duplicated role check |
| pr1-quality-dead-code-comment | 3/3 | 0/3 | dead commented-out code |

**The Compose proof — and that it survives the cheap model (the v4 column is the point):**

| issue | v1 | v2 | v3 | **v4 (Haiku)** | note |
| --- | --- | --- | --- | --- | --- |
| pr3-security-jwt-secret-fallback | 0/3 | 0/3 | 3/3 | **3/3** | only the persona builds catch — *even on Haiku* |
| pr3-security-jwt-no-algorithm-pin | 0/3 | 0/3 | 3/3 | **2/3** | personas unlock this class regardless of tier |
| pr3-security-webhook-no-url-validation | 0/3 | 0/3 | 1/3 | **3/3** | SSRF-adjacent; v4 is the *most* reliable catcher |
| pr3-security-listusers-arbitrary-filter | 2/3 | 2/3 | 0/3 | **2/3** | the one v3-on-Sonnet drops; the cheap tier keeps it |

The JWT rows are the cleanest evidence for **Compose**: the persona builds go 3/3 where the generalist (v1/v2) goes 0/3 *on Sonnet*. The decisive column is **v4**: it runs those same personas on **Haiku** and *still* goes 3/3 on `jwt-secret-fallback` and even **3/3 on the webhook SSRF issue that v3-on-Sonnet mostly misses (1/3)**. That is the whole thesis in one row — **the composition surfaces the issue class; the expensive model is not what's doing the work.**

> **One honest caveat the model-tier sweep (appendix) adds:** the v1/v2 `0/3` above are on **Sonnet**. Raw **Opus** *does* close the JWT gap on even the dumb v1 (v1-Opus 3/3) — so for the JWT class, spend and composition are partly *substitutable* (composition just does it on Haiku for $0.066 vs Opus for $0.16). The row that stays composition-**only** is the **webhook SSRF**: v4-Haiku catches it 3/3 while v1-Opus *and* v3-Opus both go 0/3. Composition reaches a class the frontier model alone does not.

---

## Implications for the demo narrative

The arc is a 4-rung climb that ends on the cheap winner:

- **TEACH (v1 → v2):** Don't claim "context strictly improves recall" — the data says it *redistributes* coverage and trades breadth for grounding. Demo: "watch v2 catch things v1 was structurally blind to" (first heatmap), then be honest it dropped a couple — which motivates *composition*.
- **COMPOSE (→ v3):** The emotional peak. One call, four personas bundled, **F1 0.96 at $0.29.** The JWT rows prove specialists unlock whole issue classes.
- **GOVERN (→ v4):** Keep the architecture that won; dial the *model* down, not the agent count. **v4: $0.066 (0.23× v3), F1 0.88, and it still catches the JWT/SSRF class on Haiku.** The talk lands here: the frontier is {v4, v3}, the same composition twice; you pick by budget, and you spend on *decomposition*, not orchestration. One-liner: **"The agentic tech lead's job isn't to build the most agents — it's to find the knee of the curve and then dial the model, not the agent count."**

**Closing note (the call to action):** the four personas here are *ours* — security hawk, perf skeptic, KISS zealot, quality critic. Yours will differ: a11y, API-compat, data-privacy, on-call-ability, whatever your team actually argues about in review. **Bring your own personas / agent use-cases — and then do the one non-negotiable thing this whole exercise demonstrates: keep a ground-truth benchmark and continuously measure your reviewer's effectiveness.** An agent you don't measure is a vibe; the precision/recall/cost numbers here are how you know a change helped instead of hurt. Composition gets you on the frontier; measurement keeps you there.

The demo run-of-show (`demo-run-of-show.md`) matches this arc.

---

## Appendix — archived experiments (spending *up* the curve)

Before settling on v4, we built the "obvious" next step after v3: split the personas into **parallel agents** and add an **Opus skeptic** to merge/prune (`v4_parallel_personas`), plus a cost-tiered variant of it (`v5_tiered`). Both are kept on disk as evidence; **neither is in the ladder** because the data says the extra machinery didn't earn its cost on these PRs.

| archived build | mean cost | F1 | vs v3 | verdict |
| --- | --- | --- | --- | --- |
| parallel personas + Opus skeptic (`v4_parallel_personas`) | $0.715 | 0.92 | 2.5× cost, **lower** F1 | the trap: more agents, more money, worse result |
| tiered parallel + skeptic (`v5_tiered`) | $0.438 | 0.92 | 1.5× cost, lower F1 | you *can* claw cost back from the trap, but it's still dominated by v3 |

Per-PR detail (for the appendix slide, if asked): parallel build — #1 F1 0.97/$0.554, #2 0.92/$0.586, #3 0.84/$1.149 (n=2³); tiered — #1 0.96/$0.303, #2 0.92/$0.370, #3 0.88/$0.642.

The lesson these earn: **complexity is a cost you must justify with measurement, not vibes.** That's why they're in the appendix rather than deleted — the negative result is part of the argument.

³ **The archived parallel build / PR#3 is n=2.** It was the heaviest cell (5 calls incl. Opus on a 713-line PR) and the CLI throttled it relentlessly. Two complete runs survived (F1 0.89 and 0.78); one attempt was clobbered to 5 findings (F1 0.25) by an overlapping resumable run during rate-limiting and is excluded (marked as an error in its trial file).

---

## Appendix — model-tier sweep (architecture × model)

The ladder fixes one model per rung. This sweep asks the orthogonal question: **for a given architecture, what does dialing the model up or down actually buy?** Every architecture was run end-to-end on **Haiku, Sonnet, and Opus (4.8)** — 3 PRs × 3 trials each. The diagonal reuses the ladder runs (v1/v2/v3 = Sonnet; v3-Haiku *is* the shipped v4). Regenerate with `python pr-agent/bench/compare.py` (now prints this matrix).

| architecture | Haiku | Sonnet | Opus 4.8 |
| --- | --- | --- | --- |
| **v1** single-shot | F1 0.80 / R 0.73 / $0.041 | F1 0.88 / R 0.84 / $0.145 | F1 0.91 / R 0.92 / $0.164 |
| **v2** repo-aware | F1 0.69 / R 0.59 / $0.125 | F1 0.85 / R 0.79 / $0.295 | F1 0.89 / R 0.87 / $0.367 |
| **v3** persona-bundle | **F1 0.88 / R 0.85 / $0.066** *(= v4)* | **F1 0.96 / R 0.97 / $0.289** *(= v3)* | F1 0.94 / R 0.96 / $0.226 |

**What the matrix says — and it sharpens the whole talk:**

1. **Architecture beats tier, per dollar.** The cheapest persona cell — **v3-on-Haiku (= v4), F1 0.88 at $0.066** — outscores v1 and v2 at *every* tier except it trails v1-on-Opus by 0.03 F1 (0.88 vs 0.91) while costing **2.5× less**. Climbing the *model* ladder on the wrong architecture (v2) tops out at 0.89 for $0.367; climbing the *architecture* ladder on the cheap model gets 0.88 for $0.066. Composition is the cheaper lever.
2. **The dumb architecture is the most tier-sensitive; the smart one is near-flat.** v1 jumps **+0.11 F1** Haiku→Opus — it leans entirely on raw model power. v3 is already 0.88 on Haiku and only climbs to 0.96 on Sonnet, and Opus *doesn't help it* (0.94 < 0.96: more findings, slightly lower precision). The personas do the work the bigger model would otherwise have to, so the bigger model just adds noise.
3. **v2 (repo-aware) is dominated at every tier** — agentic exploration is a consistent drag, not a one-PR fluke.
4. **Security class, the honest version.** Raw Opus *can* buy back the JWT class on even the dumb v1 (**v1-Opus 3/3** on both JWT issues vs **v1-Sonnet 0/3**) — so for "obvious-once-you-look" issues, spend and composition are partly **substitutable**. But the **webhook-SSRF** issue is caught reliably *only* by the persona architecture, and — the punchline — **most reliably by the cheap Haiku persona run (v4: 3/3)**, which Opus single-shot *and* Opus persona-bundle both miss (0/3). **Composition reaches an issue class that throwing the frontier model at the problem does not.**

**Frontier across all 9 cells** (cost, F1): v1-Haiku (0.041, 0.80) → **v3-Haiku/v4** (0.066, 0.88) → v1-Opus (0.164, 0.91) → v3-Opus (0.226, 0.94) → **v3-Sonnet** (0.289, 0.96). The persona architecture owns **3 of the 5** frontier points and **both top-quality corners**; the only non-persona frontier point above F1 0.88 is v1-Opus, which costs 2.5× v4 for +0.03 F1 and still misses the SSRF class.

> **Cost caveat for this table:** the **Sonnet column** is the original overnight ladder run, collected through a throttled CLI window with retry inflation, so those dollar figures are *upper bounds*. The Haiku and Opus columns ran clean. That's why v3-**Opus** ($0.226) reads *cheaper* than v3-**Sonnet** ($0.289) — an artifact of Sonnet-column retries, **not** Opus being cheaper per token. Read the F1/recall as-measured; treat the Sonnet costs as inflated. Sweep spend: **~$8.3** ($1.49 Haiku + $6.81 Opus).

---

## Caveats / reproducibility

- **Throttling:** the matrix ran on the interactive `claude` CLI (~5-hour usage window). Heavy back-to-back Opus calls (the archived parallel build) hit it, inflating latency (some runs stalled for *hours*) and producing occasional blank/truncated runs. The harness auto-retries blanks and records persistent failures as errors (`--resume` re-runs only failed/missing cells). Cost and quality metrics are unaffected; **read latency from the representative figures, not raw means.** The 4-rung ladder itself (v1–v4) is light; v4 in particular is a single fast Haiku call.
- **Concurrency incident (resolved):** because `--resume` makes the matrix re-invokable, two long-running jobs over the archived parallel build overlapped overnight and raced on the same trial files, clobbering one PR#3 trial. Caught via a finding-count/F1 stability audit once all writers exited; the trial is excluded (that cell settled at n=2). **Operational lesson worth a talk aside: never run two `--resume` jobs over the same version concurrently — agent fleets need the same write-isolation discipline as any distributed job.** Every ladder cell is clean n=3.
- **Variance (the cheap-model tax):** v4 is the loudest — **PR#1 ±0.20** (two ~0.97 runs, one 0.62 false-positive storm). The cheaper the model, the more stochastic on small diffs; variance shrinks to ±0.00 on the large PR#3. Read v4's *mean* (0.88) as "usually v3-class, occasionally needs a second opinion," and pair a budget deploy with best-of-n or a deterministic FP guard. It's why every cell is n≥2.
- **The 7× cost-collapse from the source blog isn't reachable through the CLI seam** — each call shells out separately, so a shared diff is billed as cache-write every time with no cross-call prompt-cache prefix sharing. An SDK backend with a shared cached prefix would push v4 (and the archived tiered build) cheaper still. The natural "and here's how production pushes it further" note.
