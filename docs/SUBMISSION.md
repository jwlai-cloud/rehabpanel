# RehabPanel — Submission Packet

Global AI Hackathon Series with Qwen Cloud · **Track 3: Agent Society**
Deadline 2026-07-09 14:00 PDT · Public repo · MIT · Fully synthetic data.

---

## One-liner

Five "advocate" agents and a charge-nurse referee **negotiate** which rehab
patients to follow up under scarce clinician slots. A single agent collapses the
trade-off; the negotiating society reaches a higher multi-objective score — and
the advantage widens as demand outstrips capacity.

## What it does

Rehab nurses must decide each week **which patients to see, when, and in what
mode** (clinic / tele / home) under fixed clinician time. Clinical acuity,
overdue follow-ups, continuity of care, capacity, and patient preference all
compete for the same slots. RehabPanel runs two pipelines on the **same** seeded
synthetic caseload, scored by the **same** deterministic function:

- **Baseline** — one Qwen agent, single pass.
- **Society** — Clinical-Priority, Follow-up-Window, Continuity, Capacity, and
  Preference advocates file objections; a Charge-Nurse referee resolves them one
  conflict per round and logs each ruling to a **conflict ledger**.

## The measurable result (the point of Track 3)

`make benchmark` — 5 seeds × 5 scarcity levels, deterministic, reproducible:

| demand / capacity | mean value gap (society − baseline) | min gap | feasible |
|------:|------:|------:|:--:|
| 0.8 | +45.2 | +29 | ✓ |
| 1.0 | +64.2 | +46 | ✓ |
| 1.2 | +65.2 | +34 | ✓ |
| 1.4 | +70.8 | +44 | ✓ |
| 1.6 | +66.6 | +52 | ✓ |

The society **out-scores the baseline on every single run** (min gap > 0), the
advantage **grows through the conflict-onset region** (0.8 → 1.4), and every plan
stays capacity-feasible. Headline figure: `results/gap.png`. The gain comes from
the society repairing continuity and preference that the single agent abandons,
while holding high-acuity coverage constant.

## How we built it

- **Qwen Cloud only.** All agents call Qwen via `rehabpanel/qwen_client.py` →
  OpenAI-compatible `dashscope-intl.aliyuncs.com` endpoint (Alibaba Cloud). This
  file is the deployment-proof artifact.
- **Distinct capabilities under one vendor** (ADR-3): differentiation by
  **role/prompt + tool + model tier** — referee on `qwen3.7-max`, advocates on
  cheap `qwen3.6-flash` (also the token-budget guard), baseline `qwen3.6-plus`.
- **LangGraph** state machine: draft → critique → (conditional) → arbitrate →
  loop → END. Deterministic control flow; autonomy lives inside each agent.
- **Pure-Python deterministic scorer** (`scorer.py`, no LLM) scores both
  pipelines identically — reproducibility is the differentiator over typical
  entries. Locked by unit tests in CI.
- **Dual execution path**: live Qwen agents for the demo; a deterministic
  offline reference negotiator (`REHABPANEL_OFFLINE`) implementing the same
  critique/arbitrate contract so CI, tests, and judges reproduce the gap
  key-free without spending the voucher.
- **Synthetic generator** with engineered scarcity & conflict (overdue spread,
  shared-clinician clustering, preference/capacity collisions). No real data.
- **3-panel demo UI** (static HTML): weekly calendar, scrolling conflict ledger,
  live scoreboard — with a scrubber that replays the negotiation round by round.
- **CI**: GitHub Actions runs `make test` on every push/PR; `main` is
  branch-protected on it so the objective function can't drift.

## What's next

Live-Qwen benchmark runs (currently the reproducible numbers use the offline
reference path); learned/tuned objective weights from clinician input; richer
modes (home-visit travel routing); an interactive "what-if" weight slider.

## Eligibility — new build

RehabPanel was **built fresh for this submission window** — new domain, new
concept, new code. It is not a reskin of prior work; the negotiation protocol,
scorer, generator, and UI were all written for this hackathon.

## How it maps to the rubric

- **Technical depth (30%)** — staged negotiation protocol, deterministic scorer,
  seeded reproducible benchmark + scarcity sweep, model-tiering, CI lock.
- **Innovation (30%)** — advocate/referee society with a conflict ledger;
  objective-driven negotiation, not majority vote.
- **Problem value (25%)** — a real, conflict-heavy clinical-ops pain point,
  framed as safe decision support.
- **Presentation (15%)** — 3-panel live demo + design doc + one-command repro.

## Reproduce in one command

```bash
pip install -r requirements.txt
make benchmark      # 25 runs -> results/metrics.json + results/gap.png (key-free)
make test           # locks the scorer
```

## Honest scope

- **Decision support, not autonomous clinical scheduling.** A human approves.
- **Fully synthetic data.** No real or anonymized patient records, anywhere.
- The reported numbers come from the **deterministic offline path** so anyone can
  reproduce them without a key; the live demo runs the real Qwen agents.

---

## 3-minute video script

| Time | Shot | Narration |
|------|------|-----------|
| 0:00–0:20 | Problem: calendar full, patients overflowing | "A rehab nurse has 43 slots and 56 patients due. Acuity, overdue dates, continuity, and preference all fight for the same time. Something gives." |
| 0:20–0:40 | Baseline scoreboard column | "A single agent collapses the trade-off — it fills by acuity and lets continuity rot. Baseline value: −141." |
| 0:40–1:40 | **Scrub the negotiation** (press Play) | "Now the society. Five advocates object; the referee resolves one conflict per round. Watch Tuesday 10:00 — Continuity wants P0027 with their primary nurse; the referee swaps, logs it, value climbs." Let value tick −141 → −70. |
| 1:40–2:10 | Conflict ledger close-up | "Every ruling is on the record — a single agent never shows this work." |
| 2:10–2:40 | `gap.png` scarcity sweep | "Across 25 runs the society wins every time, and the advantage widens as slots get scarcer. The conflict is the point." |
| 2:40–3:00 | qwen_client.py + repo | "All Qwen on Alibaba Cloud, deterministic scorer, one-command reproduce. Decision support, synthetic data. Thanks." |

## Submission checklist

- [x] Public repo + MIT `LICENSE` (holder set)
- [x] `qwen_client.py` shows the dashscope-intl (Alibaba Cloud) call — deploy proof
- [x] Architecture diagram (`docs/architecture.svg`)
- [x] Deterministic one-command repro (`make benchmark`) + CI lock
- [x] All data synthetic
- [ ] ≤3-min demo video recorded
- [ ] Devpost text + Track 3 + measurable gain (this doc)
- [ ] Public deploy link (static `ui/` → Vercel / Alibaba OSS at submission)
- [ ] Blog post (separate near-free prize)
