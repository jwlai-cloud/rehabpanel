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


def test_priority_weights_are_causal():
    t = _tables()
    P, C, S, M = t["patients"], t["clinicians"], t["slots"], t["meta"]
    ignore = O.negotiate(t, weights={"acuity": 10, "overdue": 1, "continuity": 0, "pref": 2})["draft"]
    favour = O.negotiate(t, weights={"acuity": 10, "overdue": 1, "continuity": 8, "pref": 2})["draft"]
    assert score(favour, P, C, S, meta=M)["continuity_breaks"] < \
           score(ignore, P, C, S, meta=M)["continuity_breaks"]
