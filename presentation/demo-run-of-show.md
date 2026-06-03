# The Agentic Tech Lead — Demo Run-of-Show

**Total talk:** 45 min · **Demo budget:** ≤20 min (you run demos fast, so this is padded)
**Audience:** tech leads, mixed seniority
**Spine:** three take-homes — **Teach · Compose · Govern** — each = *claim → evidence → how to implement → live benchmark beat*.

The demo is the proof layer under the three claims. We don't tour all five versions linearly; we run **three head-to-head diffs**, one per take-home, on the PR that makes the point loudest. **All numbers below are from the completed 45-run matrix** (`presentation/comparison.md`).

> **The data reframed the story — read this first.** The smoke tests implied a clean v1<v2<v3<v4<v5. The full matrix says something sharper: **v3 (bundled personas, one call) is the actual quality winner — F1 0.96 at $0.29 — and v4 (parallel personas + skeptic) costs 2.5× more for *lower* F1 (0.93).** So the demo's emotional peak is **v3**, and **v4 is the cautionary tale**, not the climax. This is a *better* talk for tech leads: the lesson is "measure whether the complexity earned its cost," which the data demonstrates live.

---

## Pre-flight (before you present — do NOT do live)

- [ ] Matrix already run; `presentation/comparison.md` numbers memorized for the three beats.
- [ ] Terminal A: `pr-agent/` with `.venv` active, font size cranked, scrollback cleared.
- [ ] Terminal B: the three target PR diffs open in tabs (`gh pr diff 1|2|3`).
- [ ] **Pre-warm or pre-record v4.** A live v4 run on PR#3 is ~12 min (5 sequential calls incl. Opus) and ~$1.15 — too slow for the stage, and the CLI can rate-limit it into *hours*. Run it beforehand and replay the saved `trial-*.json`, or show a recording. Only v1/v2/v3/v5 are fast enough to run truly live.
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

**How to implement:** load each persona as a profile, concatenate into one system prompt, one call. (The parallel-agents version is the next beat — and it's where the cautionary tale lives.)

**Live beat — v3 on PR#1 (and glance at PR#3):**
Run v3 live on PR#1 — it essentially aces it (**F1 0.99**). Then flash PR#3's heatmap rows for the JWT issues: red for v1/v2, green for v3.

> "Same one call. I just gave it four sets of eyes instead of one. Watch an entire class of security bugs go from invisible to caught. *This* is composition — and it's still one cheap call."

- v3 / PR#1: **F1 0.99, $0.20.** v3 overall: **F1 0.96, recall 0.97, $0.29** — the matrix winner.

---

## Beat 3 — GOVERN (≈7 min) · *"The job isn't building the most agents. It's knowing which complexity earns its cost."*

**The setup (v4, the cautionary tale):** The obvious "next step" after v3 is the impressive one — split the personas into *parallel* agents and add an **Opus skeptic** to merge and prune. It *looks* like the most sophisticated build. Run/replay v4 and let the numbers land:

> "This is the build everyone wants to demo. Four agents in parallel, a principal-engineer skeptic on top. And here's what it actually bought us…"

**Evidence (the matrix) — the gut-punch:** v4 costs **$0.71 (2.5× v3) and scores *lower*: F1 0.93 vs v3's 0.96.** More agents, more money, worse result on these PRs. Put the v3 and v4 rows side by side and let the room sit with it.

> "More machinery. 2.5× the cost. And it did *worse*. This is the trap — complexity feels like progress. The agentic tech lead's actual job is to *measure* whether it is."

**The two governance moves:**
1. **Sometimes the answer is 'don't' — v3 was already the frontier.** That's the headline.
2. **When you *do* need a v4-shaped build, engineer its cost down (v5).** v5 keeps the multi-agent shape but adds a deterministic pre-phase (gate personas with no surface in the diff; pre-cluster duplicates), tiers models (**Haiku** breadth, **Opus** skeptic only), and an **edit-list skeptic** (Opus emits drop/merge/severity edits, not re-authored prose). Result: **$0.44 (0.61× v4), F1 0.92, and genuinely fast (~155s vs v4's ~700s+).**

**Live beat — v5 vs v4 on PR#3:**

> "If you're committed to the multi-agent architecture, v5 is how you make it affordable — 0.61× the cost, ~4–5× faster, same quality band. But notice: v3 still beats both. Cost discipline *and* the humility to not over-build. That's governance."

Honest ceiling note: the literal 7× cost-collapse from the source blog needs prompt-cache prefix sharing across agents, which the CLI seam can't do — an SDK backend can. "Here's exactly where I'd spend the next week."

- v4: **F1 0.93, $0.71, ~700s** · v5: **F1 0.92, $0.44, ~155s** · v3 (still the winner): **F1 0.96, $0.29**.

---

## Beat 4 — The one slide that ties it together (≈1-2 min)

Flash the per-version rollup and the cost-vs-recall scatter from `presentation/comparison.md`. Trace the Pareto frontier with your finger: v1 (cheap floor) → **v3 (the knee — best F1, near-cheapest)** → v4 (expensive corner, buys nothing) → v5 (v4 made affordable).

> "Five versions. The lesson isn't 'the last one wins' — the most sophisticated build *lost*. It's that **each jump is a decision a tech lead owns**: give it context (and accept the trade), compose specialists (the big win), and govern cost — which sometimes means *not* building the fancy thing. Teach, compose, govern."

Close. Hand back to slides for Q&A.

---

## Timing summary

| beat | content | live? | budget |
| --- | --- | --- | --- |
| 0 | v1 cold open / PR#1 | live | 1 min |
| 1 | TEACH — v1 vs v2 / PR#2 (context as a *trade*) | live (v2) | 5 min |
| 2 | COMPOSE — v3 live / PR#1 (the hero: F1 0.96) | live | 5 min |
| 3 | GOVERN — v4 cautionary tale → v5 vs v4 / PR#3 | live (v5), replay v4 | 7 min |
| 4 | full matrix + Pareto slide | slide | 1-2 min |
| | **total** | | **≈19-20 min** |

## Risk / fallback notes

- **Network on stage:** every beat has a pre-recorded fallback. If Wi-Fi dies, switch to recordings without breaking narrative.
- **Run-to-run variance:** Haiku (v5) swings ±0.03 F1 between trials — if a live v5 run looks worse than the slide, say so out loud ("this is real, models are stochastic") rather than re-running.
- **Don't run v4 live.** Ever. ~12 min unthrottled (~$1.15), and the CLI can stall it for *hours* under rate limits. Always replay.
- **Latency dead air:** v1/v2/v3/v5 each take 1-3 min live. Fill it by reading the diff aloud and predicting what the agent will catch — turns dead time into engagement.
