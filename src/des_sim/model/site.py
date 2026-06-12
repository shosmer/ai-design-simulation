"""Multi-page site builder: the story plus six ways to grok the model.

`des-sim-site` writes docs/ as a small static site with a shared left nav:
  index.html      — the scrollytelling story (story.py, nav injected)
  explore.html    — build-your-own-2035 elasticity slider (precomputed grid)
  dots.html       — designers as dots: agent-level unit viz, two worlds
  flows.html      — where the work goes: task-hours sankey by year
  futures.html    — 27 futures, one at a time (hypothetical outcome plots)
  categories.html — five kinds of design work, five automation curves
  signals.html    — which world are we in? live measured-signal panel

Everything is computed from live data/results at build time; no external
JS/CSS dependencies. The slider grid is cached at results/explore_grid.csv —
delete it to force a re-run after engine changes.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .. import targets
from . import story
from .backcast import START_ANCHOR, calibrate_adoption
from .engine import (
    CATEGORY_STRUCTURE,
    MID_SHARE_OF_NON_JUNIOR,
    Simulation,
    build_categories,
)

DOCS = Path("docs")
RESULTS = Path("results")
MONTHS = 156  # Jan 2023 .. Dec 2035

NAV = [
    ("index.html", "The story", "scrollytelling, start here"),
    ("explore.html", "Build your own 2035", "drag the one variable that matters"),
    ("dots.html", "Designers as dots", "4,000 simulated careers, two worlds"),
    ("flows.html", "Where the work goes", "task flows: people vs AI"),
    ("futures.html", "27 futures", "one possible world at a time"),
    ("terrain.html", "The terrain of futures", "the cliff runs along one axis"),
    ("categories.html", "Five kinds of design work", "what automates first"),
    ("signals.html", "Which world are we in?", "live measured signals"),
]

INK, MUTED, PAPER, RULE = "#211d18", "#7a7065", "#faf7f0", "#c9c0b2"
RED, AMBER, BLUE, GREEN = "#bf4633", "#b08a3e", "#2e6f9e", "#2f7561"

SHELL_CSS = """
  :root { --paper:#faf7f0; --ink:#211d18; --muted:#7a7065; --rule:#c9c0b2; }
  * { box-sizing: border-box; margin: 0; }
  body { background: var(--paper); color: var(--ink);
         font-family: Georgia, 'Times New Roman', serif; line-height: 1.55; }
  nav.sitenav { position: fixed; top: 0; left: 0; bottom: 0; width: 230px;
    border-right: 1px solid var(--rule); padding: 28px 18px; overflow-y: auto;
    background: var(--paper); z-index: 50;
    font-family: -apple-system, 'Helvetica Neue', sans-serif; }
  nav.sitenav .brand { font-family: Georgia, serif; font-size: 1.05rem;
    line-height: 1.25; margin-bottom: 4px; }
  nav.sitenav .sub { font-size: .7rem; color: var(--muted); letter-spacing: .08em;
    text-transform: uppercase; margin-bottom: 22px; }
  nav.sitenav a { display: block; text-decoration: none; color: var(--ink);
    padding: 9px 10px; border-radius: 5px; margin-bottom: 2px; }
  nav.sitenav a .t { font-size: .85rem; font-weight: 600; }
  nav.sitenav a .d { font-size: .72rem; color: var(--muted); }
  nav.sitenav a:hover { background: rgba(33,29,24,.05); }
  nav.sitenav a.active { background: rgba(33,29,24,.08); }
  main.page { margin-left: 230px; padding: 48px 56px; max-width: 1040px; }
  main.page h1 { font-size: 2rem; line-height: 1.15; margin-bottom: .5rem; }
  main.page .dek { color: var(--muted); font-style: italic; margin-bottom: 2rem;
    max-width: 640px; }
  .note { font-family: -apple-system, sans-serif; font-size: .82rem;
    color: var(--muted); line-height: 1.5; max-width: 680px;
    border-top: 1px solid var(--rule); padding-top: .8rem; margin-top: 1.4rem; }
  .panel { background: #fff; border: 1px solid var(--rule); border-radius: 8px;
    padding: 20px; margin: 14px 0; }
  .chartlabel { font-family: -apple-system, sans-serif; font-size: 12px;
    fill: var(--muted); }
  button.ctl { font-family: -apple-system, sans-serif; font-size: .82rem;
    background: #fff; border: 1px solid var(--rule); border-radius: 5px;
    padding: 6px 14px; cursor: pointer; }
  button.ctl.on { background: var(--ink); color: var(--paper);
    border-color: var(--ink); }
  @media (max-width: 880px) {
    nav.sitenav { position: static; width: auto; display: flex; gap: 6px;
      overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--rule);
      padding: 12px; }
    nav.sitenav .brand, nav.sitenav .sub, nav.sitenav a .d { display: none; }
    nav.sitenav a { white-space: nowrap; }
    main.page { margin-left: 0; padding: 24px 18px; }
  }
"""


def nav_html(active: str) -> str:
    links = "".join(
        f'<a href="{href}" class="{"active" if href == active else ""}">'
        f'<span class="t">{title}</span><br><span class="d">{desc}</span></a>'
        for href, title, desc in NAV
    )
    return (
        '<nav class="sitenav"><div class="brand">Same AI.<br>Opposite outcomes.</div>'
        '<div class="sub">a working model</div>' + links + "</nav>"
    )


def shell(active: str, title: str, dek: str, body: str, script: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{SHELL_CSS}</style></head>
<body>{nav_html(active)}
<main class="page"><h1>{title}</h1><p class="dek">{dek}</p>
{body}</main>
<script>{script}</script></body></html>"""


# ---------------------------------------------------------------- explore --

EXPLORE_EPS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]
EXPLORE_SEEDS = [0, 1, 2]


