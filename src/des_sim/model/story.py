"""Animated data story: self-contained scrollytelling HTML from scenarios.csv.

Generates writeup/story/index.html — a single file with the aggregated run
data embedded, a sticky SVG chart that tweens between scenes as the reader
scrolls, and the narrative. Re-run after `des-sim-scenarios` to refresh.
A `?view=N` query param jumps straight to a scene (used for headless
screenshots and debugging).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from .. import targets

RESULTS = Path("results")
OUT = Path("writeup/story/index.html")

X_START, X_END = 2023.0, 2036.0

COLOR_SCENARIO = {"slow": "#9ec5af", "base": "#5d9b84", "fast": "#2f7561"}
COLOR_EPS = {1.0: "#bf4633", 1.5: "#b08a3e", 2.0: "#2e6f9e"}
EPS_NAME = {1.0: "inelastic (1.0)", 1.5: "middle (1.5)", 2.0: "elastic (2.0)"}


def _smooth(s: pd.Series) -> list[float]:
    return [round(v, 4) for v in s.rolling(5, center=True, min_periods=1).mean()]


def build_payload() -> dict:
    df = pd.read_csv(RESULTS / "scenarios.csv")
    months = sorted(df["month"].unique())
    x = [round(2023 + (m + 0.5) / 12, 4) for m in months]

    def by(group_col: str, value_col: str) -> dict:
        med = df.groupby([group_col, "month"])[value_col].median().unstack(0)
        return {k: _smooth(med[k]) for k in med.columns}

    def band(value_col: str) -> dict:
        g = df.groupby("month")[value_col]
        return {"lo": _smooth(g.min()), "hi": _smooth(g.max())}

    jr_scn = by("scenario", "employed_junior_vs_cf")
    jr_eps = by("elasticity", "employed_junior_vs_cf")
    tot_eps = by("elasticity", "employed_total_vs_cf")
    prem_eps = by("elasticity", "senior_premium_vs_cf")
    jr_band = band("employed_junior_vs_cf")
    tot_band = band("employed_total_vs_cf")
    prem_band = band("senior_premium_vs_cf")

    flat = [1.0] * len(x)
    end = len(x) - 1

    def series_scn(hidden: bool = False) -> list[dict]:
        return [
            {"name": n, "color": COLOR_SCENARIO[n], "values": jr_scn[n], "hidden": hidden}
            for n in ("slow", "base", "fast")
        ]

    def series_eps(data: dict, hidden: bool = False) -> list[dict]:
        return [
            {"name": f"ε {EPS_NAME[e]}", "color": COLOR_EPS[e], "values": data[e], "hidden": hidden}
            for e in (1.0, 1.5, 2.0)
        ]

    def ann_ends(data: dict, keys, fmt="{:.2f}x") -> list[dict]:
        return [
            {"xi": end, "y": data[k][end], "text": fmt.format(data[k][end])} for k in keys
        ]

    y_ratio = {"y": [0.45, 1.45], "ticks": [0.6, 0.8, 1.0, 1.2, 1.4]}

    views = [
        # 0 — baseline only
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=[{"name": n, "color": COLOR_SCENARIO[n], "values": flat, "hidden": True}
                     for n in ("slow", "base", "fast")],
             band=None, ann=[], metric="Junior designers employed, vs a world without AI", fam="jr"),
        # 1 — by capability scenario
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_scn(), band=None, ann=[],
             metric="Junior designers employed, vs a world without AI", fam="jr"),
        # 2 — same, annotated endpoints
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_scn(), band=None,
             ann=ann_ends(jr_scn, ("slow", "base", "fast")),
             metric="Junior designers employed, vs a world without AI", fam="jr"),
        # 3 — regrouped by elasticity
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_eps(jr_eps), band=None,
             ann=ann_ends(jr_eps, (1.0, 1.5, 2.0)),
             metric="Junior designers employed, vs a world without AI", fam="jr"),
        # 4 — with min-max band
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_eps(jr_eps), band=jr_band,
             ann=ann_ends(jr_eps, (1.0, 1.5, 2.0)),
             metric="Junior designers employed — band = every run", fam="jr"),
        # 5 — senior premium (relative to the no-AI world's premium)
        dict(**y_ratio, ref=1.0, refLabel="same gap as a no-AI world",
             series=series_eps(prem_eps), band=prem_band,
             ann=ann_ends(prem_eps, (1.0, 1.5, 2.0)),
             metric="Senior-to-junior pay gap, vs a world without AI", fam="prem"),
        # 6 — total employment
        dict(y=[0.65, 1.95], ticks=[0.8, 1.0, 1.2, 1.4, 1.6, 1.8], ref=1.0,
             refLabel="no-AI counterfactual",
             series=series_eps(tot_eps), band=tot_band,
             ann=ann_ends(tot_eps, (1.0, 1.5, 2.0)),
             metric="All designers employed, vs a world without AI", fam="tot"),
        # 7 — closing: band only
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_eps(jr_eps, hidden=True), band=jr_band, ann=[],
             metric="Junior designers employed — the open question", fam="jr"),
    ]

    # Extensive-margin scene: firm count vs the no-AI world. Entry doesn't
    # order cleanly by elasticity (wage feedback in elastic worlds damps it),
    # so show the all-runs median + band: more companies in every world.
    firms_med = _smooth(df.groupby("month")["n_firms_vs_cf"].median())
    firms_band = band("n_firms_vs_cf")
    firms_lo_pct = round((firms_band["lo"][end] - 1) * 100)
    firms_hi_pct = round((firms_band["hi"][end] - 1) * 100)
    firm_view = dict(
        y=[0.85, 1.95], ticks=[1.0, 1.2, 1.4, 1.6, 1.8], ref=1.0,
        refLabel="no-AI counterfactual",
        series=[
            {"name": f"median +{round((firms_med[end] - 1) * 100)}%", "color": "#2f7561",
             "values": firms_med, "hidden": False},
            {"name": "", "color": "#2f7561", "values": firms_med, "hidden": True},
            {"name": "", "color": "#2f7561", "values": firms_med, "hidden": True},
        ],
        band=firms_band,
        ann=[],
        metric="Number of tech companies, vs a world without AI (band = every run)",
        fam="firms",
    )

    # Layoffs scene (view 1): the audience's strongest prior, addressed
    # head-on. Monthly totals from the scraped layoffs.fyi events; the
    # all-time peak (Jan 2023) predates design-capable AI.
    lo = pd.read_parquet("data/processed/layoffs_fyi_events.parquet")
    lo_m = lo.groupby(lo["date"].dt.to_period("M"))["laid_off"].sum().iloc[:-1]  # last month partial
    lo_m = lo_m[lo_m.index >= "2023-01"]
    lo_x = [round(p.year + (p.month - 0.5) / 12, 4) for p in lo_m.index]
    lo_vals = [round(v / 1000, 2) for v in lo_m]
    peak_i = int(pd.Series(lo_vals).idxmax())
    views.insert(1, dict(
        y=[0, 95], ticks=[0, 30, 60, 90], fmt="plain", ref=0.0, refLabel="",
        series=series_eps(jr_eps, hidden=True), band=None,
        ann=[{"xi": peak_i, "y": 80,
              "text": f"{lo_m.index[peak_i].strftime('%b %Y')} peak — ChatGPT was 8 weeks old"}],
        metric="Measured: tech layoffs per month, thousands (layoffs.fyi)",
        extras=[{"x": lo_x, "values": lo_vals, "color": "#211d18", "bars": True,
                 "label": "layoffs (k/mo)"}],
        fam="layoffs",
    ))

    # Insert the measured input-price scene before the elasticity regroup.
    # AI line: Stanford AI Index 2025 — inference price at GPT-3.5-level
    # capability fell $20 -> $0.07 per million tokens, Nov 2022 -> Oct 2024
    # (~280x over 23 months). Drawn as the implied exponential, indexed to
    # Jan 2023 = 100, ending at the measurement boundary.
    rate = math.log(0.07 / 20.0) / 23.0  # per month
    ai_months = 22  # Jan 2023 .. Oct 2024
    ai_x = [round(2023 + (m + 0.5) / 12, 4) for m in range(ai_months)]
    ai_vals = [round(100 * math.exp(rate * m), 3) for m in range(ai_months)]
    ai_drop_pct = round(100 - ai_vals[-1], 1)

    # Only the endpoints are measured; the path between them is the implied
    # exponential — encoded as dots + a dashed fit so the chart says so itself.
    price_extras = [
        {"x": ai_x, "values": ai_vals, "color": "#211d18", "dash": "6 4",
         "markers": [[ai_x[0], ai_vals[0]], [ai_x[-1], ai_vals[-1]]],
         "label": f"AI output −{ai_drop_pct:.0f}%"}
    ]
    wage_pct_text = "a few percent"
    wage_parquet = Path("data/processed/ai_prices_wage_index.parquet")
    if wage_parquet.exists():
        eci = pd.read_parquet(wage_parquet)
        eci = eci[eci["date"] >= "2023-01-01"].sort_values("date")
        wage_vals = [round(v / eci["value"].iloc[0] * 100, 2) for v in eci["value"]]
        wage_x = [round(d.year + (d.month - 0.5) / 12, 4) for d in eci["date"]]
        wage_pct = round(wage_vals[-1] - 100)
        wage_pct_text = f"up about {wage_pct}%"
        price_extras.append(
            {"x": wage_x, "values": wage_vals, "color": "#7a7065",
             "label": f"U.S. wages +{wage_pct}%"}
        )
    views.insert(4, dict(
        y=[0, 118], ticks=[0, 25, 50, 75, 100], fmt="plain",
        ref=100.0, refLabel="Jan 2023 = 100",
        series=series_eps(jr_eps, hidden=True), band=None, ann=[],
        metric="Input prices: AI output (dots = measured endpoints, dash = fitted path) vs U.S. wages (measured)",
        extras=price_extras, fam="price",
    ))
    # After the layoffs + price inserts: 8 = total employment, 9 = open question slot.
    views.insert(9, firm_view)

    # Manager scene (view 10): derived manager seats vs the no-AI world.
    # Span-of-control flattening vs headcount growth — orders cleanly by
    # elasticity, like everything else that matters in this model.
    mgr_eps = by("elasticity", "manager_seats_vs_cf")
    mgr_band = band("manager_seats_vs_cf")
    mgmt_y = targets.management_postings()
    mgmt_m = mgmt_y.groupby(mgmt_y["date"].dt.to_period("M"))["postings_index"].mean()
    mgmt_yoy = round((mgmt_m.iloc[-1] / mgmt_m.iloc[-13] - 1) * 100)
    design_m = targets.design_postings_index()
    design_mm = design_m.groupby(design_m["date"].dt.to_period("M"))["postings_index"].mean()
    design_yoy = round((design_mm.iloc[-1] / design_mm.iloc[-13] - 1) * 100)
    views.insert(10, dict(
        **y_ratio, ref=1.0, refLabel="no-AI counterfactual",
        series=series_eps(mgr_eps), band=mgr_band,
        ann=ann_ends(mgr_eps, (1.0, 1.5, 2.0)),
        metric="Design-manager seats, vs a world without AI (band = every run)",
        fam="mgr",
    ))

    # Quality-dispersion scene (view 11): the good-enough vs arms-race
    # discriminator, measured. Floor and ceiling of web quality from HTTP
    # Archive Lighthouse accessibility percentiles.
    q = targets.quality_dispersion()
    q = q[q["date"] >= "2023-01-01"]
    q_x = [round(d.year + (d.month - 0.5) / 12, 4) for d in q["date"]]
    q_floor = [round(v, 1) for v in q["p10"]]
    q_ceiling = [round(v, 1) for v in q["p90"]]
    views.insert(11, dict(
        y=[50, 104], ticks=[60, 70, 80, 90, 100], fmt="plain",
        ref=100.0, refLabel="scale maximum",
        series=series_eps(jr_eps, hidden=True), band=None, ann=[],
        metric="Measured: web quality distribution, Lighthouse accessibility (HTTP Archive)",
        extras=[
            {"x": q_x, "values": q_floor, "color": "#211d18",
             "label": f"the floor (p10) {q_floor[-1]:.0f}"},
            {"x": q_x, "values": q_ceiling, "color": "#7a7065",
             "label": f"the ceiling (p90) {q_ceiling[-1]:.0f}"},
        ],
        fam="quality",
    ))

    # 8 — measured reality: the elasticity-evidence ratio, if data is pulled
    evidence = None
    try:
        ev = targets.design_demand_evidence()
        ev = ev[ev["month"].dt.year >= 2023]
        year_ago = ev.iloc[-13] if len(ev) > 13 else ev.iloc[0]
        delta = ev.iloc[-1]["elasticity_evidence_ratio"] - year_ago["elasticity_evidence_ratio"]
        # 6-month display smoothing, matched to the formation line below so
        # the two series on this chart have comparable volatility.
        smoothed = ev["elasticity_evidence_ratio"].rolling(6, center=True, min_periods=1).mean()
        evidence = {
            "x": [round(m.year + (m.month - 0.5) / 12, 4) for m in ev["month"]],
            "values": [round(v, 4) for v in smoothed],
            "latest": round(float(smoothed.iloc[-1]), 2),
            "asof": str(ev.iloc[-1]["month"]),
            "trend": "rising" if delta > 0.02 else ("falling" if delta < -0.02 else "flat"),
        }
        ev_extras = [{"x": evidence["x"], "values": evidence["values"],
                      "color": "#211d18",
                      "label": f"output/hiring {evidence['latest']}, {evidence['trend']}"}]
        bf_path = Path("data/processed/design_demand_business_formation.parquet")
        if bf_path.exists():
            bf = pd.read_parquet(bf_path)
            bf = bf[(bf["series"] == "information_sector_applications")
                    & (bf["date"] >= "2023-01-01")].sort_values("date")
            smooth = bf["value"].rolling(6, min_periods=3).mean()
            base_bf = smooth[bf["date"].dt.year == 2023].mean()
            keep = smooth.notna()
            bf, smooth = bf[keep], smooth[keep]  # NaN head would break the SVG path
            bf_vals = [round(v / base_bf, 4) for v in smooth]
            evidence["formation_pct"] = round((bf_vals[-1] - 1) * 100)
            ev_extras.append(
                {"x": [round(d.year + (d.month - 0.5) / 12, 4) for d in bf["date"]],
                 "values": bf_vals, "color": "#7a5b8e",
                 "label": f"new tech companies +{evidence['formation_pct']}%"})
        views.append(
            dict(**y_ratio, ref=1.0, refLabel="2023 baseline",
                 series=series_eps(jr_eps, hidden=True), band=None, ann=[],
                 metric="Measured, not simulated: two early signals (2023 = 1.0, both 6-mo smoothed)",
                 extras=ev_extras, fam="evidence")
        )
    except FileNotFoundError:
        pass

    # Auxiliary stress-run numbers for the price-scene note, if available.
    subsidy_bit = ""
    aux_path = RESULTS / "aux_summary.json"
    if aux_path.exists():
        aux = json.loads(aux_path.read_text())
        if "aux_base" in aux and "cost_subsidy_end" in aux:
            subsidy_bit = (
                f" (junior outcome {aux['aux_base']['junior_end']}x &rarr; "
                f"{aux['cost_subsidy_end']['junior_end']}x)"
            )

    jr_lo, jr_hi = jr_eps[1.0][end], jr_eps[2.0][end]
    tot_lo, tot_hi = tot_eps[1.0][end], tot_eps[2.0][end]
    pr_lo, pr_hi = prem_eps[2.0][end], prem_eps[1.0][end]
    jr_lo_pct = round((1 - jr_lo) * 100)       # "X% fewer juniors"
    jr_hi_pct = round((jr_hi - 1) * 100)       # "X% more juniors"
    tot_lo_pct = round((1 - tot_lo) * 100)
    tot_hi_pct = round((tot_hi - 1) * 100)

    steps = [
        {"view": 0, "html": (
            "<h3>First, meet the dashed line</h3>"
            "<p>We built a working model of the tech design job market: "
            "thousands of simulated designers, 150 companies deciding every "
            "month which work goes to people, to people working with AI, or to "
            "AI alone. Then we ran that world 27 times, with different "
            "assumptions and different luck.</p>"
            "<p class='note'><b>How to read this chart:</b> the dashed line is "
            "a parallel world where AI never showed up. Everything that follows "
            "is measured against it — 1.0x means “exactly as many design "
            "jobs as there would have been anyway.” Above the line, AI "
            "added jobs. Below it, AI cost jobs. This lets us separate AI's "
            "effect from everything else (like the tech downturn that started "
            "before the AI boom).</p>")},
        {"view": 1, "html": (
            f"<h3>First — what about the layoffs?</h3>"
            f"<p>You've seen the headlines; maybe you've lived them. This is "
            f"every tracked tech layoff, by month, <b>measured, not "
            f"simulated</b>. The biggest wave on record peaked in "
            f"<b>{lo_m.index[peak_i].strftime('%B %Y')}</b> — when ChatGPT was "
            f"eight weeks old and AI could not yet meaningfully do design "
            f"work. That wave was interest rates and pandemic over-hiring "
            f"unwinding, not automation. The waves since are real too — but "
            f"raw layoff counts can't tell you which cuts are AI and which "
            f"are everything else.</p>"
            f"<p class='note'>That's exactly why every chart that follows is "
            f"measured against the dashed line — a world where AI never "
            f"happened — instead of against headlines. (Data: layoffs.fyi; "
            f"about a third of tracked events don't report headcounts, so "
            f"totals undercount.)</p>")},
        {"view": 2, "html": (
            "<h3>Question one: does it matter how fast AI gets good?</h3>"
            "<p>This is the thing everyone argues about — how capable the "
            "models are, how quickly they're improving. So we ran three "
            "versions of the future: AI improves "
            "<b style='color:#9ec5af'>slowly</b>, "
            "<b style='color:#5d9b84'>moderately</b>, or "
            "<b style='color:#2f7561'>fast</b>. The gap between them is wide — "
            "the “fast” world starts with AI doing nearly four times "
            "as much design work as the “slow” one.</p>"
            "<p class='note'>The lines track <b>junior designers</b> — the "
            "entry-level jobs people worry about most. Each line is the middle "
            "outcome of nine runs of that scenario.</p>")},
        {"view": 3, "html": (
            f"<h3>Surprisingly little.</h3>"
            f"<p>By 2035, the slow, moderate, and fast worlds all end up within "
            f"a few percentage points of each other. The speed of AI progress — "
            f"the thing we argue about most — turns out to be a side plot.</p>"
            f"<p class='note'><b>What this does not say:</b> it doesn't say AI "
            f"has no effect on design jobs. It says the <i>size</i> of that "
            f"effect is decided by something other than how fast the technology "
            f"improves. Keep scrolling for what that something is.</p>")},
        {"view": 4, "html": (
            f"<h3>One input is in free fall</h3>"
            f"<p>Before asking what AI does to design jobs, watch prices — "
            f"<b>measured, not simulated</b>. The black line is the cost of AI "
            f"output at a fixed quality level: down ~{ai_drop_pct:.0f}% in "
            f"under two years (roughly 280x). The gray line is U.S. wages over "
            f"the same window: {wage_pct_text}. Design work is made from these "
            f"two inputs, and one of them is collapsing in price.</p>"
            f"<p class='note'><b>Careful with that 280x:</b> tokens are not "
            f"finished design. The real cost of AI design work includes the "
            f"human time to direct and review it, which falls far more slowly. "
            f"And part of the collapse may be <i>capex-subsidized pricing</i> — "
            f"if vendors repriced ~3x in 2027, stress runs give back roughly a "
            f"third of the elastic world's 2035 gains{subsidy_bit}. The decline "
            f"is measured; its permanence is an assumption. Sources: Stanford "
            f"AI Index 2025; Employment Cost Index.</p>")},
        {"view": 5, "html": (
            f"<h3>The variable that matters: appetite</h3>"
            f"<p>These are the <b>exact same 27 runs</b>, regrouped by a "
            f"different question: <i>when design gets cheaper — and you just "
            f"watched how much cheaper — does the world simply buy more of "
            f"it?</i> (Economists call this demand elasticity. Think of it as "
            f"the world's appetite for design.)</p>"
            f"<p>Now the lines tear apart. In the "
            f"<b style='color:#bf4633'>fixed-appetite world</b>, companies "
            f"pocket the savings and cut roles: about {jr_lo_pct}% fewer junior "
            f"designers than a world without AI. In the "
            f"<b style='color:#2e6f9e'>growing-appetite world</b>, cheaper "
            f"design means more things get designed — {jr_hi_pct}% <i>more</i> "
            f"junior jobs. Same AI. Opposite outcomes.</p>")},
        {"view": 6, "html": (
            "<h3>Every future we found</h3>"
            "<p>The shaded band shows every single run — best case to worst, "
            "every assumption, every roll of the dice. Nearly all of that "
            "spread comes from appetite, not from AI's speed.</p>"
            "<p class='note'><b>What the model can say:</b> the range of "
            "plausible futures, and which lever moves you between them. "
            "<b>What it can't say:</b> which future we'll actually get. Treat "
            "the band as the honest answer.</p>")},
        {"view": 7, "html": (
            f"<h3>What happens to paychecks</h3>"
            f"<p>Same worlds, now viewed through the pay gap between senior and "
            f"junior designers — again measured against the no-AI world, so "
            f"only AI's effect shows. In the "
            f"<b style='color:#bf4633'>fixed-appetite world</b>, AI leaves the "
            f"gap roughly where it would have been anyway. In the "
            f"<b style='color:#2e6f9e'>growing-appetite world</b>, hiring pulls "
            f"juniors up the ladder and bids up their pay — the gap narrows by "
            f"about {round((1 - pr_lo) * 100)}%.</p>"
            f"<p class='note'>Worth sitting with: the world that's better for "
            f"design jobs is also the more <i>equal</i> one. Demand, not the "
            f"technology, decides both.</p>")},
        {"view": 8, "html": (
            f"<h3>The whole profession, one chart</h3>"
            f"<p>Counting every designer — junior through senior — the same AI "
            f"either shrinks the field by about {tot_lo_pct}% or grows it by "
            f"about {tot_hi_pct}%. The difference isn't the technology. It's "
            f"whether cheaper design expands what gets designed.</p>")},
        {"view": 9, "html": (
            f"<h3>Where new demand comes from</h3>"
            f"<p>Part of the growth isn't existing companies doing more — it's "
            f"<b>companies that wouldn't otherwise exist</b>. The model lets "
            f"new firms form faster as design output gets cheaper, and every "
            f"single run ends with more tech companies than the no-AI world — "
            f"{firms_lo_pct}% to {firms_hi_pct}% more by 2035. Each one ships "
            f"user-facing products. Each one consumes design.</p>"
            f"<p class='note'>This mechanism entered the model as a hypothesis "
            f"— <i>AI lets people start their own companies</i> — and the real "
            f"world is already showing its fingerprint: new tech-company "
            f"filings are running well above their 2023 pace. You'll see that "
            f"measured line in a moment.</p>")},
        {"view": 10, "html": (
            f"<h3>And the managers?</h3>"
            f"<p>The most personally pointed question for many design leaders. "
            f"The model gives firms one design manager per ~7 designers, and AI "
            f"adoption widens that span toward ~13 — the org-flattening and "
            f"pod-structure story in the 2026 layoff reporting. The result "
            f"splits by appetite like everything else: in the "
            f"<b style='color:#bf4633'>fixed-appetite world</b>, flattening "
            f"plus smaller teams cuts manager seats to "
            f"{mgr_eps[1.0][end]:.2f}x of the no-AI world. In the "
            f"<b style='color:#2e6f9e'>growing-appetite world</b>, headcount "
            f"growth outruns the flattening — {mgr_eps[2.0][end]:.2f}x. The "
            f"compression is real; whether it nets out negative is, again, "
            f"appetite.</p>"
            f"<p class='note'><b>Measured, right now:</b> Indeed's Management "
            f"postings index is {mgmt_yoy:+d}% year-over-year while "
            f"design-adjacent postings are {design_yoy:+d}% — the squeeze is "
            f"in the live data, not just projections. Caveat: that series is "
            f"all management, not design management; no public series breaks "
            f"that out. In the model, manager seats are derived from team "
            f"sizes and spans, not simulated as individual careers.</p>")},
        {"view": 11, "html": (
            f"<h3>Is good enough killing great?</h3>"
            f"<p>The deepest question this model can't yet answer: when AI "
            f"raises everyone's design baseline, does the premium segment die "
            f"(quality converges on good-enough) or does the race restart at a "
            f"higher bar? The two futures leave <b>opposite fingerprints in "
            f"the distribution of quality</b> — and here's a first measured "
            f"trace, from Lighthouse accessibility audits across millions of "
            f"real websites. Since 2023 the floor has climbed "
            f"{q_floor[0]:.0f} &rarr; {q_floor[-1]:.0f} while the ceiling sits "
            f"at {q_ceiling[-1]:.0f}. The gap is compressing — quality is "
            f"converging, so far.</p>"
            f"<p class='note'><b>Read this one carefully:</b> the compressing "
            f"gap matches the commoditization signature, but the ceiling sits "
            f"near the top of the scale — an arms race wouldn't show here even "
            f"if underway. It would show in the <i>price</i> of premium "
            f"design, which has no public series yet. And this measures "
            f"technical quality; nobody has a Lighthouse for judgment. "
            f"Source: HTTP Archive, monthly, mobile.</p>")},
        {"view": 12, "html": (
            "<h3>So which world are we in?</h3>"
            "<p>Honestly: the historical data can't settle it. We tested the "
            "model against three years of job postings and government surveys "
            "of AI adoption, and that history fits several of these futures "
            "about equally well. Anyone giving you one confident number about "
            "design jobs in 2035 is guessing.</p>"
            "<p class='note'><b>The part that isn't a guess:</b> appetite isn't "
            "weather. Every team that treats AI as a reason to design "
            "<i>more</i> — more products, more experiments, more polish — "
            "rather than a reason to design with fewer people, is voting for "
            "the blue world.</p>")},
    ]
    if evidence:
        lean = {
            "rising": "The early evidence leans, gently, blue.",
            "falling": "The early evidence leans, gently, red.",
            "flat": "So far, it refuses to pick a side.",
        }[evidence["trend"]]
        formation_bit = ""
        if "formation_pct" in evidence:
            formation_bit = (
                f" And a second witness, in <b style='color:#7a5b8e'>violet</b>: "
                f"new tech companies — each one a future consumer of design — "
                f"are forming {evidence['formation_pct']}% above their 2023 "
                f"pace, a surge that began with the agentic-AI era."
            )
        steps.append({"view": len(views) - 1, "html": (
            f"<h3>But we can watch the answer arrive</h3>"
            f"<p>Two early signals, <b>measured, not simulated</b>. The "
            f"<b>black line</b>: designed products actually shipping (new app "
            f"releases) divided by design hiring (job postings). If appetite "
            f"grows as design gets cheaper, it should rise — as of "
            f"{evidence['asof']} it reads <b>{evidence['latest']}</b> and has "
            f"been {evidence['trend']} for a year.{formation_bit} {lean}</p>"
            f"<p class='note'><b>What this doesn't prove:</b> one app store; "
            f"raw counts ignore quality; the 2024 dip is mostly Google "
            f"tightening quality rules; and company-formation filings aren't "
            f"employer firms — some may be laid-off workers founding out of "
            f"necessity. Direction, not proof. This page rebuilds from fresh "
            f"data, so the answer sharpens right here.</p>")})

    return {"x": x, "xDomain": [X_START, X_END], "views": views, "steps": steps}


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Same AI. Opposite outcomes.</title>
<style>
  :root {
    --paper: #faf7f0; --ink: #211d18; --muted: #7a7065; --rule: #c9c0b2;
  }
  * { box-sizing: border-box; margin: 0; }
  body {
    background: var(--paper); color: var(--ink);
    font-family: Georgia, 'Times New Roman', serif;
    line-height: 1.55;
  }
  header { max-width: 720px; margin: 0 auto; padding: 12vh 24px 6vh; text-align: center; }
  header h1 { font-size: clamp(2rem, 5vw, 3.4rem); line-height: 1.1; letter-spacing: -0.01em; }
  header .dek { margin-top: 1.2rem; font-size: 1.15rem; color: var(--muted); font-style: italic; }
  header .byline {
    margin-top: 1.6rem; font-family: -apple-system, 'Helvetica Neue', sans-serif;
    font-size: 0.78rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted);
  }
  .hint { text-align: center; color: var(--muted); font-size: .85rem; padding-bottom: 8vh;
          font-family: -apple-system, sans-serif; }
  .scrolly { display: grid; grid-template-columns: minmax(0,1fr) 360px;
             max-width: 1180px; margin: 0 auto; gap: 24px; padding: 0 24px; }
  .graphic { position: sticky; top: 8vh; height: 84vh; display: flex;
             align-items: center; justify-content: center; }
  .graphic svg { width: 100%; height: auto; max-height: 84vh; }
  .steps { padding: 30vh 0 40vh; }
  .step { min-height: 78vh; display: flex; align-items: center; }
  .step .card {
    background: rgba(250,247,240,.94); border: 1px solid var(--rule);
    border-radius: 6px; padding: 22px 24px; box-shadow: 0 2px 14px rgba(33,29,24,.06);
    opacity: .35; transition: opacity .4s;
  }
  .step.active .card { opacity: 1; }
  .card h3 { font-size: 1.18rem; margin-bottom: .55rem; }
  .card p { font-size: .98rem; }
  .card p + p { margin-top: .6rem; }
  .card .note {
    margin-top: .85rem; padding-top: .75rem; border-top: 1px solid var(--rule);
    font-size: .84rem; color: var(--muted);
    font-family: -apple-system, 'Helvetica Neue', sans-serif; line-height: 1.5;
  }
  footer { max-width: 720px; margin: 0 auto; padding: 6vh 24px 14vh;
           color: var(--muted); font-size: .82rem;
           font-family: -apple-system, 'Helvetica Neue', sans-serif; }
  footer p { margin-bottom: .6rem; }
  /* chart text */
  .axis text, .endlabel, .ann, .metric, .reflabel, .todaylabel {
    font-family: -apple-system, 'Helvetica Neue', sans-serif;
  }
  .axis text { font-size: 11px; fill: var(--muted); }
  .axis line { stroke: var(--rule); stroke-width: 1; }
  .gridline { stroke: var(--rule); stroke-width: .6; opacity: .55; }
  .series { fill: none; stroke-width: 2.4; transition: stroke .7s, opacity .7s; }
  .bandpath { transition: opacity .7s; }
  .refline { stroke: #8b8275; stroke-dasharray: 5 4; stroke-width: 1.2; }
  .reflabel { font-size: 10.5px; fill: #8b8275; }
  .todayline { stroke: var(--rule); stroke-width: 1; }
  .todaylabel { font-size: 10px; fill: var(--muted); }
  .endlabel { font-size: 11px; font-weight: 600; transition: opacity .7s; }
  .ann { font-size: 12px; font-weight: 700; opacity: 0; transition: opacity .5s; }
  .ann.show { opacity: 1; }
  #chart.switching .series, #chart.switching .bandpath, #chart.switching .endlabel {
    transition: opacity .2s; opacity: 0 !important; }
  .metric { font-size: 12.5px; fill: var(--muted); letter-spacing: .04em; }
  @media (max-width: 880px) {
    .scrolly { grid-template-columns: 1fr; }
    .graphic { position: sticky; top: 0; height: 52vh; background: var(--paper);
               z-index: 2; border-bottom: 1px solid var(--rule); }
    .steps { padding-top: 6vh; }
    .step { min-height: 64vh; }
  }
</style>
</head>
<body>
<header>
  <h1>Same AI.<br>Opposite outcomes.</h1>
  <p class="dek">27 simulated futures for designers in tech — and the one variable that decides between them.</p>
  <p class="byline">Shannon Hosmer &middot; June 2026</p>
</header>
<p class="hint">Scroll &darr;</p>

<div class="scrolly">
  <div class="graphic">
    <svg id="chart" viewBox="0 0 760 520" role="img"
         aria-label="Animated chart of simulated design employment outcomes"></svg>
  </div>
  <div class="steps" id="steps"></div>
</div>

<footer>
  <p><b>Method.</b> 27 agent-based simulation runs (3 capability scenarios &times; demand
  elasticity 1.0&ndash;2.0 &times; 3 seeds), each differenced against a paired no-AI
  counterfactual with identical random events. Lines are medians; bands are min&ndash;max
  across all runs; series smoothed with a 5-month centered window for display.
  <b>Bands span the assumption grid we chose to run &mdash; they are not probability
  intervals</b>, and a wider grid would draw wider bands. All spread shown is parameter
  uncertainty within one model structure; a different model would draw different
  terrain. (An earlier version of this model produced a spurious junior collapse from a
  structural flaw that the counterfactual caught &mdash; structure matters.)</p>
  <p><b>Data.</b> Capability curves anchored to O*NET design-occupation task statements
  joined to the Anthropic Economic Index; firm adoption calibrated to the Census Bureau's
  Business Trends and Outlook Survey; labor-market context from BLS OEWS and Indeed
  Hiring Lab; company formation from Census Business Formation Statistics; layoff
  events from layoffs.fyi. The model
  includes firm entry and exit — new firms arrive faster as design output gets cheaper. The 280x figure is the Stanford AI Index 2025's measured decline in
  inference cost at fixed (GPT-3.5-level) capability, Nov 2022 &ndash; Oct 2024; in the
  model, AI cost per task falls with a 24-month half-life toward an orchestration-cost
  floor. The AEI observes one AI assistant, so visual-production automation is
  undercounted. A model is an argument made precise &mdash; not a forecast.</p>
  <p><b>Scope.</b> This is a model of the <b>U.S. tech design labor market</b> &mdash;
  the employment, wage, postings, layoff, and company-formation series are U.S. data;
  only the AI-usage (Anthropic Economic Index) and web-quality (HTTP Archive) sources
  are global. Worth holding the wider frame: an estimated <b>~13% of humanity</b>
  actively uses AI at all (~1.1B people, Jan 2026 estimate), and the U.S. alone
  accounts for ~22% of measured Claude.ai usage. This story describes the leading
  edge of AI's labor-market impact, not the world's experience of it.</p>
</footer>

<script>
const DATA = __PAYLOAD__;
const W = 760, H = 520, M = {l: 56, t: 30, r: 130, b: 40};
const [X0, X1] = DATA.xDomain;
const N = DATA.x.length;
const svg = document.getElementById('chart');
const NS = 'http://www.w3.org/2000/svg';

function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  (parent || svg).appendChild(e);
  return e;
}
const X = v => M.l + (v - X0) / (X1 - X0) * (W - M.l - M.r);
const Y = (v, d) => M.t + (1 - (v - d[0]) / (d[1] - d[0])) * (H - M.t - M.b);
const lerp = (a, b, t) => a + (b - a) * t;
const ease = t => t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2;

function linePath(vals, dom, xs) {
  xs = xs || DATA.x;
  let p = '';
  for (let i = 0; i < xs.length; i++)
    p += (i ? 'L' : 'M') + X(xs[i]).toFixed(1) + ',' + Y(vals[i], dom).toFixed(1);
  return p;
}
function areaPath(lo, hi, dom) {
  let p = '';
  for (let i = 0; i < N; i++)
    p += (i ? 'L' : 'M') + X(DATA.x[i]).toFixed(1) + ',' + Y(hi[i], dom).toFixed(1);
  for (let i = N - 1; i >= 0; i--)
    p += 'L' + X(DATA.x[i]).toFixed(1) + ',' + Y(lo[i], dom).toFixed(1);
  return p + 'Z';
}

// static layers
const gGrid = el('g', {class: 'axis'});
const bandEl = el('path', {class: 'bandpath', fill: 'rgba(33,29,24,0.08)', opacity: 0});
const todayX = X(2026.5);
el('line', {class: 'todayline', x1: todayX, x2: todayX, y1: M.t, y2: H - M.b});
el('text', {class: 'todaylabel', x: todayX + 4, y: M.t + 10}).textContent = 'today';
const refEl = el('line', {class: 'refline', x1: M.l, x2: W - M.r});
const refLbl = el('text', {class: 'reflabel', x: W - M.r + 6});
const metricEl = el('text', {class: 'metric', x: M.l, y: 16});
const gX = el('g', {class: 'axis'});
for (let yr = 2024; yr <= 2035; yr += 2) {
  el('line', {x1: X(yr), x2: X(yr), y1: H - M.b, y2: H - M.b + 4}, gX);
  const t = el('text', {x: X(yr), y: H - M.b + 16, 'text-anchor': 'middle'}, gX);
  t.textContent = yr;
}
const seriesEls = [], endEls = [];
for (let s = 0; s < 3; s++) {
  seriesEls.push(el('path', {class: 'series'}));
  endEls.push(el('text', {class: 'endlabel'}));
}
const extraEls = [], extraLbls = [];
for (let s = 0; s < 2; s++) {
  extraEls.push(el('path', {class: 'series', 'stroke-width': 2.8, opacity: 0}));
  extraLbls.push(el('text', {class: 'endlabel', opacity: 0}));
}
const gMarkers = el('g');
const gAnn = el('g');

// state
let cur = null, animId = null, curFam = '', switchTimer = null;
function snapshot(view) {
  return {
    dom: view.y.slice(),
    series: view.series.map(s => ({values: s.values.slice(), hidden: s.hidden})),
    band: view.band ? {lo: view.band.lo.slice(), hi: view.band.hi.slice()} : null,
    ref: view.ref,
  };
}
function drawTicks(view) {
  gGrid.innerHTML = '';
  for (const tv of view.ticks) {
    const y = Y(tv, view.y);
    el('line', {class: 'gridline', x1: M.l, x2: W - M.r, y1: y, y2: y}, gGrid);
    const t = el('text', {x: M.l - 8, y: y + 4, 'text-anchor': 'end'}, gGrid);
    t.textContent = view.fmt === 'plain' ? String(tv) : tv.toFixed(1) + 'x';
  }
}
function drawAnn(view) {
  gAnn.innerHTML = '';
  for (const a of view.ann) {
    const t = el('text', {
      class: 'ann', x: X(DATA.x[a.xi]) + 8, y: Y(a.y, view.y) + 4,
      fill: '#211d18',
    }, gAnn);
    t.textContent = a.text;
    t.classList.add('show');
  }
}
function render(state, view) {
  const labels = [];
  for (let s = 0; s < 3; s++) {
    const sv = state.series[s];
    seriesEls[s].setAttribute('d', linePath(sv.values, state.dom));
    seriesEls[s].setAttribute('stroke', view.series[s].color);
    seriesEls[s].style.opacity = view.series[s].hidden ? 0 : 1;
    labels.push({s, y: Y(sv.values[N - 1], state.dom) - 4});
  }
  // spread end labels apart when lines converge
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++)
    if (labels[i].y - labels[i - 1].y < 15) labels[i].y = labels[i - 1].y + 15;
  for (const L of labels) {
    endEls[L.s].setAttribute('x', X(DATA.x[N - 1]) + 8);
    endEls[L.s].setAttribute('y', L.y);
    endEls[L.s].setAttribute('fill', view.series[L.s].color);
    endEls[L.s].style.opacity = view.series[L.s].hidden ? 0 : 1;
    endEls[L.s].textContent = view.series[L.s].name;
  }
  if (state.band) {
    bandEl.setAttribute('d', areaPath(state.band.lo, state.band.hi, state.dom));
    bandEl.style.opacity = 1;
  } else bandEl.style.opacity = 0;
  const extras = view.extras || [];
  gMarkers.innerHTML = '';
  for (let s = 0; s < 2; s++) {
    if (s < extras.length) {
      const ex = extras[s];
      if (ex.bars) {  // discrete monthly quantities: columns, not a line
        let d = '';
        const y0 = Y(0, state.dom);
        for (let i = 0; i < ex.x.length; i++)
          d += 'M' + X(ex.x[i]).toFixed(1) + ',' + y0.toFixed(1)
             + 'L' + X(ex.x[i]).toFixed(1) + ',' + Y(ex.values[i], state.dom).toFixed(1);
        extraEls[s].setAttribute('d', d);
        extraEls[s].setAttribute('stroke-width', 3);
      } else {
        extraEls[s].setAttribute('d', linePath(ex.values, state.dom, ex.x));
        extraEls[s].setAttribute('stroke-width', 2.8);
      }
      if (ex.dash) extraEls[s].setAttribute('stroke-dasharray', ex.dash);
      else extraEls[s].removeAttribute('stroke-dasharray');
      if (ex.markers)
        for (const [mx, mv] of ex.markers)
          el('circle', {cx: X(mx), cy: Y(mv, state.dom), r: 4.5, fill: ex.color}, gMarkers);
      extraEls[s].setAttribute('stroke', ex.color);
      extraEls[s].style.opacity = 1;
      extraLbls[s].setAttribute('x', X(ex.x[ex.x.length - 1]) + 8);
      extraLbls[s].setAttribute('y', Y(ex.values[ex.values.length - 1], state.dom) + 4);
      extraLbls[s].setAttribute('fill', ex.color);
      extraLbls[s].textContent = ex.label;
      extraLbls[s].style.opacity = 1;
    } else { extraEls[s].style.opacity = 0; extraLbls[s].style.opacity = 0; }
  }
  const ry = Y(state.ref, state.dom);
  refEl.setAttribute('y1', ry); refEl.setAttribute('y2', ry);
  refLbl.setAttribute('y', ry + 4);
}
function setView(i) {
  const view = DATA.views[i];
  const from = cur || snapshot(view);
  const to = snapshot(view);
  if (animId) cancelAnimationFrame(animId);
  gAnn.innerHTML = '';
  metricEl.textContent = view.metric;
  refLbl.textContent = view.refLabel;
  if (window.INSTANT) {  // ?view=N debug/screenshot mode: no tween
    cur = to;
    drawTicks(view);
    render(to, view);
    drawAnn(view);
    curFam = view.fam || '';
    return;
  }
  // Tweening values between *different metrics* would animate a false
  // continuity ("the line moved" when the quantity changed). Same-family
  // transitions tween; metric changes crossfade and snap.
  const fam = view.fam || '';
  if (curFam && fam !== curFam) {
    curFam = fam;
    cur = to;
    if (switchTimer) clearTimeout(switchTimer);
    svg.classList.add('switching');
    switchTimer = setTimeout(() => {
      drawTicks(view);
      render(to, view);
      svg.classList.remove('switching');
      setTimeout(() => drawAnn(view), 250);
    }, 230);
    return;
  }
  curFam = fam;
  const t0 = performance.now(), DUR = 950;
  // band: if appearing/disappearing, snap shape but fade via CSS
  const fromBand = from.band || to.band, toBand = to.band || from.band;
  function frame(now) {
    const t = ease(Math.min(1, (now - t0) / DUR));
    const st = {
      dom: [lerp(from.dom[0], to.dom[0], t), lerp(from.dom[1], to.dom[1], t)],
      ref: lerp(from.ref, to.ref, t),
      series: to.series.map((sv, s) => ({
        values: sv.values.map((v, i) => lerp(from.series[s].values[i], v, t)),
        hidden: sv.hidden,
      })),
      band: toBand ? {
        lo: toBand.lo.map((v, i) => lerp(fromBand.lo[i], v, t)),
        hi: toBand.hi.map((v, i) => lerp(fromBand.hi[i], v, t)),
      } : null,
    };
    if (!to.band) st.band = null;
    if (t >= 1 && to.band) st.band = to.band;
    render(st, view);
    if (t < 1) animId = requestAnimationFrame(frame);
    else { cur = to; drawTicks(view); drawAnn(view); }
  }
  drawTicks(view);
  animId = requestAnimationFrame(frame);
  cur = to;
}

// steps
const stepsRoot = document.getElementById('steps');
DATA.steps.forEach((s, i) => {
  const d = document.createElement('div');
  d.className = 'step'; d.dataset.view = s.view; d.dataset.i = i;
  d.innerHTML = '<div class="card">' + s.html + '</div>';
  stepsRoot.appendChild(d);
});
const stepEls = [...document.querySelectorAll('.step')];
const obs = new IntersectionObserver(entries => {
  for (const e of entries) if (e.isIntersecting) {
    stepEls.forEach(x => x.classList.remove('active'));
    e.target.classList.add('active');
    setView(+e.target.dataset.view);
  }
}, {rootMargin: '-42% 0px -42% 0px'});
stepEls.forEach(s => obs.observe(s));

// init (and ?view=N for screenshots: jump to scene, hide prose chrome)
const q = new URLSearchParams(location.search).get('view');
if (q !== null) {
  window.INSTANT = true;
  document.querySelector('header').style.display = 'none';
  document.querySelector('.hint').style.display = 'none';
  stepsRoot.style.display = 'none';
}
cur = null;
setView(q !== null ? +q : 0);
</script>
</body>
</html>
"""


def render() -> str:
    """Full story page HTML (used by main() and by the site builder)."""
    return TEMPLATE.replace("__PAYLOAD__", json.dumps(build_payload()))


def main() -> int:
    html = render()
    # docs/index.html is the GitHub Pages copy; writeup/story/ is canonical.
    for out in (OUT, Path("docs/index.html")):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
