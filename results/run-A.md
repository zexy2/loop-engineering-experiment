# Run A — One-shot (baseline)

## Bookkeeping

| Field | Value |
|---|---|
| Date (local) | 2026-07-15 (started 2026-07-15 00:15 local, UTC+3) |
| claude --version | (to fill — run `claude --version`) |
| Model / effort | Opus 4.8 / high |
| Start time (local) | 00:15 |
| End time (local) | ~20:50 (finished shortly after the 20:40 resume; "Cogitated 5m 31s") |
| Active wall-clock (excl. pauses) | **~26 min** (see pause log) |
| Stop reason | Agent declared complete ("no further action needed") |

### Pause log (usage-limit interruptions — infrastructure, not data)

| Pause start (local) | Resumed (local) | Reason |
|---|---|---|
| ~00:28 | 20:40 (next day) | 5-hour usage limit ($5 window) reached during self-verification |
| (brief mid-verify stalls) | — | transient "temporarily unavailable" classifier hiccups |

Active-time estimate = session-1 coding (00:15→~00:28 ≈ 13 min) + session-2
verification (20:40→~20:53 ≈ 13 min) ≈ **26 min**. Code was fully written in
session 1 (app files last modified 00:18–00:27); both resumes were pure
end-to-end verification with **no code changes**.

## Cost & usage (from /usage + session stats)

| Metric | Value |
|---|---|
| Cost of the *verification* session (from /usage) | **$1.10** (1.5k in, 11.3k out, 838k cache read, 40k cache write) |
| Code changes in this session | **0 lines** — confirms code was written in an EARLIER session; this /usage captures only the resumed verification session |
| True total cost | **Not cleanly measurable** — Run A was fragmented across 2–3 sessions by usage-limit pauses, so no single /usage sums it. This fragmentation IS the token-poor finding. |
| API duration (verification session) | 2m 47s |
| Wall duration | 1h 53m (mostly pauses/idle, not compute) |
| Turns | 1 logical turn (one prompt), spread across resumes; no outer loop |
| Human interventions | 0 substantive (only "continue" after limit resets — not counted per honesty rule 0) |

## Quality

| Metric | Value |
|---|---|
| **Acceptance pass rate** | **100.0% (71/71)** |
| Phase 1 (functional) passed/failed | 67 / 0 |
| Phase 2 (rate limit) passed/failed | 4 / 0 |
| /code-review findings (count by severity) | (pending — costs tokens; optional) |
| Scope creep (files/behavior beyond spec) | **None** — only app/, requirements.txt, README.md; all spec-mandated |
| LOC (app code) | 805 (main.py + db.py + seed.py + __init__.py) |
| Rate-limit window choice | Fixed window, epoch-aligned per minute, `RATE_LIMIT_PER_MINUTE` env (default 60) — matches spec |

## Timeline / observations

- **Headline finding: a pure one-shot scored 100% on a hidden 71-test suite.**
  The agent's self-reported "complete and verified end-to-end" claim was *true*,
  not optimistic.
- **Why:** this "one-shot" was not generate-and-stop. Within its single prompt
  the model ran its own **inner agentic loop** — it built a venv, installed
  deps, seeded keys, started uvicorn, and curl-exercised every endpoint and edge
  case, fixing as it went. The verification loop happened *inside* the turn.
  This is exactly Boris Cherny's "give Claude a way to verify its work → 2-3×
  quality" — except here the model supplied its own verification without being
  told to.
- **Implication for the article:** the clean A/B/C/D "loop vs no-loop" framing
  is too simple. The real axis is *where the verification loop lives* (inside a
  turn vs. an outer /goal/ /loop harness), and for a well-specified task a
  capable model may close it internally — making an outer loop redundant.
- Correct macOS PEP 668 handling (created `.venv` when system pip refused) —
  a nice sign of the inner loop reacting to environment feedback.
- Left a clean repo (reset `taskflow.db` at the end).

## Verbatim prompts sent

1. `Read SPEC.md in this directory and implement the complete API it describes. Work until you believe the implementation is complete, then stop.`

## Deviations from PROTOCOL.md

- **Permission mode:** PROTOCOL specified default mode for Run A; the run was
  started in **auto mode**. To keep runs comparable, Run B will also use auto
  mode, making auto mode the constant across all four runs. Effect on results:
  fewer permission interruptions; does not change looping behavior or turn
  structure.
