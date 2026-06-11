"""Animated data story: self-contained scrollytelling HTML from scenarios.csv.

Generates writeup/story/index.html — a single file with the aggregated run
data embedded, a sticky SVG chart that tweens between scenes as the reader
scrolls, and the narrative. Re-run after `des-sim-scenarios` to refresh.
A `?view=N` query param jumps straight to a scene (used for headless
screenshots and debugging).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

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
    prem_eps = by("elasticity", "senior_premium")
    jr_band = band("employed_junior_vs_cf")
    tot_band = band("employed_total_vs_cf")
    prem_band = band("senior_premium")

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
             band=None, ann=[], metric="Junior designers employed, vs a world without AI"),
        # 1 — by capability scenario
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_scn(), band=None, ann=[],
             metric="Junior designers employed, vs a world without AI"),
        # 2 — same, annotated endpoints
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_scn(), band=None,
             ann=ann_ends(jr_scn, ("slow", "base", "fast")),
             metric="Junior designers employed, vs a world without AI"),
        # 3 — regrouped by elasticity
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_eps(jr_eps), band=None,
             ann=ann_ends(jr_eps, (1.0, 1.5, 2.0)),
             metric="Junior designers employed, vs a world without AI"),
        # 4 — with min-max band
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_eps(jr_eps), band=jr_band,
             ann=ann_ends(jr_eps, (1.0, 1.5, 2.0)),
             metric="Junior designers employed — band = every run"),
        # 5 — senior premium
        dict(y=[1.3, 3.7], ticks=[1.5, 2.0, 2.5, 3.0, 3.5], ref=2.14,
             refLabel="today ≈ 2.1x",
             series=series_eps(prem_eps), band=prem_band,
             ann=ann_ends(prem_eps, (1.0, 1.5, 2.0), "{:.1f}x"),
             metric="Senior-to-junior wage premium"),
        # 6 — total employment
        dict(y=[0.65, 1.95], ticks=[0.8, 1.0, 1.2, 1.4, 1.6, 1.8], ref=1.0,
             refLabel="no-AI counterfactual",
             series=series_eps(tot_eps), band=tot_band,
             ann=ann_ends(tot_eps, (1.0, 1.5, 2.0)),
             metric="All designers employed, vs a world without AI"),
        # 7 — closing: band only
        dict(**y_ratio, ref=1.0, refLabel="no-AI counterfactual",
             series=series_eps(jr_eps, hidden=True), band=jr_band, ann=[],
             metric="Junior designers employed — the open question"),
    ]

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
        {"view": 2, "html": (
            f"<h3>Surprisingly little.</h3>"
            f"<p>By 2035, the slow, moderate, and fast worlds all end up within "
            f"a few percentage points of each other. The speed of AI progress — "
            f"the thing we argue about most — turns out to be a side plot.</p>"
            f"<p class='note'><b>What this does not say:</b> it doesn't say AI "
            f"has no effect on design jobs. It says the <i>size</i> of that "
            f"effect is decided by something other than how fast the technology "
            f"improves. Keep scrolling for what that something is.</p>")},
        {"view": 3, "html": (
            f"<h3>The variable that matters: appetite</h3>"
            f"<p>These are the <b>exact same 27 runs</b>, regrouped by a "
            f"different question: <i>when design gets cheaper, does the world "
            f"simply buy more of it?</i> (Economists call this demand "
            f"elasticity. Think of it as the world's appetite for design.)</p>"
            f"<p>Now the lines tear apart. In the "
            f"<b style='color:#bf4633'>fixed-appetite world</b>, companies "
            f"pocket the savings and cut roles: about {jr_lo_pct}% fewer junior "
            f"designers than a world without AI. In the "
            f"<b style='color:#2e6f9e'>growing-appetite world</b>, cheaper "
            f"design means more things get designed — {jr_hi_pct}% <i>more</i> "
            f"junior jobs. Same AI. Opposite outcomes.</p>")},
        {"view": 4, "html": (
            "<h3>Every future we found</h3>"
            "<p>The shaded band shows every single run — best case to worst, "
            "every assumption, every roll of the dice. Nearly all of that "
            "spread comes from appetite, not from AI's speed.</p>"
            "<p class='note'><b>What the model can say:</b> the range of "
            "plausible futures, and which lever moves you between them. "
            "<b>What it can't say:</b> which future we'll actually get. Treat "
            "the band as the honest answer.</p>")},
        {"view": 5, "html": (
            f"<h3>What happens to paychecks</h3>"
            f"<p>Same worlds, now viewed through wages. Today a senior designer "
            f"earns about 2.1x what a junior earns. In the "
            f"<b style='color:#bf4633'>fixed-appetite world</b>, juniors get "
            f"scarce, seniors get expensive, and the gap climbs past "
            f"{pr_hi:.1f}x. In the <b style='color:#2e6f9e'>growing-appetite "
            f"world</b>, hiring pulls people up the ladder and the gap narrows "
            f"to about {pr_lo:.1f}x.</p>"
            f"<p class='note'>This is why the debate feels so muddled: bad news "
            f"for juniors is quietly <i>good</i> news for senior paychecks. "
            f"Different people are living in different charts.</p>")},
        {"view": 6, "html": (
            f"<h3>The whole profession, one chart</h3>"
            f"<p>Counting every designer — junior through senior — the same AI "
            f"either shrinks the field by about {tot_lo_pct}% or grows it by "
            f"about {tot_hi_pct}%. The difference isn't the technology. It's "
            f"whether cheaper design expands what gets designed.</p>")},
        {"view": 7, "html": (
            "<h3>So which world are we in?</h3>"
            "<p>Honestly: the real-world data can't tell us yet. We tested the "
            "model against three years of job postings and government surveys "
            "of AI adoption, and that history fits several of these futures "
            "about equally well. Anyone giving you one confident number about "
            "design jobs in 2035 is guessing.</p>"
            "<p class='note'><b>The part that isn't a guess:</b> appetite isn't "
            "weather. Every team that treats AI as a reason to design "
            "<i>more</i> — more products, more experiments, more polish — "
            "rather than a reason to design with fewer people, is voting for "
            "the blue world. This page rebuilds from fresh data as the picture "
            "sharpens.</p>")},
    ]

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
  across all runs; series smoothed with a 5-month centered window for display.</p>
  <p><b>Data.</b> Capability curves anchored to O*NET design-occupation task statements
  joined to the Anthropic Economic Index; firm adoption calibrated to the Census Bureau's
  Business Trends and Outlook Survey; labor-market context from BLS OEWS and Indeed
  Hiring Lab. The AEI observes one AI assistant, so visual-production automation is
  undercounted. A model is an argument made precise &mdash; not a forecast.</p>
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

function linePath(vals, dom) {
  let p = '';
  for (let i = 0; i < N; i++)
    p += (i ? 'L' : 'M') + X(DATA.x[i]).toFixed(1) + ',' + Y(vals[i], dom).toFixed(1);
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
const gAnn = el('g');

// state
let cur = null, animId = null;
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
    t.textContent = tv.toFixed(1) + 'x';
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
    requestAnimationFrame(() => requestAnimationFrame(() => t.classList.add('show')));
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


def main() -> int:
    payload = build_payload()
    html = TEMPLATE.replace("__PAYLOAD__", json.dumps(payload))
    # docs/index.html is the GitHub Pages copy; writeup/story/ is canonical.
    for out in (OUT, Path("docs/index.html")):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB, {len(payload['views'])} scenes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
