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

<!-- next entries appended below as steps land -->
