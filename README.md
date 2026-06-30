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
make test        # scorer unit tests
```

## How it works
See `docs/RehabPanel_Design_Doc.md` and the architecture diagram
(`docs/architecture.svg`). The deterministic scorer (`rehabpanel/scorer.py`)
evaluates both pipelines with the same objective function, so the measured gain
is reproducible: `make benchmark` regenerates every number.

## Qwen Cloud
All agents call Qwen models via `rehabpanel/qwen_client.py`, pointed at the
OpenAI-compatible `dashscope-intl.aliyuncs.com` endpoint (Alibaba Cloud).

## License
MIT — see `LICENSE`.