def explore_grid() -> pd.DataFrame:
    cache = RESULTS / "explore_grid.csv"
    if cache.exists():
        return pd.read_csv(cache)
    loc, scale, _ = calibrate_adoption()
    frames = []
    no_ai = {}
    for seed in EXPLORE_SEEDS:
        no_ai[seed] = Simulation(
            elasticity=1.5, months=MONTHS, seed=seed, start_anchor=START_ANCHOR,
            adoption_loc=loc, adoption_scale=scale, ai_scale=0.0,
        ).run()
    for eps in EXPLORE_EPS:
        for seed in EXPLORE_SEEDS:
            df = Simulation(
                elasticity=eps, months=MONTHS, seed=seed,
                start_anchor=START_ANCHOR, adoption_loc=loc, adoption_scale=scale,
            ).run()
            base = no_ai[seed]
            for col in ("employed_junior", "employed_total", "senior_premium", "manager_seats"):
                df[f"{col}_vs_cf"] = df[col] / base[col]
            df["eps"], df["seed"] = eps, seed
            frames.append(df)
            print(f"  explore grid: eps={eps} seed={seed}")
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(cache, index=False)
    return out


def page_explore() -> str:
    grid = explore_grid()
    sm = lambda s: s.rolling(5, center=True, min_periods=1).mean()
    data = {"eps": EXPLORE_EPS, "metrics": {}}
    for key, col in [("junior", "employed_junior_vs_cf"),
                     ("total", "employed_total_vs_cf"),
                     ("premium", "senior_premium_vs_cf"),
                     ("managers", "manager_seats_vs_cf")]:
        med = grid.groupby(["eps", "month"])[col].median().unstack(0)
        data["metrics"][key] = {str(e): [round(v, 4) for v in sm(med[e])] for e in EXPLORE_EPS}
    body = """
<div class="panel">
  <div style="font-family:-apple-system,sans-serif;font-size:.9rem;margin-bottom:6px">
    <b>The world's appetite for design</b> — when design gets cheaper, how much more does the world buy?</div>
  <input id="slider" type="range" min="0" max="8" value="4" step="1" style="width:100%">
  <div style="display:flex;justify-content:space-between;font-family:-apple-system,sans-serif;font-size:.75rem;color:var(--muted)">
    <span>appetite stays fixed</span><span id="epslabel"></span><span>appetite grows a lot</span></div>
</div>
<div class="panel"><svg id="chart" viewBox="0 0 900 380" style="width:100%"></svg></div>
<div id="readout" style="display:flex;gap:14px;flex-wrap:wrap"></div>
<p class="note">Each position is the median of three full simulation runs at that
elasticity (base capability scenario), measured against paired no-AI worlds —
readouts carry a &approx; because three seeds leave a few points of noise.
The historical record (2023–26) cannot tell us where this slider truly sits —
that's the model's central honesty. Drag it and notice which futures you can
and can't reach: the speed of AI never appears on this page.</p>"""
    script = """
const D = __DATA__;
const W=900,H=380,M={l:50,t:20,r:110,b:34};
const svg=document.getElementById('chart');
const NS='http://www.w3.org/2000/svg';
function el(t,a,p){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);(p||svg).appendChild(e);return e;}
const N=D.metrics.junior[String(D.eps[0])].length;
const X=i=>M.l+i/(N-1)*(W-M.l-M.r);
const Y=(v,y0,y1)=>M.t+(1-(v-y0)/(y1-y0))*(H-M.t-M.b);
const DOM=[0.4,2.0];
for(const tv of [0.5,1.0,1.5,2.0]){const y=Y(tv,...DOM);
  el('line',{x1:M.l,x2:W-M.r,y1:y,y2:y,stroke:'#c9c0b2','stroke-width':tv===1?1.4:0.6,'stroke-dasharray':tv===1?'5 4':''});
  const t=el('text',{x:M.l-8,y:y+4,'text-anchor':'end',class:'chartlabel'});t.textContent=tv.toFixed(1)+'x';}
for(let yr=2024;yr<=2035;yr+=2){const x=X((yr-2023)*12+6);
  const t=el('text',{x:x,y:H-M.b+16,'text-anchor':'middle',class:'chartlabel'});t.textContent=yr;}
const SERIES=[['junior','Junior designers','#2e6f9e'],['total','All designers','#211d18'],['premium','Senior/junior pay gap','#b08a3e'],['managers','Design managers','#7a5b8e']];
const paths={},labels={};
for(const [k,name,c] of SERIES){
  paths[k]=el('path',{fill:'none',stroke:c,'stroke-width':2.6});
  labels[k]=el('text',{class:'chartlabel',style:'font-weight:600','fill':c});
}
function draw(i){
  const eps=D.eps[i];
  document.getElementById('epslabel').textContent='elasticity = '+eps.toFixed(2);
  const cards=[];
  for(const [k,name,c] of SERIES){
    const vals=D.metrics[k][String(eps)];
    let d='';for(let j=0;j<N;j++)d+=(j?'L':'M')+X(j).toFixed(1)+','+Y(vals[j],...DOM).toFixed(1);
    paths[k].setAttribute('d',d);
    labels[k].setAttribute('x',X(N-1)+8);labels[k].setAttribute('y',Y(vals[N-1],...DOM)+4);
    labels[k].textContent=name;
    const end=vals[N-1];
    cards.push(`<div class="panel" style="flex:1;min-width:170px"><div style="font-family:-apple-system,sans-serif;font-size:.74rem;color:var(--muted)">${name}, 2035 vs no-AI</div><div style="font-size:1.7rem;color:${c}">&approx;${end>=1?'+':''}${Math.round((end-1)*100)}%</div></div>`);
  }
  document.getElementById('readout').innerHTML=cards.join('');
}
const slider=document.getElementById('slider');
slider.addEventListener('input',()=>draw(+slider.value));
draw(4);"""
    return shell("explore.html", "Build your own 2035",
                 "The simulation's entire spread comes down to one slider. Where do you think it sits?",
                 body, script.replace("__DATA__", json.dumps(data)))


# ------------------------------------------------------------------- dots --

