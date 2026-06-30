"""Coordinator service — the in-memory world the FastAPI backend drives.

Holds one session's world (tables + weights + committed plan + last negotiation +
incident history) behind a Store interface so a real DB can slot in later. All
planning goes through the Phase-0 in-memory engine; the scorer stays the single
pure-Python source of truth. No file IO.
"""
from __future__ import annotations
from datetime import date
from typing import Protocol

from . import generator, baseline
from .society import orchestrator as O
from .scorer import score, DEFAULT_WEIGHTS
from .ui_export import _cells  # render-ready calendar rows (pure)

SCORE_KEYS = ("value", "acuity_coverage", "overdue_days", "continuity_breaks",
              "preference_mismatches", "patients_scheduled", "feasible")

INCIDENTS = ("sick", "cancel", "referral")


# ---- persistence boundary (in-memory now; DB later) ------------------------

class Store(Protocol):
    def load(self) -> dict | None: ...
    def save(self, world: dict) -> None: ...


class InMemoryStore:
    """Single-session store. NOT multi-tenant — a DB-backed Store replaces this
    later (see spec_coordinator_app.md)."""
    def __init__(self):
        self._world: dict | None = None

    def load(self):
        return self._world

    def save(self, world):
        self._world = world


# ---- helpers ---------------------------------------------------------------

def _slim(s):
    return {k: s[k] for k in SCORE_KEYS}


def _summarise_objections(objs):
    by = {}
    for o in objs:
        by[o.get("by", "?")] = by.get(o.get("by", "?"), 0) + 1
    return by


def _capacity(plan, clinicians, slots):
    """% utilization overall + per clinician for the committed plan."""
    used = {}
    S = {s["slot_id"]: s for s in slots}
    for a in plan:
        s = S.get(a["slot_id"])
        if s:
            used[s["clinician_id"]] = used.get(s["clinician_id"], 0) + 1
    per = []
    tot_used = tot_cap = 0
    for c in clinicians:
        cap = c["weekly_capacity_slots"]
        u = used.get(c["clinician_id"], 0)
        tot_used += u; tot_cap += cap
        per.append({"id": c["clinician_id"], "name": c["name"], "used": u, "cap": cap,
                    "pct": round(100 * u / cap) if cap else 0})
    return {"overall_pct": round(100 * tot_used / tot_cap) if tot_cap else 0, "per": per}


def _alerts(plan, tables, banner):
    """Derived flags off the scored plan (not a configurable alert engine)."""
    P = {p["patient_id"]: p for p in tables["patients"]}
    assigned = {a["patient_id"] for a in plan}
    t0 = date.fromisoformat(tables["meta"]["t0"])
    out = []
    if banner:
        out.append({"level": "incident", "msg": banner})
    hi = [p for p in tables["patients"] if p["acuity_score"] >= 7 and p["patient_id"] not in assigned]
    if hi:
        out.append({"level": "critical", "msg": f"{len(hi)} high-acuity patient(s) unscheduled"})
    od = [p for p in tables["patients"]
          if p["patient_id"] not in assigned and (t0 - date.fromisoformat(p["followup_due_date"])).days > 0]
    if od:
        out.append({"level": "warn", "msg": f"{len(od)} overdue patient(s) unseen"})
    return out


def _disruption(seed_plan, new_plan):
    a = {x["patient_id"]: x["slot_id"] for x in seed_plan}
    b = {x["patient_id"]: x["slot_id"] for x in new_plan}
    changed = sum(1 for p, s in a.items() if b.get(p) != s)
    return {"changed": changed, "total": len(a)}


# ---- service ---------------------------------------------------------------

