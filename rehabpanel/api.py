"""FastAPI backend for the coordinator app. Thin HTTP layer over
CoordinatorService — the engine + scorer do the work. Single in-memory session.

Run: uvicorn rehabpanel.api:app --reload   (or `make serve`)
Respects qwen_client.is_offline(): deterministic without a key, live Qwen with.
"""
import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel

from . import generator
from .society import orchestrator as O
from .scorer import score as _score, DEFAULT_WEIGHTS
from .state_service import CoordinatorService, INCIDENTS, _cells

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


@app.get("/api/stream")
def stream(seed: int = 7, ratio: float = 1.3):
    """Server-Sent Events: run a LIVE Qwen negotiation and emit each round the instant
    its node finishes — so the UI renders the debate in REAL TIME (the ~15s of critique
    LLM calls happen between events). Forces live mode for the duration; needs the key."""
    t = generator.generate(seed=seed, ratio=ratio, write=False)
    P = {p["patient_id"]: p for p in t["patients"]}
    S = {s["slot_id"]: s for s in t["slots"]}
    C = {c["clinician_id"]: c for c in t["clinicians"]}

    def gen():
        prev = os.environ.get("REHABPANEL_OFFLINE")
        os.environ["REHABPANEL_OFFLINE"] = "0"          # real Qwen for the live stream
        try:
            yield f"data: {json.dumps({'hello': True, 'patients': len(t['patients']), 'slots': len(t['slots'])})}\n\n"
            ledger = []
            for snap in O.negotiate_stream(t, weights=dict(DEFAULT_WEIGHTS)):
                ledger += snap.get("rulings") or []
                sc = _score(snap["draft"], t["patients"], t["clinicians"], t["slots"], meta=t["meta"])
                payload = {
                    "round": snap["round"],
                    "value": sc["value"],
                    "continuity_breaks": sc["continuity_breaks"],
                    "preference_mismatches": sc["preference_mismatches"],
                    "scheduled": sc["patients_scheduled"],
                    "transcript": snap.get("transcript"),
                    "cells": _cells(snap["draft"], P, S, C),
                    "ledger": list(ledger),
                }
                yield f"data: {json.dumps(payload)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:                          # surface a stream error instead of hanging
            yield f"data: {json.dumps({'error': str(e)[:200]})}\n\n"
        finally:
            if prev is None:
                os.environ.pop("REHABPANEL_OFFLINE", None)
            else:
                os.environ["REHABPANEL_OFFLINE"] = prev

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


# serve the coordinator SPA at / and the live-stream page at /stream
_APP = Path(__file__).resolve().parent.parent / "ui" / "app.html"
_STREAM = Path(__file__).resolve().parent.parent / "ui" / "stream.html"


@app.get("/")
def index():
    if _APP.exists():
        return FileResponse(_APP)
    return JSONResponse({"ok": True, "hint": "API up. Build ui/app.html for the SPA."})


@app.get("/stream")
def stream_page():
    if _STREAM.exists():
        return FileResponse(_STREAM)
    return JSONResponse({"ok": True, "hint": "stream page missing"})