def dots_data() -> dict:
    """Sample the SAME individuals in both worlds.

    With the same seed, the initial cohort is identical across worlds (the
    runs only diverge once AI economics start to differ), so sampling fixed
    indices from the month-0 population shows the same simulated people
    living through both futures. Later entrants differ by world and are
    deliberately excluded — including them under a "same people" caption
    would be false.
    """
    loc, scale, _ = calibrate_adoption()
    raw = {}
    for key, eps in (("red", 1.0), ("blue", 2.0)):
        sim = Simulation(elasticity=eps, months=MONTHS, seed=0,
                         start_anchor=START_ANCHOR, adoption_loc=loc,
                         adoption_scale=scale, track_agents=3)
        sim.run()
        raw[key] = sim.agent_log
    n0 = min(len(raw["red"][0]), len(raw["blue"][0]))
    idx = [round(i * (n0 - 1) / 399) for i in range(400)]
    worlds = {
        key: ["".join(f[i] for i in idx) for f in frames] for key, frames in raw.items()
    }
    print(f"  dots: shared initial cohort {n0}, sampled {len(idx)} identical indices")
    return {"worlds": worlds, "step_months": 3}


def page_dots() -> str:
    data = dots_data()
    body = """
<div style="display:flex;gap:16px;align-items:center;margin-bottom:10px;font-family:-apple-system,sans-serif;font-size:.8rem">
  <button class="ctl on" id="play">&#9654; play</button>
  <input id="scrub" type="range" min="0" max="51" value="0" style="flex:1">
  <span id="datelabel" style="min-width:80px"></span>
</div>
<div style="display:flex;gap:18px;flex-wrap:wrap">
  <div class="panel" style="flex:1;min-width:340px">
    <div style="font-family:-apple-system,sans-serif;font-size:.85rem;margin-bottom:8px">
      <b style="color:#bf4633">Fixed appetite</b> (elasticity 1.0)</div>
    <canvas id="cv_red" width="420" height="460" style="width:100%"></canvas></div>
  <div class="panel" style="flex:1;min-width:340px">
    <div style="font-family:-apple-system,sans-serif;font-size:.85rem;margin-bottom:8px">
      <b style="color:#2e6f9e">Growing appetite</b> (elasticity 2.0)</div>
    <canvas id="cv_blue" width="420" height="460" style="width:100%"></canvas></div>
</div>
<div style="font-family:-apple-system,sans-serif;font-size:.78rem;color:var(--muted);margin-top:8px">
  &#9679; junior &nbsp;&#9679; mid &nbsp;&#9679; senior &nbsp;(darker = more senior)
  &nbsp;&#9675; looking for work &nbsp;&middot; left the profession</div>
<p class="note">Each dot is one simulated designer, and dot positions correspond:
the dot at row 3, column 7 on the left is the <i>same individual</i> as row 3,
column 7 on the right — 400 people sampled with identical indices from the
month-0 population, which is identical across both worlds (same random seed;
the runs only diverge as AI economics kick in). New graduates who enter later
differ by world and are not shown — their story is the pipeline charts. In both
worlds people get benched and rehired (churn is normal); what differs is where
the same careers end up, and that depends on the appetite assumption, not the
AI.</p>"""
    script = """
const D=__DATA__;
const COLORS={'1':'#8fb8d9','2':'#4a86b4','3':'#1d5380'};
const start=2023;
function drawWorld(key,frame){
  const cv=document.getElementById('cv_'+key),ctx=cv.getContext('2d');
  ctx.clearRect(0,0,cv.width,cv.height);
  const s=D.worlds[key][frame];
  const cols=20,cell=cv.width/cols;
  for(let i=0;i<s.length;i++){
    const x=(i%cols)*cell+cell/2, y=Math.floor(i/cols)*cell+cell/2, st=s[i];
    ctx.beginPath();
    if(st==='5'){ctx.fillStyle='#d8d2c6';ctx.arc(x,y,2,0,7);ctx.fill();}
    else if(st==='4'){ctx.strokeStyle='#7a7065';ctx.lineWidth=1.4;ctx.arc(x,y,cell*0.3,0,7);ctx.stroke();}
    else{ctx.fillStyle=COLORS[st]||'#999';ctx.arc(x,y,cell*0.33,0,7);ctx.fill();}
  }
}
let frame=0,playing=true;
const nFrames=D.worlds.red.length;
document.getElementById('scrub').max=nFrames-1;
function show(f){
  frame=f;
  drawWorld('red',f);drawWorld('blue',f);
  const m=f*D.step_months, yr=start+Math.floor(m/12), mo=m%12+1;
  document.getElementById('datelabel').textContent=yr+'-'+String(mo).padStart(2,'0');
  document.getElementById('scrub').value=f;
}
setInterval(()=>{if(playing){show((frame+1)%nFrames);}},380);
document.getElementById('scrub').addEventListener('input',e=>{playing=false;document.getElementById('play').classList.remove('on');show(+e.target.value);});
document.getElementById('play').addEventListener('click',e=>{playing=!playing;e.target.classList.toggle('on',playing);});
show(0);"""
    return shell("dots.html", "Designers as dots",
                 "The model isn't an equation — it's thousands of individual careers. Here are 400 of them, twice.",
                 body, script.replace("__DATA__", json.dumps(data)))


# ------------------------------------------------------------------ flows --

def flows_data() -> dict:
    loc, scale, _ = calibrate_adoption()
    cats = build_categories()
    years = {}
    rng_starts = np.random.default_rng(0).logistic(loc=loc, scale=scale, size=4000)
    for year in (2026, 2030, 2035):
        anchor = (year - 2026.5) * 12
        adoption = float(np.mean(np.clip((anchor - rng_starts) / 12.0, 0, 1)))
        flows = []
        for c in cats:
            junior_share = CATEGORY_STRUCTURE[c.name][3]
            auto = c.capability(anchor) * adoption
            human = c.workload_share * (1 - auto)
            flows.append({
                "cat": c.name.replace("_", " "),
                "ai": round(c.workload_share * auto, 4),
                "junior": round(human * junior_share, 4),
                "mid": round(human * (1 - junior_share) * MID_SHARE_OF_NON_JUNIOR, 4),
                "senior": round(human * (1 - junior_share) * (1 - MID_SHARE_OF_NON_JUNIOR), 4),
            })
        years[str(year)] = flows
    return {"years": years}


