"""Seeded synthetic caseload generator.

The `--ratio` (demand_capacity_ratio) knob is the whole experiment: set it > 1
so demand exceeds capacity and the scheduling conflict becomes real. The
baseline collapses the trade-off; the society negotiates it. The gap IS the
result, and it should widen as ratio rises.

No real or anonymized patient data is used or required.
"""
import argparse, json, random
from datetime import date, timedelta
from pathlib import Path
from faker import Faker

DATA = Path(__file__).resolve().parent.parent / "data"
T0 = date(2026, 6, 8)          # Monday — start of the planning week
HORIZON_DAYS = 5               # Mon..Fri
PROGRAMS = ["stroke", "ortho", "cardiac", "neuro", "pulmonary"]
# program -> (acuity_lo, acuity_hi, followup_interval_days)
PROFILE = {
    "stroke":    (5, 10, 7),
    "ortho":     (2, 6, 21),
    "cardiac":   (4, 9, 10),
    "neuro":     (4, 9, 14),
    "pulmonary": (3, 8, 14),
}
RISK = ["fall_risk", "bp_unstable", "wound_check", "med_review", "mobility_decline"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
AMPM = ["AM", "PM"]


def _clinicians(fk, rng, n=3):
    out = []
    for i in range(n):
        cdays = rng.sample(DAYS, k=rng.choice([3, 4]))
        out.append({
            "clinician_id": f"C{i:02d}",
            "name": fk.name(),
            "role": "rehab_nurse",
            "specialties": rng.sample(PROGRAMS, k=2),
            "weekly_capacity_slots": rng.choice([14, 16, 18]),
            "clinic_days": sorted(cdays, key=DAYS.index),
            "max_home_visits_per_day": 3,
            "base_zone": f"Z{rng.randint(1,3)}",
        })
    return out


def _slots(clinicians, rng):
    out, k = [], 0
    for c in clinicians:
        per_day = max(1, c["weekly_capacity_slots"] // len(c["clinic_days"]))
        for d in c["clinic_days"]:
            day_date = T0 + timedelta(days=DAYS.index(d))
            for s in range(per_day):
                hour = 9 + s
                out.append({
                    "slot_id": f"S{k:04d}", "clinician_id": c["clinician_id"],
                    "date": day_date.isoformat(), "start_time": f"{hour:02d}:00",
                    "duration_min": 30,
                    "mode": rng.choices(["clinic", "tele", "home"], [0.6, 0.25, 0.15])[0],
                    "zone": c["base_zone"], "status": "open",
                })
                k += 1
    return out


def _patients(fk, rng, n, clinicians):
    # cluster ~40% onto one clinician to manufacture continuity tension
    hot = clinicians[0]["clinician_id"]
    out = []
    for i in range(n):
        prog = rng.choice(PROGRAMS)
        lo, hi, interval = PROFILE[prog]
        primary = hot if rng.random() < 0.4 else rng.choice(clinicians)["clinician_id"]
        # spread due dates around T0 so a chunk are already overdue
        due_offset = rng.randint(-6, HORIZON_DAYS)
        due = T0 + timedelta(days=due_offset)
        out.append({
            "patient_id": f"P{i:04d}", "name": fk.name(),
            "age": rng.randint(28, 89), "program": prog,
            "acuity_score": rng.randint(lo, hi),
            "risk_flags": rng.sample(RISK, k=rng.randint(0, 2)),
            "primary_clinician_id": primary,
            "last_seen_date": (due - timedelta(days=interval)).isoformat(),
            "followup_due_date": due.isoformat(),
            "followup_interval_days": interval,
            "preferred_mode": rng.choices(["clinic", "tele", "home"], [0.5, 0.3, 0.2])[0],
            "availability": [f"{d}_{p}" for d in rng.sample(DAYS, 2) for p in [rng.choice(AMPM)]],
            "travel_zone": f"Z{rng.randint(1,3)}", "no_show_risk": round(rng.uniform(0.05, 0.3), 2),
            "status": "active",
        })
    return out


def generate(seed=7, ratio=1.3, n_clinicians=3):
    rng = random.Random(seed)
    fk = Faker(); Faker.seed(seed)
    clinicians = _clinicians(fk, rng, n_clinicians)
    slots = _slots(clinicians, rng)
    n_patients = max(1, round(len(slots) * ratio))   # ratio>1 => more demand than slots
    patients = _patients(fk, rng, n_patients, clinicians)
    encounters = [{
        "encounter_id": f"E{i:04d}", "patient_id": p["patient_id"],
        "clinician_id": p["primary_clinician_id"], "date": p["last_seen_date"],
        "type": "clinic", "outcome": rng.choice(["progressing", "stable", "regressed"]),
    } for i, p in enumerate(patients)]

    DATA.mkdir(exist_ok=True)
    for name, rows in [("patients", patients), ("clinicians", clinicians),
                       ("slots", slots), ("encounters", encounters)]:
        (DATA / f"{name}.json").write_text(json.dumps(rows, indent=2))
    meta = {"seed": seed, "ratio": ratio, "n_patients": len(patients),
            "n_slots": len(slots), "t0": T0.isoformat(), "horizon_days": HORIZON_DAYS}
    (DATA / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"generated: {len(patients)} patients vs {len(slots)} slots "
          f"(ratio {ratio}) seed {seed}")
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--ratio", type=float, default=1.3)
    a = ap.parse_args()
    generate(a.seed, a.ratio)
