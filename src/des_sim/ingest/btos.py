"""Census Business Trends and Outlook Survey — biweekly firm-level AI adoption.

The BTOS downloads page (census.gov/hfp/btos/data_downloads) is a JS app with
no scrapeable links, but the file URL is stable: National.xlsx holds the core
questions (including "used AI in the last two weeks" / "expect to in six
months") by NAICS sector and firm size, refreshed each biweekly release.

Census serves an HTML error page with HTTP 200 for missing files, so the
download is validated by its zip magic bytes. Sheet layout varies across
releases; raw Excel is kept and parsed lightly (one table per sheet).
There is also a BTOS API if finer-grained pulls are ever needed.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import Source, download

NATIONAL_XLSX = "https://www.census.gov/hfp/btos/downloads/National.xlsx"


class BTOS(Source):
    name = "btos"
    description = "Census BTOS biweekly AI use by sector and firm size"
    cadence = "biweekly"

    def fetch(self) -> list[Path]:
        dest = download(NATIONAL_XLSX, self.raw_dir / "National.xlsx")
        if not dest.read_bytes().startswith(b"PK"):
            dest.unlink()
            raise RuntimeError(
                f"{NATIONAL_XLSX} did not return an xlsx (Census serves an HTML "
                "error page with status 200 when a file is missing/renamed)."
            )
        return [dest]

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        sheets = pd.read_excel(raw_files[0], sheet_name=None)
        frames: dict[str, pd.DataFrame] = {}
        for sheet, df in sheets.items():
            if df.empty:
                continue
            # Footnote rows mix text into numeric columns; string-type the
            # object columns so parquet conversion doesn't fail.
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].astype("string")
            key = sheet.strip().lower().replace(" ", "_").replace("-", "_")
            frames[f"national_{key}"] = df
        return frames
