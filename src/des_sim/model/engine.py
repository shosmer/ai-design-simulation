"""Minimal vertical slice of the designer/AI labor-market model.

Monthly time steps (a simplification of the eventual event-driven core).
Included: designers with seniority, firms with task routing and demand
response, per-category AI capability curves, a talent pipeline with lagged
entry, hiring/layoff frictions, promotions, profession exit, and
market-tightness wage bargaining per seniority level.
Deliberately stubbed for the slice: AI fluency, skill atrophy, specialty.

Time has two clocks. Sim time t counts months from the run's start.
"Anchor time" counts months from mid-2026 (where the capability-curve
midpoints and adoption distribution are expressed); a run starting in
Jan 2023 passes start_anchor=-42. capability_shift moves all capability
curves later (+) or earlier (-) and is the main fitted parameter alongside
the demand elasticity. ai_scale=0 turns the model into a no-AI
counterfactual for difference-in-difference comparisons.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

JUNIOR, MID, SENIOR = 0, 1, 2
LEVEL_NAMES = ["junior", "mid", "senior"]
THROUGHPUT = [1.0, 1.6, 2.2]  # task-units/month by level
INITIAL_MONTHLY_WAGE = [70_000 / 12, 110_000 / 12, 150_000 / 12]
# Of human-remaining work not suitable for juniors, the mid/senior split:
MID_SHARE_OF_NON_JUNIOR = 0.55

AI_COST_FACTOR = 0.05  # AI cost per task-unit, vs initial blended human cost

LAYOFF_RATE_CAP = 0.08  # max share of a level's roster cut per month
HIRE_RATE_CAP = 0.15    # max growth of a level's roster per month

# Wage bargaining: wages rise when firms can't fill vacancies and fall when
# unemployment at the level sits above its natural rate, with downward
# stickiness. (Stock-based vacancy/unemployed ratios are misleading here:
# grads are often hired the same month they enter, so the unemployment stock
# undercounts available supply.)
WAGE_VACANCY_SENSITIVITY = 1.0   # per unit of unfilled-vacancies-per-employee
WAGE_UNEMP_SENSITIVITY = 0.05
NATURAL_UNEMPLOYMENT = 0.05      # pipeline entry steers toward this rate
WAGE_SLACK_THRESHOLD = 0.08      # wages only fall above this rate, so the
                                 # pipeline, not wages, absorbs normal slack
WAGE_GROWTH_BOUNDS = (-0.005, 0.012)  # per month

PROMOTION_MONTHS = {JUNIOR: 30, MID: 48}
EXIT_PROB_LONG_UNEMPLOYED = 0.12  # monthly, after 12 months unemployed
RETIRE_PROB_SENIOR = 0.003        # monthly

PIPELINE_LAG = 24      # months between perceived prospects and graduation
PIPELINE_MIN, PIPELINE_MAX = 0.2, 2.0  # entry response bounds vs baseline

# Idiosyncratic firm demand: mean-reverting log shocks, so growing firms hire
# while shrinking firms cut and aggregate hiring flows never freeze entirely
# (stationary cross-section dispersion ~18%).
DEMAND_SHOCK_SIGMA = 0.035
DEMAND_MEAN_REVERSION = 0.98


@dataclass
class TaskCategory:
    """One slice of design work with its own automation trajectory.

    capability(anchor_t) is the share of this category AI can do at anchor
    time (logistic: ceiling / steepness / midpoint, midpoints in months from
    mid-2026). junior_share is the fraction of the *human-remaining* work in
    this category suitable for juniors.
    """

    name: str
    workload_share: float
    ceiling: float
    midpoint: float
    steepness: float
    junior_share: float

    def capability(self, anchor_t: float) -> float:
        return self.ceiling / (1 + math.exp(-self.steepness * (anchor_t - self.midpoint)))


# Stylized but anchored: AEI shows production-style tasks (directive
# automation, 44% of interactions) ahead of judgment work, and the 2025-26
# trade press consistently reports "intern work" automating first.
DEFAULT_CATEGORIES = [
    TaskCategory("production", 0.30, ceiling=0.85, midpoint=18, steepness=0.15, junior_share=0.60),
    TaskCategory("wireframing_ideation", 0.15, ceiling=0.70, midpoint=28, steepness=0.12, junior_share=0.35),
    TaskCategory("prototyping_design_to_code", 0.20, ceiling=0.75, midpoint=34, steepness=0.12, junior_share=0.30),
    TaskCategory("research_synthesis", 0.15, ceiling=0.60, midpoint=44, steepness=0.10, junior_share=0.25),
    TaskCategory("strategy_judgment", 0.20, ceiling=0.25, midpoint=60, steepness=0.08, junior_share=0.05),
]


# eq=False: identity equality, so list.remove() pulls the exact agent rather
# than the first one with matching field values.
@dataclass(eq=False)
class Designer:
    level: int
    employer: int | None
    months_at_level: int = 0
    months_unemployed: int = 0


@dataclass(eq=False)
class Firm:
    base_demand: float       # task-units/month demanded at baseline unit cost
    adoption_start: float    # anchor time when AI task-routing begins
    integration_months: float = 12.0
    demand_mult: float = 1.0
    roster: list[list[Designer]] = field(default_factory=lambda: [[], [], []])

    def adoption(self, anchor_t: float) -> float:
        if anchor_t < self.adoption_start:
            return 0.0
        return min(1.0, (anchor_t - self.adoption_start) / self.integration_months)


class Simulation:
    def __init__(
        self,
        elasticity: float,
        n_firms: int = 150,
        n_designers: int = 4000,
        months: int = 120,
        seed: int = 0,
        categories: list[TaskCategory] | None = None,
        start_anchor: float = 0.0,
        capability_shift: float = 0.0,
        ai_scale: float = 1.0,
        adoption_loc: float = 6.0,
        adoption_scale: float = 10.0,
    ) -> None:
        self.elasticity = elasticity
        self.months = months
        self.start_anchor = start_anchor
        self.capability_shift = capability_shift
        self.ai_scale = ai_scale
        self.rng = np.random.default_rng(seed)
        self.categories = categories or DEFAULT_CATEGORIES

        self.wages = list(INITIAL_MONTHLY_WAGE)
        level_mix = np.array([0.30, 0.40, 0.30])
        self.level_mix = level_mix
        # AI cost is anchored to the *initial* human cost: model-server prices
        # don't rise just because designer wages do.
        self.ai_cost = AI_COST_FACTOR * self._human_cost(level_mix)

        starts = self.rng.logistic(loc=adoption_loc, scale=adoption_scale, size=n_firms)
        sizes = self.rng.lognormal(mean=0, sigma=0.8, size=n_firms)
        sizes /= sizes.sum()

        # Size base demand so the initial workforce is in equilibrium at the
        # run's starting capability and adoption levels.
        mean_adoption_0 = float(
            np.mean([min(1.0, max(0.0, (start_anchor - s) / 12.0)) for s in starts])
        )
        capacity = (level_mix * THROUGHPUT).sum() * n_designers
        human_share_0 = sum(
            c.workload_share * (1 - self._capability(c, 0) * mean_adoption_0)
            for c in self.categories
        )
        total_demand = capacity / human_share_0
        self.p0 = self._unit_cost(mean_adoption_0, 0, level_mix)

        self.firms: list[Firm] = []
        self.designers: list[Designer] = []
        for i in range(n_firms):
            firm = Firm(base_demand=total_demand * sizes[i], adoption_start=float(starts[i]))
            desired = self._desired_headcount(firm, t=0)
            for level, n in enumerate(desired):
                for _ in range(round(n)):
                    d = Designer(
                        level=level,
                        employer=i,
                        months_at_level=int(self.rng.integers(0, PROMOTION_MONTHS.get(level, 60))),
                    )
                    firm.roster[level].append(d)
                    self.designers.append(d)
            self.firms.append(firm)

        # Start the unemployed pool at the natural rate so the first years
        # aren't dominated by a pool-filling transient.
        self.unemployed: list[list[Designer]] = [[], [], []]
        for level in range(3):
            employed_lv = sum(len(f.roster[level]) for f in self.firms)
            for _ in range(round(NATURAL_UNEMPLOYMENT * employed_lv)):
                d = Designer(
                    level=level,
                    employer=None,
                    months_unemployed=int(self.rng.integers(0, 10)),
                )
                self.designers.append(d)
                self.unemployed[level].append(d)
        self.junior_hire_history: list[int] = []
        # Grad inflow sized near steady-state outflow (retirements + a churn
        # buffer); excess accumulates as unemployment until exits balance it.
        initial_juniors = sum(len(f.roster[JUNIOR]) for f in self.firms)
        self.baseline_grads = max(1, round(initial_juniors * 0.012))
        self.records: list[dict] = []

    # ---- core mechanics -------------------------------------------------

    def _capability(self, cat: TaskCategory, t: float) -> float:
        return self.ai_scale * cat.capability(t + self.start_anchor - self.capability_shift)

    def _human_cost(self, mix: np.ndarray) -> float:
        return float((mix * self.wages).sum() / (mix * THROUGHPUT).sum())

    def _employment_mix(self) -> np.ndarray:
        counts = np.array(
            [sum(len(f.roster[lv]) for f in self.firms) for lv in range(3)], dtype=float
        )
        return counts / counts.sum() if counts.sum() > 0 else self.level_mix

    def _unit_cost(self, adoption: float, t: float, mix: np.ndarray) -> float:
        human = self._human_cost(mix)
        cost = 0.0
        for c in self.categories:
            auto = self._capability(c, t) * adoption
            cost += c.workload_share * (auto * self.ai_cost + (1 - auto) * human)
        return cost

    def _desired_headcount(self, firm: Firm, t: float) -> list[float]:
        adoption = firm.adoption(t + self.start_anchor)
        mix = self._employment_mix() if self.firms else self.level_mix
        p = self._unit_cost(adoption, t, mix)
        demand = firm.base_demand * firm.demand_mult * (p / self.p0) ** (-self.elasticity)
        junior_work = mid_work = senior_work = 0.0
        for c in self.categories:
            human = demand * c.workload_share * (1 - self._capability(c, t) * adoption)
            junior_work += human * c.junior_share
            rest = human * (1 - c.junior_share)
            mid_work += rest * MID_SHARE_OF_NON_JUNIOR
            senior_work += rest * (1 - MID_SHARE_OF_NON_JUNIOR)
        return [
            junior_work / THROUGHPUT[JUNIOR],
            mid_work / THROUGHPUT[MID],
            senior_work / THROUGHPUT[SENIOR],
        ]

    def step(self, t: int) -> None:
        junior_hires = 0
        hires = [0, 0, 0]
        fills = [0, 0, 0]  # external hires + internal promotions
        vacancies_posted = [0, 0, 0]
        layoffs = 0

        # New grads enter the unemployed junior pool. Entry responds to junior
        # hiring prospects with a long lag, and to visible junior unemployment
        # without one (nobody enrolls into a market where grads sit idle).
        signal = 1.0
        if len(self.junior_hire_history) > PIPELINE_LAG + 12:
            recent = np.mean(self.junior_hire_history[-PIPELINE_LAG - 12 : -PIPELINE_LAG])
            base = np.mean(self.junior_hire_history[:12])
            if base > 0:
                signal = float(np.clip(recent / base, PIPELINE_MIN, PIPELINE_MAX))
        employed_juniors = sum(len(f.roster[JUNIOR]) for f in self.firms)
        u_junior = len(self.unemployed[JUNIOR]) / max(
            len(self.unemployed[JUNIOR]) + employed_juniors, 1
        )
        market_factor = float(np.clip(NATURAL_UNEMPLOYMENT / max(u_junior, 0.01), 0.3, 1.3))
        grads = round(self.baseline_grads * signal * market_factor)
        for _ in range(grads):
            d = Designer(level=JUNIOR, employer=None)
            self.designers.append(d)
            self.unemployed[JUNIOR].append(d)

        # Idiosyncratic firm demand shocks (mean-reverting in logs).
        for firm in self.firms:
            firm.demand_mult = math.exp(
                DEMAND_MEAN_REVERSION * math.log(firm.demand_mult)
                + self.rng.normal(0, DEMAND_SHOCK_SIGMA)
            )

        # Firms adjust rosters toward desired headcount, with frictions.
        for idx in self.rng.permutation(len(self.firms)):
            firm = self.firms[int(idx)]
            desired = self._desired_headcount(firm, t)
            for level in (SENIOR, MID, JUNIOR):
                current = len(firm.roster[level])
                gap = desired[level] - current
                if gap < -0.5:  # layoffs, capped
                    n_cut = min(round(-gap), max(1, round(LAYOFF_RATE_CAP * current)))
                    for _ in range(n_cut):
                        d = firm.roster[level].pop()
                        d.employer = None
                        d.months_unemployed = 0
                        self.unemployed[level].append(d)
                        layoffs += 1
                elif gap > 0.5:  # fill from the market first, promote for the rest
                    n_fill = min(round(gap), max(1, round(HIRE_RATE_CAP * current) + 1))
                    vacancies_posted[level] += n_fill
                    pool = self.unemployed[level]
                    n_external = min(n_fill, len(pool))
                    for _ in range(n_external):
                        d = pool.pop(int(self.rng.integers(len(pool))))
                        d.employer = int(idx)
                        d.months_unemployed = 0
                        firm.roster[level].append(d)
                        hires[level] += 1
                        fills[level] += 1
                        if level == JUNIOR:
                            junior_hires += 1
                    n_fill -= n_external
                    # Promotions are vacancy-gated: tenure makes you eligible,
                    # but you move up only when a slot opens above you that the
                    # market can't fill. In slack markets promotions freeze —
                    # the career bottleneck this model exists to study.
                    if n_fill > 0 and level > JUNIOR:
                        eligible = [
                            d
                            for d in firm.roster[level - 1]
                            if d.months_at_level >= PROMOTION_MONTHS[level - 1]
                        ]
                        for d in eligible[:n_fill]:
                            firm.roster[level - 1].remove(d)
                            d.level = level
                            d.months_at_level = 0
                            firm.roster[level].append(d)
                            fills[level] += 1

        # Tenure, retirement, unemployment aging, exits.
        exits = 0
        for firm in self.firms:
            for roster in firm.roster:
                for d in roster:
                    d.months_at_level += 1
            retiring = [
                d for d in firm.roster[SENIOR] if self.rng.random() < RETIRE_PROB_SENIOR
            ]
            for d in retiring:
                firm.roster[SENIOR].remove(d)
                self.designers.remove(d)

        for level in (JUNIOR, MID, SENIOR):
            stayers = []
            for d in self.unemployed[level]:
                d.months_unemployed += 1
                if d.months_unemployed >= 12 and self.rng.random() < EXIT_PROB_LONG_UNEMPLOYED:
                    self.designers.remove(d)
                    exits += 1
                else:
                    stayers.append(d)
            self.unemployed[level] = stayers

        # Wage bargaining (see constants above for the logic). Dead zones on
        # both signals keep equilibrium churn from producing secular drift.
        for level in range(3):
            employed_lv = sum(len(f.roster[level]) for f in self.firms)
            unfilled_rate = (vacancies_posted[level] - fills[level]) / max(employed_lv, 1)
            unemp_rate = len(self.unemployed[level]) / max(
                len(self.unemployed[level]) + employed_lv, 1
            )
            tight = max(unfilled_rate - 0.002, 0.0)
            slack = max(unemp_rate - WAGE_SLACK_THRESHOLD, 0.0)
            growth = float(
                np.clip(
                    WAGE_VACANCY_SENSITIVITY * tight - WAGE_UNEMP_SENSITIVITY * slack,
                    *WAGE_GROWTH_BOUNDS,
                )
            )
            self.wages[level] *= 1 + growth

        self.junior_hire_history.append(junior_hires)

        employed = [sum(len(f.roster[lv]) for f in self.firms) for lv in range(3)]
        mean_adoption = float(
            np.mean([f.adoption(t + self.start_anchor) for f in self.firms])
        )
        ai_task_share = sum(
            c.workload_share * self._capability(c, t) * mean_adoption for c in self.categories
        )
        self.records.append(
            {
                "month": t,
                "employed_junior": employed[JUNIOR],
                "employed_mid": employed[MID],
                "employed_senior": employed[SENIOR],
                "employed_total": sum(employed),
                "unemployed": sum(len(p) for p in self.unemployed),
                "junior_hires": junior_hires,
                "hires_total": sum(hires),
                "vacancies_posted": sum(vacancies_posted),
                "grads": grads,
                "layoffs": layoffs,
                "exits": exits,
                "ai_task_share": ai_task_share,
                "adoption": mean_adoption,
                "unit_cost_rel": self._unit_cost(mean_adoption, t, self._employment_mix())
                / self.p0,
                "wage_junior": self.wages[JUNIOR],
                "wage_mid": self.wages[MID],
                "wage_senior": self.wages[SENIOR],
                "senior_premium": self.wages[SENIOR] / self.wages[JUNIOR],
                "elasticity": self.elasticity,
            }
        )

    def run(self) -> pd.DataFrame:
        for t in range(self.months):
            self.step(t)
        df = pd.DataFrame(self.records)
        df["junior_hires_per_senior"] = (
            df["junior_hires"].rolling(12, min_periods=1).mean() * 12 / df["employed_senior"]
        )
        return df
