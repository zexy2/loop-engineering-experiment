# Deviations from PROTOCOL.md

## Run A
- Started in **auto mode** instead of default mode. To keep runs comparable,
  auto mode is now the constant across all runs.
- Two usage-limit pauses (5-hour $5 window). Handled per honesty rule 0:
  resumed same session with "continue", pauses excluded from active time.

## Scope reduction (budget)
- Only **Run A** (one-shot) and **Run C** (/goal) are executed.
- **Run B** (turn-based) and **Run D** (autonomous /loop) are designed and
  reproducible in this repo but NOT run, due to the author's usage budget.
  This is itself a finding: loop engineering presumes a generous token budget.
- Run C turn cap reduced 15 → **5** to bound cost.
