# NEXT_STEPS — RehabPanel handoff

Current, prioritized plan. Reflects the repo *as it stands now* (post-LangGraph
refactor + lazy-client fix). For design rationale see `docs/RehabPanel_Design_Doc.md`;
for guardrails see `CLAUDE.md`.

## Where the repo is right now

**Done & verified (runs key-free):**
- `generator.py` — seeded synthetic caseload; `--ratio` scarcity knob (verified: 56 patients vs 43 slots at 1.3).
- `scorer.py` — deterministic objective fn; `tests/test_scorer.py` green (3/3).
- `qwen_client.py` — lazy client, current tiers (`qwen3.7-max` / `qwen3.6-plus` / `qwen3.6-flash`).
- `society/orchestrator.py` — LangGraph state machine compiles & runs end-to-end (draft → critique → conditional → arbitrate → loop → END).
- All six agent prompts; baseline scheduler (functional, needs hardening).

**Stubbed (the actual work):**
- `society/advocates.py` → `critique()` and `propose_swap()` are `NotImplementedError`.
- `society/orchestrator.py` → `node_arbitrate` is a no-op placeholder.
- `benchmark.py` → no chart yet. `ui/` → empty.

Because the advocates are stubbed, the society currently emits the acuity-first
draft with **0 rounds** and scores identically to the baseline. That is the
expected pre-implementation state — the gap appears once negotiation works.

## Critical path (in order)

### 1. Implement `advocate.critique()`  ← start here
For each advocate: render the current draft + its slice of context, call
`chat(msgs, model=ADVOCATE_MODEL)` with `prompts/<name>.md` as the system message,
and **defensively** parse a JSON list of objections. Never let a bad parse crash
the graph — wrap in try/except, return `[]` on failure.
- **Done when:** `make society` reports a non-zero objection count and >0 rounds.

### 2. Implement `node_arbitrate` (the referee)
Take the highest-severity objection (and any contesting the same slot), call the
referee on `qwen3.7-max` with `prompts/referee.md`, apply the winning swap to
`draft`, and return a one-line `ledger` entry. The `round`/`ROUND_CAP` guard
already guarantees termination — keep it.
- **Done when:** `data/conflict_ledger.json` contains readable rulings and the
  final `draft` differs from the initial acuity-first draft.

### 3. GO / NO-GO checkpoint  ← do not skip
Run `make data RATIO=1.3 && make baseline && make society`, score both. **The
society must out-score the baseline.** Then check it widens at `RATIO=1.5`.
- If the society does **not** win, the bug is in negotiation, not the scorer
  (the scorer is locked by tests). Fix before building anything else — the
  entire submission rests on this gap.

### 4. Finish `benchmark.py`
Add the matplotlib chart: mean (society − baseline) value vs `demand_capacity_ratio`
across `SEEDS`, saved to `results/gap.png`. This chart is the headline figure.
- **Done when:** `make benchmark` writes `results/metrics.json` + `results/gap.png`.

### 5. Harden `baseline.py`
The single-agent JSON parse is naive. Validate slot/patient ids, drop dupes, and
re-prompt once on malformed output so a bad baseline run doesn't skew the comparison.

### 6. Demo UI (`ui/`)
Three panels from real output files: weekly **calendar** (assignments), scrolling
**conflict ledger**, live **scoreboard** (society vs baseline per objective).
Static HTML reading the JSON is enough — no backend needed.

## Submission assets (parallel track, start by week 3)

- 3-min video: 20s problem → narrate one Tuesday-10:00 conflict from the ledger → cut to `gap.png` → one line of honest scope ("decision support, synthetic data").
- Devpost text: what it does / how we built it / what's next.
- **Eligibility paragraph:** state it's a **new build** for the submission window.
- Public repo + MIT `LICENSE` (swap `<YOUR NAME>`), architecture diagram included.
- `qwen_client.py` is the linkable **Alibaba Cloud deployment-proof** artifact.
- Write the **blog post** too — separate near-free prize.

## Rough timeline to Jul 9

| When | Focus |
|------|-------|
| Now → +1 wk | Steps 1–3 (advocates, referee, **GO/NO-GO**) |
| +1 → +2 wk | Steps 4–5 (benchmark chart, harden baseline) |
| +2 → +3 wk | Step 6 (demo UI) + start video/write-up |
| Final wk | Record video, finalize docs, submit + blog post |

## Guardrails (repeat of CLAUDE.md, because they matter)
- Synthetic data only — never real/anonymized records in a public repo.
- Qwen-only models via `qwen_client.py`.
- Scorer stays pure-Python and **outside** the LangGraph graph.
- Keep agent messages short — the budget is a $40 voucher.
- Framing is decision-support, not autonomous clinical scheduling.
