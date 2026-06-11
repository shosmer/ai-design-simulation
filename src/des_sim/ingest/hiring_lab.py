"""Indeed Hiring Lab — job postings indices and AI-mention tracker.

Plain CSVs published on GitHub under CC-BY-4.0 (cite Hiring Lab).
Postings tracker refreshes weekly; AI tracker refreshes monthly.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import Source, download

FILES = {
    "aggregate_postings": "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/aggregate_job_postings_US.csv",
    "postings_by_sector": "https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/job_postings_by_sector_US.csv",
    "ai_postings": "https://raw.githubusercontent.com/hiring-lab/ai-tracker/main/AI_posting.csv",
}


class HiringLab(Source):
    name = "hiring_lab"
    description = "Indeed job postings indices (aggregate + by sector) and AI-mention share"
    cadence = "weekly (postings), monthly (AI tracker)"

    def fetch(self) -> list[Path]:
        return [download(url, self.raw_dir / f"{key}.csv") for key, url in FILES.items()]

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        for path in raw_files:
            df = pd.read_csv(path)
            df.columns = [c.strip().lower() for c in df.columns]
            date_cols = [c for c in df.columns if "date" in c]
            if date_cols:
                df[date_cols[0]] = pd.to_datetime(df[date_cols[0]], errors="coerce")
            frames[path.stem] = df
        return frames
