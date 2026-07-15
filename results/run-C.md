# Run C — Goal-based loop (/goal)

## Bookkeeping

| Field | Value |
|---|---|
| Date (local) | 2026-07-15 |
| claude --version | (to fill — run `claude --version`) |
| Model / effort | Opus 4.8 (1M context) / high |
| Start time (local) | ~21:27 |
| End time (local) | ~21:36 |
| Wall-clock duration | **8m 38s** (single continuous run, no pauses) |
| Stop reason | **Goal achieved** — evaluator confirmed the condition after turn 1 |

## Cost & usage (from /usage + session stats)

| Metric | Value |
|---|---|
| **Total cost (all-in, single session)** | **$1.97** |
| Opus 4.8 | 3.9k input, 39.4k output, 845.3k cache read, 51.3k cache write → **$1.94** |
| Haiku 4.5 (the /goal evaluator) | 547 input, 277 output, 27.5k cache write → **$0.036** |
| API duration | 8m 24s |
| Wall duration | 1h 20m (dominated by human/idle, not compute) |
| Turns | **1** (goal cap was 5; the outer loop needed 0 extra turns) |
| Human interventions | 0 |
| Code changes | 1438 lines added, 0 removed (clean single-session capture) |

> **Key cost finding:** the `/goal` outer loop's *direct* overhead is the
> Haiku evaluator = **$0.036**, i.e. **~1.8% of the run**. The loop is not
> expensive because of the evaluator; it is expensive only when it triggers
> extra *turns*. Here it triggered zero. Cache reads (845k) mean most tokens
> are cheap cached reads, not fresh input.

## Quality

| Metric | Value |
|---|---|
| **Acceptance pass rate** | **100.0% (71/71)** |
| Phase 1 (functional) passed/failed | 67 / 0 |
| Phase 2 (rate limit) passed/failed | 4 / 0 |
| /code-review findings | (pending — optional, costs tokens) |
| Scope creep (beyond spec) | **None** — added `.gitignore` (housekeeping); no non-spec behavior |
| LOC (app code) | **1046** (7 modules: main, db, errors, ratelimit, validation, seed, __init__) |
| Rate-limit window choice | **Sliding window** (Run A chose fixed) — both spec-compliant |

## Timeline / observations

- **Headline: the /goal outer loop added zero extra turns.** The goal
  (`Stop after 5 turns at most`) was satisfied on the **first** turn — the
  evaluator model checked the condition after turn 1 and cleared the goal. The
  outer harness did not cause a single additional iteration.
- The reason is the same as Run A: within its one turn the model ran its own
  **inner loop** — wrote a 70-assertion `smoke_test.py`, ran it against a live
  TestClient, confirmed all pass, booted real uvicorn, byte-checked the seed
  output with `od -c`, then deleted the smoke test and DBs to ship clean.
- **More modular than Run A:** Run A produced 4 files / 805 LOC in a flatter
  layout; Run C split concerns into 7 files / 1046 LOC (separate `errors.py`,
  `ratelimit.py`, `validation.py`). Same 100% score — the extra structure is a
  style difference, not a correctness gain here.
- **Independent implementation choices, both correct:** Run C used a *sliding*
  window rate limiter and made project-not-found 422 in bodies / 404 in paths;
  Run A used a *fixed* window. The hidden suite is deliberately window-agnostic
  (checks 429 + headers), so both pass — a nice illustration that a good spec
  leaves room for defensible design choices.
- Hit the same transient "temporarily unavailable" classifier hiccups as Run A
  during Bash calls, but auto mode retried automatically; no human action, no
  usage-limit pause this time.

## Verbatim prompts sent

1. `Read SPEC.md in this directory and implement the complete API it describes. Work until you believe the implementation is complete, then stop.`
2. `/goal The API described in SPEC.md is fully implemented; the server starts clean; a smoke script you write yourself exercises every endpoint in the spec including auth, rate limiting, validation and pagination edge cases, and every check passes with the server output shown as evidence. Stop after 5 turns at most.`

## Deviations from PROTOCOL.md

- Turn cap reduced 15 → 5 for budget (see `results/deviations.md`). Did not
  bind: the goal cleared in 1 turn regardless.
- Auto mode (constant across all runs).
