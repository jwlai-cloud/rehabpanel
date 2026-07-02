"""Lock the objective function on hand-built mini-cases BEFORE building agents.
These tests are what make the headline number trustworthy."""
from rehabpanel.scorer import score

META = {"t0": "2026-06-08"}
CLIN = [{"clinician_id": "C00", "weekly_capacity_slots": 2, "max_home_visits_per_day": 1}]
SLOTS = [
    {"slot_id": "S0", "clinician_id": "C00", "date": "2026-06-09", "mode": "clinic"},
    {"slot_id": "S1", "clinician_id": "C00", "date": "2026-06-09", "mode": "clinic"},
]
PATS = [
    {"patient_id": "P0", "acuity_score": 9, "followup_due_date": "2026-06-04",
     "primary_clinician_id": "C00", "preferred_mode": "clinic"},
    {"patient_id": "P1", "acuity_score": 3, "followup_due_date": "2026-06-09",
     "primary_clinician_id": "C00", "preferred_mode": "clinic"},
]


def test_feasible_clean_plan():
    a = [{"patient_id": "P0", "slot_id": "S0"}, {"patient_id": "P1", "slot_id": "S1"}]
    r = score(a, PATS, CLIN, SLOTS, meta=META)
    assert r["feasible"] is True
    assert r["continuity_breaks"] == 0


def test_double_booking_is_infeasible():
    a = [{"patient_id": "P0", "slot_id": "S0"}, {"patient_id": "P1", "slot_id": "S0"}]
    r = score(a, PATS, CLIN, SLOTS, meta=META)
    assert r["feasible"] is False


def test_unscheduled_high_acuity_hurts_value():
    full = [{"patient_id": "P0", "slot_id": "S0"}, {"patient_id": "P1", "slot_id": "S1"}]
    partial = [{"patient_id": "P1", "slot_id": "S1"}]  # drop the acuity-9 patient
    assert score(full, PATS, CLIN, SLOTS, meta=META)["value"] > \
           score(partial, PATS, CLIN, SLOTS, meta=META)["value"]


def test_seeing_more_patients_raises_value():
    """Care delivered has value: seeing a low-acuity, not-yet-overdue patient — even
    with a single continuity break — beats leaving them unseen. This closes the
    loophole where an agent scores well by dropping hard-to-place patients."""
    slots = SLOTS + [{"slot_id": "SX", "clinician_id": "C99", "date": "2026-06-09", "mode": "clinic"}]
    clin = CLIN + [{"clinician_id": "C99", "weekly_capacity_slots": 1, "max_home_visits_per_day": 1}]
    # P1 seen in SX: wrong clinician (continuity break) but preferred mode — vs P1 unseen
    seen = score([{"patient_id": "P0", "slot_id": "S0"}, {"patient_id": "P1", "slot_id": "SX"}],
                 PATS, clin, slots, meta=META)["value"]
    unseen = score([{"patient_id": "P0", "slot_id": "S0"}], PATS, clin, slots, meta=META)["value"]
    assert seen > unseen   # seeing P1 (even with one break) beats not seeing them