def page_flows() -> str:
    data = flows_data()
    body = """
<div style="margin-bottom:10px" id="yearbtns">
  <button class="ctl on" data-y="2026">2026</button>
  <button class="ctl" data-y="2030">2030</button>
  <button class="ctl" data-y="2035">2035</button>
</div>
<div class="panel"><svg id="sankey" viewBox="0 0 900 480" style="width:100%"></svg></div>
<p class="note">Shares of design work demanded, flowing from the five kinds of
design work (left) to who performs them (right), using the model's task
arithmetic: AEI-anchored capability per category &times; the BTOS-calibrated
adoption curve. Widths are shares of total design work — in elastic worlds the
total itself grows, so a shrinking human <i>share</i> can still be growing
human <i>work</i>. Design-to-code automates first; strategy barely moves.
One reconciliation note: AI's sliver looks small in 2026 because this view
spans the <i>whole economy</i>, most of which hasn't adopted yet &mdash; within
adopted firms, AI already performs ~7% of design work (the story's anchor). As
adoption spreads, the two numbers converge.</p>"""
    script = """
const D=__DATA__;
const W=900,H=480,LX=150,RX=W-170,NW=10;
const svg=document.getElementById('sankey');
const NS='http://www.w3.org/2000/svg';
function el(t,a,p){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);(p||svg).appendChild(e);return e;}
const TCOL={junior:'#8fb8d9',mid:'#4a86b4',senior:'#1d5380',ai:'#bf4633'};
const TNAME={junior:'junior designers',mid:'mid-level',senior:'senior',ai:'AI'};
function layout(flows){
  const total=flows.reduce((s,f)=>s+f.ai+f.junior+f.mid+f.senior,0);
  const SC=(H-80)/total, GAP=14;
  let y=30; const left={};
  for(const f of flows){const h=(f.ai+f.junior+f.mid+f.senior)*SC;left[f.cat]={y,h};y+=h+GAP;}
  const tt={junior:0,mid:0,senior:0,ai:0};
  for(const f of flows)for(const k in tt)tt[k]+=f[k];
  let y2=30; const right={};
  for(const k of ['junior','mid','senior','ai']){const h=tt[k]*SC;right[k]={y:y2,h};y2+=h+GAP;}
  return {left,right,SC};
}
function render(year){
  svg.innerHTML='';
  const flows=D.years[year];
  const {left,right,SC}=layout(flows);
  const rOff={junior:0,mid:0,senior:0,ai:0};
  for(const f of flows){
    let lOff=0;
    for(const k of ['ai','junior','mid','senior']){
      const v=f[k]; if(v<=0.0005)continue;
      const h=v*SC, y1=left[f.cat].y+lOff, y2=right[k].y+rOff[k];
      const mx=(LX+RX)/2;
      el('path',{d:`M${LX+NW},${y1} C${mx},${y1} ${mx},${y2} ${RX},${y2} L${RX},${y2+h} C${mx},${y2+h} ${mx},${y1+h} ${LX+NW},${y1+h} Z`,
        fill:TCOL[k],opacity:0.45});
      lOff+=h; rOff[k]+=h;
    }
  }
  for(const f of flows){const n=left[f.cat];
    el('rect',{x:LX,y:n.y,width:NW,height:n.h,fill:'#211d18'});
    const t=el('text',{x:LX-8,y:n.y+n.h/2+4,'text-anchor':'end',class:'chartlabel',fill:'#211d18'});
    t.textContent=f.cat;}
  for(const k of ['junior','mid','senior','ai']){const n=right[k];
    if(n.h<1)continue;
    el('rect',{x:RX,y:n.y,width:NW,height:n.h,fill:TCOL[k]});
    const t=el('text',{x:RX+NW+8,y:n.y+n.h/2+4,class:'chartlabel',fill:'#211d18'});
    t.textContent=TNAME[k]+' '+Math.round(n.h/SC*100)+'%';}
}
document.getElementById('yearbtns').addEventListener('click',e=>{
  if(!e.target.dataset.y)return;
  document.querySelectorAll('#yearbtns .ctl').forEach(b=>b.classList.remove('on'));
  e.target.classList.add('on');render(e.target.dataset.y);});
render('2026');"""
    return shell("flows.html", "Where the work goes",
                 "Design work, flowing from what it is to who does it — the model's core arithmetic, made visible.",
                 body, script.replace("__DATA__", json.dumps(data)))


# ---------------------------------------------------------------- futures --

