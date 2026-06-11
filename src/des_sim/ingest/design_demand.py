"""Design demand evidence — how much design is the world buying?

Two slices, per the elasticity-evidence plan:
1. Purchased design dollars: Census Service Annual Survey revenue series via
   FRED's keyless CSV endpoint (annual, ~18-month lag, employer firms only).
   No PPI deflator exists for design services, so these are nominal dollars —
   they bound the price/quantity split rather than resolve it.
2. Designed output shipped: new Google Play app releases per month, parsed
   from AppBrain's public stats page. The page embeds three monthly series
   (releases, unpublished, net change); they're identified by the arithmetic
   relationship net = releases - unpublished rather than page order, so a
   reshuffle of the page doesn't silently mislabel them. The last month is
   partial and dropped. Google Play only; quality mix unknown.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .base import Source, download

FRED_SERIES = {
    "REVEF54143ALLEST": "graphic_design_revenue",
    "REVEF54141ALLEST": "interior_design_revenue",   # non-AI-exposed comparison
    "REVEF5415ALLEST": "computer_systems_design_revenue",
}
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
APPBRAIN_URL = "https://www.appbrain.com/stats/number-of-android-apps"


class DesignDemand(Source):
    name = "design_demand"
    description = "Design purchased (SAS revenue via FRED) and shipped (Google Play releases)"
    cadence = "annual (revenue), monthly (app releases)"

    def fetch(self) -> list[Path]:
        files = []
        for sid in FRED_SERIES:
            files.append(download(FRED_URL.format(sid=sid), self.raw_dir / f"{sid}.csv"))
        files.append(
            download(
                APPBRAIN_URL,
                self.raw_dir / "appbrain.html",
                headers={"User-Agent": "Mozilla/5.0 (research; shannon.hosmer@gmail.com)"},
            )
        )
        return files

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}

        revenue = []
        for path in raw_files:
            sid = path.stem
            if sid not in FRED_SERIES:
                continue
            df = pd.read_csv(path)
            df.columns = ["date", "value"]
            df["date"] = pd.to_datetime(df["date"])
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df["series"] = FRED_SERIES[sid]
            revenue.append(df.dropna())
        frames["revenue"] = pd.concat(revenue, ignore_index=True)

        html = (self.raw_dir / "appbrain.html").read_text(errors="ignore")
        frames["app_releases"] = self._parse_appbrain(html)
        return frames

    @staticmethod
    def _parse_appbrain(html: str) -> pd.DataFrame:
        blobs = re.findall(
            r'\[(\["20\d\d-\d\d-\d\d",-?\d+\](?:,\["20\d\d-\d\d-\d\d",-?\d+\])+)\]', html
        )
        series = []
        for blob in blobs:
            pairs = re.findall(r'\["(20\d\d-\d\d-\d\d)",(-?\d+)\]', blob)
            series.append({d: int(v) for d, v in pairs})
        if len(series) < 3:
            raise RuntimeError(f"Expected 3 embedded series on AppBrain page, found {len(series)}")

        # Identify by arithmetic: net = releases - unpublished. Try each series
        # as "net" and each ordering of the other two.
        def matches(net, a, b):
            common = set(net) & set(a) & set(b)
            return common and all(abs(net[d] - (a[d] - b[d])) <= 2 for d in common)

        assignment = None
        for i in range(3):
            rest = [j for j in range(3) if j != i]
            for a, b in (rest, rest[::-1]):
                if matches(series[i], series[a], series[b]):
                    assignment = (a, b)  # releases, unpublished
        if assignment is None:
            raise RuntimeError("Could not identify releases/unpublished/net among AppBrain series")

        releases, unpublished = (series[k] for k in assignment)
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(sorted(releases)),
                "new_releases": [releases[d] for d in sorted(releases)],
                "unpublished": [unpublished.get(d) for d in sorted(releases)],
            }
        )
        return df.iloc[:-1]  # current month is partial
