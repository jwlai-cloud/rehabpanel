# CLAUDE.md — guidance for Claude Code on this repo

## What this is
RehabPanel: a multi-agent rehab patient-panel scheduler for the **Qwen Cloud
Hackathon, Track 3 (Agent Society)**. Five "advocate" agents + a referee
negotiate which patients to follow up under scarce clinician slots. The thesis:
a single agent collapses the trade-off; a negotiating society reaches a higher
multi-objective score, and the gap widens with scarcity.

Read `docs/RehabPanel_Design_Doc.md` for the full design and `docs/handoff.md`
for the build plan before making changes.

## Hard guardrails (do not violate)
1. **No real or anonymized patient data — ever.** All data comes from
   `rehabpanel/generator.py`. The repo is public; keep it synthetic.
2. **Qwen-only models** via `rehabpanel/qwen_client.py` (the dashscope-intl
   endpoint = the Alibaba Cloud deployment-proof artifact). Don't add other LLM
   vendors. Differentiate agents by prompt + tool + model TIER.
3. **The scorer is pure Python, never an LLM** (`rehabpanel/scorer.py`). Both
   baseline and society are scored by the same function. Keep it deterministic.
4. **Framing is decision-support, not autonomous clinical scheduling.**
5. Keep agent messages short — the budget is a $40 voucher.

## State of the code
DONE & tested:
- `generator.py` — seeded synthetic caseload; `--ratio` controls scarcity (use >1).
- `scorer.py` — deterministic objective; `tests/test_scorer.py` passes (3 tests).
- `schema.py`, `qwen_client.py` — complete.
- All six agent prompts in `rehabpanel/society/prompts/`.

TODO (search the code for `TODO(claude-code)`):
- `society/advocates.py` — implement `critique()` and `propose_swap()` LLM calls.
- `society/orchestrator.py` — the LangGraph state machine is wired (draft →
  critique → conditional → arbitrate → loop → END). Implement the referee LLM
  call inside `node_arbitrate` (see the TODO there) so it resolves the top
  objection, applies the swap to `draft`, and returns a ledger entry.
- `baseline.py` — already functional; harden JSON parsing/validation.
- `benchmark.py` — add the matplotlib chart (mean gap vs ratio → results/gap.png).
- `ui/` — build the 3-panel demo (calendar + conflict ledger + scoreboard).

## Models & orchestration
- Model tiers live in `rehabpanel/qwen_client.py`. Current lineup: referee
  `qwen3.7-max`, baseline `qwen3.6-plus`, advocates `qwen3.6-flash`. Verify exact
  ids against the Model Studio model list (preview strings shift); stable fallback
  aliases are `qwen-max` / `qwen-plus` / `qwen-flash`.
- Orchestration uses **LangGraph** (`StateGraph`) as an explicit, deterministic
  state machine. Do NOT move the scorer or core state into the graph — the scorer
  stays pure-Python and external for reproducibility. Don't swap in an autonomous
  framework (CrewAI-style); the protocol is a fixed graph by design.

## Conventions
- Python 3.11+, run as modules (`python -m rehabpanel.generator`).
- Validate agent JSON output defensively; never let a bad LLM parse crash a run.
- Every referee ruling MUST append a human-readable line to the conflict ledger
  — it is the demo centerpiece.
- Run `make test` after touching the scorer; run `make benchmark` to regenerate
  the headline number.

## First task suggestion
Follow **NEXT_STEPS.md** — the ordered, current plan with definitions of done.

Implement `advocates.py` + the orchestrator loop, then run
`make data && make baseline && make society && make benchmark` and confirm the
society's value exceeds the baseline's at ratio >= 1.2. If it doesn't, the bug
is in negotiation, not the scorer.