class CoordinatorService:
    def __init__(self, store: Store | None = None):
        self.store = store or InMemoryStore()

    # -- lifecycle --
    def reset(self, seed=7, ratio=1.3):
        tables = generator.generate(seed=seed, ratio=ratio, write=False)
        weights = dict(DEFAULT_WEIGHTS)
        base = baseline.plan(tables["patients"], tables["clinicians"], tables["slots"])
        final = O.negotiate(tables, weights=weights)
        bval = score(base, tables["patients"], tables["clinicians"], tables["slots"], meta=tables["meta"])["value"]
        sval = score(final["draft"], tables["patients"], tables["clinicians"], tables["slots"], meta=tables["meta"])["value"]
        world = {
            "tables": tables, "weights": weights,
            "baseline_plan": base, "committed_plan": final["draft"],
            "last_negotiation": final, "pre_replan_plan": None,
            "headline_gap": round(sval - bval, 1),
            "incidents": [], "banner": None,
            "score_history": [{"label": "initial", "value": sval}],
            "roster_status": {c["clinician_id"]: "available" for c in tables["clinicians"]},
        }
        self.store.save(world)
        return self.state()

    def _world(self):
        w = self.store.load()
        return w if w is not None else self.reset() and self.store.load()

    # -- mutations --
    def set_rules(self, weights):
        w = self._world()
        w["weights"] = {**w["weights"], **(weights or {})}
        self.store.save(w)
        return self.replan(label="rules")

    def incident(self, kind):
        if kind not in INCIDENTS:
            raise ValueError(f"unknown incident {kind}")
        w = self._world()
        t = w["tables"]
        w["pre_replan_plan"] = list(w["committed_plan"])
        if kind == "sick":
            # clinician C00 out Tuesday -> drop their Tue slots
            tue = (date.fromisoformat(t["meta"]["t0"])).isoformat()  # Mon t0; Tue = +1
            from datetime import timedelta
            tue = (date.fromisoformat(t["meta"]["t0"]) + timedelta(days=1)).isoformat()
            gone = {s["slot_id"] for s in t["slots"] if s["clinician_id"] == "C00" and s["date"] == tue}
            t["slots"] = [s for s in t["slots"] if s["slot_id"] not in gone]
            w["committed_plan"] = [a for a in w["committed_plan"] if a["slot_id"] not in gone]
            w["roster_status"]["C00"] = "sick (Tue)"
            w["banner"] = f"C00 out Tuesday — {len(gone)} slots lost"
        elif kind == "cancel":
            # a scheduled patient cancels -> free their slot
            if w["committed_plan"]:
                cancelled = w["committed_plan"][len(w["committed_plan"]) // 2]
                w["committed_plan"] = [a for a in w["committed_plan"] if a is not cancelled]
                w["banner"] = f"{cancelled['patient_id']} cancelled — slot {cancelled['slot_id']} free"
        elif kind == "referral":
            # urgent high-acuity referral added to the backlog
            pid = f"P9{len(t['patients']):03d}"
            c0 = t["clinicians"][0]["clinician_id"]
            t["patients"].append({
                "patient_id": pid, "name": "Urgent Referral", "age": 70, "program": "stroke",
                "acuity_score": 9, "risk_flags": ["deterioration"], "primary_clinician_id": c0,
                "last_seen_date": t["meta"]["t0"], "followup_due_date": t["meta"]["t0"],
                "followup_interval_days": 7, "preferred_mode": "clinic", "availability": [],
                "travel_zone": "Z1", "no_show_risk": 0.1, "status": "active"})
            w["banner"] = f"Urgent referral {pid} (acuity 9) added to backlog"
        # live score AFTER incident, BEFORE replan (the drop)
        sval = score(w["committed_plan"], t["patients"], t["clinicians"], t["slots"], meta=t["meta"])["value"]
        w["incidents"].append({"kind": kind, "banner": w["banner"]})
        w["score_history"].append({"label": kind, "value": sval})
        self.store.save(w)
        return self.state()

    def replan(self, label="replan"):
        w = self._world()
        t = w["tables"]
        seed = w["committed_plan"]
        final = O.negotiate(t, seed_draft=seed, weights=w["weights"])
        w["pre_replan_plan"] = list(seed)
        w["committed_plan"] = final["draft"]
        w["last_negotiation"] = final
        w["banner"] = None
        sval = score(final["draft"], t["patients"], t["clinicians"], t["slots"], meta=t["meta"])["value"]
        w["score_history"].append({"label": label, "value": sval})
        self.store.save(w)
        return self.state()

    # -- read --
    def state(self):
        w = self._world()
        t = w["tables"]
        P = {p["patient_id"]: p for p in t["patients"]}
        S = {s["slot_id"]: s for s in t["slots"]}
        C = {c["clinician_id"]: c for c in t["clinicians"]}
        committed = score(w["committed_plan"], t["patients"], t["clinicians"], t["slots"], meta=t["meta"])
        base = score(w["baseline_plan"], t["patients"], t["clinicians"], t["slots"], meta=t["meta"])
        rounds, cum = [], []
        for snap in w["last_negotiation"]["snapshots"]:
            cum = cum + snap["rulings"]
            sc = score(snap["draft"], t["patients"], t["clinicians"], t["slots"], meta=t["meta"])
            rounds.append({
                "round": snap["round"], "score": _slim(sc),
                "cells": _cells(snap["draft"], P, S, C), "ledger": list(cum),
                "objections": _summarise_objections(snap.get("objections", [])),
                "moved": sum(1 for c in _cells(snap["draft"], P, S, C) if c["round"] == snap["round"]),
            })
        disruption = _disruption(w["pre_replan_plan"], w["committed_plan"]) if w["pre_replan_plan"] else None
        return {
            "meta": t["meta"], "weights": w["weights"], "headline_gap": w["headline_gap"],
            "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "clinicians": [{"id": c["clinician_id"], "name": c["name"],
                            "status": w["roster_status"].get(c["clinician_id"], "available"),
                            "cap": c["weekly_capacity_slots"]} for c in t["clinicians"]],
            "agents": [
                {"name": "priority", "objective": "high-acuity seen", "tier": "qwen3.6-flash"},
                {"name": "window", "objective": "overdue follow-ups", "tier": "qwen3.6-flash"},
                {"name": "continuity", "objective": "stay with primary nurse", "tier": "qwen3.6-flash"},
                {"name": "capacity", "objective": "feasibility (veto)", "tier": "qwen3.6-flash"},
                {"name": "preference", "objective": "mode/availability", "tier": "qwen3.6-flash"},
                {"name": "referee", "objective": "arbitrate + log", "tier": "qwen3.7-max"},
            ],
            "scores": {"committed": _slim(committed), "baseline": _slim(base)},
            "disruption": disruption,
            "capacity": _capacity(w["committed_plan"], t["clinicians"], t["slots"]),
            "plan_cells": _cells(w["committed_plan"], P, S, C),
            "patients": [{"id": p["patient_id"], "name": p["name"], "acuity": p["acuity_score"],
                          "program": p["program"], "primary": p["primary_clinician_id"],
                          "pref": p["preferred_mode"], "due": p["followup_due_date"],
                          "scheduled": p["patient_id"] in {a["patient_id"] for a in w["committed_plan"]}}
                         for p in t["patients"]],
            "rounds": rounds, "ledger": w["last_negotiation"]["ledger"],
            "alerts": _alerts(w["committed_plan"], t, w["banner"]),
            "incidents": w["incidents"], "score_history": w["score_history"],
            "counts": {"patients": len(t["patients"]), "slots": len(t["slots"]),
                       "scheduled": len(w["committed_plan"])},
        }
