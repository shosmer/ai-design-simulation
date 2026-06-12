"""Scenario bands: what is robust across assumptions vs assumption-driven.

Runs slow/base/fast capability scenarios x the credible elasticity range
(the backcast only weakly identifies it) x seeds, each differenced against a
paired no-AI counterfactual, and renders fan charts. The point is honest
public claims: findings that hold across every run are reported as robust;
everything else is shown as a band.

Scenario definitions scale the AEI-anchored capability curves:
- anchor_max: share of the most AI-mature category (design-to-code) done by
  AI in adopted tech firms at mid-2026
- steepness_scale: how fast curves rise toward their ceilings
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .. import targets
from .backcast import BACKCAST_START, START_ANCHOR, calibrate_adoption
from .engine import CATEGORY_STRUCTURE, Simulation, build_categories

SCENARIOS = {
    "slow": {"anchor_max": 0.12, "steepness_scale": 0.75},
    "base": {"anchor_max": 0.25, "steepness_scale": 1.0},
    "fast": {"anchor_max": 0.45, "steepness_scale": 1.3},
}
SCENARIO_COLORS = {"slow": "tab:green", "base": "tab:blue", "fast": "tab:red"}
ELASTICITIES = [1.0, 1.5, 2.0]  # credible range from the (flat) backcast fit
SEEDS = [0, 1, 2]
MONTHS = 156  # Jan 2023 -> end 2035
RESULTS = Path("results")


def live_rel_maturity() -> dict[str, float] | None:
    """Recompute relative maturity from the latest AEI pull; None on failure
    (build_categories then falls back to the hardcoded release values)."""
    try:
        prof = targets.aei_category_profile().set_index("category")
        intensity = {
            name: prof.loc[name, "maturity"] / structure[0]
            for name, structure in CATEGORY_STRUCTURE.items()
        }
        peak = max(intensity.values())
        return {name: v / peak for name, v in intensity.items()}
    except Exception as exc:
        print(f"  (live AEI profile unavailable, using hardcoded values: {exc})")
        return None


def run_all() -> pd.DataFrame:
    loc, scale, _ = calibrate_adoption()
    rel = live_rel_maturity()
    frames = []

    no_ai: dict[int, pd.DataFrame] = {}
    for seed in SEEDS:
        no_ai[seed] = Simulation(
            elasticity=1.5,
            months=MONTHS,
            seed=seed,
            start_anchor=START_ANCHOR,
            adoption_loc=loc,
            adoption_scale=scale,
            ai_scale=0.0,
        ).run()

    for name, params in SCENARIOS.items():
        cats = build_categories(rel, **params)
        for eps in ELASTICITIES:
            for seed in SEEDS:
                df = Simulation(
                    elasticity=eps,
                    months=MONTHS,
                    seed=seed,
                    start_anchor=START_ANCHOR,
                    adoption_loc=loc,
                    adoption_scale=scale,
                    categories=cats,
                ).run()
                base = no_ai[seed]
                for col in (
                    "employed_junior",
                    "employed_mid",
                    "employed_senior",
                    "employed_total",
                    "senior_premium",
                    "n_firms",
                    "manager_seats",
                ):
                    df[f"{col}_vs_cf"] = df[col] / base[col]
                df["scenario"] = name
                df["seed"] = seed
                frames.append(df)
                print(f"  ran scenario={name} eps={eps} seed={seed}")
    out = pd.concat(frames, ignore_index=True)
    out["date"] = out["month"].map(
        dict(enumerate(pd.period_range(start=BACKCAST_START, periods=MONTHS, freq="M").to_timestamp()))
    )
    return out


def plot(df: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    panels = [
        ("employed_junior_vs_cf", "Junior employment vs no-AI counterfactual"),
        ("employed_total_vs_cf", "Total employment vs no-AI counterfactual"),
        ("senior_premium_vs_cf", "Senior/junior wage premium vs no-AI counterfactual"),
    ]
    dates = df.drop_duplicates("month").sort_values("month")["date"]
    for ax, (col, title) in zip(axes, panels):
        for name in SCENARIOS:
            g = df[df["scenario"] == name].groupby("month")[col]
            lo, mid, hi = g.min(), g.median(), g.max()
            color = SCENARIO_COLORS[name]
            ax.fill_between(dates, lo, hi, color=color, alpha=0.15)
            ax.plot(dates, mid, color=color, label=name)
        if col.endswith("_vs_cf"):
            ax.axhline(1.0, color="black", linewidth=0.6, alpha=0.5)
        ax.axvline(pd.Timestamp("2026-07-01"), color="black", alpha=0.3, linewidth=0.8)
        ax.set_title(title, fontsize=10)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.suptitle(
        "Bands = min-max across elasticity (1.0-2.0) and seeds; lines = medians. Vertical line = mid-2026.",
        fontsize=9,
    )
    fig.tight_layout()
    out = RESULTS / "scenarios.png"
    fig.savefig(out, dpi=150)
    return out


def robustness_summary(df: pd.DataFrame) -> dict:
    """What holds in every run vs what varies."""
    summary: dict = {"runs": 0, "per_run": []}
    for (name, eps, seed), g in df.groupby(["scenario", "elasticity", "seed"]):
        g = g.sort_values("month")
        post = g[g["month"] >= 42]  # mid-2026 onward
        trough_i = post["employed_junior_vs_cf"].idxmin()
        summary["per_run"].append(
            {
                "scenario": name,
                "elasticity": float(eps),
                "seed": int(seed),
                "junior_trough_ratio": float(post["employed_junior_vs_cf"].min()),
                "junior_trough_date": str(post.loc[trough_i, "date"].date()),
                "junior_end_ratio": float(g["employed_junior_vs_cf"].iloc[-1]),
                "total_end_ratio": float(g["employed_total_vs_cf"].iloc[-1]),
                "premium_end": float(g["senior_premium_vs_cf"].iloc[-1]),
                "firms_end_ratio": float(g["n_firms_vs_cf"].iloc[-1]),
                "managers_end_ratio": float(g["manager_seats_vs_cf"].iloc[-1]),
                "ai_task_share_end": float(g["ai_task_share"].iloc[-1]),
            }
        )
    per = pd.DataFrame(summary["per_run"])
    summary["runs"] = len(per)
    summary["robust"] = {
        "junior_dip_in_all_runs": bool((per["junior_trough_ratio"] < 0.97).all()),
        "junior_trough_ratio_range": [
            float(per["junior_trough_ratio"].min()),
            float(per["junior_trough_ratio"].max()),
        ],
        "junior_end_ratio_range": [
            float(per["junior_end_ratio"].min()),
            float(per["junior_end_ratio"].max()),
        ],
        "total_end_ratio_range": [
            float(per["total_end_ratio"].min()),
            float(per["total_end_ratio"].max()),
        ],
        "premium_rises_in_all_runs": bool((per["premium_end"] > 1.0).all()),
        "firms_end_ratio_range": [
            float(per["firms_end_ratio"].min()),
            float(per["firms_end_ratio"].max()),
        ],
        "managers_end_ratio_range": [
            float(per["managers_end_ratio"].min()),
            float(per["managers_end_ratio"].max()),
        ],
    }
    return summary


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    print("Running scenario grid (3 scenarios x 3 elasticities x 3 seeds + counterfactuals)...")
    df = run_all()
    df.to_csv(RESULTS / "scenarios.csv", index=False)
    out = plot(df)
    summary = robustness_summary(df)
    (RESULTS / "scenarios_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    per = pd.DataFrame(summary["per_run"])
    print(f"\nWrote {out}, results/scenarios.csv, results/scenarios_summary.json\n")
    print("Across all", summary["runs"], "runs:")
    r = summary["robust"]
    print(f"  junior dip after mid-2026 in every run: {r['junior_dip_in_all_runs']}")
    print(f"  junior trough (vs no-AI): {r['junior_trough_ratio_range'][0]:.2f} to {r['junior_trough_ratio_range'][1]:.2f}")
    print(f"  junior at end of 2035 (vs no-AI): {r['junior_end_ratio_range'][0]:.2f} to {r['junior_end_ratio_range'][1]:.2f}")
    print(f"  total at end of 2035 (vs no-AI): {r['total_end_ratio_range'][0]:.2f} to {r['total_end_ratio_range'][1]:.2f}")
    print(f"  senior premium rises vs no-AI in every run: {r['premium_rises_in_all_runs']}")
    print(f"  firm count at end of 2035 (vs no-AI): {r['firms_end_ratio_range'][0]:.2f} to {r['firms_end_ratio_range'][1]:.2f}")
    print("\nMedian trough date by scenario:")
    for name, g in per.groupby("scenario"):
        dates = pd.to_datetime(g["junior_trough_date"])
        print(f"  {name:<5} {dates.quantile(0.5, interpolation='nearest').date()}  (trough ratio median {g['junior_trough_ratio'].median():.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
