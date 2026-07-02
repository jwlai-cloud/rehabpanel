"""Phase-1 backend contract: the CoordinatorService incident -> replan loop and
the FastAPI app wiring. Offline (deterministic), no network."""
import os
import pytest

from rehabpanel.state_service import CoordinatorService, INCIDENTS


@pytest.fixture(autouse=True)
def _offline():
    prev = os.environ.get("REHABPANEL_OFFLINE")
    os.environ["REHABPANEL_OFFLINE"] = "1"
    yield
    os.environ.pop("REHABPANEL_OFFLINE", None) if prev is None else os.environ.update(REHABPANEL_OFFLINE=prev)


def _svc():
    s = CoordinatorService()
    s.reset(seed=7, ratio=1.3)
    return s


def test_state_shape():
    st = _svc().state()
    assert len(st["agents"]) == 6                       # 5 advocates + referee
    assert {a["name"] for a in st["agents"]} >= {"priority", "referee", "capacity"}
    assert st["scores"]["committed"]["feasible"]
    assert st["rounds"] and st["plan_cells"]
    assert "overall_pct" in st["capacity"]
    assert st["headline_gap"] > 0                        # society beat baseline at init


@pytest.mark.parametrize("kind", INCIDENTS)
def test_incident_then_replan_recovers(kind):
    s = _svc()
    v0 = s.state()["score_history"][-1]["value"]
    after = s.incident(kind)
    v_after = after["score_history"][-1]["value"]
    assert after["incidents"][-1]["kind"] == kind
    recovered = s.replan()
    v_rec = recovered["score_history"][-1]["value"]
    assert recovered["scores"]["committed"]["feasible"]
    assert v_rec >= v_after                              # replan recovers (or holds)
    assert recovered["disruption"] is not None
    assert recovered["disruption"]["changed"] <= recovered["disruption"]["total"]


def test_sick_incident_drops_score():
    s = _svc()
    v0 = s.state()["score_history"][-1]["value"]
    s.incident("sick")                                  # lose slots -> orphaned patients
    assert s.state()["score_history"][-1]["value"] < v0


def test_set_rules_updates_weights_and_replans():
    s = _svc()
    n0 = len(s.state()["score_history"])
    st = s.set_rules({"continuity": 0})
    assert st["weights"]["continuity"] == 0
    assert len(st["score_history"]) > n0                 # a replan was recorded


def test_unknown_incident_rejected():
    with pytest.raises(ValueError):
        _svc().incident("earthquake")


def test_fastapi_app_exposes_routes():
    from rehabpanel.api import app
    paths = {r.path for r in app.routes}
    assert {"/api/state", "/api/replan", "/api/rules"} <= paths
    assert "/api/incident/{kind}" in paths


def test_stream_token_gate(monkeypatch):
    """When REHABPANEL_DEMO_TOKEN is set (public deploy), /api/stream must 401 without
    a matching ?token= — it bills the voucher, so an ungated public URL is a cost DoS."""
    from fastapi.testclient import TestClient
    from rehabpanel.api import app
    c = TestClient(app)
    monkeypatch.setenv("REHABPANEL_DEMO_TOKEN", "s3cret")
    assert c.get("/api/stream").status_code == 401                 # no token
    assert c.get("/api/stream?token=wrong").status_code == 401      # wrong token
    # correct token / unset gate would start a real negotiation — not exercised here.
