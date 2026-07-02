# RehabPanel — Submission Packet

Global AI Hackathon Series with Qwen Cloud · **Track 3: Agent Society**
Deadline 2026-07-09 14:00 PDT · Public repo · MIT · Fully synthetic data.

**Live demo (Alibaba Cloud):** http://8.222.187.218 — lands on **▶ Replay** (a real
Qwen negotiation, 160→181, free, no key). **◉ Run live** streams a fresh real
negotiation and is token-gated to protect the voucher; the judge link (with the
token) is provided in the Devpost submission, not this public repo.

---

## One-liner

Five "advocate" agents and a charge-nurse referee **negotiate** which rehab
patients to follow up under scarce clinician slots. A single agent collapses the
trade-off; the negotiating society reaches a higher multi-objective score on the
same scorer — repairing the continuity and preference a single agent abandons.

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

Two planners, the **same** deterministic scorer, the **same** week (56 patients,
43 slots, seed 7, demand/capacity 1.3). A recorded **real Qwen** negotiation
(bundled, replayable in-app via **▶ Replay**):

| Objective | Single agent | Society (live Qwen) |
|---|---:|---:|
| Total score *(higher is better)* | 160 | **181** (+21) |
| Continuity breaks *(lower is better)* | 30 | **25** |
| Preference mismatches *(lower is better)* | 26 | **17** |
| Overdue days *(lower is better)* | 209 | **207** |
| High-acuity coverage | 100% | 100% |
| Patients scheduled | 43 / 56 | 43 / 56 |

The society climbs **160 → 181, +21** over **12 rounds** — each round all five
advocates voice objections and the flagship referee explains every ruling in prose.
The gain is architectural (negotiation, not a bigger model): the society repairs
the continuity and preference a single agent abandons while holding high-acuity
coverage. Press **◉ Run live (Qwen)** to watch a fresh negotiation stream round by
round.

