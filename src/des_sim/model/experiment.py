"""First experiment: sweep the elasticity of demand for design output.

Runs the engine across elasticities and seeds, writes results/sweep.csv and
results/first_experiment.png, and prints whether the junior-pipeline-collapse
validation target emerges.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .engine import Simulation

ELASTICITIES = [0.3, 0.75, 1.25, 2.0]
SEEDS = [0, 1, 2]
MONTHS = 120
RESULTS = Path("results")


def run_sweep() -> pd.DataFrame:
    frames = []
    for eps in ELASTICITIES:
        for seed in SEEDS:
            df = Simulation(elasticity=eps, months=MONTHS, seed=seed).run()
            df["seed"] = seed
            frames.append(df)
            print(f"  ran elasticity={eps} seed={seed}")
    return pd.concat(frames, ignore_index=True)


def plot(mean: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    for eps, g in mean.groupby("elasticity"):
        axes[0].plot(g["month"], g["junior_hires_per_senior"], label=f"ε={eps}")
        axes[1].plot(g["month"], g["employed_total"] / g["employed_total"].iloc[0], label=f"ε={eps}")
    axes[0].set_title("Junior hires per senior (annualized, 12-mo rolling)")
    axes[1].set_title("Total employment (relative to month 0)")

    mid = mean[mean["elasticity"] == ELASTICITIES[len(ELASTICITIES) // 2]]
    for level in ("junior", "mid", "senior"):
        axes[2].plot(mid["month"], mid[f"employed_{level}"], label=level)
    ax2b = axes[2].twinx()
    ax2b.plot(mid["month"], mid["ai_task_share"], color="gray", linestyle="--", label="AI task share")
    ax2b.set_ylabel("AI task share", color="gray")
    axes[2].set_title(f"Employment by level (ε={mid['elasticity'].iloc[0]})")

    for ax in axes:
        ax.set_xlabel("month (0 = mid-2026)")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    out = RESULTS / "first_experiment.png"
    fig.savefig(out, dpi=150)
    return out


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    print("Running elasticity sweep...")
    raw = run_sweep()
    raw.to_csv(RESULTS / "sweep.csv", index=False)
    mean = raw.groupby(["elasticity", "month"], as_index=False).mean(numeric_only=True)
    out = plot(mean)

    print(f"\nWrote {RESULTS / 'sweep.csv'} and {out}\n")
    print(f"{'ε':>5} {'emp Δ@end':>10} {'jr/sr @0':>9} {'jr/sr @end':>10} {'collapse?':>9}")
    for eps, g in mean.groupby("elasticity"):
        emp_delta = g["employed_total"].iloc[-1] / g["employed_total"].iloc[0] - 1
        ratio_0 = g["junior_hires_per_senior"].iloc[11]  # after rolling window fills
        ratio_end = g["junior_hires_per_senior"].iloc[-1]
        collapsed = "yes" if ratio_end < 0.5 * ratio_0 else "no"
        print(f"{eps:>5} {emp_delta:>+10.1%} {ratio_0:>9.3f} {ratio_end:>10.3f} {collapsed:>9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
