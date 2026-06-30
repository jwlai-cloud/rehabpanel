"""GO/NO-GO as a deterministic test: the society must out-score the single-agent
baseline, with the gap widening as scarcity rises. Runs fully OFFLINE (the
deterministic reference negotiator), so CI proves the thesis without an API key
and without burning the $40 voucher. The LLM path is exercised separately in
test_advocates_llm_path.py.
"""
import os
import pytest

from rehabpanel import generator, baseline
from rehabpanel.society import orchestrator
from rehabpanel.scorer import score_file

DATA = orchestrator.DATA
SEEDS = [7, 13, 42]


@pytest.fixture(autouse=True)
def _force_offline():
    prev = os.environ.get("REHABPANEL_OFFLINE")
    os.environ["REHABPANEL_OFFLINE"] = "1"
    yield
    if prev is None:
        os.environ.pop("REHABPANEL_OFFLINE", None)
    else:
        os.environ["REHABPANEL_OFFLINE"] = prev


def _run_pair(seed, ratio):
    generator.generate(seed=seed, ratio=ratio)
    baseline.run(seed)
    final = orchestrator.run(seed)
    b = score_file(DATA / "assignments_baseline.json")
    s = score_file(DATA / "assignments_society.json")
    return b, s, final


def _mean_gap(ratio):
    gaps = []
    for seed in SEEDS:
        b, s, _ = _run_pair(seed, ratio)
        gaps.append(s["value"] - b["value"])
    return sum(gaps) / len(gaps)


def test_society_beats_baseline_under_scarcity():
    """At ratio 1.3 the society out-scores the baseline on every seed, and both
    plans stay feasible (capacity is never violated)."""
    for seed in SEEDS:
        b, s, _ = _run_pair(seed, 1.3)
        assert s["feasible"], f"society infeasible seed {seed}"
        assert b["feasible"], f"baseline infeasible seed {seed}"
        assert s["value"] > b["value"], f"society did not beat baseline seed {seed}"


def test_gap_widens_with_scarcity():
    """The advantage of negotiating grows as demand outstrips capacity:
    mean gap at ratio 1.3 exceeds mean gap at the low-scarcity 0.8 case."""
    assert _mean_gap(1.3) > _mean_gap(0.8)


def test_referee_logs_ledger_and_moves_off_the_draft():
    """The negotiation produces readable rulings and the final plan differs from
    the initial acuity-first draft — i.e. negotiation actually happened."""
    b, s, final = _run_pair(7, 1.3)
    assert len(final["ledger"]) >= 1
    assert all(isinstance(line, str) and line for line in final["ledger"])
    assert s["continuity_breaks"] < b["continuity_breaks"]
    assert final["round"] >= 1


def test_society_stays_feasible_at_high_scarcity():
    for seed in SEEDS:
        _, s, _ = _run_pair(seed, 1.5)
        assert s["feasible"]
