"""Anthropic Economic Index — occupation/task-level AI usage data.

Downloads the latest release_* directory from the HuggingFace dataset
(Anthropic/EconomicIndex, CC-BY). Release contents vary (CSVs, docs),
so raw files are kept as-is; any CSVs are also written to processed/.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from huggingface_hub import HfApi, snapshot_download

from .base import Source

REPO_ID = "Anthropic/EconomicIndex"


class AnthropicEconomicIndex(Source):
    name = "aei"
    description = "Anthropic Economic Index: task-level AI usage, automation vs augmentation"
    cadence = "roughly quarterly"

    def fetch(self) -> list[Path]:
        api = HfApi()
        files = api.list_repo_files(REPO_ID, repo_type="dataset")
        releases = sorted({f.split("/")[0] for f in files if f.startswith("release_")})
        if not releases:
            raise RuntimeError(f"No release_* directories found in {REPO_ID}")
        latest = releases[-1]
        self.notes = f"Pulled {latest}"
        local = snapshot_download(
            repo_id=REPO_ID,
            repo_type="dataset",
            allow_patterns=[f"{latest}/*"],
            local_dir=self.raw_dir,
        )
        return sorted(p for p in Path(local).rglob("*") if p.is_file() and ".cache" not in p.parts)

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        for path in raw_files:
            if path.suffix.lower() != ".csv":
                continue
            try:
                frames[path.stem] = pd.read_csv(path)
            except Exception:  # release layouts vary; keep going
                continue
        return frames
