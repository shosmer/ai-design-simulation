"""PM vs designer openings — sampled directly from public company job boards.

Greenhouse, Lever, and Ashby expose public JSON APIs for company job boards
(keyless, intended for consumption). This adapter samples a fixed panel of
well-known tech companies, classifies titles into design / product-management
buckets, and accumulates one snapshot per pull — building the PM:design
openings ratio from primary sources (third-party trackers like TrueUp are
bot-walled and unverifiable).

Caveats: a sampled panel (~40 boards), not the market; title classification
is regex-based and documented below; openings are not hires. The panel is
fixed so the ratio is comparable across snapshots; companies whose boards
move providers drop out visibly (coverage is recorded per snapshot).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd
import requests

from .base import Source

GREENHOUSE = [
    "airbnb", "stripe", "coinbase", "databricks", "figma", "gitlab", "dropbox",
    "doordash", "robinhood", "duolingo", "pinterest", "reddit", "discord",
    "brex", "instacart", "affirm", "airtable", "asana", "cloudflare",
    "mongodb", "datadog", "elastic", "hashicorp", "twilio", "squarespace",
    "webflow", "grammarly", "retool", "scaleai", "anthropic", "openai",
    "vercel",
]
LEVER = ["spotify", "canva", "palantir", "plaid", "ramp"]
ASHBY = ["linear", "notion", "zapier", "deel"]

DESIGN_RE = re.compile(
    r"(product design|ux|user experience|visual design|brand design|design system"
    r"|content design|design manager|design director|design lead|graphic design"
    r"|motion design|web design|interaction design|service design|\bdesigner\b"
    r"|design research|user research)",
    re.IGNORECASE,
)
DESIGN_EXCLUDE_RE = re.compile(
    r"(design engineer|design verification|(electrical|mechanical|silicon|chip"
    r"|asic|analog|hardware|cell|antenna|network) design)",
    re.IGNORECASE,
)
PM_RE = re.compile(
    r"(product manager|product management|head of product|director.{0,3}product"
    r"|vp.{0,3}product|group product|principal product|product lead\b|chief product)",
    re.IGNORECASE,
)
PM_EXCLUDE_RE = re.compile(r"(product marketing|product design)", re.IGNORECASE)

UA = {"User-Agent": "des-sim-ingest/0.1 (research; shannon.hosmer@gmail.com)"}


def _titles(provider: str, company: str) -> list[str] | None:
    try:
        if provider == "greenhouse":
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs",
                headers=UA, timeout=30,
            )
            r.raise_for_status()
            return [j["title"] for j in r.json().get("jobs", [])]
        if provider == "lever":
            r = requests.get(f"https://api.lever.co/v0/postings/{company}?mode=json",
                             headers=UA, timeout=30)
            r.raise_for_status()
            return [j["text"] for j in r.json()]
        if provider == "ashby":
            r = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{company}",
                headers=UA, timeout=30,
            )
            r.raise_for_status()
            return [j["title"] for j in r.json().get("jobs", [])]
    except Exception:
        return None
    return None


def classify(title: str) -> str | None:
    if PM_RE.search(title) and not PM_EXCLUDE_RE.search(title):
        return "pm"
    if DESIGN_RE.search(title) and not DESIGN_EXCLUDE_RE.search(title):
        return "design"
    return None


class JobBoards(Source):
    name = "job_boards"
    description = "PM vs designer openings from public Greenhouse/Lever/Ashby boards"
    cadence = "continuous (one snapshot per pull; panel of ~40 tech companies)"

    def fetch(self) -> list[Path]:
        panel = [("greenhouse", c) for c in GREENHOUSE] + \
                [("lever", c) for c in LEVER] + [("ashby", c) for c in ASHBY]
        results = []
        for provider, company in panel:
            titles = _titles(provider, company)
            if titles is not None:
                results.append({"provider": provider, "company": company, "titles": titles})
        self.notes = f"{len(results)}/{len(panel)} boards responded"
        dest = self.raw_dir / "boards.json"
        dest.write_text(json.dumps(results))
        return [dest]

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        boards = json.loads(raw_files[0].read_text())
        today = dt.date.today().isoformat()
        rows = []
        for b in boards:
            buckets = {"design": 0, "pm": 0}
            for t in b["titles"]:
                kind = classify(t)
                if kind:
                    buckets[kind] += 1
            rows.append({
                "snapshot_date": today, "company": b["company"],
                "provider": b["provider"], "n_design": buckets["design"],
                "n_pm": buckets["pm"], "n_total": len(b["titles"]),
            })
        snapshot = pd.DataFrame(rows)
        existing_path = self.processed_dir / f"{self.name}_snapshots.parquet"
        if existing_path.exists():
            existing = pd.read_parquet(existing_path)
            snapshot = pd.concat([existing, snapshot], ignore_index=True).drop_duplicates(
                subset=["snapshot_date", "company"], keep="last"
            )
        return {"snapshots": snapshot}
