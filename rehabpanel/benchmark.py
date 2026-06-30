"""Baseline vs society across N seeds and a scarcity sweep.

The headline figure: sweep demand_capacity_ratio 0.8 -> 1.6 and show the
society's value advantage GROWING with scarcity. Reproducible via `make benchmark`.
"""
import json
from pathlib import Path
from .generator import generate
from .scorer import score_file
from . import baseline
from .society import orchestrator

RESULTS = Path(__file__).resolve().parent.parent / "results"
SEEDS = [7, 13, 21, 42, 99]
RATIOS = [0.8, 1.0, 1.2, 1.4, 1.6]


def run():
    RESULTS.mkdir(exist_ok=True)
    rows = []
    for ratio in RATIOS:
        for seed in SEEDS:
            generate(seed=seed, ratio=ratio)
            baseline.run(seed); orchestrator.run(seed)
            b = score_file(Path(__file__).resolve().parent.parent / "data" / "assignments_baseline.json")
            s = score_file(Path(__file__).resolve().parent.parent / "data" / "assignments_society.json")
            rows.append({"ratio": ratio, "seed": seed,
                         "baseline_value": b["value"], "society_value": s["value"],
                         "gap": round(s["value"] - b["value"], 2)})
    (RESULTS / "metrics.json").write_text(json.dumps(rows, indent=2))
    # TODO(claude-code): matplotlib chart of mean gap vs ratio -> results/gap.png
    print(f"benchmark -> {len(rows)} runs written to results/metrics.json")
    return rows


if __name__ == "__main__":
    run()
