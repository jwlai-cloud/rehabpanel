# CLAUDE.md — guidance for Claude Code on this repo

## What this is
RehabPanel: a multi-agent rehab patient-panel scheduler for the **Qwen Cloud
Hackathon, Track 3 (Agent Society)**. Five "advocate" agents + a referee
negotiate which patients to follow up under scarce clinician slots. The thesis:
a single agent collapses the trade-off; a negotiating society reaches a higher
multi-objective score, and the gap widens with scarcity.

Read `docs/RehabPanel_Design_Doc.md` (design, incl. §9 the coordinator app) and
`docs/spec_coordinator_app.md` before making changes. `docs/BUILD_LOG.md` is the
running record.

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

## State of the code — SHIPPED
Core + coordinator app are built and tested (`make test` = 30 tests, CI-locked).
- `generator.py` — seeded synthetic caseload (`--ratio` scarcity); `generate()`
  returns the tables in-memory (still writes files for the CLI).
- `scorer.py` — deterministic objective (pure Python), locked by `tests/test_scorer.py`.
- `society/advocates.py` — `critique()` + `propose_swap()` (LLM path + deterministic
  offline path); priority weights scale advocate severities (causal).
- `society/orchestrator.py` — `negotiate(tables, seed_draft, weights)`: draft →
  critique → negotiate → arbitrate loop, **warm-start replan**, per-round objections;
  the referee logs the conflict ledger. Scorer stays external. Round 0 draft is a
  deterministic acuity-first fill (no LLM); autonomy lives in critique + ruling.
  Per-round transcript surfaces **all five advocates' objections** (each its own
  reason), and the **referee's ruling is written by the flagship model in prose**
  (live) with the deterministic rule string as the reproducible fallback — the
  decision itself stays deterministic (`_decide` on the priority ranking).
- `baseline.py` — single-agent (LLM + offline greedy), hardened parse.
- `benchmark.py` — scarcity sweep → `results/gap.png`.
- **Coordinator app:** `api.py` (FastAPI) + `state_service.py` (in-memory session
  behind a `Store` interface; incident → warm re-plan; causal rules) +
  `ui/app.html` (5-view SPA). `make serve`. Container: `Dockerfile` + `docs/deploy.md`.
  Entry points (consolidated): **▶ Replay** = replays a bundled recording of a real
  Qwen negotiation (`/api/replay`, no key/tokens — the SPA's DEFAULT view); **◉ Run
  live (Qwen)** = a fresh real negotiation streamed round-by-round (`/api/stream`,
  needs the key). No offline-deterministic result is ever shown in the UI. Deploy =
  Config A (`docs/deploy.md`): `REHABPANEL_OFFLINE=1` + key.
- The UI never names a model — advocates show as "fast tier", the referee as
  "flagship tier" — because the exact ids get swapped.
- Demo video + render tooling are kept **local only** (not in the repo) — for
  personal demo/practice.

## Models & orchestration
- Model tiers live in `rehabpanel/qwen_client.py`, all env-overridable
  (`REHABPANEL_{REFEREE,BASELINE,ADVOCATE}_MODEL`). Differentiate by TIER, not vendor:
  referee = flagship, advocates = fast, baseline = strong single. Exact ids shift
  (preview strings) and the voucher quota per id varies, so treat them as swappable —
  the shipped live demo pumps advocates to `qwen3.7-plus` + referee `qwen3.7-max`
  (more quota + richer reasoning). Never surface an id in the UI (see above).
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

## Working on this repo now
The build is shipped. Source of truth: `docs/spec_coordinator_app.md` (the app)
and `docs/RehabPanel_Design_Doc.md` (design + engine); `docs/BUILD_LOG.md` for history.

- `make test` after anything scorer-adjacent · `make serve` to run the app ·
  `make benchmark` to regenerate the headline gap.
- Guardrails stay sacred: Qwen-only, and the scorer stays pure-Python + external
  + CI-locked. If the society ever fails to beat the baseline at ratio >= 1.2,
  the bug is in negotiation, not the scorer.
