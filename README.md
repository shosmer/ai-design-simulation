# des-sim

Simulation of AI's impact on designers in the tech industry: an agent-based
model (designers, firms, AI capability, tasks, talent pipeline) on a
discrete-event backbone. This repo currently contains the **data ingestion
layer** that keeps the model's calibration targets fresh.

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```sh
des-sim-ingest list                  # show sources and cadence
des-sim-ingest pull                  # pull everything
des-sim-ingest pull hiring_lab btos  # pull specific sources
```

Raw artifacts land in `data/raw/<source>/<date>/`, tidied tables in
`data/processed/<source>_<table>.parquet`, and `data/manifest.json` records
what was pulled when.

## Model

```sh
python -m des_sim.targets   # print calibration targets from the latest data
des-sim-run                 # run the demand-elasticity sweep -> results/
```

```sh
des-sim-backcast            # calibrate to BTOS, fit on 2023-26, project to 2035
```

`src/des_sim/model/engine.py` is the vertical slice: designers
(junior/mid/senior), firms with task routing, demand response, and
idiosyncratic demand churn, firm entry/exit (entry accelerates as design
output gets cheaper — the extensive margin visible in Census BFS), declining
AI cost per task (24-month half-life toward an orchestration floor),
per-category AI capability curves, vacancy-gated promotions,
market-tightness wage bargaining, and a talent pipeline that responds to
prospects. Stubbed: AI fluency, skill atrophy, specialty. Every run is scored against a paired no-AI counterfactual
(same seed, `ai_scale=0`) — an early version without this comparison
produced a spurious "junior collapse at every elasticity" from a
non-stationary baseline; the counterfactual is what caught it.

```sh
des-sim-scenarios           # slow/base/fast x elasticity x seeds -> fan charts
des-sim-story               # animated scrollytelling page -> writeup/story/
```

Capability curves are anchored to data: O*NET design-occupation task
statements joined to AEI task-level usage and automation modes set each
category's *relative* AI maturity (design-to-code far ahead; production
second), and scenarios vary the *absolute* level (slow/base/fast; base =
AI performs ~7% of design work in adopted tech firms, mid-2026). Known
bias: AEI observes Claude only, so visual-production automation in image
tools is undercounted — production is a lower bound.

Headline result (June 2026, `des-sim-scenarios`): **capability timing
barely matters; demand elasticity decides everything.** Across slow/base/
fast scenarios, 2035 outcomes move by a few points — across the credible
elasticity range (1.0-2.0) the junior outcome spans 0.65x to 1.70x the
no-AI counterfactual and total employment 0.90x to 2.34x. With firm entry
in the model, AI leaves the senior-junior pay gap roughly unchanged in the
inelastic world and *narrows* it up to ~45% in the elastic one — the
better-for-jobs world is also the more equal one. The 2023-26 backcast fit
cannot pin ε down (flat fit surface, best-fit point unstable across curve
revisions), so public claims should be ranges, not points. See
`results/scenarios.png`.

## Sources

| Source | Cadence | Feeds which model piece |
|---|---|---|
| `hiring_lab` | weekly / monthly | Labor demand + matching: Indeed postings indices (aggregate, by sector) and share of postings mentioning AI ([github.com/hiring-lab](https://github.com/hiring-lab), CC-BY-4.0 — cite Hiring Lab) |
| `btos` | biweekly | Firm AI-adoption S-curve: Census BTOS AI use by sector and firm size (raw Excel; layout varies per release) |
| `oews` | annual (spring) | Ground truth for headcount and wage distributions: BLS OEWS for design SOC codes + software developers as comparison |
| `aei` | ~quarterly | Task routing + automatability: Anthropic Economic Index task-level usage, automation vs augmentation ([HuggingFace](https://huggingface.co/datasets/Anthropic/EconomicIndex), CC-BY) |
| `layoffs_fyi` | continuous | Layoff events scraped from the Airtable shared view behind layoffs.fyi (signed accessPolicy flow; falls back to a manual CSV at `data/manual/layoffs_fyi.csv` if the scheme changes). ~1/3 of events lack headcounts |
| `levels_fyi` | continuous | Wage-by-seniority calibration: stub until [API access](https://www.levels.fyi/api-access/) is granted (`LEVELS_FYI_API_KEY`) |
| `onet_tasks` | quarterly | Capability anchoring: official O*NET task statements (task text → SOC) joined to AEI usage |
| `design_demand` | annual / monthly | The elasticity question itself: Census SAS design-industry revenue (via FRED) + Google Play app releases (AppBrain). `targets.design_demand_evidence()` computes the output-shipped vs design-hiring ratio — rising = elastic-world evidence |
| `ai_prices` | per pull | Per-token prices for ~300 models (OpenRouter, keyless); snapshots accumulate into a time series that grounds the engine's AI-cost-decline assumption |

Annual reports worth folding in by hand each cycle: Stanford HAI AI Index
(April), UX Tools Design Tools Survey, NN/g State of UX.

## Scheduling

Weekly pull via cron (matches the fastest non-manual cadence worth polling):

```cron
0 7 * * 1 cd /Users/shannonhosmer/Code/des-sim && .venv/bin/des-sim-ingest pull >> data/ingest.log 2>&1
```

On macOS, a `launchd` agent survives sleep/reboot better than cron; or run it
as a scheduled Claude Code routine.

## Layout

```
src/des_sim/
  cli.py            # des-sim-ingest entry point
  ingest/
    base.py         # Source ABC, download helpers, manifest
    hiring_lab.py   # Indeed Hiring Lab CSVs (GitHub)
    btos.py         # Census BTOS Excel scrape
    oews.py         # BLS OEWS national zip, filtered to design SOCs
    aei.py          # Anthropic Economic Index (HuggingFace, latest release)
    layoffs.py      # layoffs.fyi manual CSV
    levels.py       # Levels.fyi API stub
data/
  raw/<source>/<date>/   # immutable downloads (gitignored)
  processed/*.parquet    # tidied tables (gitignored)
  manual/                # hand-dropped exports (layoffs_fyi.csv)
  manifest.json          # what was pulled, when, how many rows
```
