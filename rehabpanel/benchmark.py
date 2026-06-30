"""Baseline vs society across N seeds and a scarcity sweep.

The headline figure: sweep demand_capacity_ratio 0.8 -> 1.6 and show the
society's value advantage GROWING with scarcity. Reproducible via `make benchmark`.

Runs in whatever mode qwen_client.is_offline() reports. Offline (no key) uses the
deterministic reference negotiator — reproducible and free, which is what makes
`make benchmark` a one-command repro for judges. With a key set it runs the live
Qwen agents (note: 25 negotiations will spend the voucher).
"""
import json
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")  # headless: write a PNG, never open a window
import matplotlib.pyplot as plt

from .generator import generate
from .scorer import score_file
from .qwen_client import is_offline
from . import baseline
from .society import orchestrator

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
DATA = ROOT / "data"
SEEDS = [7, 13, 21, 42, 99]
RATIOS = [0.8, 1.0, 1.2, 1.4, 1.6]


def run():
    RESULTS.mkdir(exist_ok=True)
    mode = "offline (deterministic)" if is_offline() else "online (live Qwen)"
    print(f"benchmark mode: {mode}")
    rows = []
    for ratio in RATIOS:
        for seed in SEEDS:
            generate(seed=seed, ratio=ratio)
            baseline.run(seed)
            orchestrator.run(seed)
            b = score_file(DATA / "assignments_baseline.json")
            s = score_file(DATA / "assignments_society.json")
            rows.append({"ratio": ratio, "seed": seed,
                         "baseline_value": b["value"], "society_value": s["value"],
                         "gap": round(s["value"] - b["value"], 2),
                         "feasible": s["feasible"] and b["feasible"]})
    (RESULTS / "metrics.json").write_text(json.dumps(rows, indent=2))
    chart(rows, mode)
    print(f"benchmark -> {len(rows)} runs -> results/metrics.json + results/gap.png")
    return rows


def chart(rows, mode):
    """Mean society-minus-baseline value gap vs scarcity, with min/max band."""
    by_ratio = {}
    for r in rows:
        by_ratio.setdefault(r["ratio"], []).append(r["gap"])
    ratios = sorted(by_ratio)
    means = [mean(by_ratio[r]) for r in ratios]
    lows = [min(by_ratio[r]) for r in ratios]
    highs = [max(by_ratio[r]) for r in ratios]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.fill_between(ratios, lows, highs, alpha=0.15, color="#2a7", label="seed min–max")
    ax.plot(ratios, means, "-o", color="#176", lw=2, label="mean gap")
    ax.axhline(0, color="#999", lw=1, ls="--")
    ax.axvline(1.0, color="#c44", lw=1, ls=":", label="demand = capacity")
    ax.set_xlabel("demand / capacity ratio  (→ scarcer)")
    ax.set_ylabel("society − baseline value")
    ax.set_title(f"RehabPanel: negotiation advantage vs scarcity\n({len(SEEDS)} seeds · {mode})")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(RESULTS / "gap.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    run()
