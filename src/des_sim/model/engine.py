"""Minimal vertical slice of the designer/AI labor-market model.

Monthly time steps (a simplification of the eventual event-driven core).
Included: designers with seniority, firms with task routing and demand
response, per-category AI capability curves, a talent pipeline with lagged
entry, hiring/layoff frictions, promotions, and profession exit.
Deliberately stubbed for the slice: AI fluency, wage bargaining, skill
atrophy, designer specialty.

The make-or-break question this slice answers: does the junior pipeline
collapse emerge from task-level automation alone, and how does the
elasticity of demand for design output change the answer?
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

JUNIOR, MID, SENIOR = 0, 1, 2
LEVEL_NAMES = ["junior", "mid", "senior"]
THROUGHPUT = [1.0, 1.6, 2.2]  # task-units/month by level
# Of human-remaining work not suitable for juniors, the mid/senior split:
MID_SHARE_OF_NON_JUNIOR = 0.55

AI_COST_FACTOR = 0.05  # AI cost per task-unit, as a fraction of human cost

LAYOFF_RATE_CAP = 0.08  # max share of a level's roster cut per month
HIRE_RATE_CAP = 0.15    # max growth of a level's roster per month

PROMOTION_MONTHS = {JUNIOR: 30, MID: 48}
EXIT_PROB_LONG_UNEMPLOYED = 0.12  # monthly, after 12 months unemployed
RETIRE_PROB_SENIOR = 0.003        # monthly

PIPELINE_LAG = 24      # months between perceived prospects and graduation
PIPELINE_MIN, PIPELINE_MAX = 0.2, 2.0  # entry response bounds vs baseline


@dataclass
class TaskCategory:
    """One slice of design work with its own automation trajectory.

    capability(t) is the share of this category AI can do at month t
    (logistic: ceiling / steepness / midpoint). junior_share is the fraction
    of the *human-remaining* work in this category suitable for juniors.
    """

    name: str
    workload_share: float
    ceiling: float
    midpoint: float
    steepness: float
    junior_share: float

    def capability(self, t: float) -> float:
        return self.ceiling / (1 + math.exp(-self.steepness * (t - self.midpoint)))


# t=0 is mid-2026. Stylized but anchored: AEI shows production-style tasks
# (directive automation, 44% of interactions) ahead of judgment work, and
# the 2025-26 trade press consistently reports "intern work" automating first.
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


@dataclass
class Firm:
    base_demand: float       # task-units/month demanded at baseline unit cost
    adoption_start: float    # month AI task-routing begins
    integration_months: float = 12.0
    roster: list[list[Designer]] = field(default_factory=lambda: [[], [], []])

    def adoption(self, t: float) -> float:
        if t < self.adoption_start:
            return 0.0
        return min(1.0, (t - self.adoption_start) / self.integration_months)


class Simulation:
    def __init__(
        self,
        elasticity: float,
        n_firms: int = 150,
        n_designers: int = 4000,
        months: int = 120,
        seed: int = 0,
        categories: list[TaskCategory] | None = None,
    ) -> None:
        self.elasticity = elasticity
        self.months = months
        self.rng = np.random.default_rng(seed)
        self.categories = categories or DEFAULT_CATEGORIES

        # Firm adoption staggering: BTOS has the Information sector at ~40%
        # adoption in mid-2026 and climbing, so center the logistic near t=6.
        starts = self.rng.logistic(loc=6, scale=10, size=n_firms).clip(min=0)
        sizes = self.rng.lognormal(mean=0, sigma=0.8, size=n_firms)
        sizes /= sizes.sum()

        # Baseline blended human cost per task-unit (constant for the slice).
        level_mix = np.array([0.30, 0.40, 0.30])
        self.human_cost = float(
            (level_mix * [70_000 / 12, 110_000 / 12, 150_000 / 12]).sum()
            / (level_mix * THROUGHPUT).sum()
        )

        # Size base demand so the initial workforce is in equilibrium at t=0
        # capability levels, then staff each firm to its t=0 desired counts.
        capacity = (level_mix * THROUGHPUT).sum() * n_designers
        human_share_0 = sum(
            c.workload_share * (1 - c.capability(0) * 0.4) for c in self.categories
        )
        total_demand = capacity / human_share_0
        self.p0 = self._unit_cost(adoption=0.4, t=0)

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

        self.unemployed: list[list[Designer]] = [[], [], []]
        self.junior_hire_history: list[int] = []
        self.baseline_grads = max(1, round(len(self.designers) * 0.30 * 0.025))
        self.records: list[dict] = []

    # ---- core mechanics -------------------------------------------------

    def _unit_cost(self, adoption: float, t: float) -> float:
        cost = 0.0
        for c in self.categories:
            auto = c.capability(t) * adoption
            cost += c.workload_share * (auto * AI_COST_FACTOR + (1 - auto)) * self.human_cost
        return cost

    def _desired_headcount(self, firm: Firm, t: float) -> list[float]:
        adoption = firm.adoption(t) if t > 0 else 0.4
        p = self._unit_cost(adoption, t)
        demand = firm.base_demand * (p / self.p0) ** (-self.elasticity)
        junior_work = mid_work = senior_work = 0.0
        for c in self.categories:
            human = demand * c.workload_share * (1 - c.capability(t) * adoption)
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
        layoffs = 0

        # New grads enter the unemployed junior pool; entry responds to
        # junior hiring prospects with a long lag.
        signal = 1.0
        if len(self.junior_hire_history) > PIPELINE_LAG + 12:
            recent = np.mean(self.junior_hire_history[-PIPELINE_LAG - 12 : -PIPELINE_LAG])
            base = np.mean(self.junior_hire_history[:12])
            if base > 0:
                signal = float(np.clip(recent / base, PIPELINE_MIN, PIPELINE_MAX))
        grads = round(self.baseline_grads * signal)
        for _ in range(grads):
            d = Designer(level=JUNIOR, employer=None)
            self.designers.append(d)
            self.unemployed[JUNIOR].append(d)

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
                elif gap > 0.5:  # hires from the unemployed pool, capped
                    n_hire = min(round(gap), max(1, round(HIRE_RATE_CAP * current) + 1))
                    pool = self.unemployed[level]
                    for _ in range(min(n_hire, len(pool))):
                        d = pool.pop(int(self.rng.integers(len(pool))))
                        d.employer = int(idx)
                        d.months_unemployed = 0
                        firm.roster[level].append(d)
                        if level == JUNIOR:
                            junior_hires += 1

        # Promotions, tenure, unemployment aging, exits.
        exits = 0
        for firm in self.firms:
            for level in (MID, JUNIOR):  # promote top-down to avoid double moves
                threshold = PROMOTION_MONTHS[level]
                for d in [x for x in firm.roster[level] if x.months_at_level >= threshold]:
                    firm.roster[level].remove(d)
                    d.level = level + 1
                    d.months_at_level = 0
                    firm.roster[level + 1].append(d)
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

        self.junior_hire_history.append(junior_hires)

        employed = [sum(len(f.roster[lv]) for f in self.firms) for lv in range(3)]
        mean_adoption = float(np.mean([f.adoption(t) for f in self.firms]))
        ai_task_share = sum(
            c.workload_share * c.capability(t) * mean_adoption for c in self.categories
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
                "grads": grads,
                "layoffs": layoffs,
                "exits": exits,
                "ai_task_share": ai_task_share,
                "unit_cost_rel": self._unit_cost(mean_adoption, t) / self.p0,
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
