"""Single-agent baseline: one Qwen call schedules the whole caseload in one pass.

This is the control the society must beat. It deliberately receives the same
data and the same objective description as the society — its weakness is
structural (one pass, no negotiation), not informational.

Offline (no DASHSCOPE_API_KEY / REHABPANEL_OFFLINE=1) it runs a deterministic
acuity-first greedy fill — the single agent that "collapses the trade-off" by
anchoring on the most legible objective. Same control, reproducible key-free.
"""
import argparse, json, re
from pathlib import Path
from .qwen_client import chat, is_offline, BASELINE_MODEL

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
    """Defensive: extract the JSON list; [] on any failure (never crash)."""
    try:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        return json.loads(m.group(0)) if m else []
    except (json.JSONDecodeError, AttributeError, TypeError):
        return []


def validate(assignments, patients, slots):
    """Keep only well-formed rows with known ids; drop duplicate slot/patient
    use so a sloppy single-pass plan can't fake feasibility or skew the score."""
    P = {p["patient_id"] for p in patients}
    S = {s["slot_id"] for s in slots}
    seen_slots, seen_pats, clean = set(), set(), []
    for a in assignments:
        if not isinstance(a, dict):
            continue
        pid, sid = a.get("patient_id"), a.get("slot_id")
        if pid not in P or sid not in S or sid in seen_slots or pid in seen_pats:
            continue
        seen_slots.add(sid); seen_pats.add(pid)
        clean.append({"patient_id": pid, "slot_id": sid, "rationale": a.get("rationale", "")})
    return clean


def _greedy(patients, slots):
    """Acuity-first single pass — the deterministic offline baseline."""
    ranked = sorted(patients, key=lambda p: -p["acuity_score"])
    out = []
    for p, s in zip(ranked, slots):
        out.append({"patient_id": p["patient_id"], "slot_id": s["slot_id"],
                    "rationale": "baseline: acuity-first"})
    return out


def plan(patients, clinicians, slots, weights=None):
    """In-memory single-agent plan (no file IO). Offline = acuity-first greedy;
    online = one Qwen pass, parsed + validated, re-prompted once if malformed."""
    if is_offline():
        return _greedy(patients, slots)
    prompt = build_prompt(patients, clinicians, slots)
    raw = chat([{"role": "user", "content": prompt}], model=BASELINE_MODEL)
    assignments = validate(parse_assignments(raw), patients, slots)
    if not assignments:  # re-prompt once, keeping the bad reply in history so the model can correct it
        msgs = [{"role": "user", "content": prompt},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "That was not valid JSON. Reply with ONLY the JSON list "
                                            "of {patient_id, slot_id, rationale}."}]
        assignments = validate(parse_assignments(chat(msgs, model=BASELINE_MODEL)), patients, slots)
    return assignments


def run(seed=7):
    patients, clinicians, slots = _load("patients"), _load("clinicians"), _load("slots")
    assignments = plan(patients, clinicians, slots)
    (DATA / "assignments_baseline.json").write_text(json.dumps(assignments, indent=2))
    print(f"baseline -> {len(assignments)} assignments")
    return assignments


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=7)
    run(ap.parse_args().seed)