**Second gain — adaptivity under disruption.** After an incident (nurse sick,
cancellation, urgent referral), the society **warm-repairs** the plan with
**minimal disruption** — e.g. *4 of 39* appointments changed — while a cold
single-agent re-draft would churn most of the week (you'd re-notify everyone).
We report disruption honestly as its own metric (a diff outside the locked
scorer); we do **not** claim a raw-value win on re-plan.

## How we built it

- **Qwen Cloud only.** All agents call Qwen via `rehabpanel/qwen_client.py` →
  OpenAI-compatible `dashscope-intl.aliyuncs.com` endpoint (Alibaba Cloud). This
  file is the deployment-proof artifact.
- **Distinct capabilities under one vendor** (ADR-3): differentiation by
  **role/prompt + tool + model tier** — the referee on a flagship Qwen tier, the
  advocates on a fast/cheap tier (also the token-budget guard), the single-agent
  baseline on a strong tier — so the society's win is architectural, not
  model-horsepower. Exact ids are env-overridable and swap as quota / preview
  strings shift; the UI never names one (advocates show "fast tier", referee
  "flagship tier").
- **LangGraph** state machine: draft → critique → negotiate → arbitrate → loop →
  END. Deterministic control flow + a deterministic referee *decision*; autonomy
  (each advocate's objections, and the referee's prose *rationale*) lives inside
  the agents.
- **Pure-Python deterministic scorer** (`scorer.py`, no LLM) scores both
  pipelines identically — reproducibility is the differentiator over typical
  entries. Locked by unit tests in CI.
- **Runs on real Qwen**: the demo and the recorded run are genuine Qwen
  negotiations. A key-free deterministic path (`REHABPANEL_OFFLINE`) implementing
  the same critique/arbitrate contract exists only so CI and unit tests run
  without spending the voucher.
- **Synthetic generator** with engineered scarcity & conflict (overdue spread,
  shared-clinician clustering, preference/capacity collisions). No real data.
- **Negotiation view**: weekly calendar + a live conflict ledger + a per-round
  score spark + the round-by-round transcript (every advocate's objection and the
  referee's prose ruling). Two triggers: **▶ Replay** — a bundled recording of a
  real negotiation (no key / no tokens, the default view) — and **◉ Run live
  (Qwen)** — a fresh real negotiation streamed round by round.
- **CI**: GitHub Actions runs `make test` on every push/PR; `main` is
  branch-protected on it so the objective function can't drift.
- **Coordinator app** (`make serve`): a FastAPI backend over an in-memory
  session + a 5-view SPA (Caseload · Team · Rules · Schedule/Negotiation · KPIs).
  The society **assists a nurse coordinator**: set the roster/caseload/rule, then
  when reality breaks (nurse sick · patient cancels · urgent referral) the live
  score drops and **Re-plan** runs a *warm* negotiation that repairs only what
  broke. Priority weights are causal on the negotiation. See
  `docs/architecture_app.svg` and `docs/spec_coordinator_app.md`.

## What's next

Merge the LLM critique with the rule critique so the live negotiation surfaces more
improving swaps per round; learned/tuned objective weights from clinician input;
richer modes (home-visit travel routing); a scarcity sweep of live runs.

## Eligibility — new build

RehabPanel was **built fresh for this submission window** — new domain, new
concept, new code. It is not a reskin of prior work; the negotiation protocol,
scorer, generator, and UI were all written for this hackathon.

## How it maps to the rubric

- **Technical depth (30%)** — staged negotiation protocol (draft → critique →
  negotiate → arbitrate), pure-Python deterministic scorer, model-tiering, CI lock.
- **Innovation (30%)** — advocate/referee society with a conflict ledger;
  objective-driven negotiation, not majority vote.
- **Problem value (25%)** — a real, conflict-heavy clinical-ops pain point,
  framed as safe decision support.
- **Presentation (15%)** — live-negotiation demo + design doc + one-command run.

## Run it

```bash
pip install -r requirements.txt
make test           # locks the deterministic scorer (CI runs this on every push)
make serve          # → http://localhost:8000 · ▶ Replay a real run, or ◉ Run live (with a key)
```

## Honest scope

- **Decision support, not autonomous clinical scheduling.** A human approves.
- **Fully synthetic data.** No real or anonymized patient records, anywhere.
- The reported numbers are from a **real Qwen** negotiation, replayable in-app; a
  key-free deterministic path exists only for CI and unit tests.

---

## 3-minute video script

Driven by the **coordinator app** (`make serve`).

| Time | View / action | Narration |
|------|---------------|-----------|
| 0:00–0:25 | **Caseload** + **Team** | "A coordinator has 56 patients due but 43 slots across three nurses. Acuity, overdue dates, continuity and preference all fight for the same time." |
| 0:25–0:45 | **Rules** sliders | "This is the priority rule the society optimizes — and it's causal: drop continuity to zero and the agents stop protecting primary-nurse matches." |
| 0:45–1:45 | **Schedule** → press **◉ Run live (Qwen)** | "Watch the society negotiate — live. Each round all five advocates object on their own objective; the charge-nurse referee resolves one conflict and explains the ruling in plain language. Value climbs 160 → 181, +21 — a gain a single agent never finds. (▶ Replay shows the same recorded run instantly, no tokens.)" |
| 1:45–2:20 | **Incident → Nurse sick → Re-plan** | "Reality breaks: a nurse calls in sick, orphaning patients. Re-plan — the society warm-repairs, changing only a handful of appointments; a single agent would re-shuffle the whole week." |
| 2:20–2:45 | **KPIs** session timeline | "Every disruption dips, every re-plan recovers — with minimal disruption. That's the measurable efficiency." |
| 2:45–3:00 | **Conflict ledger** + `qwen_client.py` | "Every ruling is logged — an auditable record of why each patient sits where they do. Same scorer for both planners; the society just negotiates a better plan. All Qwen on Alibaba Cloud. Decision support, synthetic data." |

## Submission checklist

- [x] Public repo + MIT `LICENSE` (holder set)
- [x] `qwen_client.py` shows the dashscope-intl (Alibaba Cloud) call — deploy proof
- [x] Architecture diagram (`docs/architecture.svg`)
- [x] One-command run (`make serve`) + CI-locked scorer (`make test`)
- [x] All data synthetic
- [ ] ≤3-min demo video recorded
- [ ] Devpost text + Track 3 + measurable gain (this doc)
- [x] Public deploy link — **Alibaba Cloud SAS**, http://8.222.187.218 (live app; ▶ Replay free, ◉ Run live token-gated)
- [ ] Blog post (separate near-free prize)
