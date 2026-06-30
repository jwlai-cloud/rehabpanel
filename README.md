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
make demo        # 3-panel UI at http://localhost:8000 (scrub the negotiation)
make test        # scorer unit tests
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

## How it works
See `docs/RehabPanel_Design_Doc.md` and the architecture diagram
(`docs/architecture.svg`). The deterministic scorer (`rehabpanel/scorer.py`)
evaluates both pipelines with the same objective function, so the measured gain
is reproducible: `make benchmark` regenerates every number.

## Docs
- `docs/RehabPanel_Design_Doc.md` — design + ADRs
- `docs/spec_negotiation.md` — negotiation build spec
- `docs/SUBMISSION.md` — submission packet + video script
- `docs/BUILD_LOG.md` — running build record

## Qwen Cloud
All agents call Qwen models via `rehabpanel/qwen_client.py`, pointed at the
OpenAI-compatible `dashscope-intl.aliyuncs.com` endpoint (Alibaba Cloud).

## License
MIT — see `LICENSE`.
