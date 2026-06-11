"""BLS Occupational Employment and Wage Statistics — annual employment and wages.

Scrapes the OEWS tables page for the latest national all-occupations zip
(oesmYYnat.zip), then filters to design-relevant SOC codes plus software
developers as a comparison group.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from .base import Source, download, fetch_text

TABLES_PAGE = "https://www.bls.gov/oes/tables.htm"

DESIGN_SOCS = {
    "15-1255",  # web and digital interface designers
    "27-1021",  # commercial and industrial designers
    "27-1024",  # graphic designers
    "27-1014",  # special effects artists and animators
    "27-1011",  # art directors
    "15-1252",  # software developers (comparison group)
}


class OEWS(Source):
    name = "oews"
    description = "BLS OEWS national employment and wage estimates for design occupations"
    cadence = "annual (spring release of prior-May estimates)"

    def fetch(self) -> list[Path]:
        html = fetch_text(TABLES_PAGE)
        links = re.findall(r'href="([^"]*oesm(\d{2})nat\.zip)"', html)
        if not links:
            raise RuntimeError(f"No oesmYYnat.zip link found on {TABLES_PAGE}")
        latest = max(links, key=lambda m: int(m[1]))[0]
        url = urljoin(TABLES_PAGE, latest)
        dest = self.raw_dir / Path(url).name
        return [download(url, dest)]

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        frames = []
        with zipfile.ZipFile(raw_files[0]) as zf:
            for member in zf.namelist():
                if not member.lower().endswith(".xlsx"):
                    continue
                with zf.open(member) as f:
                    df = pd.read_excel(f)
                df.columns = [c.strip().upper() for c in df.columns]
                if "OCC_CODE" not in df.columns:
                    continue
                frames.append(df[df["OCC_CODE"].isin(DESIGN_SOCS)])
        if not frames:
            raise RuntimeError("No xlsx with an OCC_CODE column found in OEWS zip")
        return {"design_occupations": pd.concat(frames, ignore_index=True)}
