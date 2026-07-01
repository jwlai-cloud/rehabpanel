# Deploy — RehabPanel coordinator app

The app is a FastAPI backend + a static SPA (`ui/app.html`) in one container.
End target is **Alibaba Cloud** (matches the `dashscope-intl` endpoint in
`qwen_client.py`).

**Modes** (all set by env — the app never surfaces a deterministic-engine score):
- **Default view** = a bundled recording of a *real* Qwen negotiation
  (`rehabpanel/recordings/negotiation.jsonl`) — replays with **▶ Replay**, no key,
  no tokens. Works even key-free.
- **◉ Run live (Qwen)** = a *fresh* real negotiation. Needs `DASHSCOPE_API_KEY`
  in the container; fires only when clicked (`/api/stream` forces live for its
  duration, so the rest of the app stays cheap).

**Recommended for judges (Config A):** `REHABPANEL_OFFLINE=1` + the key. Default
browsing stays fast/free (shows the bundled real run); Run live does the real
thing on demand. Do **not** set `REHABPANEL_OFFLINE=0` on a public URL — it makes
every page load and incident call Qwen, draining the voucher.

## Local container
```bash
docker build -t rehabpanel .
docker run --rm -p 8000:8000 rehabpanel            # http://localhost:8000 (Replay works, no key)
# Config A — Run live fires real Qwen on click:
docker run --rm -p 8000:8000 \
  -e REHABPANEL_OFFLINE=1 -e DASHSCOPE_API_KEY=sk-... rehabpanel
```
`make docker-build` / `make docker-run` wrap these.

## Alibaba Cloud — recommended: Simple Application Server (SAS/SWAS)
For an LLM-API-wrapper app like this (no GPU), **SAS is the ~5-minute path** and
gives a running instance for the hackathon's proof-of-deployment screenshot:

1. **Register** at alibabacloud.com (needs email + card; free tier covers this).
2. **SAS console** → *Create Server* → Region **Singapore** → Image **Docker**
   (Docker + Compose preinstalled) → smallest plan → pay → *Reset Password*.
3. **Connect** (Workbench, in-browser) and run:
   ```bash
   git clone https://github.com/jwlai-cloud/rehabpanel.git && cd rehabpanel
   docker build -t rehabpanel .
   docker run -d --restart unless-stopped -p 80:8000 \
     -e REHABPANEL_OFFLINE=1 -e DASHSCOPE_API_KEY=sk-... rehabpanel   # Config A; omit the key for a free Replay-only demo
   ```
4. **Firewall** → open TCP **80**. Open `http://<public-ip>` → the app.
5. **Proof screenshot:** SAS console → your instance / Workbench Overview showing
   the **running** server. That's the required proof of Alibaba Cloud deployment.

## Alibaba Cloud — ACR + serverless (alternative)
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
- `REHABPANEL_OFFLINE=1` and `DASHSCOPE_API_KEY` (as a secret) — Config A: default
  Replay + Run live on demand, or
- leave defaults (no key) for a free, Replay-only public demo.

> ⚠️ Put the key in the platform's **secret/env store**, never in the image or git.

## Notes
- Single in-memory session (one world) — fine for a demo, **not multi-tenant**.
  The `Store` interface in `state_service.py` is where a DB-backed store slots in
  for real multi-user deployment.
- Generic hosts (Render, Fly.io, Cloud Run) work identically — they all honour
  `$PORT` and run the same image.
