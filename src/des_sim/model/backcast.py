"""Backcast Jan 2023 -> mid-2026 and fit the model to observed data.

Identification strategy: the raw design-postings decline since 2023 mixes the
post-2022 macro correction with AI effects, so the model is scored on a
difference-in-difference — the ratio of design-adjacent postings to the
aggregate Indeed postings index (real), against the ratio of hiring flows in
an AI run to a paired no-AI counterfactual run (simulated, same seed).

Calibrated/fitted in three layers:
1. Firm adoption-start distribution: fitted exogenously (logit-linear) to the
   Census BTOS "used AI in the last two weeks" series, scaled to the tech
   sector (Information runs ~2x the national rate, May 2026: 39.7% vs 19.8%).
   The BTOS file only carries recent cycles, so two documented early anchors
   are added: 3.9% (Nov 2023) and 5.4% (Feb 2024), per census.gov reporting.
   Caveat: the early figures come from the narrower "produce goods/services"
   question wording; treated as one series here.
2. Demand elasticity and capability-curve shift: grid-searched on backcast RMSE.
3. Everything else: held at engine defaults.

Outputs: results/backcast_fit.png, results/projection.png, results/fit.json.
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
from .engine import Simulation

ANCHOR_DATE = pd.Timestamp("2026-07-01")  # anchor time 0 = mid-2026
BACKCAST_START = pd.Timestamp("2023-01-01")
START_ANCHOR = -42  # months from anchor to backcast start
BACKCAST_MONTHS = 42
PROJECTION_MONTHS = 156  # Jan 2023 -> end 2035

TECH_ADOPTION_SCALE = 2.0
EARLY_BTOS_ANCHORS = [("2023-11-01", 0.039), ("2024-02-24", 0.054)]

ELASTICITY_GRID = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
SHIFT_GRID = [-6, 0, 6, 12, 18, 24]  # months; + = capability arrives later
FIT_SEEDS = [0, 1]
PROJECTION_SEEDS = [0, 1, 2]
RESULTS = Path("results")


def _anchor_months(dates: pd.Series) -> pd.Series:
    return (dates.dt.year - ANCHOR_DATE.year) * 12 + (dates.dt.month - ANCHOR_DATE.month)


def calibrate_adoption() -> tuple[float, float, pd.DataFrame]:
    """Fit logistic adoption-share curve; return (loc, scale) in anchor time."""
    btos = targets.btos_ai_adoption()
    used = btos[btos["Question"].str.contains("In the last two weeks", na=False)]
    series = used.groupby("date", as_index=False)["share"].mean()
    early = pd.DataFrame(
        [(pd.Timestamp(d), s) for d, s in EARLY_BTOS_ANCHORS], columns=["date", "share"]
    )
    series = pd.concat([early, series], ignore_index=True)
    series["share_tech"] = (series["share"] * TECH_ADOPTION_SCALE).clip(upper=0.97)
    series["anchor_t"] = _anchor_months(series["date"])

    y = np.log(series["share_tech"] / (1 - series["share_tech"]))
    slope, intercept = np.polyfit(series["anchor_t"], y, 1)
    loc = -intercept / slope  # anchor month when half of tech firms have adopted
    scale = 1 / slope
    return float(loc), float(scale), series


def real_relative_postings() -> pd.DataFrame:
    """Design-adjacent postings index relative to the aggregate index, monthly,
    normalized to 1 at the backcast start."""
    design = targets.design_postings_index()
    design_mean = design.groupby("date", as_index=False)["postings_index"].mean()

    agg = pd.read_parquet("data/processed/hiring_lab_aggregate_postings.parquet")
    agg = agg[agg["variable"] == "total postings"][
        ["date", "indeed_job_postings_index_sa"]
    ].rename(columns={"indeed_job_postings_index_sa": "aggregate_index"})

    merged = design_mean.merge(agg, on="date")
    merged = merged[merged["date"] >= BACKCAST_START]
    merged["month"] = merged["date"].dt.to_period("M")
    monthly = merged.groupby("month", as_index=False)[
        ["postings_index", "aggregate_index"]
    ].mean()
    monthly["ratio"] = monthly["postings_index"] / monthly["aggregate_index"]
    monthly["ratio"] /= monthly["ratio"].iloc[0]
    monthly["t"] = (monthly["month"].dt.year - BACKCAST_START.year) * 12 + (
        monthly["month"].dt.month - BACKCAST_START.month
    )
    return monthly[["t", "ratio"]]


def run_pair(
    eps: float, shift: float, seed: int, months: int, loc: float, scale: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    common = dict(
        elasticity=eps,
        months=months,
        seed=seed,
        start_anchor=START_ANCHOR,
        capability_shift=shift,
        adoption_loc=loc,
        adoption_scale=scale,
    )
    return Simulation(**common).run(), Simulation(**common, ai_scale=0.0).run()


def sim_relative_flows(ai: pd.DataFrame, no_ai: pd.DataFrame) -> pd.Series:
    """AI-attributable hiring-flow ratio, smoothed; the sim analog of the
    real design-vs-aggregate postings ratio."""
    flows_ai = (ai["hires_total"] + ai["vacancies_posted"]).rolling(6, min_periods=1).mean()
    flows_no = (no_ai["hires_total"] + no_ai["vacancies_posted"]).rolling(6, min_periods=1).mean()
    ratio = flows_ai / flows_no.clip(lower=1)
    return ratio / ratio.iloc[:6].mean()


def fit(loc: float, scale: float, real: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    rows = []
    real_by_t = real.set_index("t")["ratio"]
    for eps in ELASTICITY_GRID:
        for shift in SHIFT_GRID:
            ratios = []
            for seed in FIT_SEEDS:
                ai, no_ai = run_pair(eps, shift, seed, BACKCAST_MONTHS, loc, scale)
                ratios.append(sim_relative_flows(ai, no_ai))
            sim_ratio = pd.concat(ratios, axis=1).mean(axis=1)
            common_t = [t for t in real_by_t.index if 6 <= t < BACKCAST_MONTHS]
            err = sim_ratio.iloc[common_t].to_numpy() - real_by_t.loc[common_t].to_numpy()
            rmse = float(np.sqrt((err**2).mean()))
            rows.append({"elasticity": eps, "shift": shift, "rmse": rmse})
            print(f"  eps={eps:<5} shift={shift:>+3}  rmse={rmse:.4f}")
    grid = pd.DataFrame(rows)
    best = grid.loc[grid["rmse"].idxmin()].to_dict()
    return best, grid


def project(best: dict, loc: float, scale: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    ai_runs, no_runs = [], []
    for seed in PROJECTION_SEEDS:
        ai, no_ai = run_pair(
            best["elasticity"], best["shift"], seed, PROJECTION_MONTHS, loc, scale
        )
        ai_runs.append(ai)
        no_runs.append(no_ai)
    ai = pd.concat(ai_runs).groupby("month", as_index=False).mean(numeric_only=True)
    no_ai = pd.concat(no_runs).groupby("month", as_index=False).mean(numeric_only=True)
    for df in (ai, no_ai):
        df["date"] = pd.period_range(
            start=BACKCAST_START, periods=len(df), freq="M"
        ).to_timestamp()
    return ai, no_ai


def plot_fit(
    best: dict,
    loc: float,
    scale: float,
    btos: pd.DataFrame,
    real: pd.DataFrame,
    ai: pd.DataFrame,
    no_ai: pd.DataFrame,
) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    window = ai[ai["month"] < BACKCAST_MONTHS]
    axes[0].plot(window["date"], window["adoption"], label="sim: mean firm adoption")
    axes[0].scatter(
        btos["date"],
        btos["share_tech"],
        color="crimson",
        s=18,
        zorder=3,
        label="BTOS x2 (tech-scaled), + early anchors",
    )
    axes[0].set_title("Firm AI adoption: calibration")
    axes[0].set_ylim(0, 1)

    sim_ratio = sim_relative_flows(
        window, no_ai[no_ai["month"] < BACKCAST_MONTHS]
    )
    dates = window["date"]
    axes[1].plot(dates, sim_ratio, label=f"sim AI/no-AI hiring flows (ε={best['elasticity']}, shift={best['shift']:+.0f}mo)")
    real_dates = [BACKCAST_START + pd.DateOffset(months=int(t)) for t in real["t"]]
    axes[1].plot(real_dates, real["ratio"], color="crimson", label="real: design vs aggregate postings")
    axes[1].set_title("Backcast fit: AI-attributable hiring decline")

    for ax in axes:
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    out = RESULTS / "backcast_fit.png"
    fig.savefig(out, dpi=150)
    return out


def plot_projection(best: dict, ai: pd.DataFrame, no_ai: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    for level, color in [("junior", "tab:blue"), ("mid", "tab:orange"), ("senior", "tab:green")]:
        axes[0].plot(ai["date"], ai[f"employed_{level}"], color=color, label=level)
        axes[0].plot(no_ai["date"], no_ai[f"employed_{level}"], color=color, alpha=0.35, linestyle="--")
    axes[0].set_title("Employment by level (dashed = no-AI counterfactual)")

    axes[1].plot(ai["date"], ai["employed_total"], label="with AI")
    axes[1].plot(no_ai["date"], no_ai["employed_total"], linestyle="--", label="no-AI counterfactual")
    axes[1].set_title("Total design employment")

    axes[2].plot(ai["date"], ai["senior_premium"], label="senior/junior wage premium")
    ax2b = axes[2].twinx()
    ax2b.plot(ai["date"], ai["ai_task_share"], color="gray", linestyle="--", label="AI task share")
    ax2b.set_ylabel("AI task share", color="gray")
    axes[2].set_title("Wage premium and AI task share")

    for ax in axes:
        ax.axvline(ANCHOR_DATE, color="black", alpha=0.3, linewidth=0.8)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.suptitle(
        f"Projection 2023-2035, fitted ε={best['elasticity']}, capability shift {best['shift']:+.0f}mo"
        " (vertical line = today)",
        fontsize=10,
    )
    fig.tight_layout()
    out = RESULTS / "projection.png"
    fig.savefig(out, dpi=150)
    return out


def main() -> int:
    RESULTS.mkdir(exist_ok=True)

    print("Calibrating adoption curve to BTOS...")
    loc, scale, btos = calibrate_adoption()
    half_date = ANCHOR_DATE + pd.DateOffset(months=int(loc))
    print(f"  median tech-firm adoption start: {half_date:%Y-%m} (loc={loc:+.1f}mo, scale={scale:.1f})")

    print("Computing real design-vs-aggregate postings ratio...")
    real = real_relative_postings()
    print(f"  relative decline Jan 2023 -> latest: {real['ratio'].iloc[-1] - 1:+.1%}")

    print("Fitting elasticity and capability shift on the backcast...")
    best, grid = fit(loc, scale, real)
    print(f"  best: elasticity={best['elasticity']} shift={best['shift']:+.0f}mo rmse={best['rmse']:.4f}")

    print("Running 2023-2035 projection with fitted parameters...")
    ai, no_ai = project(best, loc, scale)

    fit_png = plot_fit(best, loc, scale, btos, real, ai, no_ai)
    proj_png = plot_projection(best, ai, no_ai)
    (RESULTS / "fit.json").write_text(
        json.dumps(
            {
                "adoption_loc_anchor_months": loc,
                "adoption_scale_months": scale,
                "best": best,
                "grid": grid.to_dict(orient="records"),
            },
            indent=2,
        )
        + "\n"
    )

    today_idx = (ai["date"] - pd.Timestamp.today()).abs().idxmin()
    end = ai.iloc[-1]
    today = ai.iloc[today_idx]
    no_end = no_ai.iloc[-1]
    print(f"\nWrote {fit_png}, {proj_png}, {RESULTS / 'fit.json'}\n")
    print(f"At end of 2035 (vs no-AI counterfactual):")
    print(f"  total employment: {end['employed_total'] / no_end['employed_total'] - 1:+.1%}")
    print(f"  junior employment: {end['employed_junior'] / no_end['employed_junior'] - 1:+.1%}")
    print(f"  senior premium: {end['senior_premium']:.2f}x (today: {today['senior_premium']:.2f}x)")
    print(f"  AI task share: {end['ai_task_share']:.0%} (today: {today['ai_task_share']:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
