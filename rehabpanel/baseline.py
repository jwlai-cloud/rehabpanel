"""Single-agent baseline: one Qwen call schedules the whole caseload in one pass.

This is the control the society must beat. It deliberately receives the same
data and the same objective description as the society — its weakness is
structural (one pass, no negotiation), not informational.
"""
import argparse, json, re
from pathlib import Path
from .qwen_client import chat, BASELINE_MODEL

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(n):
    return json.loads((DATA / f"{n}.json").read_text())


def build_prompt(patients, clinicians, slots):
    return (
        "You are a rehab nurse scheduler. Assign patients to open slots to maximize "
        "clinical value: prioritize high-acuity and overdue patients, keep continuity "
        "with the primary clinician, respect capacity and patient mode preference. "
        "Return ONLY JSON: a list of {\"patient_id\":..,\"slot_id\":..,\"rationale\":..}. "
        "Do not exceed slot capacity; each slot used at most once.\n\n"
        f"PATIENTS:\n{json.dumps(patients)}\n\nCLINICIANS:\n{json.dumps(clinicians)}\n\n"
        f"SLOTS:\n{json.dumps(slots)}\n"
    )


def parse_assignments(text):
    m = re.search(r"\[.*\]", text, re.DOTALL)
    return json.loads(m.group(0)) if m else []


def run(seed=7):
    patients, clinicians, slots = _load("patients"), _load("clinicians"), _load("slots")
    prompt = build_prompt(patients, clinicians, slots)
    text = chat([{"role": "user", "content": prompt}], model=BASELINE_MODEL)
    assignments = parse_assignments(text)
    out = DATA / "assignments_baseline.json"
    out.write_text(json.dumps(assignments, indent=2))
    print(f"baseline -> {len(assignments)} assignments")
    return assignments


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=7)
    run(ap.parse_args().seed)
