"""FastAPI backend for the coordinator app. Thin HTTP layer over
CoordinatorService — the engine + scorer do the work. Single in-memory session.

Run: uvicorn rehabpanel.api:app --reload   (or `make serve`)
Respects qwen_client.is_offline(): deterministic without a key, live Qwen with.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .state_service import CoordinatorService, INCIDENTS

app = FastAPI(title="RehabPanel Coordinator")
svc = CoordinatorService()
svc.reset()  # seed the world at startup


class Rules(BaseModel):
    acuity: float | None = None
    overdue: float | None = None
    continuity: float | None = None
    pref: float | None = None


@app.get("/api/state")
def get_state():
    return svc.state()


@app.post("/api/reset")
def reset(seed: int = 7, ratio: float = 1.3):
    return svc.reset(seed=seed, ratio=ratio)


@app.post("/api/incident/{kind}")
def incident(kind: str):
    if kind not in INCIDENTS:
        return JSONResponse({"error": f"unknown incident '{kind}'", "allowed": list(INCIDENTS)},
                            status_code=400)
    return svc.incident(kind)


@app.post("/api/replan")
def replan():
    return svc.replan()


@app.post("/api/rules")
def rules(r: Rules):
    return svc.set_rules({k: v for k, v in r.model_dump().items() if v is not None})


# serve the SPA (built in later phases) at / when present
_UI = Path(__file__).resolve().parent.parent / "ui"
if (_UI / "app.html").exists():
    app.mount("/", StaticFiles(directory=_UI, html=True), name="ui")
