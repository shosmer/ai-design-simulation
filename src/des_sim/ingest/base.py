"""Shared infrastructure for data source adapters.

Each adapter subclasses Source and implements fetch() (download raw
artifacts) and optionally transform() (tidy them into DataFrames).
pull() runs both and records the result in data/manifest.json.
"""
from __future__ import annotations

import abc
import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
import requests

# BLS and Census reject requests without an identifiable User-Agent;
# they ask for contact info so they can reach you instead of blocking you.
USER_AGENT = "des-sim-ingest/0.1 (shannon.hosmer@gmail.com)"


@dataclass
class PullResult:
    source: str
    fetched_at: str
    raw_files: list[str]
    processed_files: list[str]
    rows: dict[str, int]
    notes: str = ""


class Source(abc.ABC):
    name: str = ""
    description: str = ""
    cadence: str = ""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.notes = ""

    @property
    def raw_dir(self) -> Path:
        d = self.data_dir / "raw" / self.name / dt.date.today().isoformat()
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def processed_dir(self) -> Path:
        d = self.data_dir / "processed"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @abc.abstractmethod
    def fetch(self) -> list[Path]:
        """Download raw artifacts into self.raw_dir and return their paths."""

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        """Tidy raw files into named DataFrames. Empty dict = raw-only source."""
        return {}

    def pull(self) -> PullResult:
        raw_files = self.fetch()
        frames = self.transform(raw_files) if raw_files else {}
        processed_files: list[str] = []
        rows: dict[str, int] = {}
        for key, df in frames.items():
            out = self.processed_dir / f"{self.name}_{key}.parquet"
            df.to_parquet(out, index=False)
            processed_files.append(str(out))
            rows[key] = len(df)
        return PullResult(
            source=self.name,
            fetched_at=dt.datetime.now().isoformat(timespec="seconds"),
            raw_files=[str(p) for p in raw_files],
            processed_files=processed_files,
            rows=rows,
            notes=self.notes,
        )


def download(url: str, dest: Path, *, headers: dict | None = None, timeout: int = 300) -> Path:
    merged = {"User-Agent": USER_AGENT}
    merged.update(headers or {})
    resp = requests.get(url, headers=merged, timeout=timeout)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def fetch_text(url: str, *, timeout: int = 60) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def update_manifest(data_dir: Path, result: PullResult) -> Path:
    manifest_path = Path(data_dir) / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    manifest[result.source] = asdict(result)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path
