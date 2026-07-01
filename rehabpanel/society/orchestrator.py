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

from .advocates import build_all, parse_json_obj, _OFFLINE_CRITIQUE
from ..qwen_client import chat, is_offline, REFEREE_MODEL

DATA = Path(__file__).resolve().parent.parent.parent / "data"
PROMPTS = Path(__file__).resolve().parent / "prompts"
ROUND_CAP = 6        # online default — caps referee LLM calls (token budget)
SEVERITY_EXIT = 3   # preference objections are severity 3 — include them so the
                    # society also optimizes preference (a swap that would worsen a
                    # higher-ranked objective is still rejected by the referee)


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
    weights: dict          # priority weights — causal on advocate severities
    seed_draft: list       # warm start: repair this plan instead of drafting cold
    draft: list
    objections: list
    nego: dict             # this round's brokered move + negotiation transcript
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
    """Start the plan. WARM: if a seed_draft is given (re-plan after an incident),
    carry over every still-valid assignment and let critique/arbitrate repair only
    what broke — minimal disruption. COLD: Capacity emits a feasible skeleton,
    Priority fills by acuity. Orphaned carry-overs (slot gone) simply drop and
    become unscheduled, which the advocates then object to (the incident's damage,
    made visible)."""
    seed = state.get("seed_draft") or []
    S = {s["slot_id"]: s for s in state["slots"]}
    P = {p["patient_id"] for p in state["patients"]}
    draft, used_s, used_p = [], set(), set()
    if seed:
        for a in seed:
            if not isinstance(a, dict):
                continue  # tolerate a corrupted/partial seed without crashing the draft
            sid, pid = a.get("slot_id"), a.get("patient_id")
            if sid in S and pid in P and sid not in used_s and pid not in used_p:
                used_s.add(sid); used_p.add(pid)
                draft.append({"patient_id": pid, "slot_id": sid,
                              "assigned_in_round": 0, "rationale": "carried over"})
    else:
        for p in sorted(state["patients"], key=lambda p: -p["acuity_score"]):
            free = next((s for s in state["slots"] if s["slot_id"] not in used_s), None)
            if not free:
                break
            used_s.add(free["slot_id"])
            draft.append({"patient_id": p["patient_id"], "slot_id": free["slot_id"],
                          "assigned_in_round": 0, "rationale": "draft: acuity-first"})
    return {"draft": draft, "round": 0, "ledger": [], "stalled": False, "nego": {},
            "snapshots": [{"round": 0, "draft": [dict(a) for a in draft],
                           "rulings": [], "objections": [], "transcript": None}]}


def node_critique(state: SocietyState) -> dict:
    """Each advocate files objections (1-10 severity) against the current draft."""
    advocates = build_all()
    ctx = {k: state[k] for k in ("patients", "clinicians", "slots")}
    ctx["meta"] = state.get("meta")
    ctx["weights"] = state.get("weights") or {}
    objections = []
    for name, adv in advocates.items():
        try:
            objections += [{**o, "by": name} for o in adv.critique(state["draft"], ctx)]
        except Exception:
            pass  # an advocate must never crash the negotiation
    return {"objections": objections}


# ---- negotiation: proposals -> coalitions -> referee brokering ---------------

def _ctx(state):
    return {"patients": state["patients"], "clinicians": state["clinicians"],
            "slots": state["slots"], "meta": state.get("meta"),
            "weights": state.get("weights") or {}}


def _cost(fn, draft, ctx):
    """Weighted objection severity an advocate sees in a draft (its 'pain')."""
    try:
        return sum(o.get("severity", 0) for o in fn(draft, ctx))
    except Exception:
        return 0


def _coalitions(move, state):
    """Referee's internal impact model (deterministic + cheap, even online): apply
    the move to a copy and group advocates by whose objective improves (FOR) or
    worsens (AGAINST), sized by the drop/rise in their weighted objection cost."""
    S = {s["slot_id"]: s for s in state["slots"]}
    ctx = _ctx(state)
    after, _ = _apply_move(state["draft"], move, S, 0)
    forc, against = [], []
    for name, fn in _OFFLINE_CRITIQUE.items():
        delta = _cost(fn, state["draft"], ctx) - _cost(fn, after, ctx)  # >0 => improved
        if delta > 0:
            forc.append({"agent": name, "value": delta})
        elif delta < 0:
            against.append({"agent": name, "value": -delta})
    return forc, against


_ROLE = {"priority": "Priority", "window": "Follow-up Window", "continuity": "Continuity",
         "capacity": "Capacity", "preference": "Preference", "referee": "Charge-Nurse Referee"}

# Global priority ranking (the design's "acuity > continuity > preference; capacity
# never violated"). The referee brokers on this ordering, not raw severity sums, so
# it faithfully weighs objectives without importing the scorer into the graph.
_RANK = {"capacity": 100, "priority": 40, "window": 30, "continuity": 20, "preference": 10}


