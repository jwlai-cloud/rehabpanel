"""Pydantic models for the five synthetic tables. No real data, ever."""
from __future__ import annotations
from datetime import date
from typing import Literal
from pydantic import BaseModel

Program = Literal["stroke", "ortho", "cardiac", "neuro", "pulmonary"]
Mode = Literal["clinic", "tele", "home"]


class Patient(BaseModel):
    patient_id: str
    name: str
    age: int
    program: Program
    acuity_score: int               # 1..10
    risk_flags: list[str] = []
    primary_clinician_id: str
    last_seen_date: date
    followup_due_date: date         # some intentionally before t0 (overdue)
    followup_interval_days: int
    preferred_mode: Mode
    availability: list[str] = []    # e.g. ["Mon_AM", "Tue_AM"]
    travel_zone: str
    no_show_risk: float = 0.1
    status: str = "active"


class Clinician(BaseModel):
    clinician_id: str
    name: str
    role: str = "rehab_nurse"
    specialties: list[Program] = []
    weekly_capacity_slots: int
    clinic_days: list[str] = []
    max_home_visits_per_day: int = 3
    base_zone: str


class Slot(BaseModel):
    slot_id: str
    clinician_id: str
    date: date
    start_time: str
    duration_min: int = 30
    mode: Mode = "clinic"
    zone: str
    status: Literal["open", "booked"] = "open"


class Encounter(BaseModel):
    encounter_id: str
    patient_id: str
    clinician_id: str
    date: date
    type: Mode
    outcome: str


class Assignment(BaseModel):
    patient_id: str
    slot_id: str
    assigned_in_round: int = 0
    rationale: str = ""
