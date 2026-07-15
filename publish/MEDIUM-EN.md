<!--
════════════════════════════════════════════════════════════════════
  MEDIUM PASTE GUIDE (do not copy this comment block)
  1. Put the title/subtitle into Medium's own title fields (below).
  2. Copy the body starting at "BODY START".
  3. Wherever you see [IMAGE: ...], drag-drop the PNG, then delete that line.
     Charts: article/charts/*@2x.png
  4. Medium does NOT support tables — they were turned into lists / charts.
     Code fences (```) paste fine.
  5. Tags (max 5 on Medium): suggested list at the bottom.
════════════════════════════════════════════════════════════════════

TITLE (Medium "Title" field):
I Tried to Test "Loop Engineering." The Loop Never Ran — and That Was the Lesson.

SUBTITLE (Medium "Subtitle"):
A controlled, reproducible experiment with Claude Code (Opus 4.8), real numbers, and an honest negative result.
-->

<!-- ═══════════ BODY START (copy from here down) ═══════════ -->

In June 2026, a new phrase took over the AI-coding corner of the internet: **loop engineering**. Peter Steinberger put it bluntly — *"You shouldn't be prompting coding agents anymore. You should be designing loops that prompt your agents."* Boris Cherny, who leads Claude Code at Anthropic, said the same about his own work: *"I don't prompt Claude anymore. I have loops running that prompt Claude and figuring out what to do. My job is to write loops."* Addy Osmani named the discipline, and by the end of the month Anthropic had published its own taxonomy of loops.

Every article I could find explained *what* loop engineering is. None of them ran a controlled experiment to find out *when it actually helps*. So I did — and the result surprised me enough that I almost didn't publish it. Then I realized the surprise **was** the finding.

> **TL;DR:** I gave the same well-specified task to Claude Code four ways, scored each against a hidden test suite it never saw, and measured cost, time, and quality. A plain one-shot prompt scored **100%**. A goal-based loop (`/goal`) also scored **100%** — and its outer loop fired **zero** extra iterations. For a task this clean, the loop was redundant.

## The layers nobody separates

Before the experiment, one distinction that most write-ups blur:

- **The inner loop** is what any capable coding agent does inside a *single* turn: reason → act (edit, run a test, hit an endpoint) → observe → repeat. You don't design this; it's how the model works.
- **The outer loop** is what *you* design: `/goal`, `/loop`, scheduled routines — a harness that re-prompts the agent across many turns or sessions until a stop condition holds. **This is what "loop engineering" actually means.**

Keep those two apart, because the whole result of this experiment lives in the gap between them.

Anthropic's own taxonomy sorts outer loops into four types:

- **Turn-based** — your prompt triggers it, stops when the model thinks it's done (plain prompt).
- **Goal-based** — your prompt triggers it, stops when an evaluator confirms a condition (`/goal`).
- **Time-based** — a schedule triggers it, stops when you cancel or the work completes (`/loop`, `/schedule`).
- **Proactive** — an event triggers it (no human), each task stops at its own goal (routines + workflows).

## The experiment

**One task, given four ways.** The task: build a **Task Manager REST API** from a single spec file — 15 endpoints, API-key auth, per-key multi-tenancy, rate limiting with headers, pagination, bulk operations, status transitions, tag normalization, and a pile of named edge cases. Substantial, but fully specified.

The four planned runs:

- **A — One-shot:** a single prompt, no follow-ups.
- **B — Turn-based:** a human relays only mechanical failure output each turn.
- **C — Goal-based:** `/goal` with a verifiable stop condition, then walk away.
- **D — Autonomous:** `/loop` + a self-verification skill, running unattended.

**The honesty machinery.** Quality is scored by a **71-test black-box acceptance suite** that drives the API over HTTP. The agent **never sees it** — which kills the obvious failure mode where a model "passes" by overfitting to tests it can read. Each run happens in a fresh directory and a fresh session. I wrote a reference implementation first and confirmed the suite gives it 71/71, so a low score would mean a real defect, not a broken test.

Everything — spec, hidden suite, prompts, raw metrics — is in the repo (link at the end). That's the point: you can re-run it and check me.

**A budget confession up front:** I ran this on a standard plan, not an enterprise token faucet. That constraint ended up shaping the findings, so I'm reporting it as data, not hiding it.

## What actually happened

### Run A — One-shot: 100%

I sent exactly one prompt: *"Read SPEC.md and implement the complete API it describes. Work until you believe the implementation is complete, then stop."*

The agent wrote 805 lines across four files — and then, **without being asked**, built a virtualenv, installed dependencies, seeded keys, started the real server, and curl-exercised every endpoint and edge case, fixing as it went. When it stopped and claimed "complete and verified end-to-end," I braced for optimism.

The hidden suite: **71/71. 100%.** The claim was true.

But look at *what* happened: this "one-shot" was not generate-and-stop. The model ran a full verification loop **inside its single turn**. This is exactly Cherny's rule — *"give Claude a way to verify its work and it will 2–3× the quality"* — except no one gave it anything. It supplied its own verification.

### Run C — Goal-based loop: also 100%, zero extra turns

Same task, but now I wrapped it in an outer loop. After the same opening prompt I set a goal:

> `/goal The API described in SPEC.md is fully implemented; the server starts clean; a smoke script you write yourself exercises every endpoint … and every check passes with the server output shown as evidence. Stop after 5 turns at most.`

Then I left. The `/goal` primitive runs a separate evaluator model after every turn to check the condition, and keeps the agent working until it holds or the turn cap hits.

Result: **`Goal achieved (8m · 1 turn · 39.4k tokens)`.** The evaluator confirmed "done" after the **first** turn. The outer loop — the whole point of loop engineering — fired **zero** additional iterations. Score on the hidden suite: **71/71 again.**

Why? Same reason as Run A. Inside its one turn, the model wrote a 70-assertion smoke test, ran it against a live server, byte-checked the seed output with `od -c`, then deleted its scratch files to ship clean. The verification loop lived *inside the turn*; the outer harness had nothing left to do.

[IMAGE: chart1_score_turns@2x.png — "Same task, same score — the outer loop did nothing"]

Two independent, fully-correct implementations that even made *different* defensible design choices (fixed vs sliding window rate limiting) — because a good spec leaves room for judgment, and the window-agnostic tests accept both. (Run A: 805 lines, 4 files. Run C: 1046 lines, 7 files. Neither drifted beyond the spec.)

## The cost finding that breaks a myth

The most repeated warning about loops is "watch out, they get expensive." The `/usage` breakdown showed *why* that warning is usually misattributed.

Run C's cost report listed **two** models:

```
claude-opus-4-8:  3.9k in, 39.4k out, 845k cache read, 51k cache write   $1.94
claude-haiku-4-5:   547 in,   277 out,      0 cache read, 27k cache write $0.036
```

That second line is the `/goal` **evaluator** — the "judge" that checks the stop condition each turn. It runs on cheap Haiku and cost **3.6 cents: ~1.8% of the run.**

So the loop is **not** expensive because of the evaluator. A loop gets expensive only when it triggers **extra turns** — each turn re-reads context, re-runs tools, and re-emits output. Here it triggered zero extra turns, so the whole goal-based run came in at **$1.97, all-in, for a 1046-line, 100%-correct API.** Cheap.

[IMAGE: chart2_cost_breakdown@2x.png — "The loop's overhead is 1.8%"]

The lesson generalizes: *the cost of a loop is roughly the cost of one turn × the number of turns it forces.* If your task closes in one turn, an outer loop is almost free. If it thrashes for twenty turns, that's where the bill — and the runaway-commit horror stories — come from.

## The token-poor reality (the part most posts skip)

Here's what didn't make the clean metrics table. Run A hit a wall — literally:

```
API Error: 402 {"error":"5-hour included-usage limit reached.
You have used the $5.00 allowance for this window."}
```

[IMAGE: your own '402 Usage limit reached' screenshot — this is the spot]

…at minute 12, mid-verification. The run had to be paused and resumed across **three** sessions over two days as usage windows reset. That's why Run A's cost can't even be cleanly summed: it's fragmented across sessions, and the `/usage` of the final session literally reports *"0 lines changed"* because the code was written in an earlier one.

I had planned four runs. **I ran two.** Runs B and D are designed and reproducible in the repo, but I didn't execute them — I ran out of budget I was willing to spend on a blog post.

This is not a footnote; it's a finding. Osmani warned in his original piece that loop economics "can swing wildly if you are token rich or poor." Loop engineering — especially the autonomous, run-while-you-sleep kind — quietly assumes a generous token budget. If you're on a normal plan, the honest headline is: *the outer loop you were told to build may cost more than the thing it automates, and you'll feel it at minute 12.*

## So — was the experiment "wrong"?

A fair reader (and my own conscience) asked: *you set out to test loops, but the loop never actually looped. Isn't that a broken experiment?*

Partly, yes — and it's worth stating plainly. I did **not** measure how a loop performs when it runs many iterations. I measured something narrower and, I think, more useful: **for a well-specified, self-contained, single-turn-verifiable task, the outer loop is redundant.** The model's inner loop already closes the gap.

That's not "loops don't work." It's "loops solve a problem this task didn't have." And that reframes the real question.

## When does an outer loop actually earn its cost?

Cross-referencing Anthropic's taxonomy with what I observed, an outer loop pays off precisely when the **inner** loop *can't* close on its own — when at least one of these is true:

- **The spec is ambiguous or evolving.** Each iteration is a chance to correct course. A crisp spec (like mine) removes this need entirely.
- **"Done" depends on external state.** A flaky dependency, a real database with drift, CI turning red, a PR getting review comments — things the model can't settle inside one turn because reality changes between turns.
- **The work doesn't fit one context window.** A large migration the model has to chip away at across turns, using a state file as memory.
- **The work is recurring.** Same task, new inputs, on a schedule — morning triage, dependency sweeps. Here the loop isn't optional; it's the whole design.

My task had **none** of these. Which is exactly why the loop sat idle.

**A practical rule of thumb:** before you design a loop, ask whether a good spec plus a verification the model can run itself would close the task in one turn. If yes, write the spec and the check — not the loop. Loop engineering is powerful, but it's the answer to *"the inner loop can't finish this alone,"* not a default posture.

## Honest limitations

- **n = 1 per method.** This is a case study, not a benchmark. Trends, not proofs.
- **Only two of four runs executed** (budget). B and D are in the repo, unrun.
- **One task type** (a CRUD API). Results may not transfer to UI work, algorithmic problems, or genuinely open-ended tasks.
- **The inner/outer loop distinction blurs the "one-shot" baseline** — Run A wasn't a pure single shot, because the model loops internally. That blur is itself the main finding.

## Reproduce it

The full harness — spec, the hidden 71-test suite, the scorer, both runs' output, every raw metric, and the two unrun run designs — is here:

**→ https://github.com/zexy2/loop-engineering-experiment**

Clone it, point it at your own agent, and check whether your task needs the loop at all before you build one.

*If you take one thing: separate the inner loop from the outer loop, and don't pay for the second when the first already finished the job.*

<!-- ═══════════ BODY END ═══════════

SUGGESTED MEDIUM TAGS (max 5):
  Loop Engineering, AI, Claude, Software Engineering, Developer Tools

IMAGE ORDER:
  1. chart1_score_turns@2x.png   → after "What actually happened"
  2. chart2_cost_breakdown@2x.png → in the cost section
  3. your 402 screenshot          → in the "token-poor reality" section
  (Optionally use chart1 as the cover image.)
-->
