"""Calibration targets: named series the model must reproduce.

Each function reads data/processed/*.parquet (produced by `des-sim-ingest pull`)
and returns a tidy DataFrame. These are the empirical series simulation runs
get scored against.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROCESSED = Path("data/processed")

# Indeed sector taxonomy has no "design" sector; these four carry most
# design-role postings (product/UX in software, visual in marketing/media).
DESIGN_ADJACENT_SECTORS = [
    "Software Development",
    "Marketing",
    "Media & Communications",
    "Arts & Entertainment",
]

# Keyword net for design-related O*NET task statements in the AEI data.
DESIGN_TASK_KEYWORDS = (
    "design|graphic|user experience|user interface|wireframe|prototype|mockup|usability"
)


def _read(name: str) -> pd.DataFrame:
    path = PROCESSED / name
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `des-sim-ingest pull` first")
    return pd.read_parquet(path)


def design_postings_index() -> pd.DataFrame:
    """Indeed postings index for design-adjacent sectors, long format.

    Index is relative to Feb 1, 2020 = 100. Weekly cadence.
    """
    df = _read("hiring_lab_postings_by_sector.parquet")
    out = df[df["display_name"].isin(DESIGN_ADJACENT_SECTORS)].copy()
    return out[["date", "display_name", "indeed_job_postings_index"]].rename(
        columns={"display_name": "sector", "indeed_job_postings_index": "postings_index"}
    )


def ai_postings_share() -> pd.DataFrame:
    """Share of US job postings mentioning AI/GenAI terms. Daily, monthly refresh."""
    df = _read("hiring_lab_ai_postings.parquet")
    return df[["date", "ai_share_postings"]]


def btos_ai_adoption() -> pd.DataFrame:
    """Share of businesses answering Yes to 'used AI in the last two weeks'.

    Period codes are YYYYCC (CC = biweekly cycle within the year); the date
    column is an approximation (cycle midpoint), good enough for curve fitting.
    """
    est = _read("btos_national_response_estimates.parquet")
    ai_rows = est[
        est["Question"].astype(str).str.contains("artificial intelligence", case=False, na=False)
        & est["Answer"].astype(str).str.strip().str.lower().eq("yes")
    ]
    if ai_rows.empty:
        raise ValueError("No AI-use question found in BTOS estimates; check sheet contents")
    period_cols = [c for c in est.columns if str(c).isdigit() and len(str(c)) == 6]
    long = ai_rows.melt(
        id_vars=["Question"], value_vars=period_cols, var_name="period", value_name="share"
    )
    # Suppressed cells appear as "." or "S"; coerce them to NaN.
    long["share"] = pd.to_numeric(long["share"].astype(str).str.rstrip("%"), errors="coerce") / 100
    year = long["period"].str[:4].astype(int)
    cycle = long["period"].str[4:].astype(int)
    long["date"] = pd.to_datetime(year.astype(str)) + pd.to_timedelta((cycle - 1) * 14 + 7, "D")
    return long.dropna(subset=["share"]).sort_values("date")[["date", "share", "Question"]]


def aei_design_task_usage(geo_id: str = "GLOBAL") -> pd.DataFrame:
    """Claude usage share of design-related O*NET tasks (latest AEI release)."""
    df = _aei()
    tasks = df[
        (df["facet"] == "onet_task")
        & (df["variable"] == "onet_task_pct")
        & (df["geo_id"] == geo_id)
    ]
    mask = tasks["cluster_name"].astype(str).str.contains(DESIGN_TASK_KEYWORDS, case=False)
    out = tasks[mask][["geo_id", "cluster_name", "value"]].rename(
        columns={"cluster_name": "task", "value": "usage_pct"}
    )
    return out.sort_values("usage_pct", ascending=False)


def aei_collaboration_split() -> pd.DataFrame:
    """Automation vs augmentation interaction-mode shares (latest AEI release).

    Directive and feedback-loop modes count as automation; learning,
    task-iteration, and validation as augmentation.
    """
    df = _aei()
    collab = df[
        (df["facet"] == "collaboration")
        & (df["variable"] == "collaboration_pct")
        & (df["geo_id"] == "GLOBAL")
    ]
    out = collab[["geo_id", "cluster_name", "value"]].rename(
        columns={"cluster_name": "mode", "value": "pct"}
    )
    automation = {"directive", "feedback loop"}
    out["grouping"] = out["mode"].astype(str).str.lower().map(
        lambda m: "automation" if m in automation else "augmentation"
    )
    return out


# Design occupations for the capability anchoring (O*NET task join).
DESIGN_OCCUPATION_SOCS = ["15-1255", "27-1024", "27-1021", "27-1011", "27-1014"]

# Ordered rules mapping O*NET design-task text to the model's task categories
# (first match wins). Tuned against the actual 119 design-occupation task
# statements; see aei_category_profile() output for the resulting assignment.
CATEGORY_RULES = [
    ("strategy_judgment", "confer|consult|client|stakeholder|strateg|budget|coordinate|direct others|negotiate|market|present.*to"),
    ("research_synthesis", "user needs|usability|research|analyz|data|test|feedback|evaluat"),
    ("prototyping_design_to_code", "code|script|program|application|implement|prototype|e-commerce|database|technical"),
    ("wireframing_ideation", "site map|template|wireframe|mockup|sketch|concept|menu design|plan|layout"),
    ("production", "image|illustrat|artwork|graphic|animation|render|photograph|brochure|multimedia|web site|web page|logo|typograph|drawing|model|storyboard"),
]
AUTOMATION_MODES = {"directive", "feedback loop"}


def aei_category_profile() -> pd.DataFrame:
    """Per task-category AI maturity profile for design occupations.

    Joins official O*NET task statements for design SOCs to AEI task-level
    usage and collaboration modes, then aggregates to the model's categories:
    - usage_pct: share of all Claude.ai conversations on these tasks
    - automation_share: usage-weighted share in automation modes
      (directive + feedback loop, of classified conversations)
    - rel_maturity: usage intensity x automation share, max-normalized.
      This is the data-grounded *relative* input to capability anchoring;
      the absolute level is a separate, documented assumption.
    """
    onet = _read("onet_tasks_statements.parquet")
    design = onet[onet["onet_soc_code"].str[:7].isin(DESIGN_OCCUPATION_SOCS)].copy()
    design["key"] = design["task"].str.lower().str.strip()
    design = design.drop_duplicates("key")

    def categorize(text: str) -> str:
        for cat, pattern in CATEGORY_RULES:
            if pd.Series([text]).str.contains(pattern, case=False, regex=True).iloc[0]:
                return cat
        return "production"

    design["category"] = design["key"].map(categorize)

    aei = _aei()
    g = aei[aei["geo_id"] == "GLOBAL"]
    usage = g[(g["facet"] == "onet_task") & (g["variable"] == "onet_task_pct")].copy()
    usage["key"] = usage["cluster_name"].astype(str).str.lower().str.strip()
    merged = design.merge(usage[["key", "value"]], on="key", how="inner").rename(
        columns={"value": "usage_pct"}
    )

    collab = g[
        (g["facet"] == "onet_task::collaboration")
        & (g["variable"] == "onet_task_collaboration_pct")
    ].copy()
    parts = collab["cluster_name"].astype(str).str.rsplit("::", n=1, expand=True)
    collab["key"] = parts[0].str.lower().str.strip()
    collab["mode"] = parts[1].str.lower().str.strip()
    collab = collab[collab["mode"] != "not_classified"]
    collab["is_auto"] = collab["mode"].isin(AUTOMATION_MODES)
    auto = (
        collab.groupby("key")
        .apply(
            lambda x: x.loc[x["is_auto"], "value"].sum() / max(x["value"].sum(), 1e-9),
            include_groups=False,
        )
        .rename("automation_share")
        .reset_index()
    )
    merged = merged.merge(auto, on="key", how="left")
    merged["automation_share"] = merged["automation_share"].fillna(0.0)

    prof = merged.groupby("category").apply(
        lambda x: pd.Series(
            {
                "n_tasks": len(x),
                "usage_pct": x["usage_pct"].sum(),
                "automation_share": (x["usage_pct"] * x["automation_share"]).sum()
                / max(x["usage_pct"].sum(), 1e-9),
            }
        ),
        include_groups=False,
    ).reset_index()
    prof["maturity"] = prof["usage_pct"] * prof["automation_share"]
    prof["rel_maturity"] = prof["maturity"] / prof["maturity"].max()
    return prof.sort_values("rel_maturity", ascending=False)


def design_demand_evidence() -> pd.DataFrame:
    """The elasticity-evidence ratio: designed output shipped vs design labor demanded.

    Monthly, both indexed to their 2023 average. The ratio rising means the
    world is shipping more designed product per unit of design hiring — the
    signature of the elastic ("appetite grows") world. Flat or falling is
    evidence for the inelastic world. Output proxy is Google Play app
    releases (12-month rolling mean); labor proxy is the mean Indeed postings
    index for design-adjacent sectors.

    Caveat: the output proxy absorbs platform-policy shocks that have nothing
    to do with demand — Google's 2024 quality crackdown roughly halved monthly
    releases. Read the trend, not the level, and prefer year-over-year moves.
    """
    apps = _read("design_demand_app_releases.parquet")
    apps["date"] = pd.to_datetime(apps["date"])
    apps = apps.sort_values("date")
    apps["output"] = apps["new_releases"].rolling(12, min_periods=6).mean()
    apps["month"] = apps["date"].dt.to_period("M")

    postings = design_postings_index()
    postings["month"] = postings["date"].dt.to_period("M")
    labor = postings.groupby("month", as_index=False)["postings_index"].mean().rename(
        columns={"postings_index": "labor"}
    )

    merged = apps[["month", "output"]].merge(labor, on="month").dropna()
    base = merged[merged["month"].dt.year == 2023]
    merged["output_idx"] = merged["output"] / base["output"].mean()
    merged["labor_idx"] = merged["labor"] / base["labor"].mean()
    merged["elasticity_evidence_ratio"] = merged["output_idx"] / merged["labor_idx"]
    return merged


def tech_firm_formation() -> pd.DataFrame:
    """Census BFS: monthly business applications, the extensive-margin signal.

    Information-sector applications ~= new tech companies; each user-facing
    entrant is a future consumer of design output. Applications are filings,
    not employer firms, and formation surges can include laid-off workers
    founding out of necessity — direction over level.
    """
    df = _read("design_demand_business_formation.parquet")
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date")


def tech_layoffs_monthly() -> pd.DataFrame:
    """Monthly tech layoffs (layoffs.fyi events, summed headcounts).

    Caveats: ~1/3 of tracked events report no headcount, so totals
    undercount; attribution is impossible from counts alone — the all-time
    peak (Jan 2023) predates design-capable AI. Credit layoffs.fyi.
    """
    df = _read("layoffs_fyi_events.parquet")
    monthly = (
        df.groupby(df["date"].dt.to_period("M"))["laid_off"].sum().rename("laid_off").reset_index()
    )
    monthly.columns = ["month", "laid_off"]
    return monthly


def design_revenue() -> pd.DataFrame:
    """Census SAS revenue (via FRED) for design service industries, nominal $M.

    Annual with ~18-month lag; employer firms only; no design-services PPI
    exists, so price vs quantity cannot be separated — use as a bound.
    """
    df = _read("design_demand_revenue.parquet")
    df["date"] = pd.to_datetime(df["date"])
    return df


def oews_anchors() -> pd.DataFrame:
    """Employment counts and wage distribution anchors for design SOC codes."""
    df = _read("oews_design_occupations.parquet")
    cols = [c for c in ("OCC_CODE", "OCC_TITLE", "TOT_EMP", "A_MEDIAN", "A_PCT10", "A_PCT90") if c in df.columns]
    return df[cols]


def _aei() -> pd.DataFrame:
    matches = sorted(PROCESSED.glob("aei_aei_raw_claude_ai_*.parquet"))
    if not matches:
        raise FileNotFoundError("No AEI claude_ai parquet found — run `des-sim-ingest pull aei`")
    return pd.read_parquet(matches[-1])


def summary() -> str:
    """One-screen text summary of all targets, for eyeballing against sim output."""
    lines = []
    postings = design_postings_index()
    latest = postings.sort_values("date").groupby("sector").tail(1)
    lines.append("Indeed postings index (Feb 2020 = 100), latest:")
    for _, r in latest.iterrows():
        lines.append(f"  {r['sector']:<28} {r['postings_index']:.1f}")
    ai = ai_postings_share()
    lines.append(f"AI-mention share of postings: {ai['ai_share_postings'].iloc[-1]:.2f}% ({ai['date'].iloc[-1]:%Y-%m-%d})")
    btos = btos_ai_adoption()
    lines.append(f"BTOS firms using AI: {btos['share'].iloc[-1]:.1%} ({btos['date'].iloc[-1]:%Y-%m-%d})")
    split = aei_collaboration_split()
    g = split.groupby("grouping")["pct"].sum()
    lines.append(f"AEI interaction modes: automation {g.get('automation', 0):.0f}%, augmentation {g.get('augmentation', 0):.0f}%")
    for _, r in oews_anchors().iterrows():
        lines.append(f"OEWS {r['OCC_CODE']} {r['OCC_TITLE']}: {r['TOT_EMP']:,.0f} employed, median ${r['A_MEDIAN']:,.0f}")
    try:
        ev = design_demand_evidence()
        latest = ev.iloc[-1]
        year_ago = ev.iloc[-13] if len(ev) > 13 else ev.iloc[0]
        trend = "rising (elastic-world evidence)" if latest["elasticity_evidence_ratio"] > year_ago["elasticity_evidence_ratio"] * 1.02 else (
            "falling (inelastic-world evidence)" if latest["elasticity_evidence_ratio"] < year_ago["elasticity_evidence_ratio"] * 0.98 else "flat (inconclusive)"
        )
        lines.append(
            f"Elasticity evidence (output shipped / design hiring, 2023=1.0): "
            f"{latest['elasticity_evidence_ratio']:.2f} as of {latest['month']}, {trend}"
        )
    except FileNotFoundError:
        lines.append("Elasticity evidence: run `des-sim-ingest pull design_demand` first")
    try:
        bf = tech_firm_formation()
        info = bf[bf["series"] == "information_sector_applications"]
        recent = info[info["date"] >= info["date"].max() - pd.DateOffset(months=12)]["value"].mean()
        plateau = info[info["date"].dt.year.isin([2022, 2023, 2024])]["value"].mean()
        lines.append(
            f"Tech firm formation (BFS, Information sector): {recent:,.0f}/mo trailing year, "
            f"{recent / plateau - 1:+.0%} vs the 2022-24 plateau"
        )
    except FileNotFoundError:
        pass
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
