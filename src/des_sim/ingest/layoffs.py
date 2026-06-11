"""Tech layoff events — manual export from layoffs.fyi.

layoffs.fyi is an Airtable behind the site with no stable API, so this
adapter reads a manually exported CSV dropped at data/manual/layoffs_fyi.csv
(open the shared Airtable view on layoffs.fyi -> "..." -> Download CSV).
Cross-check candidates: trueup.io/layoffs, state WARN-notice databases.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from .base import Source


class LayoffsFyi(Source):
    name = "layoffs_fyi"
    description = "Tech layoff events (company, headcount, date) via manual CSV export"
    cadence = "continuous (manual export step)"

    def fetch(self) -> list[Path]:
        manual = self.data_dir / "manual" / "layoffs_fyi.csv"
        if not manual.exists():
            self.notes = (
                f"No export found at {manual}. Download the CSV from the "
                "layoffs.fyi Airtable view and drop it there, then re-run."
            )
            return []
        dest = self.raw_dir / manual.name
        shutil.copy2(manual, dest)
        return [dest]

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        df = pd.read_csv(raw_files[0])
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        date_cols = [c for c in df.columns if "date" in c]
        if date_cols:
            df[date_cols[0]] = pd.to_datetime(df[date_cols[0]], errors="coerce")
        return {"events": df}
