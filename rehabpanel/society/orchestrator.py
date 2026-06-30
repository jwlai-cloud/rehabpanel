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
import argparse, json
from pathlib import Path
from typing import TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, START, END

from .advocates import build_all
from ..qwen_client import chat, REFEREE_MODEL

DATA = Path(__file__).resolve().parent.parent.parent / "data"
ROUND_CAP = 6
SEVERITY_EXIT = 4


class SocietyState(TypedDict):
    patients: list
    clinicians: list
    slots: list
    draft: list
    objections: list
    ledger: Annotated[list, operator.add]   # rulings accumulate across rounds
    round: int


def _load(n):
    return json.loads((DATA / f"{n}.json").read_text())


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
    return {"draft": draft, "round": 0, "ledger": []}


def node_critique(state: SocietyState) -> dict:
    """Each advocate files objections (1-10 severity) against the current draft."""
    advocates = build_all()
    ctx = {k: state[k] for k in ("patients", "clinicians", "slots")}
    objections = []
    for name, adv in advocates.items():
        try:
            objections += [{**o, "by": name} for o in adv.critique(state["draft"], ctx)]
        except NotImplementedError:
            pass  # TODO(claude-code): remove once advocates are implemented
    return {"objections": objections}


def node_arbitrate(state: SocietyState) -> dict:
    """Referee resolves the highest-severity objection and logs the ruling.

    TODO(claude-code): replace the no-op below with a referee LLM call
    (prompts/referee.md) that:
      1. requests swap proposals (with marginal values) for hot objections,
      2. rules using global weights + marginal values,
      3. applies the winning swap to `draft`,
      4. returns a one-line ledger entry.
    The round counter + ROUND_CAP guarantee termination meanwhile.
    """
    hot = sorted((o for o in state["objections"] if o.get("severity", 0) >= SEVERITY_EXIT),
                 key=lambda o: -o["severity"])
    ledger_entry = []
    if hot:
        top = hot[0]
        # referee_msg = [{"role": "system", "content": (PROMPTS/"referee.md").read_text()}, ...]
        # ruling = parse(chat(referee_msg, model=REFEREE_MODEL))
        # apply ruling to draft ...
        ledger_entry = [f"round {state['round']+1}: {top.get('by')} objection on "
                        f"{top.get('patient_id')} (sev {top.get('severity')}) — TODO resolve"]
    return {"round": state["round"] + 1, "ledger": ledger_entry}


def should_continue(state: SocietyState) -> str:
    hot = [o for o in state["objections"] if o.get("severity", 0) >= SEVERITY_EXIT]
    if hot and state["round"] < ROUND_CAP:
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
        "slots": _load("slots"), "draft": [], "objections": [], "ledger": [], "round": 0,
    }
    final = build_graph().invoke(init)
    (DATA / "assignments_society.json").write_text(json.dumps(final["draft"], indent=2))
    (DATA / "conflict_ledger.json").write_text(json.dumps(final["ledger"], indent=2))
    print(f"society -> {len(final['draft'])} assignments, "
          f"{len(final['ledger'])} rulings, {final['round']} rounds")
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=7)
    run(ap.parse_args().seed)
