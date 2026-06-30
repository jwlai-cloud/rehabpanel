"""Charge-Nurse Referee orchestration as a LangGraph state machine.

WHY LANGGRAPH (and not a heavyweight autonomous framework): the negotiation
protocol is a DETERMINISTIC state machine — Draft -> Critique -> Arbitrate with
a loop and an explicit exit condition — not open-ended tool-calling autonomy.
LangGraph gives us an explicit, visualizable graph while we keep full control of
the control flow. Autonomy lives INSIDE each agent's reasoning, not in the loop.

The deterministic scorer is intentionally kept OUTSIDE the graph (called after
the graph finishes) so the benchmark stays reproducible and framework-agnostic.

Graph:
    START -> draft -> critique -> [hot objections & round<cap ?]
                         ^                |  yes -> arbitrate -> (back to critique)
                         |________________|  no  -> END
"""
import argparse, json, os
from datetime import date
from pathlib import Path
from typing import TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, START, END

from .advocates import build_all, parse_json_obj
from ..qwen_client import chat, is_offline, REFEREE_MODEL

DATA = Path(__file__).resolve().parent.parent.parent / "data"
PROMPTS = Path(__file__).resolve().parent / "prompts"
ROUND_CAP = 6        # online default — caps referee LLM calls (token budget)
SEVERITY_EXIT = 4


def round_cap():
    """Offline negotiation is ~free, so let it run one conflict at a time to
    convergence (a richer ledger + a watchable demo); online stays capped tight
    to protect the $40 voucher. Override with REHABPANEL_ROUND_CAP."""
    env = os.environ.get("REHABPANEL_ROUND_CAP")
    if env:
        return int(env)
    return 40 if is_offline() else ROUND_CAP


class SocietyState(TypedDict):
    patients: list
    clinicians: list
    slots: list
    meta: dict
    draft: list
    objections: list
    ledger: Annotated[list, operator.add]      # rulings accumulate across rounds
    snapshots: Annotated[list, operator.add]   # per-round plan state (drives the scrub UI)
    round: int
    stalled: bool


def _load(n):
    return json.loads((DATA / f"{n}.json").read_text())


def _slot_label(slot):
    """'Tue 10:00' — human-readable for the conflict ledger."""
    wd = date.fromisoformat(slot["date"]).strftime("%a")
    return f"{wd} {slot.get('start_time', '')}".strip()


def _apply_move(draft, move, slots_by_id, rnd):
    """Apply a referee-approved {patient_id, slot_id} move, keeping the plan
    feasible (no double-book): swap slots if the target is occupied, displace if
    the mover was unscheduled, else just move. Returns (new_draft, changed)."""
    pid, sid = move.get("patient_id"), move.get("slot_id")
    if sid not in slots_by_id or pid is None:
        return draft, False
    new = [dict(a) for a in draft]
    occupant = next((a for a in new if a["slot_id"] == sid), None)
    mover = next((a for a in new if a["patient_id"] == pid), None)
    if occupant is mover and mover is not None:
        return draft, False  # already there
    if mover and occupant:                      # swap the two patients' slots
        occupant["slot_id"], mover["slot_id"] = mover["slot_id"], sid
        for a in (occupant, mover):              # both patients moved this round
            a["assigned_in_round"] = rnd
            a["rationale"] = "referee: swap"
    elif mover and not occupant:                # target free — just move
        mover["slot_id"] = sid
        mover["assigned_in_round"] = rnd
        mover["rationale"] = "referee: move"
    elif occupant and not mover:                # mover unscheduled — displace
        new = [a for a in new if a is not occupant]
        new.append({"patient_id": pid, "slot_id": sid,
                    "assigned_in_round": rnd, "rationale": "referee: seat"})
    else:                                       # both free
        new.append({"patient_id": pid, "slot_id": sid,
                    "assigned_in_round": rnd, "rationale": "referee: seat"})
    return new, True


# ---- nodes -----------------------------------------------------------------

def node_draft(state: SocietyState) -> dict:
    """Capacity emits feasible skeleton; Priority fills by acuity (first pass)."""
    ranked = sorted(state["patients"], key=lambda p: -p["acuity_score"])
    open_slots = list(state["slots"])
    draft = []
    for p in ranked:
        if not open_slots:
            break
        s = open_slots.pop(0)
        draft.append({"patient_id": p["patient_id"], "slot_id": s["slot_id"],
                      "assigned_in_round": 0, "rationale": "draft: acuity-first"})
    return {"draft": draft, "round": 0, "ledger": [], "stalled": False,
            "snapshots": [{"round": 0, "draft": [dict(a) for a in draft], "rulings": []}]}


