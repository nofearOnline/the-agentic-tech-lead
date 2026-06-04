# The Agentic Tech Lead — Demo Run-of-Show

**Total talk:** 45 min · **Demo budget:** ≤20 min (you run demos fast, so this is padded)
**Audience:** tech leads, mixed seniority
**Spine:** three take-homes — **Teach · Compose · Govern** — each = *claim → evidence → how to implement → live benchmark beat*.

The demo is the proof layer under the three claims. It's a **4-rung ladder** — **v1** single-shot → **v2** repo-aware → **v3** persona-bundle → **v4** persona-bundle-made-cheap — run as head-to-head diffs on the PR that makes each point loudest. **All numbers below are from the benchmark matrix** (`presentation/comparison.md`).

> **The shape of the story.** v1 is the baseline. v2 *trades* breadth for repo-grounding (Teach). v3 bundles four reviewer personas into one call and **wins the matrix: F1 0.96 at $0.29** (Compose). Then the punchline: **v4 is v3 with one knob changed — the model dialed Sonnet → Haiku.** It lands **F1 0.88 at $0.066** (~4× cheaper than v3), *still* catches the JWT/SSRF security class on the cheap model, and the cost/quality frontier collapses to just **{v4, v3} — the same architecture twice.** Closing line: *composition is the value; the model tier is just the dial — so build your own personas and always measure.* (We also tried spending the *other* direction — parallel agents + a skeptic — it cost ~2.5× more and scored lower; that's an optional aside / appendix, not a rung.)

---

## Pre-flight (before you present — do NOT do live)

- [ ] Matrix already run; `presentation/comparison.md` numbers memorized for the beats.
- [ ] Terminal A: `pr-agent/` with `.venv` active, font size cranked, scrollback cleared.
- [ ] Terminal B: the three target PR diffs open in tabs (`gh pr diff 1|2|3`).
- [ ] **All four ladder rungs run live.** v1/v2/v3/v4 each take ~1–3 min. **v4 is the fastest (~80s, ~$0.07, single Haiku call)** and is the live closer.
- [ ] *Optional appendix only:* if you plan to show the "spend up" aside, **pre-record the parallel+skeptic build** — a live run on PR#3 is ~12 min and ~$1.15 and the CLI can rate-limit it into *hours*. Never run it live; replay the saved `trial-*.json`.
- [ ] `compare.py` output piped to a clean pager / rendered table ready to flash.
- [ ] One backup terminal recording of every beat in case Wi-Fi/network dies on stage.

---

## Beat 0 — Cold open (≈1 min, no slide math)

Run v1 live on **PR#1** (coupon, smallest diff). One model call, diff in, findings out.

> "This is the whole agent: paste the diff into one model, ask for problems. It's genuinely good — it'll catch most of this small PR. Watch where it stops being good."

Leave the v1 findings on screen. This is the baseline every later beat is measured against.

- v1 / PR#1: **F1 0.90, $0.13, ~127s, 12.7/15 caught** (mean of 3). It's already strong on a small PR — that's the point.

---

## Beat 1 — TEACH (≈5 min) · *"Give the agent your codebase, not just the diff."*

**Claim:** A diff-only reviewer is structurally blind to anything that requires knowing the rest of the repo — naming conventions, the logger you standardized on, the helper that already exists. You give the agent the repo, and it catches a whole class of "this isn't how *we* do it here" issues. **But — and this is the honest part — context is a *trade*, not a free upgrade.**

**Evidence (the matrix):** v2 newly flipped misses into catches that *require* repo knowledge — `snake-case-response` 0/3→3/3, `console.log`-vs-pino 1/3→3/3, `admin-by-email-suffix` 0/3→3/3, sync-webhook-in-charge 0/3→3/3, admin-no-pagination 0/3→3/3. **And** it got more conservative and dropped others (the PR#2 N+1 and in-memory-filter perf bugs, 3/3→0/3). Net mean recall actually dipped 0.84→0.79.

**How to implement:** an agentic loop with `Read`/`Grep`/`Glob` over a worktree checked out at the PR head SHA. The model decides what to open.

**Live beat — v1 vs v2 on PR#2 (refunds, medium):**
Run v2 live. Show a context-dependent catch (console.log vs pino, naming). Then — deliberately — show one it dropped that v1 had.

> "Same model, same PR. I just let it *look around*. Watch it catch things it was structurally blind to before — and watch it get cautious and miss a couple it used to flag. Context isn't a magic upgrade; it's a trade. Which is exactly why we don't stop here — we **compose**."

- v2 / PR#2: **F1 0.89, $0.29, ~190s.** Mean recall across all PRs 0.79 (down from v1's 0.84) — use this honesty; it sets up Compose.

---

## Beat 2 — COMPOSE (≈6 min) · *"Many sharp specialists beat one general genius — and the data agrees emphatically."*

**Claim:** A single prompt asked to "find everything" regresses to shallow, generic feedback. Decompose the review into **personas** — a security hawk, a perf skeptic, a KISS zealot, a quality critic — each with one obsession. This is "review like *our team* reviews."

**Evidence (the matrix):** v3 bundles all four personas into *one* call and **tops the entire matrix: F1 0.96, recall 0.97, for $0.29.** The cleanest proof is the JWT issue class — `jwt-secret-fallback` and `jwt-no-algorithm-pin` go **0/3 for v1 and v2 → 3/3 for v3.** The security-hawk persona reliably surfaces a whole category the generalist never raises. *This is the emotional peak of the talk.*

**How to implement:** load each persona as a profile, concatenate into one system prompt, one call. (Splitting them into parallel agents + a skeptic is the tempting "next step" — we tried it; it lost. Appendix.)

**Live beat — v3 on PR#1 (and glance at PR#3):**
Run v3 live on PR#1 — it essentially aces it (**F1 0.99**). Then flash PR#3's heatmap rows for the JWT issues: red for v1/v2, green for v3.

> "Same one call. I just gave it four sets of eyes instead of one. Watch an entire class of security bugs go from invisible to caught. *This* is composition — and it's still one cheap call."

- v3 / PR#1: **F1 0.99, $0.20.** v3 overall: **F1 0.96, recall 0.97, $0.29** — the matrix winner.

---

## Beat 3 — GOVERN (≈6 min) · *"The job isn't building the most agents. It's finding the knee, then dialing the model — not the agent count."*

**Claim:** Once you've found the architecture that wins (v3), governance is a *cost* question, and the right lever is the **model tier**, not more orchestration. Keep the personas; dial the model down.

**Live beat — v4 on PR#3 (run it LIVE; this is the closer):**
v4 is v3 with one knob changed: the bundled-persona call runs on **Haiku** instead of Sonnet. ~80 seconds, ~7 cents. While it runs, predict aloud: "watch it *still* catch the JWT secret fallback — the bug the diff-only reviewer in Beat 0 was blind to."

**Evidence (the matrix):** v4 lands **F1 0.88 at $0.066 — ~4× cheaper than v3** — and the heatmap proves the win is the *architecture*, not the spend: on Haiku it still goes **3/3 on `jwt-secret-fallback`** (v1/v2 on Sonnet: 0/3) and even **3/3 on the webhook SSRF issue v3-on-Sonnet mostly misses (1/3)**. On the hardest PR it nearly ties v3 (0.89 vs 0.91) at **1/6 the cost**. v4 also **dominates v1**: same F1 (0.88), half the cost, plus a path to the security class v1 can't see.

> "Same four personas. One model tier down. It still sees the security class the generic reviewer never will — because the *composition* is doing the work, not the expensive model. The frontier is just two points, v4 and v3, and they're the same design. You're not choosing an architecture anymore; you're choosing a budget."

**Be honest about the tax:** Haiku is more stochastic on small diffs (PR#1 swung F1 0.62↔0.97). For a budget deploy you'd run best-of-n (still cheaper than one v3 call) or a deterministic false-positive guard. Say it out loud — it's the credible version.

**Optional 60-sec aside (the road not taken):** "The tempting move after v3 is to spend *up* — parallel persona agents, an Opus skeptic to merge them. We built it. It cost ~2.5× v3 and scored *lower* (F1 0.92). Even the cost-optimized version of it lost to v3. More agents felt like progress; the data said otherwise. That's the whole reason we measure." (Replay only — never run live; numbers in the appendix of `comparison.md`.)

- **v4: F1 0.88, $0.066** (cheap frontier point) · v3: **F1 0.96, $0.29** (quality knee). Archived "spend up" builds: parallel+skeptic 0.92/$0.72, tiered 0.92/$0.44 — both dominated.

---

## Beat 4 — The one slide that ties it together + the call to action (≈2-3 min)

Flash the cost-vs-F1 scatter from `presentation/comparison.md` and trace the frontier with your finger — it collapses to **two points, and they're the same architecture**: **v4** (cheap corner, $0.066 / F1 0.88) and **v3** (the knee, $0.29 / F1 0.96). Circle v1 as *dominated by v4* (same F1, twice the cost). If you showed the aside, drop the archived builds up-and-right of v3 and label them "dominated."

> "Four rungs. The lesson isn't 'the last one is fanciest' — the last one is the *cheapest*, and it's the same design as the best one. **Each jump is a decision a tech lead owns**: give it context (and accept the trade), compose specialists (the big win), and govern cost by dialing the *model*, not the agent count. Composition is the frontier; the model is just where you sit on it."

**Then the call to action — land the plane here:**

> "Two things to take back to your teams. **One: bring your own personas.** Ours are a security hawk, a perf skeptic, a KISS zealot, a quality critic — because that's who argues in *our* reviews. Yours might be accessibility, API-compatibility, data-privacy, on-call-ability. The architecture is the same; the *use-cases* are yours to define. **Two — and this is non-negotiable: measure it, continuously.** Everything I just showed you is only knowable because we kept a ground-truth benchmark and scored every version on precision, recall, and cost. An agent you don't measure is a vibe. The tech lead's job in the agentic era isn't to ship the most agents — it's to *teach* the agent your codebase, *compose* the specialists your team needs, and *govern* it with numbers. Teach, compose, govern."

Close. Hand back to slides for Q&A.

---

## Timing summary

| beat | content | live? | budget |
| --- | --- | --- | --- |
| 0 | v1 cold open / PR#1 | live | 1 min |
| 1 | TEACH — v1 vs v2 / PR#2 (context as a *trade*) | live (v2) | 5 min |
| 2 | COMPOSE — v3 live / PR#1 (the hero: F1 0.96) | live | 5 min |
| 3 | GOVERN — **v4 live** / PR#3 ($0.066, still catches JWT) + optional 60s "spend-up" aside | **live (v4)** | 6 min |
| 4 | frontier = {v4, v3} slide + call to action (BYO personas, always measure) | slide | 2-3 min |
| | **total** | | **≈19-20 min** (drop the aside / trim Beat 2 if tight) |

## Risk / fallback notes

- **Network on stage:** every beat has a pre-recorded fallback. If Wi-Fi dies, switch to recordings without breaking narrative.
- **Run-to-run variance:** Haiku swings — **v4 up to ±0.20 on the small PR#1**. Run the live v4 beat on **PR#3**, where it's rock-stable (±0.00) and the JWT/SSRF catches are reliable. If any live run looks worse than the slide, say so out loud ("this is real, cheap models are stochastic — which is exactly the tax I flagged") rather than re-running. The variance is *on-message*, not an accident.
- **v4 is the safest live closer:** ~80s, ~$0.07, single call (no throttle risk), and on PR#3 it's deterministic enough to trust on stage.
- **Never run the archived parallel+skeptic build live** (only relevant if you show the optional aside). ~12 min unthrottled (~$1.15), and the CLI can stall it for *hours* under rate limits. Always replay a saved trial.
- **Latency dead air:** v1/v2/v3/v4 each take 1-3 min live. Fill it by reading the diff aloud and predicting what the agent will catch — turns dead time into engagement.