def _decide(forc, against):
    """Referee's ruling: never break feasibility (capacity veto), else approve iff
    the FOR coalition's top objective outranks (or ties) the AGAINST coalition's."""
    if any(a["agent"] == "capacity" for a in against):
        return False
    fr = max((_RANK.get(f["agent"], 0) for f in forc), default=0)
    ar = max((_RANK.get(a["agent"], 0) for a in against), default=0)
    return fr > 0 and fr >= ar


def _margin(forc, against):
    """Signed priority margin (top FOR rank - top AGAINST rank); very negative on a
    capacity veto or no FOR. Used to choose between competing proposals."""
    if any(a["agent"] == "capacity" for a in against):
        return -999
    fr = max((_RANK.get(f["agent"], 0) for f in forc), default=0)
    ar = max((_RANK.get(a["agent"], 0) for a in against), default=0)
    return (fr - ar) if fr > 0 else -999


def _bargain_enabled():
    return os.environ.get("REHABPANEL_BARGAIN") == "1"


def _propose(objection, adv, state, S, P):
    """Ask an advocate for a feasible swap addressing an objection; None if invalid."""
    try:
        swap = adv.propose_swap(objection, state)
    except Exception:
        return None
    if not swap or not isinstance(swap.get("move"), dict):
        return None
    m = swap["move"]
    if m.get("patient_id") not in P or m.get("slot_id") not in S:
        return None
    return swap


def _top_obj(agent, state):
    objs = [o for o in state["objections"]
            if o.get("by") == agent and o.get("severity", 0) >= SEVERITY_EXIT]
    return max(objs, key=lambda o: o.get("severity", 0)) if objs else None


def _transcript(top, swap, forc, against, label, decision, counter=None, chosen="proposal"):
    """Structured negotiation exchange — drives the UI chat + ledger line. With a
    `counter` (bargaining mode), it records the opposer's counter-proposal and which
    side the referee chose."""
    by = top.get("by")
    # the "active" proposer whose move is actually applied — the counter-proposer
    # when the referee chose the counter, else the original proposer. Drives both
    # the skipped 'supports' turn (they already spoke via proposes/counters) and
    # the ledger attribution, so the ledger names who really won.
    counter_won = bool(decision and chosen == "counter" and counter)
    win = counter["agent"] if counter_won else by
    win_reason = counter.get("reason", "") if counter_won else swap.get("reason", "")
    turns = [
        {"agent": by, "role": _ROLE.get(by, by), "stance": "objects",
         "text": top.get("reason", ""), "value": top.get("severity", 0)},
        {"agent": by, "role": _ROLE.get(by, by), "stance": "proposes",
         "text": swap.get("reason", ""), "value": swap.get("marginal_value", 0)},
    ]
    if counter:
        ca = counter["agent"]
        turns.append({"agent": ca, "role": _ROLE.get(ca, ca), "stance": "counters",
                      "text": counter.get("reason", ""), "value": counter.get("marginal_value", 0)})
    for f in forc:
        if f["agent"] == win:
            continue
        turns.append({"agent": f["agent"], "role": _ROLE.get(f["agent"], f["agent"]),
                      "stance": "supports", "text": "objective improves", "value": f["value"]})
    for a in against:
        turns.append({"agent": a["agent"], "role": _ROLE.get(a["agent"], a["agent"]),
                      "stance": "opposes", "text": "objective worsens", "value": a["value"]})
    for_v = sum(f["value"] for f in forc)
    ag_v = sum(a["value"] for a in against)
    if not decision:
        rule = "rejects — no proposal outranks the opposition"
    elif counter:
        rule = f"chose the {chosen} — FOR ({for_v}) vs AGAINST ({ag_v})"
    else:
        rule = f"approves — coalition FOR ({for_v}) vs AGAINST ({ag_v})"
    turns.append({"agent": "referee", "role": _ROLE["referee"], "stance": "ruling",
                  "text": rule + " at current weights", "value": for_v - ag_v})
    line = f"{label} — {_ROLE.get(win, win)}: {win_reason}. Referee {rule}."
    return {"contested": label, "turns": turns,
            "coalition_for": [f["agent"] for f in forc], "for_value": for_v,
            "coalition_against": [a["agent"] for a in against], "against_value": ag_v,
            "decision": "apply" if decision else "reject", "ledger": line}