def node_critique(state: SocietyState) -> dict:
    """Each advocate files objections (1-10 severity) against the current draft."""
    advocates = build_all()
    ctx = {k: state[k] for k in ("patients", "clinicians", "slots")}
    ctx["meta"] = state.get("meta")
    objections = []
    for name, adv in advocates.items():
        try:
            objections += [{**o, "by": name} for o in adv.critique(state["draft"], ctx)]
        except Exception:
            pass  # an advocate must never crash the negotiation
    return {"objections": objections}


def _referee_rule(top, swap, slot_label):
    """Build the apply-dict + one human-readable ledger line for a resolved
    objection. Offline = template; online = let qwen3.7-max phrase the rationale."""
    move = swap["move"]
    if is_offline():
        line = (f"{slot_label} — {top.get('by')}({top.get('patient_id')}, sev "
                f"{top.get('severity')}): {top.get('reason')}. Ruling: {swap.get('reason')} "
                f"(marginal value {swap.get('marginal_value')}).")
        return move, line
    try:
        msg = [{"role": "system", "content": (PROMPTS / "referee.md").read_text()},
               {"role": "user", "content": "Resolve this objection. Return ONLY JSON "
                '{"apply":{"<patient_id>":"<slot_id>"},"ledger_entry":"..."}.\n'
                + json.dumps({"objection": top, "proposed_swap": swap})}]
        ruling = parse_json_obj(chat(msg, model=REFEREE_MODEL))
        apply = ruling.get("apply") or {}
        if apply:
            pid, sid = next(iter(apply.items()))
            move = {"patient_id": pid, "slot_id": sid}
        return move, ruling.get("ledger_entry") or f"{slot_label} — resolved {top.get('patient_id')}."
    except Exception:
        line = f"{slot_label} — {top.get('by')}({top.get('patient_id')}): {swap.get('reason')}."
        return move, line


def node_arbitrate(state: SocietyState) -> dict:
    """Referee resolves the single highest-severity *actionable* objection this
    round: request a swap from the relevant advocate, rule on global weights +
    marginal value, apply it feasibly, and log one ledger line. One conflict per
    round keeps the ledger a readable play-by-play (and drives the scrub demo).
    If no hot objection can be actioned, mark stalled so the loop exits."""
    advocates = build_all()
    S = {s["slot_id"]: s for s in state["slots"]}
    rnd = state["round"] + 1
    hot = sorted((o for o in state["objections"] if o.get("severity", 0) >= SEVERITY_EXIT),
                 key=lambda o: -o.get("severity", 0))
    for top in hot:
        adv = advocates.get(top.get("by"))
        if not adv:
            continue
        try:
            swap = adv.propose_swap(top, state)
        except Exception:
            swap = None
        if not swap or not isinstance(swap.get("move"), dict):
            continue  # never let a malformed LLM move crash the round
        move = swap["move"]
        pid, sid = move.get("patient_id"), move.get("slot_id")
        if pid is None or sid not in S:
            continue  # skip invalid/hallucinated moves before the costly referee call
        label = _slot_label(S[sid])
        move, line = _referee_rule(top, swap, label)
        new_draft, changed = _apply_move(state["draft"], move, S, rnd)
        if not changed:
            continue
        return {"round": rnd, "draft": new_draft, "ledger": [line], "stalled": False,
                "snapshots": [{"round": rnd, "draft": [dict(a) for a in new_draft],
                               "rulings": [line]}]}
    return {"round": rnd, "stalled": True}  # nothing actionable -> exit


def should_continue(state: SocietyState) -> str:
    if state.get("stalled"):
        return "end"
    hot = [o for o in state["objections"] if o.get("severity", 0) >= SEVERITY_EXIT]
    if hot and state["round"] < round_cap():
        return "arbitrate"
    return "end"


# ---- graph -----------------------------------------------------------------

def build_graph():
    g = StateGraph(SocietyState)
    g.add_node("draft", node_draft)
    g.add_node("critique", node_critique)
    g.add_node("arbitrate", node_arbitrate)
    g.add_edge(START, "draft")
    g.add_edge("draft", "critique")
    g.add_conditional_edges("critique", should_continue,
                            {"arbitrate": "arbitrate", "end": END})
    g.add_edge("arbitrate", "critique")
    return g.compile()


def run(seed=7):
    init: SocietyState = {
        "patients": _load("patients"), "clinicians": _load("clinicians"),
        "slots": _load("slots"), "meta": _load("meta"),
        "draft": [], "objections": [], "ledger": [], "snapshots": [],
        "round": 0, "stalled": False,
    }
    final = build_graph().invoke(init)
    (DATA / "assignments_society.json").write_text(json.dumps(final["draft"], indent=2))
    (DATA / "conflict_ledger.json").write_text(json.dumps(final["ledger"], indent=2))
    (DATA / "society_rounds.json").write_text(json.dumps(final["snapshots"], indent=2))
    print(f"society -> {len(final['draft'])} assignments, "
          f"{len(final['ledger'])} rulings, {final['round']} rounds")
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=7)
    run(ap.parse_args().seed)
