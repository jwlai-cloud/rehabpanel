# RehabPanel

A multi-agent **Agent Society** that schedules rehab patient follow-ups under
scarce clinician time. Built for the Global AI Hackathon Series with Qwen Cloud
(Track 3). Five advocate agents — clinical priority, follow-up window, continuity,
capacity, and patient preference — **negotiate** a weekly schedule, refereed by a
charge-nurse agent. A single-agent baseline collapses the trade-off; the society
negotiates it, and the advantage grows as demand outstrips capacity.

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
> offline reference negotiator reproduces the benchmark gap so CI and judges
> don't spend the voucher. Set the key and `unset REHABPANEL_OFFLINE` to run the
> live Qwen agents.

## Result

`make benchmark` — 5 seeds × 5 scarcity levels, deterministic:

| demand / capacity | mean value gap (society − baseline) | feasible |
|------:|------:|:--:|
| 0.8 | +45.2 | ✓ |
| 1.0 | +64.2 | ✓ |
| 1.2 | +65.2 | ✓ |
| 1.4 | +70.8 | ✓ |
| 1.6 | +66.6 | ✓ |

The society out-scores the single agent on **every run**, and the advantage
**grows through the conflict-onset region (0.8 → 1.4)** (`results/gap.png`). It
wins by repairing continuity and preference that the single agent abandons, while
holding high-acuity coverage constant.

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
`ui/app.html`. Runs key-free (deterministic) or on live Qwen with a key.
Containerised: `make docker-build && make docker-run` — deploy to Alibaba Cloud
per `docs/deploy.md`.

## How it works
See `docs/RehabPanel_Design_Doc.md` and the architecture diagrams
(`docs/architecture.svg` engine · `docs/architecture_app.svg` coordinator app).
The deterministic scorer (`rehabpanel/scorer.py`)
evaluates both pipelines with the same objective function, so the measured gain
is reproducible: `make benchmark` regenerates every number.

## Docs
- `docs/RehabPanel_Design_Doc.md` — design + ADRs
- `docs/spec_negotiation.md` — negotiation engine spec
- `docs/spec_coordinator_app.md` — coordinator-app redesign spec
- `docs/SUBMISSION.md` — submission packet + video script
- `docs/deploy.md` — container + Alibaba Cloud deploy
- `docs/BUILD_LOG.md` — running build record

## Qwen Cloud
All agents call Qwen models via `rehabpanel/qwen_client.py`, pointed at the
OpenAI-compatible `dashscope-intl.aliyuncs.com` endpoint (Alibaba Cloud).

## License
MIT — see `LICENSE`.
