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

<!-- next entries appended below as steps land -->
