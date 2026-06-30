# Deploy — RehabPanel coordinator app

The app is a FastAPI backend + a static SPA (`ui/app.html`) in one container.
It runs **key-free** (deterministic offline engine) by default; set the Qwen key
to drive the live agents. End target is **Alibaba Cloud** (matches the
`dashscope-intl` endpoint in `qwen_client.py`).

## Local container
```bash
docker build -t rehabpanel .
docker run --rm -p 8000:8000 rehabpanel            # http://localhost:8000 (offline)
# live Qwen agents:
docker run --rm -p 8000:8000 \
  -e REHABPANEL_OFFLINE=0 -e DASHSCOPE_API_KEY=sk-... rehabpanel
```
`make docker-build` / `make docker-run` wrap these.

## Alibaba Cloud (target)
Build → push to **Container Registry (ACR)** → run on a container host. Use the
**Singapore** region to match the `dashscope-intl` endpoint.

```bash
# 1. build + push to ACR
docker build -t rehabpanel .
docker tag rehabpanel registry-intl.ap-southeast-1.aliyuncs.com/<ns>/rehabpanel:latest
docker push       registry-intl.ap-southeast-1.aliyuncs.com/<ns>/rehabpanel:latest
```

Then deploy the image on one of:
- **Function Compute (FC)** — custom-container function, HTTP trigger. FC injects
  `PORT`; the Dockerfile honours it. Cheapest for a demo (scale-to-zero).
- **Serverless App Engine (SAE)** — container application, public endpoint.
- **ECS** — a VM running `docker run` behind a security-group rule on :8000.

Set env on the service:
- `REHABPANEL_OFFLINE=0` and `DASHSCOPE_API_KEY` (as a secret) for live Qwen, or
- leave defaults for a free, deterministic public demo.

> ⚠️ Put the key in the platform's **secret/env store**, never in the image or git.

## Notes
- Single in-memory session (one world) — fine for a demo, **not multi-tenant**.
  The `Store` interface in `state_service.py` is where a DB-backed store slots in
  for real multi-user deployment.
- Generic hosts (Render, Fly.io, Cloud Run) work identically — they all honour
  `$PORT` and run the same image.
