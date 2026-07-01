"""The five advocate agents. Each runs on the cheap Qwen tier and argues from
ONE objective — that single-lens focus is what makes them distinct capabilities
rather than five copies of the same generalist.

Each advocate exposes:
  - critique(draft, context) -> list of objections
        [{patient_id, slot_id, severity, reason}]   (capacity: {slot_id, clinician_id, severity, reason})
  - propose_swap(objection, state) -> {move:{patient_id, slot_id}, marginal_value, reason}

Two execution paths behind one contract (see docs/spec_coordinator_app.md):
  * LLM path   — calls Qwen with prompts/<name>.md as the system prompt.
  * offline path (qwen_client.is_offline()) — a deterministic, pure-Python
    reference negotiator implementing the SAME objective by rule, so CI / tests /
    judges reproduce the gap key-free. Both feed the same external scorer.

Defensive by design: a bad LLM parse returns []/no-op, never crashes the graph.
"""
from __future__ import annotations
import json
import re
from datetime import date
from pathlib import Path

from ..qwen_client import chat, is_offline, ADVOCATE_MODEL

PROMPTS = Path(__file__).resolve().parent / "prompts"
ADVOCATES = ["priority", "window", "continuity", "capacity", "preference"]

ACUITY_HIGH = 7  # matches scorer's high-acuity threshold


def _system(name):
    return (PROMPTS / f"{name}.md").read_text()


# ---- defensive parsing -----------------------------------------------------

def parse_json_list(text: str) -> list:
    """Never let a bad LLM parse crash the graph; return [] on any failure."""
    try:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        return json.loads(m.group(0)) if m else []
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []


def parse_json_obj(text: str) -> dict:
    """Extract the first JSON object; {} on failure."""
    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0)) if m else {}
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}


# ---- shared deterministic helpers (used by the offline path) ---------------

def _index(rows, key):
    return {r[key]: r for r in rows}


def _assigned_map(draft):
    """patient_id -> slot_id for the current draft (last write wins)."""
    return {a["patient_id"]: a["slot_id"] for a in draft}


def _used_slots(draft):
    return {a["slot_id"] for a in draft}


def _t0(ctx):
    meta = ctx.get("meta") or {}
    return date.fromisoformat(meta.get("t0", "2026-06-08"))


def _overdue_days(patient, t0):
    """Days overdue at t0 (0 if not yet due)."""
    due = date.fromisoformat(patient["followup_due_date"])
    return max(0, (t0 - due).days)


def _open_slots(ctx, draft):
    used = _used_slots(draft)
    return [s for s in ctx["slots"] if s["slot_id"] not in used]


# Scorer's default weights — used to scale advocate severity so the Rules view is
# causal: a weight near 0 drops that objective below SEVERITY_EXIT (the referee
# ignores it), a raised weight makes it outrank others. With no weights passed,
# severities are unchanged (default behaviour).
_DEFAULT_W = {"acuity": 10.0, "overdue": 1.0, "continuity": 4.0, "pref": 2.0}


def _scale(ctx, key, base):
    w = ctx.get("weights") or {}
    if key not in w:
        return base
    d = _DEFAULT_W.get(key, w[key])   # reference weight (the default for known objectives)
    if not d:                         # no positive reference to scale against -> leave unscaled
        return base
    return max(0, min(10, round(base * (w[key] / d))))


# ---- deterministic critique per objective ----------------------------------

def _crit_priority(draft, ctx):
    assigned = _assigned_map(draft)
    out = []
    for p in ctx["patients"]:
        if p["acuity_score"] >= ACUITY_HIGH and p["patient_id"] not in assigned:
            out.append({"patient_id": p["patient_id"], "slot_id": None,
                        "severity": _scale(ctx, "acuity", min(10, p["acuity_score"])),
                        "reason": f"acuity {p['acuity_score']}, unscheduled"})
    return out


def _crit_window(draft, ctx):
    assigned = _assigned_map(draft)
    t0 = _t0(ctx)
    out = []
    for p in ctx["patients"]:
        od = _overdue_days(p, t0)
        if od > 0 and p["patient_id"] not in assigned:
            out.append({"patient_id": p["patient_id"], "slot_id": None,
                        "severity": _scale(ctx, "overdue", min(10, max(1, od))),
                        "reason": f"{od} days overdue, unscheduled"})
    return out


def _crit_continuity(draft, ctx):
    S = _index(ctx["slots"], "slot_id")
    P = _index(ctx["patients"], "patient_id")
    out = []
    for a in draft:
        slot, p = S.get(a["slot_id"]), P.get(a["patient_id"])
        if not slot or not p:
            continue
        if slot["clinician_id"] != p["primary_clinician_id"]:
            out.append({"patient_id": p["patient_id"], "slot_id": a["slot_id"],
                        "severity": _scale(ctx, "continuity", 5),
                        "reason": f"primary {p['primary_clinician_id']}, assigned {slot['clinician_id']}"})
    return out


