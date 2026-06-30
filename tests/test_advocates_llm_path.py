"""Exercise the LLM path of the advocates without a key, by monkeypatching the
Qwen `chat` call. The contract: parse defensively, never crash the graph."""
from rehabpanel.society import advocates as A

CTX = {
    "patients": [
        {"patient_id": "P0", "acuity_score": 9, "followup_due_date": "2026-06-04",
         "primary_clinician_id": "C00", "preferred_mode": "clinic"},
    ],
    "slots": [{"slot_id": "S0", "clinician_id": "C00", "date": "2026-06-09",
               "start_time": "09:00", "mode": "clinic"}],
    "clinicians": [{"clinician_id": "C00", "weekly_capacity_slots": 2, "max_home_visits_per_day": 1}],
    "meta": {"t0": "2026-06-08"},
}
DRAFT = [{"patient_id": "P0", "slot_id": "S0"}]


def test_parse_json_list_handles_garbage():
    assert A.parse_json_list("not json at all") == []
    assert A.parse_json_list('prose [{"a":1}] trailer') == [{"a": 1}]
    assert A.parse_json_list("[broken") == []


def test_parse_json_obj_handles_garbage():
    assert A.parse_json_obj("nope") == {}
    assert A.parse_json_obj('ok {"move": {"patient_id": "P0"}} x') == {"move": {"patient_id": "P0"}}


def test_critique_online_parses_objections(monkeypatch):
    monkeypatch.setattr(A, "is_offline", lambda: False)
    monkeypatch.setattr(A, "chat",
                        lambda *a, **k: '[{"patient_id":"P0","slot_id":null,"severity":8,"reason":"x"}]')
    objs = A.Advocate("priority").critique(DRAFT, CTX)
    assert objs == [{"patient_id": "P0", "slot_id": None, "severity": 8, "reason": "x"}]


def test_critique_online_bad_output_returns_empty(monkeypatch):
    monkeypatch.setattr(A, "is_offline", lambda: False)
    monkeypatch.setattr(A, "chat", lambda *a, **k: "the model rambled, no JSON here")
    assert A.Advocate("window").critique(DRAFT, CTX) == []


def test_critique_online_transport_error_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(A, "is_offline", lambda: False)
    monkeypatch.setattr(A, "chat", boom)
    assert A.Advocate("continuity").critique(DRAFT, CTX) == []


def test_propose_swap_online_parses(monkeypatch):
    monkeypatch.setattr(A, "is_offline", lambda: False)
    monkeypatch.setattr(A, "chat",
                        lambda *a, **k: '{"move":{"patient_id":"P0","slot_id":"S0"},"marginal_value":4,"reason":"r"}')
    state = {**CTX, "draft": DRAFT}
    swap = A.Advocate("continuity").propose_swap({"patient_id": "P0", "slot_id": "S0"}, state)
    assert swap["move"] == {"patient_id": "P0", "slot_id": "S0"}


def test_propose_swap_online_bad_output_returns_none(monkeypatch):
    monkeypatch.setattr(A, "is_offline", lambda: False)
    monkeypatch.setattr(A, "chat", lambda *a, **k: "no json here, just prose")
    state = {**CTX, "draft": DRAFT}
    assert A.Advocate("continuity").propose_swap({"patient_id": "P0", "slot_id": "S0"}, state) is None


def test_propose_swap_online_non_dict_move_returns_none(monkeypatch):
    # malformed: "move" present but not an object -> must not reach the orchestrator
    monkeypatch.setattr(A, "is_offline", lambda: False)
    monkeypatch.setattr(A, "chat", lambda *a, **k: '{"move": "S0", "marginal_value": 4}')
    state = {**CTX, "draft": DRAFT}
    assert A.Advocate("preference").propose_swap({"patient_id": "P0", "slot_id": "S0"}, state) is None


def test_propose_swap_online_transport_error_returns_none(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(A, "is_offline", lambda: False)
    monkeypatch.setattr(A, "chat", boom)
    state = {**CTX, "draft": DRAFT}
    assert A.Advocate("window").propose_swap({"patient_id": "P0", "slot_id": "S0"}, state) is None