def page_futures() -> str:
    df = pd.read_csv(RESULTS / "scenarios.csv")
    sm = lambda s: s.rolling(5, center=True, min_periods=1).mean()
    runs = []
    for (scn, eps, seed), g in df.groupby(["scenario", "elasticity", "seed"]):
        g = g.sort_values("month")
        runs.append({
            "label": f"{scn} capability, elasticity {eps}",
            "eps": eps,
            "values": [round(v, 4) for v in sm(g["employed_junior_vs_cf"])],
        })
    data = {"runs": runs}
    body = """
<div style="display:flex;gap:14px;align-items:center;margin-bottom:10px;font-family:-apple-system,sans-serif;font-size:.85rem">
  <button class="ctl on" id="play">&#9654; play</button>
  <span id="runlabel" style="color:var(--muted)"></span>
</div>
<div class="panel"><svg id="chart" viewBox="0 0 900 420" style="width:100%"></svg></div>
<p class="note">Junior design employment vs the no-AI world — shown one
simulated future at a time instead of as a band, because bands get read as
"the forecast plus noise" when the truth is closer to "here are distinct
worlds we can't yet choose between." Earlier futures linger as ghosts. One
honesty note: these 27 are <i>combinations from our assumption grid</i>, not
random draws from a forecast — they are equally spaced, not equally likely.
The red-tinted runs are inelastic worlds, blue-tinted elastic; notice the
color, not the wiggle, is what separates them.</p>"""
    script = """
const D=__DATA__;
const W=900,H=420,M={l:50,t:20,r:30,b:34};
const svg=document.getElementById('chart');
const NS='http://www.w3.org/2000/svg';
function el(t,a,p){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);(p||svg).appendChild(e);return e;}
const N=D.runs[0].values.length;
const X=i=>M.l+i/(N-1)*(W-M.l-M.r);
const Y=v=>M.t+(1-(v-0.4)/(1.8-0.4))*(H-M.t-M.b);
for(const tv of [0.6,1.0,1.4,1.8]){
  el('line',{x1:M.l,x2:W-M.r,y1:Y(tv),y2:Y(tv),stroke:'#c9c0b2','stroke-width':tv===1?1.4:0.6,'stroke-dasharray':tv===1?'5 4':''});
  const t=el('text',{x:M.l-8,y:Y(tv)+4,'text-anchor':'end',class:'chartlabel'});t.textContent=tv.toFixed(1)+'x';}
for(let yr=2024;yr<=2035;yr+=2){
  const t=el('text',{x:X((yr-2023)*12+6),y:H-M.b+16,'text-anchor':'middle',class:'chartlabel'});t.textContent=yr;}
const gGhost=el('g'); const live=el('path',{fill:'none','stroke-width':2.8});
const ECOL={'1':'#bf4633','1.5':'#b08a3e','2':'#2e6f9e'};
function pathOf(vals){let d='';for(let i=0;i<N;i++)d+=(i?'L':'M')+X(i).toFixed(1)+','+Y(vals[i]).toFixed(1);return d;}
let order=[...D.runs.keys()].sort(()=>Math.random()-0.5), pos=0, playing=true;
function step(){
  const run=D.runs[order[pos]];
  const col=ECOL[String(run.eps)]||'#7a7065';
  el('path',{d:live.getAttribute('d')||'',fill:'none',stroke:live.getAttribute('stroke')||col,'stroke-width':1,opacity:0.18},gGhost);
  if(gGhost.children.length>40)gGhost.removeChild(gGhost.firstChild);
  live.setAttribute('d',pathOf(run.values));
  live.setAttribute('stroke',col);
  document.getElementById('runlabel').textContent='future '+(pos+1)+' of '+D.runs.length+' — '+run.label;
  pos=(pos+1)%order.length;
}
setInterval(()=>{if(playing)step();},900);
document.getElementById('play').addEventListener('click',e=>{playing=!playing;e.target.classList.toggle('on',playing);});
step();"""
    return shell("futures.html", "27 futures",
                 "Not a forecast with error bars — 27 distinct worlds, visited one at a time.",
                 body, script.replace("__DATA__", json.dumps(data)))


# ---------------------------------------------------------------- terrain --

TERRAIN_ANCHORS = [0.08, 0.15, 0.25, 0.35, 0.45]
TERRAIN_SEEDS = [0, 1]


def terrain_grid() -> pd.DataFrame:
    """Outcome grid over (capability anchor x elasticity): 90 runs, cached."""
    cache = RESULTS / "terrain_grid.csv"
    if cache.exists():
        return pd.read_csv(cache)
    loc, scale, _ = calibrate_adoption()
    no_ai = {
        seed: Simulation(elasticity=1.5, months=MONTHS, seed=seed,
                         start_anchor=START_ANCHOR, adoption_loc=loc,
                         adoption_scale=scale, ai_scale=0.0).run()
        for seed in TERRAIN_SEEDS
    }
    rows = []
    for a in TERRAIN_ANCHORS:
        cats = build_categories(anchor_max=a)
        for eps in EXPLORE_EPS:
            for seed in TERRAIN_SEEDS:
                df = Simulation(
                    elasticity=eps, months=MONTHS, seed=seed,
                    start_anchor=START_ANCHOR, adoption_loc=loc,
                    adoption_scale=scale, categories=cats,
                ).run()
                base = no_ai[seed]
                sub = df[df["month"] % 6 == 0]
                for _, r in sub.iterrows():
                    m = int(r["month"])
                    rows.append({
                        "anchor": a, "eps": eps, "seed": seed, "month": m,
                        "junior": r["employed_junior"] / base["employed_junior"].iloc[m],
                        "total": r["employed_total"] / base["employed_total"].iloc[m],
                    })
            print(f"  terrain grid: anchor={a} eps={eps}")
    out = pd.DataFrame(rows)
    out.to_csv(cache, index=False)
    return out


