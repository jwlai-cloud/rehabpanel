# RehabPanel — Build & Handoff Doc

Everything needed to go from empty repo to a submittable Track 3 project. Pairs with `RehabPanel_Design_Doc.md`.

---

## 1. Quick start (target: first agent running in ~30 min)

```bash
git clone <your-public-repo> && cd rehabpanel
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # openai, faker, pydantic, matplotlib, pytest
cp .env.example .env                      # add DASHSCOPE_API_KEY
make data        # generate a seeded synthetic caseload
make baseline    # run single-agent scheduler
make society     # run the negotiation
make benchmark   # baseline vs society across seeds + scarcity sweep
make demo        # launch the 3-panel UI
```

`requirements.txt` core: `openai` (used against the Qwen endpoint), `faker`, `pydantic`, `matplotlib`, `pytest`.

---

## 2. Repo scaffold

```
rehabpanel/
├── README.md
├── LICENSE                      # OSS license (MIT/Apache-2.0) — REQUIRED for submission
├── Makefile                     # data / baseline / society / benchmark / demo targets
├── requirements.txt
├── .env.example                 # DASHSCOPE_API_KEY=...
├── docs/
│   ├── RehabPanel_Design_Doc.md
│   ├── rehabpanel_architecture.mermaid
│   └── handoff.md               # this file
├── rehabpanel/
│   ├── qwen_client.py           # ⭐ Alibaba Cloud proof artifact (dashscope-intl)
│   ├── schema.py                # pydantic models for the 5 tables
│   ├── generator.py             # seeded synthetic data + demand_capacity_ratio knob
│   ├── scorer.py                # ⭐ deterministic objective function (no LLM)
│   ├── baseline.py              # single-agent scheduler
│   ├── society/
│   │   ├── orchestrator.py      # referee + Draft→Critique→Negotiate→Arbitrate loop
│   │   ├── advocates.py         # 5 advocate agents
│   │   └── prompts/             # one .md per agent (priority, window, continuity, capacity, preference, referee)
│   └── benchmark.py             # N seeds × scarcity sweep → metrics + charts
├── data/                        # generated outputs (gitignore the large ones, commit one seed sample)
├── results/                     # metrics.json + charts
├── ui/                          # demo: calendar + conflict ledger + scoreboard
└── tests/                       # scorer unit tests (lock the objective function)
```

⭐ = the two files that most affect your score: `qwen_client.py` (deployment proof) and `scorer.py` (reproducible result).

---

## 3. Qwen client (the deployment-proof artifact)

```python
# rehabpanel/qwen_client.py
import os
from openai import OpenAI

QWEN = OpenAI(
    api_key=os.environ["DASHSCOPE_API_KEY"],
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",  # Alibaba Cloud / Qwen Cloud
)

REFEREE_MODEL  = "qwen-max"    # larger tier — verify exact ids via the model-selection doc
ADVOCATE_MODEL = "qwen-turbo"  # cheap tier for the 5 advocates

def chat(messages, model=ADVOCATE_MODEL, **kw):
    return QWEN.chat.completions.create(model=model, messages=messages, **kw)
```

Confirm exact model ids against the resources page's "Choose Your Model" link before finalizing.

---

## 4. Data schema (5 tables)

```jsonc
// patients.json
{ "patient_id":"P0014","name":"<faker>","age":67,"program":"stroke",
  "acuity_score":8,"risk_flags":["fall_risk","bp_unstable"],
  "primary_clinician_id":"C03","last_seen_date":"2026-05-20",
  "followup_due_date":"2026-06-04","followup_interval_days":14,
  "preferred_mode":"clinic","availability":["Mon_AM","Tue_AM","Thu_PM"],
  "travel_zone":"Z2","no_show_risk":0.15,"status":"active" }

// clinicians.json
{ "clinician_id":"C03","name":"<faker>","role":"rehab_nurse",
  "specialties":["stroke","neuro"],"weekly_capacity_slots":18,
  "clinic_days":["Mon","Tue","Thu"],"max_home_visits_per_day":3,"base_zone":"Z1" }

// slots.json
{ "slot_id":"S0421","clinician_id":"C03","date":"2026-06-09","start_time":"10:00",
  "duration_min":30,"mode":"clinic","zone":"Z1","status":"open" }

// encounters.json   (history → powers continuity + realism)
{ "encounter_id":"E1099","patient_id":"P0014","clinician_id":"C03","date":"2026-05-20",
  "type":"clinic","outcome":"progressing" }

// assignments.json  (OUTPUT of both pipelines)
{ "patient_id":"P0014","slot_id":"S0421","assigned_in_round":3,
  "rationale":"acuity 8 prioritized over continuity at w-config A" }
```

