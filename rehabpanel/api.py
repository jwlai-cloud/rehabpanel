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


_BUNDLED_REPLAY = Path(__file__).resolve().parent / "recordings" / "negotiation.jsonl"


@app.get("/api/replay")
def replay():
    """Return a previously recorded real-Qwen negotiation (round events + inter-round
    gaps in seconds) so the SPA can replay it — no key, no tokens. Reads the jsonl at
    $REHABPANEL_REPLAY, else the bundled recording. Lines are "<ts>\\t<sse-payload>".
    This is the SPA's default view and a no-cost demo of a genuine negotiation."""
    path = os.environ.get("REHABPANEL_REPLAY")
    if not path or not Path(path).exists():
        path = str(_BUNDLED_REPLAY) if _BUNDLED_REPLAY.exists() else None
    if not path:
        return JSONResponse({"error": "no replay available"}, status_code=404)
    rounds, ts = [], []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        t, _, pl = line.partition("\t") if "\t" in line else (None, None, line)
        try:
            d = json.loads(pl)
        except Exception:
            continue
        if "round" in d:
            rounds.append(d)
            ts.append(float(t) if t else None)
    gaps = []
    for i in range(len(ts)):
        nxt = ts[i + 1] if (i + 1 < len(ts) and ts[i + 1] and ts[i]) else (ts[i] + 2.5 if ts[i] else None)
        gaps.append(round(nxt - ts[i], 2) if (nxt and ts[i]) else 2.5)
    return {"events": rounds, "gaps": gaps}


# serve the coordinator SPA at /
_APP = Path(__file__).resolve().parent.parent / "ui" / "app.html"


@app.get("/")
def index():
    if _APP.exists():
        return FileResponse(_APP)
    return JSONResponse({"ok": True, "hint": "API up. Build ui/app.html for the SPA."})