def page_terrain() -> str:
    grid = terrain_grid()
    months = [int(m) for m in sorted(grid["month"].unique())]
    data = {"eps": EXPLORE_EPS, "anchors": TERRAIN_ANCHORS, "months": months, "metrics": {}}
    for key in ("junior", "total"):
        g = grid.groupby(["anchor", "eps", "month"])[key].median().reset_index()
        g[key] = g.groupby(["anchor", "eps"])[key].transform(
            lambda s: s.rolling(3, center=True, min_periods=1).mean()
        )
        lookup = {
            (r["anchor"], r["eps"], r["month"]): float(round(r[key], 3))
            for _, r in g.iterrows()
        }
        data["metrics"][key] = [
            [[lookup[(a, e, m)] for e in EXPLORE_EPS] for a in TERRAIN_ANCHORS]
            for m in months
        ]
    body = """
<div style="display:flex;gap:14px;align-items:center;margin-bottom:10px;font-family:-apple-system,sans-serif;font-size:.85rem;flex-wrap:wrap">
  <span id="metricbtns">
    <button class="ctl on" data-m="junior">junior designers</button>
    <button class="ctl" data-m="total">all designers</button></span>
  <button class="ctl" id="play">&#9654; play</button>
  <input id="scrub" type="range" min="0" max="25" value="25" style="flex:1;min-width:160px">
  <span id="datelabel" style="min-width:60px;color:var(--muted)"></span>
</div>
<div class="panel" style="cursor:grab">
  <svg id="terrain" viewBox="0 0 900 520" style="width:100%"></svg></div>
<p class="note">Every vertex is the median of real simulation runs at that
(appetite, capability) pair, measured against paired no-AI worlds. The flat
translucent sheet is the no-AI world (1.0x). <b>Drag to rotate</b>, and notice
the shape of the claim this whole project makes: the terrain is a cliff along
the <i>appetite</i> axis and nearly flat along the <i>AI capability</i> axis.
Press play to watch the cliff grow out of flat ground — in 2026 the terrain
barely exists. Two honesty notes: the vertices span the assumption grid we
chose to run (they are not probabilities — a wider grid would draw wider
terrain), and all of it is one model structure: a different model would draw
different terrain. For reading precise values, the slider page is the better
tool; this page communicates shape. A model is a map of assumption space, not
a forecast; this is the map.</p>"""
    script = """
const D=__DATA__;
const svg=document.getElementById('terrain');
const W=900,H=520,CX=W/2,CY=H/2+30,SC=290,ZS=170;
const NE=D.eps.length,NA=D.anchors.length;
let theta=-0.65, frame=D.months.length-1, metric='junior', playing=false;
function val(f,ia,ie){return D.metrics[metric][f][ia][ie];}
function project(ix,iy,z){
  const x=(ix/(NE-1)-0.5)*2.0, y=(iy/(NA-1)-0.5)*1.1;
  const xr=x*Math.cos(theta)-y*Math.sin(theta), yr=x*Math.sin(theta)+y*Math.cos(theta);
  return [CX+xr*SC, CY+yr*SC*0.42-(z-1)*ZS, yr];
}
function color(v){
  if(v>=1){const t=Math.min((v-1)/0.7,1);return `rgb(${Math.round(190-144*t)},${Math.round(185-74*t)},${Math.round(178-20*t)})`;}
  const t=Math.min((1-v)/0.45,1);
  return `rgb(${Math.round(190+1*t)},${Math.round(185-115*t)},${Math.round(178-127*t)})`;
}
function render(){
  let out='';
  // reference plane z=1
  const rp=[project(0,0,1),project(NE-1,0,1),project(NE-1,NA-1,1),project(0,NA-1,1)];
  out+=`<polygon points="${rp.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ')}" fill="rgba(33,29,24,0.07)" stroke="#c9c0b2" stroke-dasharray="4 3"/>`;
  // surface quads, painter's order
  const quads=[];
  for(let ia=0;ia<NA-1;ia++)for(let ie=0;ie<NE-1;ie++){
    const c=[[ie,ia],[ie+1,ia],[ie+1,ia+1],[ie,ia+1]];
    const pts=c.map(([e,a])=>project(e,a,val(frame,a,e)));
    const depth=pts.reduce((s,p)=>s+p[2],0)/4;
    const v=(val(frame,ia,ie)+val(frame,ia,ie+1)+val(frame,ia+1,ie)+val(frame,ia+1,ie+1))/4;
    quads.push({depth,pts,v});
  }
  quads.sort((q1,q2)=>q1.depth-q2.depth);
  for(const q of quads)
    out+=`<polygon points="${q.pts.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ')}" fill="${color(q.v)}" stroke="#faf7f0" stroke-width="0.8" fill-opacity="0.92"/>`;
  // axis labels at projected edge midpoints (pushed outward)
  const ax=project((NE-1)/2,-0.7,1), ay=project(-1.1,(NA-1)/2,1);
  out+=`<text x="${ax[0]}" y="${ax[1]+18}" text-anchor="middle" class="chartlabel">appetite for design &rarr; (elasticity ${D.eps[0]} &ndash; ${D.eps[NE-1]})</text>`;
  out+=`<text x="${ay[0]}" y="${ay[1]}" text-anchor="middle" class="chartlabel">AI capability &rarr;</text>`;
  // corner value tags — all four, so magnitudes are readable despite 3D
  const tags=[[0,0],[NE-1,0],[0,NA-1],[NE-1,NA-1]];
  for(const [e,a] of tags){const v=val(frame,a,e);const p=project(e,a,v);
    out+=`<text x="${p[0]+6}" y="${p[1]-8}" class="chartlabel" style="font-weight:600" fill="${v>=1?'#2e6f9e':'#bf4633'}">${v.toFixed(2)}x</text>`;}
  // fixed color legend (does not rotate)
  out+='<defs><linearGradient id="lg" x1="0" x2="1"><stop offset="0" stop-color="'+color(0.55)+'"/><stop offset="0.5" stop-color="'+color(1)+'"/><stop offset="1" stop-color="'+color(1.7)+'"/></linearGradient></defs>';
  out+=`<rect x="${W-180}" y="14" width="120" height="10" fill="url(#lg)"/>`;
  out+=`<text x="${W-180}" y="38" class="chartlabel">0.55x</text>`;
  out+=`<text x="${W-124}" y="38" class="chartlabel">1.0x</text>`;
  out+=`<text x="${W-72}" y="38" class="chartlabel">1.7x</text>`;
  svg.innerHTML=out;
  const m=D.months[frame], yr=2023+Math.floor(m/12), mo=m%12+1;
  document.getElementById('datelabel').textContent=yr+'-'+String(mo).padStart(2,'0');
  document.getElementById('scrub').value=frame;
}
document.getElementById('scrub').max=D.months.length-1;
let dragging=false,lastX=0;
svg.addEventListener('pointerdown',e=>{dragging=true;lastX=e.clientX;});
window.addEventListener('pointermove',e=>{if(dragging){theta+=(e.clientX-lastX)*0.006;lastX=e.clientX;render();}});
window.addEventListener('pointerup',()=>dragging=false);
document.getElementById('scrub').addEventListener('input',e=>{playing=false;document.getElementById('play').classList.remove('on');frame=+e.target.value;render();});
document.getElementById('play').addEventListener('click',e=>{playing=!playing;e.target.classList.toggle('on',playing);if(playing&&frame>=D.months.length-1)frame=0;});
setInterval(()=>{if(playing){frame=Math.min(frame+1,D.months.length-1);render();if(frame>=D.months.length-1){playing=false;document.getElementById('play').classList.remove('on');}}},350);
document.getElementById('metricbtns').addEventListener('click',e=>{
  if(!e.target.dataset.m)return;metric=e.target.dataset.m;
  document.querySelectorAll('#metricbtns .ctl').forEach(b=>b.classList.toggle('on',b===e.target));render();});
render();"""
    return shell("terrain.html", "The terrain of futures",
                 "The headline finding is a geometric claim — so here it is as geometry. Drag to rotate.",
                 body, script.replace("__DATA__", json.dumps(data)))