def _crit_preference(draft, ctx):
    S = _index(ctx["slots"], "slot_id")
    P = _index(ctx["patients"], "patient_id")
    out = []
    for a in draft:
        slot, p = S.get(a["slot_id"]), P.get(a["patient_id"])
        if not slot or not p:
            continue
        if slot["mode"] != p["preferred_mode"]:
            out.append({"patient_id": p["patient_id"], "slot_id": a["slot_id"],
                        "severity": _scale(ctx, "pref", 3),
                        "reason": f"prefers {p['preferred_mode']}, booked {slot['mode']}"})
    return out


def _crit_capacity(draft, ctx):
    """Veto (severity 10) any feasibility breach: double-book, weekly cap,
    home-visits/day. The draft is built feasible — this guards against swaps."""
    S = _index(ctx["slots"], "slot_id")
    C = _index(ctx["clinicians"], "clinician_id")
    out, seen, per_clin, home = [], set(), {}, {}
    for a in draft:
        sid = a["slot_id"]
        slot = S.get(sid)
        if not slot:
            continue
        if sid in seen:
            out.append({"slot_id": sid, "clinician_id": slot["clinician_id"],
                        "severity": 10, "reason": f"double-booked slot {sid}"})
            continue
        seen.add(sid)
        cid = slot["clinician_id"]
        per_clin[cid] = per_clin.get(cid, 0) + 1
        if slot["mode"] == "home":
            key = (cid, slot["date"])
            home[key] = home.get(key, 0) + 1
    for cid, n in per_clin.items():
        if cid in C and n > C[cid]["weekly_capacity_slots"]:
            out.append({"slot_id": None, "clinician_id": cid, "severity": 10,
                        "reason": f"{cid} over weekly capacity ({n})"})
    for (cid, d), n in home.items():
        if cid in C and n > C[cid]["max_home_visits_per_day"]:
            out.append({"slot_id": None, "clinician_id": cid, "severity": 10,
                        "reason": f"{cid} over home-visit cap on {d}"})
    return out


_OFFLINE_CRITIQUE = {
    "priority": _crit_priority,
    "window": _crit_window,
    "continuity": _crit_continuity,
    "capacity": _crit_capacity,
    "preference": _crit_preference,
}


# ---- deterministic swap proposals -------------------------------------------

def _free_slot_for(pred, ctx, draft):
    """First open slot matching pred(slot), else None."""
    for s in _open_slots(ctx, draft):
        if pred(s):
            return s
    return None


def _swap_continuity(objection, ctx, draft):
    """Move the patient to a slot with their PRIMARY clinician. Prefer an open
    primary slot; else swap with a patient sitting in a primary-of-P slot who is
    NOT themselves in their own primary slot (so the trade can't worsen them)."""
    P = _index(ctx["patients"], "patient_id")
    S = _index(ctx["slots"], "slot_id")
    pid = objection.get("patient_id")
    p = P.get(pid)
    if not p:
        return None
    primary = p["primary_clinician_id"]
    s = _free_slot_for(lambda sl: sl["clinician_id"] == primary, ctx, draft)
    if s:
        return {"move": {"patient_id": pid, "slot_id": s["slot_id"]},
                "marginal_value": 4.0, "reason": f"{pid} -> primary {primary} (open slot)"}
    # try a mutually-non-worsening swap
    for a in draft:
        q, qslot = P.get(a["patient_id"]), S.get(a["slot_id"])
        if not q or not qslot or a["patient_id"] == pid:
            continue
        if qslot["clinician_id"] == primary and qslot["clinician_id"] != q["primary_clinician_id"]:
            return {"move": {"patient_id": pid, "slot_id": a["slot_id"]},
                    "marginal_value": 4.0,
                    "reason": f"{pid} <-> {a['patient_id']} to fix continuity"}
    return None


def _swap_preference(objection, ctx, draft):
    """Move the patient to an OPEN slot matching their preferred mode AND their
    current clinician — so fixing preference never trades away continuity
    (a strictly non-regressing move)."""
    P = _index(ctx["patients"], "patient_id")
    S = _index(ctx["slots"], "slot_id")
    pid = objection.get("patient_id")
    p = P.get(pid)
    cur = S.get(objection.get("slot_id"))
    if not p or not cur:
        return None
    pref, cid = p["preferred_mode"], cur["clinician_id"]
    s = _free_slot_for(lambda sl: sl["mode"] == pref and sl["clinician_id"] == cid, ctx, draft)
    if s:
        return {"move": {"patient_id": pid, "slot_id": s["slot_id"]},
                "marginal_value": 2.0, "reason": f"{pid} -> {pref} slot (same clinician)"}
    return None


