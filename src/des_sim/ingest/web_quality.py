"""Web design quality distribution — HTTP Archive Lighthouse accessibility scores.

Monthly percentiles (p10..p90) of Lighthouse accessibility audits across
millions of real websites, 2017-present. Feeds the quality-dispersion
discriminator: good-enough commoditization predicts the floor rises while the
ceiling stalls (variance collapses); a quality arms race predicts both rise.
Caveats: technical quality only (no Lighthouse for aesthetic judgment), and
the ceiling sits near the scale max, so it is censored on the upside.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .base import Source, download

URL = "https://cdn.httparchive.org/v1/static/reports/a11yScores.json"


class WebQuality(Source):
    name = "web_quality"
    description = "Lighthouse accessibility score percentiles (HTTP Archive)"
    cadence = "monthly"

    def fetch(self) -> list[Path]:
        return [download(URL, self.raw_dir / "a11yScores.json")]

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        rows = json.loads(raw_files[0].read_text())
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], format="%Y_%m_%d")
        for col in ("p10", "p25", "p50", "p75", "p90"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return {"a11y_scores": df[["date", "client", "p10", "p25", "p50", "p75", "p90"]].dropna()}
