# RehabPanel coordinator app — FastAPI + static SPA.
# Runs key-free (deterministic offline engine) by default; set
# REHABPANEL_OFFLINE=0 + DASHSCOPE_API_KEY to drive the live Qwen agents.
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
