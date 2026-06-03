# Benchmark Comparison — 5 reviewer versions × 3 PRs

Generated from the full eval matrix: **5 versions × 3 PRs × 3 trials**. 44 trials counted (one v4/PR#3 trial excluded as a catastrophic throttle casualty — see caveats), so all cells are n=3 except v4/PR#3 which is n=2. Ground truth: 62 planted issues across the three PRs (15 / 14 / 33). Scoring is many-to-one (one finding may cover multiple co-located issues). Backend: `claude` CLI. Total counted spend **$16.21**.

Regenerate the raw tables with: `python pr-agent/bench/compare.py`

---

## TL;DR — the three things this data actually shows

1. **The fancy multi-agent build (v4) does NOT beat the simple one (v3) on these PRs — and costs ~2.5× more.** v3 (all four personas bundled into one call) tops the whole matrix at **F1 0.96 / recall 0.97 for $0.29**. v4 (parallel personas + Opus skeptic) lands at **F1 0.92 for $0.72**. More machinery, more money, *lower* F1. This is the headline lesson for a tech-lead audience: **complexity is a cost you must justify with measurement, not vibes.**
2. **Cost scales faster than quality.** Going v1 → v4 is ~4.9× the spend for the same F1 band (0.88 → 0.92). The quality ceiling on these PRs is ~0.96 (v3), and you hit it cheaply.
3. **"Give it the repo" (v2) is not a free win.** Repo-awareness *changed* what got caught (it newly nailed context-dependent issues v1 was blind to) but it also got more conservative and **regressed mean recall 0.84 → 0.79**. Context is a trade, not a strict upgrade — an honest, useful nuance.

> These results complicate the clean "each version strictly beats the last" arc. That's good: the most credible version of this talk is the one where the data occasionally contradicts the hype, and the tech lead's job is to *notice*. See "Implications for the demo narrative" at the bottom.

---

## Per-version rollup (mean across all PRs/trials)

| version | mean cost | repr. latency¹ | precision | recall | F1 | cost vs v1 | cost vs v4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **v1** single_shot | **$0.145** | ~140s | 0.94 | 0.84 | 0.88 | 1.0× | 0.20× |
| **v2** repo_aware | $0.295 | ~190s | 0.92 | 0.79 | 0.85 | 2.0× | 0.41× |
| **v3** persona_bundle | $0.289 | ~305s | 0.95 | **0.97** | **0.96** | 2.0× | 0.40× |
| **v4** parallel_personas | $0.715 | ~700s² | 0.91 | 0.93 | 0.92 | 4.9× | 1.00× |
| **v5** tiered | $0.438 | ~155s | 0.93 | 0.92 | 0.92 | 3.0× | 0.61× |

¹ **Latency caveat:** the overnight run was heavily rate-limited by the Claude CLI subscription's usage window, so raw mean latency is contaminated by *waiting* (some runs sat for hours). The figures above are **representative latencies from the unthrottled trials** (median of runs <900s), which reflect real compute time. Cost and P/R/F1 are unaffected by throttling and are reported as-measured.
² v4 on the large PR#3 runs ~700–740s unthrottled (5 sequential model calls incl. Opus); on small PRs ~200–230s.

---

## Per-(version × PR) detail

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
| v4 | #1 | 3 | $0.554 | 16.7 | 14.3/15 | 0.99 | 0.96 | 0.97 ± 0.03 |
| v4 | #2 | 3 | $0.586 | 19.7 | 14.0/14 | 0.85 | 1.00 | 0.92 ± 0.01 |
| v4 | #3 | 2³ | $1.149 | 27.5 | 26.0/33 | 0.89 | 0.79 | 0.84 ± 0.07 |
| v5 | #1 | 3 | $0.303 | 14.3 | 14.0/15 | 1.00 | 0.93 | 0.96 ± 0.04 |
| v5 | #2 | 3 | $0.370 | 15.3 | 13.3/14 | 0.89 | 0.95 | 0.92 ± 0.02 |
| v5 | #3 | 3 | $0.642 | 31.3 | 29.0/33 | 0.88 | 0.88 | 0.88 ± 0.04 |

³ **v4/PR#3 is n=2.** This was the heaviest cell in the matrix (5 calls incl. Opus on a 713-line PR) and the Claude CLI throttled it relentlessly across multiple overlapping attempts. Two complete runs survived (F1 0.89 / 29 findings and F1 0.78 / 26 findings — real variance, both kept); one attempt was clobbered to 5 findings (F1 0.25) by an overlapping resumable run during rate-limiting and is excluded as a catastrophic failure (marked as an error in its trial file). The pre-matrix smoke test (F1 0.94, 32/33) sits at the top of this cell's range. The other eight v4 cells are clean n=3.

---

## Cost vs. recall — scatter/bubble chart data

One point per (version, PR). x = mean cost (USD), y = mean recall, label/size = F1.

| version | PR | cost (x) | recall (y) | F1 |
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
| v4 | #1 | 0.554 | 0.96 | 0.97 |
| v4 | #2 | 0.586 | 1.00 | 0.92 |
| v4 | #3 | 1.149 | 0.79 | 0.84 |
| v5 | #1 | 0.303 | 0.93 | 0.96 |
| v5 | #2 | 0.370 | 0.95 | 0.92 |
| v5 | #3 | 0.642 | 0.88 | 0.88 |

**Pareto read:** v3 dominates the cost/recall frontier on every PR. v1 is the cheap floor; v4 is the expensive corner (top-right) that buys nothing over v3; v5 sits between v4 and v3.

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

**Issues the whole field struggles with (good "even the best agent misses things" slide):**

| issue | v1 | v2 | v3 | v4 | v5 | note |
| --- | --- | --- | --- | --- | --- | --- |
| pr3-security-webhook-no-url-validation | 0/3 | 0/3 | 1/3 | 0/2 | 0/3 | SSRF-adjacent; nearly universal miss |
| pr3-security-listusers-arbitrary-filter | 2/3 | 2/3 | 0/3 | 0/2 | 2/3 | v3/v4 miss it; cheaper models catch it |
| pr3-security-jwt-secret-fallback | 0/3 | 0/3 | 3/3 | 0/2 | 3/3 | only the persona builds reliably catch |
| pr3-security-jwt-no-algorithm-pin | 0/3 | 0/3 | 3/3 | 0/2 | 3/3 | personas unlock this class |

The JWT rows are the cleanest evidence for **Compose**: v3 (bundled personas) goes 3/3 where the generalist (v1/v2) goes 0/3. (v4's `0/2` here is its two surviving PR#3 trials both missing them — small-sample noise on a throttle-damaged cell, not a reliable signal; v5 confirms the pattern at 3/3.)

---

## Implications for the demo narrative

The smoke tests implied a clean v1 < v2 < v3 < v4, then v5 = v4-but-cheaper. The full matrix says something sharper and more honest:

- **TEACH (v1 → v2):** Don't claim "context strictly improves recall" — the data says it *redistributes* coverage and trades breadth for grounding. Demo it as: "watch v2 catch things v1 was structurally blind to" (the first heatmap above), then be honest that it also dropped a couple — which motivates *composition*.
- **COMPOSE (→ v3):** This is the real hero. One call, four personas bundled, **F1 0.96 at $0.29.** The JWT rows prove specialists unlock whole issue classes. Land the talk's emotional peak here, not on v4.
- **GOVERN (v4 → v5, reframed):** v4 is the cautionary tale, not the climax: more agents + a skeptic = ~2.5× cost and *lower* F1 than v3 on these PRs. The governance lesson is twofold: (a) v5 shows you *can* claw cost back from a v4-style build (0.61× v4, ~4–5× faster), but (b) the deeper move is **measuring whether you needed v4 at all.** "The agentic tech lead's job isn't to build the most agents — it's to know which complexity earns its cost."

This is a stronger talk than the linear one. Recommend reordering Beat 2/3 around v3-as-hero and v4-as-cautionary-tale. The demo run-of-show (`demo-run-of-show.md`) has been updated to match.

---

## Caveats / reproducibility

- **Throttling:** the matrix was run on the interactive `claude` CLI, which enforces a ~5-hour usage window. Heavy back-to-back Opus calls (v4) hit it, inflating latency (some runs stalled for *hours*) and producing occasional blank/truncated runs. The harness now auto-retries blanks and records persistent failures as errors (`--resume` re-runs only failed/missing cells). Cost and quality metrics are unaffected; **latency should be read from the representative figures, not raw means.**
- **Concurrency incident (resolved):** because `--resume` makes the matrix re-invokable, two long-running v4 jobs ended up overlapping overnight and raced on the same trial files, briefly producing inconsistent reads and clobbering one v4/PR#3 trial down to 5 findings. Caught via a finding-count/F1 stability audit once all writers exited; the single catastrophic trial is excluded (v4/PR#3 settled at n=2). **Operational lesson worth a talk aside: never run two `--resume` jobs over the same version concurrently — agent fleets need the same write-isolation discipline as any distributed job.** Every other cell is clean n=3.
- **Variance:** Haiku-tier breadth (v5) shows ±0.02–0.04 F1 between trials; v4/PR#3 shows ±0.07 across its two surviving runs. Expect run-to-run wobble.
- **The 7× cost-collapse from the source blog isn't reachable through the CLI seam** — each agent shells out separately, so the shared diff is billed as cache-write on every call with no cross-call prompt-cache prefix sharing. An SDK backend with a shared cached prefix would widen v5's advantage further. This is the natural "and here's how production pushes it further" note.
