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


# Scale advocate severity so the Rules view is causal: a weight near 0 drops that
# objective below SEVERITY_EXIT (the referee ignores it), a raised weight makes it
# outrank others. The reference is the SCORER's own default weights, so the DEFAULT
# config always leaves severities UNSCALED — otherwise re-weighting the scorer would
# silently mute the advocates (halving continuity/pref once dropped them below exit).
from ..scorer import DEFAULT_WEIGHTS as _SCORER_W
_DEFAULT_W = {k: _SCORER_W[k] for k in ("acuity", "overdue", "continuity", "pref")}


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
    # 1) open slot: preferred mode + same clinician (strictly non-regressing)
    s = _free_slot_for(lambda sl: sl["mode"] == pref and sl["clinician_id"] == cid, ctx, draft)
    if s:
        return {"move": {"patient_id": pid, "slot_id": s["slot_id"]},
                "marginal_value": 2.0, "reason": f"{pid} -> {pref} slot (same clinician)"}
    # 2) open slot: preferred mode + the patient's PRIMARY clinician (fixes pref AND continuity)
    s = _free_slot_for(lambda sl: sl["mode"] == pref and sl["clinician_id"] == p["primary_clinician_id"],
                       ctx, draft)
    if s:
        return {"move": {"patient_id": pid, "slot_id": s["slot_id"]},
                "marginal_value": 3.0, "reason": f"{pid} -> {pref} slot w/ primary"}
    # 3) full plan: prefer a swap with q in the SAME clinician's preferred-mode slot —
    #    only the modes trade, so continuity is unchanged for both (the safest pref fix).
    for a in draft:
        if a["patient_id"] == pid:
            continue
        qslot = S.get(a["slot_id"])
        if qslot and qslot["mode"] == pref and qslot["clinician_id"] == cid:
            return {"move": {"patient_id": pid, "slot_id": a["slot_id"]},
                    "marginal_value": 2.0, "reason": f"{pid} <-> {a['patient_id']} (same clinician, {pref})"}
    # 4) any preferred-mode slot — the referee's coalition model rejects the swap if it
    #    worsens a higher-ranked objective (e.g. continuity), so this can only help net.
    for a in draft:
        if a["patient_id"] == pid:
            continue
        qslot = S.get(a["slot_id"])
        if qslot and qslot["mode"] == pref:
            return {"move": {"patient_id": pid, "slot_id": a["slot_id"]},
                    "marginal_value": 2.0, "reason": f"{pid} <-> {a['patient_id']} for {pref} slot"}
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
        objs = []
        try:
            # System = SHARED caseload prefix (cached across all advocates + rounds)
            # + this advocate's role. User = only the small, changing plan state.
            # Ask for the TOP 3 objections, not an exhaustive list — tiny output = fast.
            sysmsg = _caseload_ref(context) + "\n\n---\n" + self.system
            usermsg = (_assignment_state(draft, context) +
                       '\n\nReturn ONLY your 3 most severe objections on YOUR objective as a JSON list, '
                       'most severe first: [{"patient_id":..,"slot_id":..,"severity":1-10,"reason":".."}]. '
                       "[] if none.")
            msg = [{"role": "system", "content": sysmsg}, {"role": "user", "content": usermsg}]
            objs = [o for o in parse_json_list(chat(msg, model=ADVOCATE_MODEL)) if isinstance(o, dict)][:3]
        except Exception:
            objs = []  # never crash the graph on an LLM/transport error
        # Live LLM output is flaky (empty / unparseable) -> the society would raise
        # zero objections and return the raw draft. Fall back to the deterministic
        # critique so it ALWAYS negotiates. Both paths feed the same scorer.
        return objs or _OFFLINE_CRITIQUE[self.name](draft, context)

    # -- propose_swap ---------------------------------------------------------
    def propose_swap(self, objection, state):
        """A concrete swap addressing the objection — DETERMINISTIC in both modes.
        The advocates' real LLM reasoning lives in critique(); the mechanical swap
        (which feasible slot to move to) needs no extra LLM round-trip, so live runs
        stay fast/cheap: the only live calls are the short, cached-prefix critiques."""
        ctx = {k: state[k] for k in ("patients", "clinicians", "slots") if k in state}
        ctx["meta"] = state.get("meta")
        return self._offline_swap(objection, ctx, state["draft"])

    def _offline_swap(self, objection, ctx, draft):
        if self.name == "continuity":
            return _swap_continuity(objection, ctx, draft)
        if self.name == "preference":
            return _swap_preference(objection, ctx, draft)
        if self.name in ("priority", "window"):
            return _swap_seat(objection, ctx, draft, self.name)
        return None  # capacity does not trade


def _caseload_ref(context):
    """The invariant caseload as a compact table. IDENTICAL on every call and every
    round, so it forms a cacheable prompt PREFIX — Qwen auto prefix-caching bills the
    big context once and re-prefills it near-instantly, instead of re-sending it per
    advocate per round (the token/latency waste)."""
    P, S = context["patients"], context["slots"]
    pl = "\n".join(f"{p['patient_id']} acu{p['acuity_score']} prim:{p['primary_clinician_id']} "
                   f"pref:{p['preferred_mode']} due:{p['followup_due_date']}" for p in P)
    sl = "\n".join(f"{s['slot_id']} {s['clinician_id']} {s['mode']} {s['date']}" for s in S)
    return f"CASELOAD (fixed reference)\n# patients: id acuity primary pref due\n{pl}\n\n# slots: id clinician mode date\n{sl}"


def _assignment_state(draft, context):
    """The VARIABLE part — just the current patient->slot map + who's unscheduled.
    Small, so only this changes between calls; the caseload prefix stays cached."""
    seated = ", ".join(f"{a['patient_id']}->{a['slot_id']}" for a in draft)
    seen = _assigned_map(draft)
    unseen = [p["patient_id"] for p in context["patients"] if p["patient_id"] not in seen]
    return f"CURRENT PLAN: {seated}\nUNSCHEDULED: {', '.join(unseen) or 'none'}"


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