def node_negotiate(state: SocietyState) -> dict:
    """Draft -> Critique -> NEGOTIATE -> Arbitrate. The relevant advocate proposes a
    swap; a deterministic impact model forms FOR/AGAINST coalitions; the referee
    brokers on the priority ranking. With REHABPANEL_BARGAIN=1, when a proposal draws
    opposition the top opposing advocate makes a COUNTER-proposal and the referee
    chooses between them — a genuine multi-turn exchange. Records the chosen move +
    transcript; tries the next objection on rejection; stalls if none survive."""
    advocates = build_all()
    S = {s["slot_id"]: s for s in state["slots"]}
    P = {p["patient_id"] for p in state["patients"]}
    hot = sorted((o for o in state["objections"] if o.get("severity", 0) >= SEVERITY_EXIT),
                 key=lambda o: -o.get("severity", 0))
    rejected = []
    for top in hot:
        adv = advocates.get(top.get("by"))
        if not adv:
            continue
        swap = _propose(top, adv, state, S, P)
        if not swap:
            continue
        forc, against = _coalitions(swap["move"], state)
        counter = counter_swap = c_forc = c_against = None
        if _bargain_enabled() and against:                 # multi-turn: let the opposer counter
            opp = max(against, key=lambda a: _RANK.get(a["agent"], 0))["agent"]
            oo, oa = _top_obj(opp, state), advocates.get(opp)
            counter_swap = _propose(oo, oa, state, S, P) if (oo and oa) else None
            if counter_swap:                               # a concrete alternative move
                counter = {**counter_swap, "agent": opp}   # explicit opp wins over any model-returned 'agent'
                c_forc, c_against = _coalitions(counter_swap["move"], state)
            else:                                          # else the opposer defends the status quo
                oppval = next((a["value"] for a in against if a["agent"] == opp), 0)
                counter = {"agent": opp, "reason": "hold — keep the current assignment",
                           "marginal_value": oppval}
        opts = [("proposal", swap["move"], forc, against)]
        if counter_swap:
            opts.append(("counter", counter_swap["move"], c_forc, c_against))
        viable = [o for o in opts if _decide(o[2], o[3])]
        chosen = max(viable, key=lambda o: _margin(o[2], o[3])) if viable else None
        label = _slot_label(S[swap["move"]["slot_id"]])
        if chosen:
            _, move_, f_, a_ = chosen
            tr = _transcript(top, swap, f_, a_, label, True, counter=counter, chosen=chosen[0])
            tr["rejected"] = rejected
            return {"nego": {"move": move_, "transcript": tr, "line": tr["ledger"]}}
        tr = _transcript(top, swap, forc, against, label, False, counter=counter)
        rejected.append({"contested": tr["contested"], "role": tr["turns"][0]["role"],
                         "line": tr["ledger"]})
    return {"nego": {"move": None, "rejected": rejected}, "stalled": True}


def node_arbitrate(state: SocietyState) -> dict:
    """Apply the referee-brokered move and log the agreement + transcript."""
    rnd = state["round"] + 1
    nego = state.get("nego") or {}
    move = nego.get("move")
    if not move:
        return {"round": rnd, "stalled": True}
    S = {s["slot_id"]: s for s in state["slots"]}
    new_draft, changed = _apply_move(state["draft"], move, S, rnd)
    if not changed:
        return {"round": rnd, "stalled": True}
    line = nego.get("line", "")
    return {"round": rnd, "draft": new_draft, "ledger": [line], "stalled": False,
            "snapshots": [{"round": rnd, "draft": [dict(a) for a in new_draft],
                           "rulings": [line], "objections": state["objections"],
                           "transcript": nego.get("transcript")}]}


def should_continue(state: SocietyState) -> str:
    if state.get("stalled"):
        return "end"
    hot = [o for o in state["objections"] if o.get("severity", 0) >= SEVERITY_EXIT]
    if hot and state["round"] < round_cap():
        return "negotiate"
    return "end"


# ---- graph -----------------------------------------------------------------

def build_graph():
    g = StateGraph(SocietyState)
    g.add_node("draft", node_draft)
    g.add_node("critique", node_critique)
    g.add_node("negotiate", node_negotiate)
    g.add_node("arbitrate", node_arbitrate)
    g.add_edge(START, "draft")
    g.add_edge("draft", "critique")
    g.add_conditional_edges("critique", should_continue,
                            {"negotiate": "negotiate", "end": END})
    g.add_edge("negotiate", "arbitrate")
    g.add_edge("arbitrate", "critique")
    return g.compile()


def negotiate(tables, seed_draft=None, weights=None):
    """In-memory negotiation: takes the world tables (+ optional warm-start draft
    and priority weights), returns the final graph state (draft, ledger,
    snapshots, round...). No file IO — the API and CLI both call this. The scorer
    stays external; score snapshots afterwards."""
    init: SocietyState = {
        "patients": tables.get("patients", []), "clinicians": tables.get("clinicians", []),
        "slots": tables.get("slots", []), "meta": tables.get("meta", {}),
        "weights": weights or {}, "seed_draft": seed_draft or [],
        "draft": [], "objections": [], "nego": {}, "ledger": [], "snapshots": [],
        "round": 0, "stalled": False,
    }
    return build_graph().invoke(init)


def run(seed=7):
    tables = {n: _load(n) for n in ("patients", "clinicians", "slots")}
    tables["meta"] = _load("meta")
    final = negotiate(tables)
    (DATA / "assignments_society.json").write_text(json.dumps(final["draft"], indent=2))
    (DATA / "conflict_ledger.json").write_text(json.dumps(final["ledger"], indent=2))
    (DATA / "society_rounds.json").write_text(json.dumps(final["snapshots"], indent=2))
    print(f"society -> {len(final['draft'])} assignments, "
          f"{len(final['ledger'])} rulings, {final['round']} rounds")
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=7)
    run(ap.parse_args().seed)