# ------------------------------------------------------------- categories --

def page_categories() -> str:
    slow = build_categories(anchor_max=0.12, steepness_scale=0.75)
    base = build_categories()
    fast = build_categories(anchor_max=0.45, steepness_scale=1.3)
    months = list(range(-42, 115, 2))  # 2023 .. 2036 in anchor time
    panels = []
    for i, c in enumerate(base):
        name = c.name.replace("_", " ")
        share, _, _, junior_share = CATEGORY_STRUCTURE[c.name]
        W, H = 300, 170
        Xc = lambda m: 10 + (m + 42) / 156 * (W - 20)
        Yc = lambda v: 12 + (1 - v) * (H - 40)
        def path(cat):
            return "".join(
                ("L" if j else "M") + f"{Xc(m):.1f},{Yc(cat.capability(m)):.1f}"
                for j, m in enumerate(months)
            )
        svg = (
            f'<svg viewBox="0 0 {W} {H}" style="width:100%">'
            f'<line x1="{Xc(0)}" x2="{Xc(0)}" y1="10" y2="{H-26}" stroke="{RULE}"/>'
            f'<text x="{Xc(0)+3}" y="20" class="chartlabel" font-size="9">today</text>'
            f'<path d="{path(slow[i])}" fill="none" stroke="#9ec5af" stroke-width="1.6"/>'
            f'<path d="{path(fast[i])}" fill="none" stroke="#2f7561" stroke-width="1.6" stroke-dasharray="4 3"/>'
            f'<path d="{path(base[i])}" fill="none" stroke="{INK}" stroke-width="2.4"/>'
            f'<text x="10" y="{H-8}" class="chartlabel">2023</text>'
            f'<text x="{W-38}" y="{H-8}" class="chartlabel">2036</text>'
            f'<text x="{W-10}" y="20" text-anchor="end" class="chartlabel">ceiling {c.ceiling:.0%}</text>'
            f"</svg>"
        )
        panels.append(
            f'<div class="panel" style="flex:1;min-width:280px;max-width:330px">'
            f'<div style="font-family:-apple-system,sans-serif;font-size:.88rem"><b>{name}</b></div>'
            f'<div style="font-family:-apple-system,sans-serif;font-size:.72rem;color:{MUTED};margin-bottom:6px">'
            f"{share:.0%} of design work &middot; {junior_share:.0%} of its human side suits juniors</div>"
            f"{svg}</div>"
        )
    body = (
        '<div style="display:flex;gap:14px;flex-wrap:wrap">' + "".join(panels) + "</div>"
        '<div style="font-family:-apple-system,sans-serif;font-size:.78rem;color:var(--muted);margin-top:8px">'
        "&mdash; base scenario &nbsp;&nbsp;&#8213; light: slow scenario &nbsp;&nbsp;&#8211;&#8211; dashed: fast scenario. "
        "Y axis: share of that work AI can perform in firms that have adopted it.</div>"
        '<p class="note">Find your own work here. The curves\' <i>relative</i> heights come from '
        "data — official O*NET task statements for design occupations joined to measured AI "
        "usage (Anthropic Economic Index) — and the model never treats \"AI capability\" as one "
        "number. Design-to-code is far ahead; visual production is undercounted (the usage data "
        "observes a text-first assistant); strategy and judgment work barely registers and is "
        "capped lowest. The absolute level is the scenario assumption the other pages vary.</p>"
    )
    return shell("categories.html", "Five kinds of design work",
                 "“AI capability” is five different curves, not one — and which curve your work sits on is most of your personal exposure.",
                 body)


# ---------------------------------------------------------------- signals --

def _sparkline(values: list[float], color: str = INK, w: int = 220, h: int = 44) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    pts = "".join(
        ("L" if i else "M")
        + f"{4 + i / (len(values) - 1) * (w - 8):.1f},{h - 6 - (v - lo) / rng * (h - 12):.1f}"
        for i, v in enumerate(values)
    )
    return (f'<svg viewBox="0 0 {w} {h}" style="width:{w}px;height:{h}px">'
            f'<path d="{pts}" fill="none" stroke="{color}" stroke-width="1.8"/></svg>')