**Generator must engineer scarcity & conflict:** program-specific acuity/interval distributions, a deliberate fraction of patients **already overdue at t0**, a cluster sharing one primary clinician (continuity tension), preferences that collide with capacity, and a single `demand_capacity_ratio` knob (set > 1). Seed everything for reproducibility.

---

## 5. Scorer contract (lock this first — it defines "winning")

```python
# scorer.py — pure function, no LLM. Same fn scores baseline AND society.
def score(assignments, patients, clinicians, slots, weights) -> dict:
    # 1. HARD: capacity feasibility — any violation => infeasible (disqualify plan)
    # 2. SOFT weighted value:
    #    value = w_acuity * acuity_coverage
    #          - w_overdue * sum(days_overdue)
    #          - w_continuity * continuity_breaks
    #          - w_pref * preference_mismatches
    return {"feasible": bool, "value": float,
            "acuity_coverage": float, "overdue_days": int,
            "continuity_breaks": int, "preference_mismatches": int}
```

Write unit tests that pin the objective on hand-built mini-cases **before** building agents — this is what makes the result trustworthy.

---

## 6. Build timeline (≈4 weeks, evenings, to Jul 9)

| Week | Milestone | Done = |
|------|-----------|--------|
| **1** | Schema + generator + scorer + tests | `make data` produces a conflict-heavy caseload; scorer tests pass |
| **1–2** | Qwen client + baseline | `make baseline` produces a feasible scored schedule |
| **2–3** | Society: advocates + referee + negotiation loop | `make society` produces schedule + conflict ledger, terminates |
| **3** | Benchmark + scarcity sweep | `make benchmark` outputs the society>baseline gap chart |
| **3–4** | Demo UI (3 panels) | calendar + ledger + scoreboard render from real outputs |
| **4** | Write-up, README, 3-min video, submit | all submission-checklist items green |

**Critical path:** scorer and generator first. If a number isn't appearing, the riskiest assumption is whether the society actually beats the baseline — smoke-test that on day 1 of week 2 with a stub society, before polishing agents.

---

## 7. Demo plan (3-minute video)

Three panels side by side: **weekly calendar** filling slot by slot · **conflict ledger / agent transcript** scrolling as agents argue · **live scoreboard** (society vs baseline, per objective). Script: 20s problem framing → narrate one Tuesday-10:00 conflict start to finish → cut to the scarcity-sweep chart showing the gap widening → one line of honest scope ("decision support on synthetic data").

---

## 8. Submission checklist (mapped to the rules)

- [ ] Public repo with an OSS **LICENSE** file
- [ ] `qwen_client.py` clearly shows the dashscope-intl (Alibaba Cloud) call — **deployment proof**
- [ ] Architecture diagram included (`docs/rehabpanel_architecture.mermaid`)
- [ ] ≤3-min demo video; project functions as shown
- [ ] Text description names **Track 3** and states the measurable gain
- [ ] **"Significantly updated / newly built"** paragraph — state it's a new build
- [ ] All data synthetic; no real/anonymized patient records anywhere in the repo
- [ ] Third-party libs (Faker, OpenAI SDK) used within their licenses
- [ ] One-command `make benchmark` reproduces the reported numbers
- [ ] Also write the **blog post** — near-free extra prize, separate from the grand prize

---

## 9. Domain questions for your wife (make the weights ring true)

1. What actually flags a rehab patient as urgent for follow-up — which red flags?
2. Typical follow-up intervals by program (stroke vs ortho vs cardiac)?
3. How much does seeing the *same* nurse genuinely matter vs. just being seen?
4. Roughly how often is demand > available slots — is the squeeze real?
5. What drives a clinic visit vs. a phone/tele check-in?
6. What falls through the cracks in the current manual process? *(→ your Impact-criterion gold)*

Use her answers to set the scorer **weights** and the generator **distributions** — not to source any real data.
