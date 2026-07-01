"""Phase-0 engine contract: in-memory generate/negotiate, warm-start re-plan
(low disruption), per-round objections, and causal priority weights. All offline
(deterministic), so CI proves it key-free.
"""
import os
import pytest

from rehabpanel import generator
from rehabpanel.society import orchestrator as O
from rehabpanel.scorer import score
from rehabpanel import baseline


@pytest.fixture(autouse=True)
def _offline():
    prev = os.environ.get("REHABPANEL_OFFLINE")
    os.environ["REHABPANEL_OFFLINE"] = "1"
    yield
    os.environ.pop("REHABPANEL_OFFLINE", None) if prev is None else os.environ.update(REHABPANEL_OFFLINE=prev)


def _tables():
    return generator.generate(seed=7, ratio=1.3, write=False)


def _disruption(seed_plan, new_plan):
    a = {x["patient_id"]: x["slot_id"] for x in seed_plan}
    b = {x["patient_id"]: x["slot_id"] for x in new_plan}
    return sum(1 for p, s in a.items() if b.get(p) != s)


def test_generate_returns_tables_without_writing():
    t = generator.generate(seed=7, ratio=1.3, write=False)
    assert set(t) >= {"patients", "clinicians", "slots", "meta"}
    assert len(t["patients"]) == round(len(t["slots"]) * 1.3)
    assert t["meta"]["t0"]


def test_negotiate_in_memory_beats_baseline():
    t = _tables()
    P, C, S, M = t["patients"], t["clinicians"], t["slots"], t["meta"]
    final = O.negotiate(t)
    soc = score(final["draft"], P, C, S, meta=M)
    base = score(baseline.plan(P, C, S), P, C, S, meta=M)
    assert soc["feasible"]
    assert soc["value"] > base["value"]
    assert final["round"] >= 1


def test_snapshots_carry_objections():
    final = O.negotiate(_tables())
    # round 0 = draft, later rounds carry the objections the referee weighed
    assert all("objections" in snap for snap in final["snapshots"])
    assert any(snap["objections"] for snap in final["snapshots"][1:])


def test_warm_replan_is_less_disruptive_than_cold():
    t = _tables()
    plan0 = O.negotiate(t)["draft"]
    # incident: clinician C00 calls in sick -> their slots vanish
    t2 = dict(t)
    t2["slots"] = [s for s in t["slots"] if s["clinician_id"] != "C00"]
    warm = O.negotiate(t2, seed_draft=plan0)["draft"]
    cold = O.negotiate(t2, seed_draft=None)["draft"]
    P, C, M = t["patients"], t["clinicians"], t["meta"]
    assert score(warm, P, C, t2["slots"], meta=M)["feasible"]
    assert _disruption(plan0, warm) < _disruption(plan0, cold)


def test_referee_ranking_decisions():
    from rehabpanel.society.orchestrator import _decide
    assert _decide([{"agent": "priority", "value": 3}], []) is True
    # preference can't outrank priority even with a bigger raw value
    assert _decide([{"agent": "preference", "value": 9}], [{"agent": "priority", "value": 1}]) is False
    # capacity in the AGAINST coalition is an absolute veto
    assert _decide([{"agent": "priority", "value": 1}], [{"agent": "capacity", "value": 1}]) is False
    # continuity outranks preference
    assert _decide([{"agent": "continuity", "value": 1}], [{"agent": "preference", "value": 9}]) is True


def test_negotiation_emits_transcript_with_coalitions():
    final = O.negotiate(_tables())
    trs = [s["transcript"] for s in final["snapshots"] if s.get("transcript")]
    assert trs, "negotiation produced no transcripts"
    tr = trs[0]
    assert tr["turns"] and tr["coalition_for"]
    assert any(t["stance"] == "ruling" for t in tr["turns"])
    assert tr["decision"] in ("apply", "reject")


def test_incident_replan_surfaces_opposition():
    """A warm re-plan after a sick incident should produce at least one round with
    a real AGAINST coalition — the referee brokering a genuine disagreement."""
    t = _tables()
    plan0 = O.negotiate(t)["draft"]
    t2 = dict(t)
    t2["slots"] = [s for s in t["slots"] if s["clinician_id"] != "C00"]
    final = O.negotiate(t2, seed_draft=plan0)
    against = [s["transcript"] for s in final["snapshots"]
               if s.get("transcript") and s["transcript"]["coalition_against"]]
    assert against, "no opposing coalition surfaced on incident re-plan"


def test_bargaining_produces_counter_proposals():
    """With REHABPANEL_BARGAIN=1, a contested re-plan round yields a counter-turn
    (the opposer's alternative) — a genuine multi-turn exchange. Off by default."""
    prev = os.environ.get("REHABPANEL_BARGAIN")
    os.environ["REHABPANEL_BARGAIN"] = "1"
    try:
        t = _tables()
        plan0 = O.negotiate(t)["draft"]
        t2 = dict(t)
        t2["slots"] = [s for s in t["slots"] if s["clinician_id"] != "C00"]
        final = O.negotiate(t2, seed_draft=plan0)
        counters = [tr for s in final["snapshots"] if (tr := s.get("transcript"))
                    and any(x["stance"] == "counters" for x in tr["turns"])]
        assert counters, "bargaining produced no counter-proposals"
    finally:
        os.environ.pop("REHABPANEL_BARGAIN", None) if prev is None else os.environ.update(REHABPANEL_BARGAIN=prev)


def test_counter_win_is_attributed_to_the_counter_proposer():
    """When the referee picks the COUNTER, the ledger + coalition transcript must
    credit the counter-proposer, not the original proposer (else the demo's ledger
    lies about who won)."""
    from rehabpanel.society.orchestrator import _transcript
    top = {"by": "priority", "reason": "acuity 8 unscheduled", "severity": 8}
    swap = {"reason": "seat P13 over P00", "marginal_value": 8, "move": {"patient_id": "P13"}}
    counter = {"agent": "window", "reason": "hold — keep the current assignment", "marginal_value": 3}
    # coalitions AS SEEN FOR THE CHOSEN COUNTER: window (its own counter) + continuity support it
    forc = [{"agent": "window", "value": 3}, {"agent": "continuity", "value": 5}]
    against = [{"agent": "preference", "value": 2}]
    tr = _transcript(top, swap, forc, against, "Mon 13:00", True, counter=counter, chosen="counter")
    assert "Follow-up Window" in tr["ledger"] and "hold" in tr["ledger"]
    assert "seat P13" not in tr["ledger"]                       # not the losing original proposal
    stances = {t["agent"]: t["stance"] for t in tr["turns"]}
    assert stances["window"] == "counters"                      # window spoke as counter, not a redundant 'supports'
    assert not any(t["stance"] in ("supports", "opposes") for t in tr["turns"])  # coalition shown in arrays, not generic turns
    assert "continuity" in tr["coalition_for"]                  # the genuine supporter is recorded in the FOR coalition
    assert "preference" in tr["coalition_against"]


def test_priority_weights_are_causal():
    t = _tables()
    P, C, S, M = t["patients"], t["clinicians"], t["slots"], t["meta"]
    ignore = O.negotiate(t, weights={"acuity": 10, "overdue": 1, "continuity": 0, "pref": 2})["draft"]
    favour = O.negotiate(t, weights={"acuity": 10, "overdue": 1, "continuity": 8, "pref": 2})["draft"]
    assert score(favour, P, C, S, meta=M)["continuity_breaks"] < \
           score(ignore, P, C, S, meta=M)["continuity_breaks"]
