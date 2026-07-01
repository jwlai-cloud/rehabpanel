# RehabPanel coordinator app — FastAPI + static SPA.
# Default view replays a bundled real Qwen negotiation (no key). Add
# DASHSCOPE_API_KEY (keep REHABPANEL_OFFLINE=1) so the "Run live" button
# fires a fresh real negotiation on click. See docs/deploy.md (Config A).
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rehabpanel/ rehabpanel/
COPY ui/ ui/

ENV PORT=8000 \
    REHABPANEL_OFFLINE=1
EXPOSE 8000

# shell form so ${PORT} expands (Function Compute / SAE inject their own PORT)
CMD ["sh", "-c", "uvicorn rehabpanel.api:app --host 0.0.0.0 --port ${PORT}"]
