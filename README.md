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
idiosyncratic demand churn, per-category AI capability curves,
vacancy-gated promotions, market-tightness wage bargaining, and a talent
pipeline that responds to prospects. Stubbed: AI fluency, skill atrophy,
specialty. Every run is scored against a paired no-AI counterfactual
(same seed, `ai_scale=0`) — an early version without this comparison
produced a spurious "junior collapse at every elasticity" from a
non-stationary baseline; the counterfactual is what caught it.

Fitted result (June 2026, `des-sim-backcast`): with adoption calibrated to
BTOS and (ε, capability timing) fitted on the 2023-26 design-vs-aggregate
postings ratio, best fit is ε≈1.5. Projection: junior employment dips
2027-2030 while production work automates, then demand expansion re-absorbs
juniors; total employment +28% vs no-AI by 2035; senior wage premium rises.
Caveats: the fit surface is flat (the data so far only weakly identifies ε),
and the model *under*-predicts the observed design-postings decline to date.
See `results/`.

## Sources

| Source | Cadence | Feeds which model piece |
|---|---|---|
| `hiring_lab` | weekly / monthly | Labor demand + matching: Indeed postings indices (aggregate, by sector) and share of postings mentioning AI ([github.com/hiring-lab](https://github.com/hiring-lab), CC-BY-4.0 — cite Hiring Lab) |
| `btos` | biweekly | Firm AI-adoption S-curve: Census BTOS AI use by sector and firm size (raw Excel; layout varies per release) |
| `oews` | annual (spring) | Ground truth for headcount and wage distributions: BLS OEWS for design SOC codes + software developers as comparison |
| `aei` | ~quarterly | Task routing + automatability: Anthropic Economic Index task-level usage, automation vs augmentation ([HuggingFace](https://huggingface.co/datasets/Anthropic/EconomicIndex), CC-BY) |
| `layoffs_fyi` | manual export | Discrete shock events: drop the layoffs.fyi Airtable CSV at `data/manual/layoffs_fyi.csv` |
| `levels_fyi` | continuous | Wage-by-seniority calibration: stub until [API access](https://www.levels.fyi/api-access/) is granted (`LEVELS_FYI_API_KEY`) |

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
