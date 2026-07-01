# Spec: Negotiation Society (advocates + referee)

Implements the stubbed core of RehabPanel — the `feat/negotiation` branch.
Pairs with `RehabPanel_Design_Doc.md` (§3–4). Historical: this is the engine
spec; the app that operates it is specced in `spec_coordinator_app.md`.
This spec is the review contract; the PR is the human gate (branch protection on
`main` requires it).

## Objective

Make the multi-agent **society** out-score the single-agent **baseline** on the
deterministic scorer, with the gap widening as scarcity (`demand_capacity_ratio`)
rises. Concretely: implement `advocate.critique()`, `advocate.propose_swap()`,
and the referee in `orchestrator.node_arbitrate()` so `make society` emits a
negotiated schedule + a human-readable conflict ledger, and the benchmark shows
`society_value > baseline_value` at ratio ≥ 1.2.

Success = the thesis is demonstrable **and reproducible without burning the
$40 voucher**.

## Tech Stack

Python 3.11+, LangGraph (`StateGraph`, already wired), OpenAI SDK → dashscope-intl
(Qwen Cloud), pydantic, matplotlib, pytest. No new dependencies.

## Key decision: dual path (LLM + deterministic offline)

The thesis is that the **negotiation protocol** produces the gap. We implement it
two ways behind one contract:

- **LLM path** (key present): advocates run on `qwen3.6-flash`, referee on
  `qwen3.7-max`. Real agents argue. This is the demo. (ADR-3)
- **Offline path** (`qwen_client.is_offline()` — no `DASHSCOPE_API_KEY`, or
  `REHABPANEL_OFFLINE=1`): a pure-Python deterministic reference negotiator that
  implements the *same* critique/arbitrate objectives by rule. Lets CI, tests,
  and judges reproduce the benchmark gap key-free, and isolates the value of the
  negotiation *structure* from LLM cleverness (a clean ablation).

Both paths feed the **same external scorer** (unchanged, still pure-Python and
outside the graph — guardrail #3 preserved). The referee never calls the scorer;
it arbitrates on global weights + advocate marginal values, per the design.

## Contracts (shapes the code must honor)

- `critique(draft, context) -> list[objection]`, where
  `objection = {patient_id, slot_id|null, severity:1..10, reason:str, by:str}`.
  Capacity advocate emits `{slot_id, clinician_id, severity:10, reason}` (veto).
- `propose_swap(objection, state) -> {move:{patient_id, slot_id}, marginal_value:float, reason}`.
- Referee `node_arbitrate` resolves the top hot objection (severity ≥
  `SEVERITY_EXIT`), applies the winning swap to `draft` **feasibly** (no
  double-book, no capacity breach — displaced patient re-homed to a free slot or
  dropped), appends ONE ledger line, increments `round`. `ROUND_CAP` guarantees
  termination.
- Every LLM parse is defensive: malformed output → `[]`/no-op, never a crash.

## Project Structure (files touched)

```
rehabpanel/qwen_client.py        → add is_offline()
rehabpanel/society/advocates.py  → implement critique + propose_swap (+ offline rules)
rehabpanel/society/orchestrator.py → implement node_arbitrate + feasible swap apply
rehabpanel/baseline.py           → offline greedy fallback + harden JSON parse
rehabpanel/benchmark.py          → matplotlib gap chart → results/gap.png
tests/test_negotiation.py        → NEW: GO/NO-GO as a deterministic CI test
ui/                              → 3-panel demo (calendar · ledger · scoreboard)
```

## Code Style

Match the repo: terse module docstrings stating *why*, compact functions,
defensive JSON parsing, run-as-module (`python -m rehabpanel.society.orchestrator`).
Example (defensive parse, the repo's house style):

```python
def parse_json_list(text: str) -> list:
    """Never let a bad LLM parse crash the graph; return [] on any failure."""
    try:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        return json.loads(m.group(0)) if m else []
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []
```

## Testing Strategy

pytest, `make test`. `test_scorer.py` stays the locked objective (do not touch).
New `test_negotiation.py` runs fully **offline** (deterministic path), so CI
proves the thesis without a key:
- society plan is feasible;
- `society_value >= baseline_value` at ratio 1.3 across seeds;
- mean gap at ratio 1.5 ≥ mean gap at ratio 1.2 (widening);
- referee emits ≥1 ledger entry and the final draft differs from the draft.
LLM-path parsing is unit-tested with monkeypatched `chat`.

## Boundaries

- **Always:** run `make test` after touching anything scorer-adjacent; keep the
  scorer pure-Python and outside the graph; Qwen-only; synthetic data only;
  defensive JSON parsing; short agent messages.
- **Ask first:** changing scorer weights or the objective; adding dependencies;
  changing `scorer.py` / `test_scorer.py`.
- **Never:** real/anonymized data; another LLM vendor; commit a key; let a bad
  parse crash a run; an LLM scorer.

## Success Criteria

1. `make data RATIO=1.3 && make baseline && make society` runs key-free
   (offline path) and `make society` writes a non-empty `conflict_ledger.json`
   with readable rulings; final society plan ≠ initial acuity-first draft.
2. `pytest -q` green, including `test_negotiation.py` proving society ≥ baseline
   at ratio ≥ 1.2 and a widening gap.
3. `make benchmark` writes `results/metrics.json` + `results/gap.png`.
4. With `DASHSCOPE_API_KEY` set, the same commands run the live Qwen agents
   (LLM path) unchanged. (The demo UI is now the coordinator app — `make serve`.)

## Open Questions (non-blocking; resolved by defaults)

- Exact Qwen model ids drift; current tiers kept, env-overridable, fallback
  aliases documented in `qwen_client.py`. Verify against Model Studio before the
  live demo.
- Scorer weights are the design defaults; tuning is "ask first" and out of scope
  for this PR.