def page_signals() -> str:
    cards = []

    def card(title, spark_vals, color, reading, lean, lean_color, caveat, span):
        cards.append(
            f'<div class="panel" style="width:330px">'
            f'<div style="font-family:-apple-system,sans-serif;font-size:.82rem"><b>{title}</b></div>'
            f"{_sparkline(spark_vals, color)}"
            f'<div style="font-family:-apple-system,sans-serif;font-size:.66rem;color:{MUTED}">{span}</div>'
            f'<div style="font-size:1.25rem">{reading} '
            f'<span style="font-family:-apple-system,sans-serif;font-size:.72rem;background:{lean_color};color:#fff;'
            f'padding:2px 8px;border-radius:9px;vertical-align:middle">{lean}</span></div>'
            f'<div style="font-family:-apple-system,sans-serif;font-size:.72rem;color:{MUTED};margin-top:4px">{caveat}</div></div>'
        )

    try:
        ev = targets.design_demand_evidence()
        latest, year_ago = ev.iloc[-1], ev.iloc[-13 if len(ev) > 13 else 0]
        rising = latest["elasticity_evidence_ratio"] > year_ago["elasticity_evidence_ratio"] * 1.02
        # 6-mo display smoothing, matched to the story's evidence scene so the
        # headline reading agrees across pages
        smoothed = ev["elasticity_evidence_ratio"].rolling(6, center=True, min_periods=1).mean()
        card("Designed output ÷ design hiring",
             [round(v, 3) for v in smoothed][-48:], INK,
             f"{smoothed.iloc[-1]:.2f}",
             "leans blue" if rising else "leans red", BLUE if rising else RED,
             f"2023 = 1.0, 6-mo smoothed; as of {latest['month']}. Rising = world ships more design per designer hired.",
             "window: last 4 years")
    except FileNotFoundError:
        pass
    try:
        bf = targets.tech_firm_formation()
        info = bf[bf["series"] == "information_sector_applications"]
        vals = [round(v) for v in info["value"].rolling(6, min_periods=3).mean().dropna()]
        recent = info[info["date"] >= info["date"].max() - pd.DateOffset(months=12)]["value"].mean()
        plateau = info[info["date"].dt.year.isin([2022, 2023, 2024])]["value"].mean()
        up = recent > plateau * 1.05
        card("New tech companies / month (Census BFS)", vals[-48:], "#7a5b8e",
             f"{recent:,.0f}", "leans blue" if up else "neutral", BLUE if up else MUTED,
             f"Trailing year vs 2022-24 plateau: {recent / plateau - 1:+.0%}. Filings, not employer firms.",
             "window: last 4 years")
    except FileNotFoundError:
        pass
    try:
        lo = targets.tech_layoffs_monthly()
        vals = [round(v / 1000, 1) for v in lo["laid_off"].iloc[:-1]]
        last12 = sum(vals[-12:])
        card("Tech layoffs, thousands / month (layoffs.fyi)", vals[-48:], RED,
             f"{vals[-1]:.0f}k", "ambiguous", MUTED,
             f"~{last12:.0f}k in the trailing year. Peak was Jan 2023 — before design-capable AI. "
             "Counts can't separate AI cuts from everything else.",
             "window: last 4 years")
    except FileNotFoundError:
        pass
    try:
        mgmt = targets.management_postings()
        mm = mgmt.groupby(mgmt["date"].dt.to_period("M"))["postings_index"].mean()
        mvals = [round(v, 1) for v in mm]
        myoy = mvals[-1] / mvals[-13] - 1 if len(mvals) > 13 else 0
        card("Management postings (Indeed, all management)", mvals[-48:], RED,
             f"{mvals[-1]:.0f}", "compression" if myoy < -0.03 else "neutral",
             RED if myoy < -0.03 else MUTED,
             f"Index, Feb 2020 = 100; {myoy:+.0%} y/y. The middle-management squeeze watch — "
             "all management, not design management specifically.",
             "window: last 4 years")
    except FileNotFoundError:
        pass
    try:
        postings = targets.design_postings_index()
        m = postings.groupby(postings["date"].dt.to_period("M"))["postings_index"].mean()
        vals = [round(v, 1) for v in m]
        yoy = vals[-1] / vals[-13] - 1 if len(vals) > 13 else 0
        card("Design-adjacent job postings (Indeed)", vals[-48:], GREEN,
             f"{vals[-1]:.0f}", "leans red" if yoy < -0.03 else "neutral", RED if yoy < -0.03 else MUTED,
             f"Index, Feb 2020 = 100; {yoy:+.0%} y/y. Demand for design *labor*, not design output.",
             "window: last 4 years")
    except FileNotFoundError:
        pass
    try:
        btos = targets.btos_ai_adoption()
        s = btos.groupby("date")["share"].mean()
        card("Firms using AI (Census BTOS)", [round(v, 3) for v in s], BLUE,
             f"{s.iloc[-1]:.0%}", "context", MUTED,
             "National, all sectors; Information sector runs ~2x this. Feeds the adoption curve.",
             "window: since late 2025 (all available)")
    except (FileNotFoundError, ValueError):
        pass
    try:
        snaps = pd.read_parquet("data/processed/ai_prices_snapshots.parquet")
        n_dates = snaps["snapshot_date"].nunique()
        cheap = snaps[snaps["snapshot_date"] == snaps["snapshot_date"].max()]["completion_per_token"]
        med = cheap[cheap > 0].median() * 1e6
        card("AI price per million output tokens (median model)", [], MUTED,
             f"${med:,.2f}", "accumulating", MUTED,
             f"{n_dates} snapshot(s) so far — this series grows with every data refresh. "
             "Token prices at fixed capability fell ~280x in 18 months (Stanford AI Index).",
             "window: accumulating from June 2026")
    except FileNotFoundError:
        pass

    body = (
        f'<div style="font-family:-apple-system,sans-serif;font-size:.78rem;color:{MUTED};margin-bottom:14px">'
        f"Built {dt.date.today():%B %d, %Y} — every card recomputes from fresh data on rebuild.</div>"
        '<div style="display:flex;gap:14px;flex-wrap:wrap">' + "".join(cards) + "</div>"
        '<p class="note">The simulation says demand elasticity decides designers\' future; '
        "these are the measured series that will reveal it. Lean chips use simple disclosed thresholds (ratio: ±2% over the trailing year; formation: +5% vs the 2022-24 plateau; postings: −3% y/y) — summaries, not statistical tests. No single card proves anything — "
        "the blue world announces itself as a pattern: output-per-hire rising, formation surging, "
        "postings stabilizing. The red world is the same cards with the signs flipped.</p>"
    )
    return shell("signals.html", "Which world are we in?",
                 "The model can't tell you. These live signals eventually will.", body)


# ------------------------------------------------------------------- main --

def page_story() -> str:
    html = story.render()
    html = html.replace("<body>", "<body>" + nav_html("index.html"))
    html = html.replace(
        "</style>",
        SHELL_CSS.replace("main.page", "main.unused_page") + """
  header, .hint, .scrolly, footer { margin-left: 230px; }
  @media (max-width: 880px) { header, .hint, .scrolly, footer { margin-left: 0; } }
</style>""".replace("</style>", "") + "</style>",
    )
    return html


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    pages = {
        "index.html": page_story,
        "explore.html": page_explore,
        "dots.html": page_dots,
        "flows.html": page_flows,
        "futures.html": page_futures,
        "terrain.html": page_terrain,
        "categories.html": page_categories,
        "signals.html": page_signals,
    }
    for name, builder in pages.items():
        print(f"building {name}...")
        (DOCS / name).write_text(builder())
        print(f"  wrote docs/{name} ({(DOCS / name).stat().st_size / 1024:.0f} KB)")
    # keep the standalone story copy in sync
    Path("writeup/story").mkdir(parents=True, exist_ok=True)
    Path("writeup/story/index.html").write_text(story.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
