# v3 - persona-bundle reviewer

The demo's pivot: from a *generic* "you are a senior engineer" reviewer (v1) to
one that **reviews like OUR team**. Same machinery as v1 — one LLM call, no
tools, diff-only — but the generic framing is replaced by a bundle of the
team's four reviewer personas.

```
PR number  ->  gh pr diff  ->  ONE claude call (no tools)  ->  findings
                                  ^ system prompt = preamble + 4 personas + output contract
```

## The idea (from the HoneyBook blog that inspired the talk)

Instead of one generic prompt, concatenate the team's distinct reviewer
profiles into a single bundled prompt and make **one** call that reviews the
diff through all of them at once, attributing each finding to the persona that
raised it. This is the deliberately *simple* bundling approach — one call, all
personas. (One-agent-per-persona is a later version's job, not this one.)

The four personas (authored in `pr-agent/personas/*.md`, read at runtime):

| id | lens |
|---|---|
| `security_hawk` | secrets, PAN/CVC/PII, crypto, authn/authz, SSRF, injection |
| `perf_skeptic` | N+1, load-all-then-filter, sync work on hot paths, unbounded reads |
| `kiss_zealot` | over-engineering, YAGNI, dead code, hidden global state |
| `quality_critic` | honest names/errors/status codes, validation, real tests |

## How the bundle is built

`_load_personas()` reads every `*.md` under `pr-agent/personas/` (path derived
from `__file__`, never hardcoded), sorted for a stable prompt. The system prompt
is then assembled as:

1. a **preamble** telling the model it is a *team* of four distinct reviewers
   (don't water them down into a generic senior reviewer), plus the hard rule
   that every finding must carry a `source` set to one of the persona ids;
2. each persona's full markdown under a `### PERSONA: <id>` header, so the model
   keeps each voice distinct and attribution has a stable key;
3. the shared **output contract** — the same single ```json fenced block
   (`{summary, findings:[{file,line_start,line_end,category,severity,title,message,source}]}`)
   the other versions use, parsed by `shared.extract_fenced_json`.

## Attribution

Each finding's `source` is the persona that raised it. `_coerce_findings`
trusts the model's `source` only when it matches a known persona id; anything
else falls back to `v3_persona_bundle`, so attribution can never silently point
at a made-up persona. If two personas would flag the same line for different
reasons, the model emits one finding per persona.

## What changed from v1

| | v1 | v3 |
|---|---|---|
| Framing | one generic "senior engineer" prompt | four bundled team personas |
| Calls | 1 (single shot, no tools) | 1 (single shot, no tools) — **unchanged** |
| Model | `config.model_for("generalist")` | `config.model_for("generalist")` — **unchanged** |
| `source` | `v1_generalist` | the persona that raised the finding |

Holding the call count, tool surface, and model identical to v1 is the point:
the v1-vs-v3 delta isolates the **personas**, not the architecture. The agentic
/ tiered machinery is left for later versions.

## Usage

From `pr-agent/v3_persona_bundle/`:

```bash
python review.py <pr-url-or-number> [--repo OWNER/REPO] [--config PATH] [--json]
```

Or via the bench harness, from `pr-agent/`:

```bash
python -m bench.run_eval --version v3_persona_bundle --pr 1 --trials 1
```

`gh` must be authenticated for diff/metadata fetching.

## Cost / latency

A single-shot call like v1, but with a larger system prompt (the four persona
profiles), so expect a touch more input cost than v1 and comparable latency —
roughly $0.15–0.40 and 1–3 min on the configured `generalist` model.
