"""AI inference prices — OpenRouter public model catalog, snapshotted.

OpenRouter exposes per-token prices for ~300 models with no API key. There is
no historical endpoint, so this adapter *accumulates*: each pull appends
today's snapshot to the processed parquet (deduped on date + model), building
a frontier-price time series the longer the pipeline runs. Feeds the model's
AI-cost-decline assumption (AI_COST_HALF_LIFE) with an observable series.

Also pulls the Employment Cost Index (wages & salaries, FRED: ECIWAG) — the
human-input price series the AI price is contrasted against in the story's
"one input is in free fall" scene.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from .base import Source, download

URL = "https://openrouter.ai/api/v1/models"
ECI_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=ECIWAG"


class AiPrices(Source):
    name = "ai_prices"
    description = "Per-token AI prices (OpenRouter catalog) + ECI wage index"
    cadence = "continuous (price series grows one snapshot per pull); ECI quarterly"

    def fetch(self) -> list[Path]:
        return [
            download(URL, self.raw_dir / "models.json"),
            download(ECI_URL, self.raw_dir / "eciwag.csv"),
        ]

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        models = json.loads(raw_files[0].read_text())["data"]
        today = dt.date.today().isoformat()
        rows = []
        for m in models:
            pricing = m.get("pricing") or {}
            try:
                prompt = float(pricing.get("prompt") or "nan")
                completion = float(pricing.get("completion") or "nan")
            except ValueError:
                continue
            rows.append(
                {
                    "snapshot_date": today,
                    "model": m.get("id"),
                    "prompt_per_token": prompt,
                    "completion_per_token": completion,
                    "context_length": m.get("context_length"),
                }
            )
        snapshot = pd.DataFrame(rows).dropna(subset=["prompt_per_token"])

        existing_path = self.processed_dir / f"{self.name}_snapshots.parquet"
        if existing_path.exists():
            existing = pd.read_parquet(existing_path)
            snapshot = pd.concat([existing, snapshot], ignore_index=True).drop_duplicates(
                subset=["snapshot_date", "model"], keep="last"
            )
        self.notes = f"{snapshot['snapshot_date'].nunique()} snapshot date(s) accumulated"

        eci = pd.read_csv(self.raw_dir / "eciwag.csv")
        eci.columns = ["date", "value"]
        eci["date"] = pd.to_datetime(eci["date"])
        eci["value"] = pd.to_numeric(eci["value"], errors="coerce")
        return {"snapshots": snapshot, "wage_index": eci.dropna()}