def _swap_seat(objection, ctx, draft, kind):
    """priority/window: seat an unscheduled patient. Prefer an OPEN slot
    (preferring their primary clinician). If the week is full, displace the
    lowest-acuity seated patient this one STRICTLY outranks on acuity — which
    improves or holds acuity coverage. This is the incident-recovery lever: at
    the initial plan the unscheduled are already the lowest acuity so nothing
    fires, but a patient orphaned by an incident (previously seated, higher
    acuity) can bump the weakest seated to get care back."""
    P = _index(ctx["patients"], "patient_id")
    pid = objection.get("patient_id")
    p = P.get(pid)
    if not p:
        return None
    s = _open_slots(ctx, draft)
    if s:
        primary = p["primary_clinician_id"]
        best = next((sl for sl in s if sl["clinician_id"] == primary), s[0])
        return {"move": {"patient_id": pid, "slot_id": best["slot_id"]},
                "marginal_value": float(min(10, p["acuity_score"])),
                "reason": f"seat {pid} ({kind}) in open slot"}
    seated = sorted((P[a["patient_id"]]["acuity_score"], a["slot_id"], a["patient_id"])
                    for a in draft if a["patient_id"] in P)
    if seated and p["acuity_score"] > seated[0][0]:
        acu_l, sid_l, qid = seated[0]
        return {"move": {"patient_id": pid, "slot_id": sid_l},
                "marginal_value": float(min(10, p["acuity_score"])),
                "reason": f"seat {pid} (acuity {p['acuity_score']}) over {qid} (acuity {acu_l})"}
    return None


# ---- the advocate ----------------------------------------------------------

class Advocate:
    def __init__(self, name):
        self.name = name
        self.system = _system(name)

    # -- critique -------------------------------------------------------------
    def critique(self, draft, context):
        """Objections with 1-10 severity. Offline = deterministic rule; online =
        Qwen call parsed defensively."""
        if is_offline():
            return _OFFLINE_CRITIQUE[self.name](draft, context)
        try:
            msg = [{"role": "system", "content": self.system},
                   {"role": "user", "content": _render_draft(draft, context)}]
            objs = parse_json_list(chat(msg, model=ADVOCATE_MODEL))
            return [o for o in objs if isinstance(o, dict)]
        except Exception:
            return []  # never crash the graph on an LLM/transport error

    # -- propose_swap ---------------------------------------------------------
    def propose_swap(self, objection, state):
        """A swap + the marginal value the advocate places on the trade."""
        ctx = {k: state[k] for k in ("patients", "clinicians", "slots") if k in state}
        ctx["meta"] = state.get("meta")
        draft = state["draft"]
        if is_offline():
            return self._offline_swap(objection, ctx, draft)
        try:
            payload = {"objection": objection, "draft": draft}
            msg = [{"role": "system", "content": self.system},
                   {"role": "user",
                    "content": "Propose ONE swap to address this objection. Return ONLY JSON "
                               '{"move":{"patient_id":..,"slot_id":..},"marginal_value":<num>,"reason":..}.\n'
                               + json.dumps(payload)}]
            obj = parse_json_obj(chat(msg, model=ADVOCATE_MODEL))
            return obj if isinstance(obj.get("move"), dict) else None
        except Exception:
            return None

    def _offline_swap(self, objection, ctx, draft):
        if self.name == "continuity":
            return _swap_continuity(objection, ctx, draft)
        if self.name == "preference":
            return _swap_preference(objection, ctx, draft)
        if self.name in ("priority", "window"):
            return _swap_seat(objection, ctx, draft, self.name)
        return None  # capacity does not trade


def _render_draft(draft, context):
    """Compact context for the LLM path — short to protect the token budget."""
    P = _index(context["patients"], "patient_id")
    S = _index(context["slots"], "slot_id")
    rows = []
    for a in draft:
        p, s = P.get(a["patient_id"]), S.get(a["slot_id"])
        if p and s:
            rows.append(f"{p['patient_id']}(acu{p['acuity_score']},prim {p['primary_clinician_id']},"
                        f"pref {p['preferred_mode']})->{s['slot_id']}[{s['clinician_id']},{s['mode']},{s['date']}]")
    unseen = [p["patient_id"] for p in context["patients"] if p["patient_id"] not in _assigned_map(draft)]
    return ("DRAFT:\n" + "\n".join(rows) + "\n\nUNSCHEDULED: " + ", ".join(unseen)
            + "\n\nFile your objections now.")


def build_all():
    return {n: Advocate(n) for n in ADVOCATES}
