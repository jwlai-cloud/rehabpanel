"""Bundle the latest run (data/ + scores) into ui/state.json so the static demo
UI renders without any backend or cross-directory fetch. Run via `make ui`
(or implicitly by `make demo`) after baseline + society have produced output.
"""
import json
from datetime import date
from pathlib import Path

from .scorer import score

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UI = ROOT / "ui"


def _load(n):
    return json.loads((DATA / f"{n}.json").read_text())


def _load_opt(name, default):
    p = DATA / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else default


def _cells(assignments, P, S, C):
    """Render-ready per-assignment rows for the calendar panel."""
    out = []
    for a in assignments:
        s, p = S.get(a["slot_id"]), P.get(a["patient_id"])
        if not s or not p:
            continue
        out.append({
            "slot_id": s["slot_id"],
            "day": date.fromisoformat(s["date"]).strftime("%a"),
            "date": s["date"],
            "time": s.get("start_time", ""),
            "clinician_id": s["clinician_id"],
            "clinician": C.get(s["clinician_id"], {}).get("name", s["clinician_id"]),
            "mode": s["mode"],
            "patient_id": p["patient_id"],
            "patient": p["name"],
            "acuity": p["acuity_score"],
            "continuity_ok": s["clinician_id"] == p["primary_clinician_id"],
            "pref_ok": s["mode"] == p["preferred_mode"],
            "round": a.get("assigned_in_round", 0),
        })
    out.sort(key=lambda c: (c["date"], c["clinician_id"], c["time"]))
    return out


def build():
    patients, clinicians, slots = _load("patients"), _load("clinicians"), _load("slots")
    meta = _load("meta")
    P = {p["patient_id"]: p for p in patients}
    S = {s["slot_id"]: s for s in slots}
    C = {c["clinician_id"]: c for c in clinicians}

    base = _load_opt("assignments_baseline", [])
    soc = _load_opt("assignments_society", [])
    ledger = _load_opt("conflict_ledger", [])

    state = {
        "meta": meta,
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "clinicians": [{"id": c["clinician_id"], "name": c["name"]} for c in clinicians],
        "scores": {
            "baseline": score(base, patients, clinicians, slots, meta=meta),
            "society": score(soc, patients, clinicians, slots, meta=meta),
        },
        "society_cells": _cells(soc, P, S, C),
        "baseline_cells": _cells(base, P, S, C),
        "ledger": ledger,
        "counts": {"patients": len(patients), "slots": len(slots),
                   "scheduled_society": len(soc), "scheduled_baseline": len(base)},
    }
    UI.mkdir(exist_ok=True)
    (UI / "state.json").write_text(json.dumps(state, indent=2))
    print(f"ui_export -> ui/state.json "
          f"({len(soc)} society assignments, {len(ledger)} rulings)")
    return state


if __name__ == "__main__":
    build()
