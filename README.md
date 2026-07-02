# RehabPanel

A multi-agent **Agent Society** that schedules rehab patient follow-ups under
scarce clinician time. Built for the Global AI Hackathon Series with Qwen Cloud
(Track 3). Five advocate agents — clinical priority, follow-up window, continuity,
capacity, and patient preference — **negotiate** a weekly schedule, refereed by a
charge-nurse agent. A single-agent baseline collapses the trade-off; the society
negotiates it — recovering the continuity and preference a single agent abandons,
on the same scorer.

> Decision support on **fully synthetic data**. No real patient records.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your Qwen Cloud (DASHSCOPE) key
make data        # seeded synthetic caseload (set scarcity: RATIO=1.3)
make baseline    # single-agent scheduler
make society     # multi-agent negotiation -> schedule + conflict ledger
make benchmark   # baseline vs society across seeds + a scarcity sweep
make serve       # coordinator app at http://localhost:8000 (live backend)
make test        # unit tests
```

> Runs **key-free** by default: with no `DASHSCOPE_API_KEY`, a deterministic
> reference path implements the same negotiation contract so CI and unit tests
> run without spending the voucher. Set the key to run the live Qwen agents (and
> the in-app **▶ Replay** shows a recorded real negotiation with no key).

## Result

Two planners, the **same** deterministic scorer, the **same** week (56 patients,
43 slots). A recorded **real Qwen** negotiation (in-app **▶ Replay**):

| Objective | Single agent | Society (live) |
|---|---:|---:|
| Total score *(higher is better)* | 160 | **181** (+21) |
| Continuity breaks | 30 | **25** |
| Preference mismatches | 26 | **17** |
| Overdue days | 209 | **207** |
| High-acuity coverage | 100% | 100% |

The society climbs **160 → 181 (+21)** over 12 rounds — all five advocates voice
objections each round and the referee explains every ruling. It wins by repairing
the continuity and preference a single agent abandons, while holding high-acuity
coverage. Press **◉ Run live (Qwen)** to stream a fresh one.

## Coordinator app (`make serve`)
A multi-view app where the agent society **assists a nurse coordinator**: see the
**Caseload** and **Team**, set the **priority Rule** (causal weight sliders),
watch the **Schedule** negotiate round-by-round, and track **KPIs**. When reality
breaks — a nurse calls in **sick**, a patient **cancels**, an **urgent referral**
arrives — the live score drops; **Re-plan** runs a *warm* negotiation that
repairs only what broke. Two measurable gains:
- **Initial plan:** society value > single-agent baseline (the table above).
- **After a disruption:** the society recovers with **minimal disruption**
  (e.g. 4/39 appointments changed) — see `docs/architecture_app.svg`.

FastAPI backend (`rehabpanel/api.py`) over an in-memory session; the SPA is
`ui/app.html`. The Schedule view has **▶ Replay** (a recorded real Qwen
negotiation — key-free, the default view) and **◉ Run live (Qwen)** (a fresh one,
needs a key). Containerised: `make docker-build && make docker-run` — deploy to
Alibaba Cloud per `docs/deploy.md` (Config A).

## How it works
See `docs/RehabPanel_Design_Doc.md` and the architecture diagrams
(`docs/architecture.svg` engine · `docs/architecture_app.svg` coordinator app).
The deterministic scorer (`rehabpanel/scorer.py`, pure Python, no LLM)
evaluates both pipelines with the same objective function and is CI-locked
(`make test`), so the head-to-head is apples-to-apples.

## Docs
- `docs/RehabPanel_Design_Doc.md` — design + ADRs
- `docs/spec_coordinator_app.md` — coordinator-app spec
- `docs/SUBMISSION.md` — submission packet + video script
- `docs/deploy.md` — container + Alibaba Cloud deploy
- `docs/BUILD_LOG.md` — running build record

## Qwen Cloud
All agents call Qwen models via `rehabpanel/qwen_client.py`, pointed at the
OpenAI-compatible `dashscope-intl.aliyuncs.com` endpoint (Alibaba Cloud).

## License
MIT — see `LICENSE`.
