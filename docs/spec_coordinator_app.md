# Spec: Coordinator App — RehabPanel redesign

Turns the single-page demo into a multi-view app where the **agent society
assists a nurse coordinator** to plan the week and **re-plan when reality
breaks**. Output of the grilling session (see `docs/BUILD_LOG.md`). The PR(s) are
the review gate (branch protection on `main`).

## Objective

Make the AI-agent society the visible, central planner — and prove Track 3 on
screen: (a) role decomposition, (b) conflict resolution via dialogue,
(c) measurable gain over a single-agent baseline. The coordinator sets the
constraints and approves; the society does the multi-objective negotiation and
*shows its work*.

## Framing (locked)

- **Agents = planner. Human = pilot/approver.** Coordinator never hand-places
  patients; they set roster / caseload / rules, press **Re-plan**, review the
  ledger, approve. The agents do the planning a coordinator otherwise does in
  their head or a dumb rules engine does crudely.
- **Incident-driven re-planning is the core loop.** Reality breaks (nurse sick,
  leave, patient cancels) → live score drops → Re-plan → society re-negotiates →
  score recovers → ledger explains.

## Locked decisions (from the grill)

1. **Negotiation view, 3 lanes:** agent roster (5 advocates + referee, each
   tagged with its objective + model tier) · live **hybrid** negotiation log
   (per round: all objections collapsed `[Continuity×3, Window×1…] → ruling →
   +Δ`, click to expand) · score-per-round timeline vs baseline line.
2. **Engine emits per-round `objections` + post-round score** (score computed
   outside the graph, in the API/export layer — scorer stays external).
3. **3 scripted incidents:** nurse sick (drop slots) · patient cancels (free a
   slot) · urgent referral (add A9 patient). Each: apply → score drops → Re-plan.
4. **Warm replan:** re-plan starts from the *current disrupted plan* and repairs
   only what broke (minimal disruption). Baseline replans cold for contrast.
5. **Replan metric = disruption (displayed KPI), NOT raw value.** Honest: a cold
   baseline can match/beat warm on raw value, so we do **not** claim a value win
   on replan. The society's win is **minimal churn** (`changed N/total
   appointments`) + fewer rounds. Computed as a pure diff *outside* the locked
   scorer. The **initial-plan value gain** (society > baseline, widening with
   scarcity) stays the headline measurable gain.
   - *Documented alternative (not built):* bake a stability term into a separate
     replan objective — `value − w_stability·churn`. Rejected for now: edits the
     locked scorer, makes it stateful, forks the objective, deadline risk. On
     record for future.
6. **Charts (3):** score-per-round timeline · session timeline (dips per
   incident, recoveries per replan) · capacity gauge. KPI tiles: capacity %,
   continuity breaks, overdue days, high-acuity coverage, disruption.
7. **Alerts = derived flags off scorer output** (incident banner + standing
   flags: high-acuity unscheduled, capacity >100%, overdue unseen). NOT a
   configurable alert engine. They drive the demo: flag fires → Re-plan → clears.
8. **Backend = FastAPI, single in-memory session**, seeded, behind a **repository
   interface** so a real DB drops in later (in-memory impl now; DB = future,
   revisit). Respects `is_offline()` (deterministic without key, live Qwen with).
9. **Weights are causal on the negotiation**, not just the score: live → weights
   in prompts; offline → advocate severities scale by the matching weight. The
   Rules view is a real lever and proves agents optimize the stated objective.
10. **Phased build; `main` stays a shippable submission throughout.** Thesis-first
    order; cut Phase 4 depth before the core if time runs short.

## Architecture

```
Browser (views)  ──HTTP──►  FastAPI  ──►  Store (interface)
                                     │       └─ InMemoryStore (now) / DbStore (later)
                                     └─►  engine (in-memory, no file IO):
                                           generator.generate() -> tables
                                           baseline.plan(tables, weights)
                                           orchestrator.negotiate(tables, seed_draft, weights)
                                           scorer.score(...)  ← pure Python, unchanged
```

**Endpoints:** `GET /state` · `POST /incident/{sick|cancel|referral}` ·
`POST /replan` · `POST /rules` (weights) · `POST /reset`.

**Engine refactor (Phase 0):** `generate()` returns tables (still writes files
for the CLI); `baseline.plan()` and `orchestrator.negotiate()` take in-memory
tables + optional seed draft + weights and *return* state; existing `run()` CLIs
become thin wrappers (file IO). `make society` etc. keep working. Scorer logic
untouched.

**Snapshot schema (per round):** `{round, draft, rulings, objections}`; the
export/API layer scores each snapshot → adds `score`, `disruption`.

## Views

1. **Caseload** — patient backlog table (acuity, program, overdue, primary, pref)
   + click → detail card. The demand / problem framing.
2. **Team** — nurse roster + capacity; buttons to mark **sick / leave** (incident).
3. **Rules** — priority weight sliders (acuity/overdue/continuity/pref); causal →
   re-plan. Shows "what we optimize."
4. **Schedule / Negotiation** — calendar (current plan) + the 3-lane negotiation
   view (roster · hybrid log · score timeline) + **Re-plan** + incident buttons.
   The hero.
5. **KPIs** — capacity gauge, KPI tiles, session timeline, alert strip.

## Phase plan

| Phase | Build | Shippable |
|---|---|---|
| 0 | engine refactor (in-mem args, per-round objections, warm-start, weights-causal) + tests | tests green |
| 1 | FastAPI + endpoints + Store interface (in-mem impl) | API smoke |
| 2 | Negotiation view + score timeline | ✅ demo |
| 3 | incident loop + warm replan + disruption KPI + alerts | ✅ demo |
| 4 | Caseload · Team · Rules · KPI dashboard + charts | ✅ full |
| 5 | new 3-min video + refresh all docs/artifacts | ✅ submission |

## Boundaries

- **Always:** scorer pure-Python + external + CI-locked; Qwen-only; synthetic
  data; `main` stays a valid submission; defensive parsing; short agent messages.
- **Ask first:** any change to `scorer.py`/`test_scorer.py` or the objective;
  new deps beyond FastAPI/uvicorn; baking stability into the scorer.
- **Never:** real data; another LLM vendor; commit a key; LLM scorer.

## Track 3 mapping (on screen)

- **Role decomposition / assignment** → agent-roster lane (5 distinct objectives
  + tiers).
- **Dialogue / disagreement / conflict resolution** → hybrid negotiation log
  (objections → referee ruling → who lost).
- **Measurable gain** → initial value vs baseline (headline) + replan disruption
  efficiency (adaptivity).

## Docs/artifacts to keep in sync (Phase 5 + as phases land)

README · SUBMISSION.md · RehabPanel_Design_Doc.md · architecture.mermaid/.svg ·
BUILD_LOG.md · video_script.md + the live Artifact demo.
