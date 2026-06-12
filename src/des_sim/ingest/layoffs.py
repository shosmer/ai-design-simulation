"""Tech layoff events — layoffs.fyi, scraped from its Airtable shared view.

layoffs.fyi has no API; it embeds an Airtable shared view. The embed page
carries a signed accessPolicy that authorizes one readSharedViewData call —
fetch page, extract policy, call once, save raw JSON. Fragile by nature
(Airtable could change the scheme); on any failure this falls back to a
manual CSV export dropped at data/manual/layoffs_fyi.csv.

Caveats for analysis: only ~2/3 of events carry a headcount (totals
undercount); coverage is best for US/tech; credit layoffs.fyi when citing.
"""
from __future__ import annotations

import json
import re
import shutil
import urllib.parse
from pathlib import Path

import pandas as pd
import requests

from .base import Source

EMBED_URL = "https://airtable.com/embed/app1PaujS9zxVGUZ4/shroKsHx3SdYYOzeh"
APP_ID = "app1PaujS9zxVGUZ4"
VIEW_ID = "viwN3RMGptp84mfag"
BROWSER_UA = "Mozilla/5.0 (research; shannon.hosmer@gmail.com)"


class LayoffsFyi(Source):
    name = "layoffs_fyi"
    description = "Tech layoff events (company, headcount, date) via layoffs.fyi"
    cadence = "continuous"

    def fetch(self) -> list[Path]:
        try:
            return [self._scrape()]
        except Exception as exc:
            manual = self.data_dir / "manual" / "layoffs_fyi.csv"
            if manual.exists():
                self.notes = f"Scrape failed ({exc}); used manual CSV export."
                dest = self.raw_dir / manual.name
                shutil.copy2(manual, dest)
                return [dest]
            self.notes = (
                f"Scrape failed ({exc}) and no manual export at {manual}. "
                "Airtable may have changed its shared-view scheme."
            )
            return []

    def _scrape(self) -> Path:
        html = requests.get(EMBED_URL, headers={"User-Agent": BROWSER_UA}, timeout=60).text
        m = re.search(r'accessPolicy=([^&"\\\s]+)', html)
        if not m:
            raise RuntimeError("no accessPolicy on embed page")
        policy = urllib.parse.unquote(m.group(1))
        url = (
            f"https://airtable.com/v0.3/view/{VIEW_ID}/readSharedViewData"
            f"?stringifiedObjectParams=%7B%7D&accessPolicy={urllib.parse.quote(policy)}"
        )
        resp = requests.get(
            url,
            headers={
                "User-Agent": BROWSER_UA,
                "x-airtable-application-id": APP_ID,
                "x-requested-with": "XMLHttpRequest",
                "x-time-zone": "America/New_York",
            },
            timeout=120,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "data" not in payload or not payload["data"].get("rows"):
            raise RuntimeError("shared-view response had no rows")
        dest = self.raw_dir / "layoffs_shared_view.json"
        dest.write_bytes(resp.content)
        return dest

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        path = raw_files[0]
        if path.suffix == ".json":
            data = json.loads(path.read_text())["data"]
            col_names = {c["id"]: c["name"] for c in data["columns"]}
            df = pd.DataFrame(
                [{col_names[k]: v for k, v in r["cellValuesByColumnId"].items()}
                 for r in data["rows"]]
            )
        else:
            df = pd.read_csv(path)
        df.columns = [
            re.sub(r"[^a-z0-9]+", "_", c.strip().lower()).strip("_") for c in df.columns
        ]
        date_col = next(c for c in df.columns if "date" in c and "added" not in c)
        n_col = next(c for c in df.columns if "laid_off" in c)
        df["date"] = pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.tz_localize(None)
        df["laid_off"] = pd.to_numeric(df[n_col], errors="coerce")
        keep = [c for c in ("company", "industry", "country", "stage", "date", "laid_off") if c in df.columns]
        out = df[keep].dropna(subset=["date"]).sort_values("date")
        for col in out.columns:
            if out[col].dtype == object:
                out[col] = out[col].astype(str)
        return {"events": out}
