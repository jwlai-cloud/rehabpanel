# RehabPanel — Build Log

Running record of the build (spec-driven). Newest first. Each entry: what
changed, why, how verified. Pairs with `spec_negotiation.md`.

## 2026-06-30

### Repo hardening (PR #1, branch `chore/repo-hardening`)
- LICENSE: `<YOUR NAME>` → `Junwei Lai` (GitHub detects MIT in About).
- Added `.github/workflows/ci.yml`: `make test` on push/PR — locks the scorer.
- Added root `conftest.py`: fixed pre-existing `ModuleNotFoundError: rehabpanel`
  when running `make test` from a fresh checkout (repo root now on `sys.path`).
- Verified: `make test` → `3 passed`. CI `test` check green on PR #1.
- `main` branch-protected: PR required + `test` check required (strict), 0
  approvals (solo), admin escape-hatch on.

### Spec + plan (branch `feat/negotiation`)
- Wrote `docs/spec_negotiation.md` — the negotiation build contract.
- Decision: dual path (live Qwen LLM + deterministic offline reference) behind
  one contract, so CI/tests/judges reproduce the gap key-free without burning
  the $40 voucher. Scorer stays external/pure-Python (guardrail #3 intact).

### Negotiation core: advocates + referee (steps 1–3, 5)
- `qwen_client.is_offline()` — picks LLM vs deterministic path.
- `advocates.py` — `critique()` + `propose_swap()` for all 5 advocates, both
  paths; defensive JSON parse (`parse_json_list/obj`). Offline swaps are
  provably non-regressing (continuity → open/primary or non-worsening mutual
  swap; preference → same-clinician preferred-mode open slot; seat → open slots
  only, no zero-sum displacement).
- `orchestrator.node_arbitrate` — referee resolves hot objections, applies
  feasible swaps (`_apply_move`), logs one readable ledger line each
  (`'Tue 10:00 — ...'`). Offline batches compatible swaps/round; online resolves
  the top one/round (budget). Stall flag + ROUND_CAP guarantee termination.
- `baseline.py` — offline acuity-first greedy fallback; online parse hardened
  (validate ids, drop dupes, one re-prompt).

**GO/NO-GO (offline, seeds 7/13/42) — society beats baseline, all feasible:**

| ratio | mean gap |
|------:|---------:|
| 0.8 | 49.3 |
| 1.0 | 73.0 |
| 1.2 | 79.0 |
| 1.3 | 82.3 |
| 1.5 | 78.7 |

Gap widens through the conflict-onset region (0.8→1.3), plateaus at 1.5 as the
society hits its swap/round ceiling. Society's win comes from continuity (e.g.
30→13 breaks) + same-clinician preference fixes, holding acuity coverage at
24/24. Locked as `tests/test_negotiation.py`. Suite: 13 passed.

### Benchmark chart (step 4)
- `benchmark.py` now writes `results/gap.png` (matplotlib, Agg) alongside
  `metrics.json`: mean society−baseline gap vs ratio, with a seed min–max band,
  `demand=capacity` marker, and zero line. Respects `is_offline()` (default
  offline = free + reproducible; warns if run live).
- 5 seeds × 5 ratios = 25 runs, all feasible, min gap +33 (society wins every
  single run): 0.8→46, 1.0→64, 1.2→65, 1.4→72, 1.6→66.

### PR #2 review fixes (bots: gemini, sourcery)
- **[HIGH] crash guard** — `node_arbitrate` validated `move` is a dict + pid/sid
  exist before the referee call; advocate `propose_swap` rejects non-dict `move`
  at source. A malformed LLM move can no longer raise `AttributeError`.
- **[MED]** swap now updates *both* patients' rationale (`referee: swap`), not
  just the mover's — accurate tracking in the schedule + UI.
- benchmark `chart()` excludes infeasible runs (logs the count) so the curve
  reflects only constraint-satisfying plans.
- tests: termination contract (`round <= round_cap()`, stalled-or-no-hot) +
  `propose_swap` malformed/non-dict/transport-error coverage. Suite 13 → 17.

### Scrub-the-negotiation UI + one-conflict-per-round
- Orchestrator now resolves ONE objection per round (faithful to the design's
  play-by-play ledger) and emits a per-round `snapshots` list →
  `data/society_rounds.json`. `round_cap()`: offline runs to convergence (~free),
  online stays capped at 6 (voucher).
- `ui_export` builds a per-round timeline (score + cells + cumulative ledger).
- `ui/index.html`: scrubber (◀ ▶ Play slider) animates the negotiation — value
  climbs −141→−70 round by round, moved cards glow, ledger fills, scoreboard
  tracks the live round. Seed 7 @ 1.3 → 10 rounds.

## 2026-07-01

### Scorer reweight — value breadth of care
- `DEFAULT_WEIGHTS` now values patients-seen: `seen=5` per scheduled patient
  (acuity 10, overdue 1, continuity 2, pref 1). Patients-seen is the primary
  clinical good, so the objective rewards breadth of care. Scores flip positive.
  `make benchmark` re-run: society wins every scarcity level (means +28→+44, min
  +18). Locked by `test_scorer.py` — suite green.

### Entry-point consolidation + replay-as-default
- Removed the separate `/stream` page (`ui/stream.html` + route) and the offline
  **Play** button. Schedule view now has **▶ Replay** — a bundled recording of a
  REAL Qwen negotiation (`/api/replay`, key-free, the **default** view) — and
  **◉ Run live (Qwen)** (`/api/stream`, fresh real run). No deterministic-society
  score is ever shown in the UI; the score spark grows per round.
- Bundled `rehabpanel/recordings/negotiation.jsonl` (fully synthetic) so Replay
  works on deploy with no key. Deploy = **Config A** (`REHABPANEL_OFFLINE=1` + key;
  Run live forces live on click). Model ids removed from the UI (tier labels only,
  since they get swapped as quota/preview strings shift).

### Richer negotiation transcript (A + B)
- **A** — every advocate that objects now speaks each round with its own reason
  (not just the winner): all five voices visible.
- **B** — the flagship referee writes its ruling rationale **in prose** (live); the
  deterministic rule string is the reproducible fallback + ledger line. The
  **decision stays deterministic** (`_decide` on the priority ranking) — the LLM
  adds reasoning, never changes the outcome or the score.
- Live re-capture (advocates on a strong tier, referee flagship): **12 rounds,
  160 → 181 (+21)**, all-voices + prose rulings; bundled as the Replay demo. Live
  converges below the offline ceiling (~212) because LLM critique is less
  exhaustive than the rule critique — honest, not a scorer artifact.
- Tests updated for the new transcript shape (generic supports/opposes turns →
  coalition arrays). Suite **36 passed**.
