# Experiment Protocol

This document defines exactly how each run is executed, so the experiment is
reproducible and the comparison is fair. Deviations must be logged in
`results/deviations.md`.

---

## Constants (identical across all runs)

- **Model:** Claude Opus 4.8, effort: high, same Claude Code version (record it: `claude --version`).
- **Input:** the agent receives **only** `spec/SPEC.md` (copied into the run directory as `SPEC.md`).
- **Tech stack:** pinned by the spec (Python 3 + FastAPI + SQLite) so runs are comparable.
- **Working directory:** `runs/run-<X>/` — fresh, empty except `SPEC.md`. Each is its own git repo (`git init`) so diffs and commit counts are measurable.
- **Session:** each run starts with a **brand-new Claude Code session** (no shared context, no memory of other runs). Auto-memory should be irrelevant since directories are distinct; if the agent references another run, abort and restart that run (log it).
- **The acceptance suite** (`harness/acceptance_tests/`) is **never** shown, mentioned, or made readable to the agent. It runs only *after* a run is declared finished.
- **Permission mode:** auto mode for C and D (unattended); default for A and B.

## Timing & bookkeeping (every run)

1. Record start time (`date -u +%FT%TZ`) in `results/run-<X>.md`.
2. Run the agent per the run-specific procedure below.
3. Record end time when the stop condition fires.
4. Immediately capture: `/usage` output (tokens, cost), turn count, and the full transcript path.
5. Kill any server the agent left running.
6. From the repo root: `harness/run_tests.sh runs/run-<X>` → writes score to `results/run-<X>-score.json`.
7. Run `/code-review` (fresh session) on the run's final state; record finding count + severities.
8. Fill in the metrics table in `results/run-<X>.md`.

---

## Run A — One-shot (baseline)

**Rule:** exactly one prompt, zero follow-ups, no human feedback. When the agent
stops, the run is over — whatever the state.

**Prompt (verbatim):**

```
Read SPEC.md in this directory and implement the complete API it describes.
Work until you believe the implementation is complete, then stop.
```

- The agent MAY run its own tests/server within its single turn (that's the
  model's built-in inner loop — we're measuring the *absence of an outer loop*).
- No `/goal`, no `/loop`, no second prompt. If it asks a question, reply only:
  "Use your best judgment. This is the only guidance you will receive."
  (count it as a human intervention).

## Run B — Turn-based loop (human as the verification loop)

**Rule:** the human relays *only mechanical failure output* — no hints, no
design advice. This simulates the classic "human in the loop" pattern where the
human is the feedback channel.

1. Initial prompt: same as Run A's prompt.
2. After each agent stop: start the server, exercise the API manually per
   `harness/manual_check.md` (a fixed, scripted checklist — NOT the acceptance
   suite), and paste raw failing output back with only:
   `This failed: <output>. Fix it.`
3. Stop when the fixed checklist fully passes, or after **8 feedback turns**,
   whichever comes first.
4. Every feedback turn counts as a human intervention.

## Run C — Goal-based loop (/goal)

**Rule:** the human writes a verifiable stop condition once, enables auto mode,
and does not interact again.

1. Prompt: same as Run A's prompt, then immediately:
   ```
   /goal The API described in SPEC.md is fully implemented; the server starts
   clean; a smoke script you write yourself exercises every endpoint in the
   spec including auth, rate limiting, validation and pagination edge cases,
   and every check passes with the server output shown as evidence.
   Stop after 5 turns at most.
   ```
2. Auto mode on. Zero human messages until the goal clears or the turn cap hits.

**Turn cap note:** reduced from 15 to **5** for budget reasons (see
`results/deviations.md`). Given Run A reached 100% in a single turn's inner
loop, 5 outer turns is a generous ceiling for a goal-based comparison.

## Run D — Autonomous loop (/loop + verification skill)

**Rule:** the human designs the loop (a verification skill + a recurring
prompt), starts it, and walks away. This is the "loop engineering" posture.

1. Before starting: place `.claude/skills/verify-api/SKILL.md` (from
   `harness/loop_assets/`) into the run directory — a self-verification
   checklist derived ONLY from the spec (it does not reference the acceptance
   suite).
2. Initial prompt: same as Run A's prompt.
3. Then: `/loop 5m Continue implementing SPEC.md. Each iteration: run the
   verify-api skill, fix everything it finds, and record progress in
   PROGRESS.md. If verify-api passes completely, say LOOP-DONE and stop.`
4. Auto mode on. Stop the loop when the agent says LOOP-DONE, or after
   **2 hours**, whichever comes first.

---

## Honesty rules

0. **Usage-limit interruptions are infrastructure, not data.** If a run stalls
   because the account hits its usage limit: note the pause time, wait for the
   limit window to reset, and resume the SAME session (`claude --continue` /
   reopening the session) without adding any new instructions beyond
   "continue". The pause does not count as a human intervention. Wall-clock
   time is reported as **active time** (total minus pause windows); pauses are
   logged per run. Token/cost metrics are unaffected (they accumulate across
   the pause).
1. **No retries for a better story.** Each run is executed once. A run is
   restarted only for infrastructure failures (machine crash, API outage),
   never for bad agent output — and every restart is logged.
2. **The hidden suite stays hidden.** It is not in any run directory, not
   readable from them, and never quoted to the agent.
3. **Failures are data.** A 40% pass rate gets published like a 100% one.
4. **Verbatim prompts.** All prompts are given exactly as written here.
5. **Same-week execution.** All runs within the same week to hold the model
   version roughly constant; record `claude --version` per run.

## Threats to validity (to acknowledge in the article)

- n=1 per method — this is a case study, not a benchmark. Trends, not proofs.
- Run B's "mechanical feedback only" is stricter than real human collaboration.
- The model's inner agentic loop (running its own tests within a turn) blurs
  the one-shot baseline; we measure *outer-loop* differences.
- The spec is one task type (CRUD API); results may not generalize to UI or
  algorithmic work.
