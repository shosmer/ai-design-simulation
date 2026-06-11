"""O*NET task statements — maps task text to occupations (SOC codes).

Used to identify which AEI O*NET tasks belong to design occupations, so the
capability anchoring rests on the official occupation-task mapping rather
than keyword matching. Probes recent database versions and takes the newest.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from .base import USER_AGENT, Source, download

VERSIONS = ["db_31_0", "db_30_1", "db_30_0", "db_29_3"]
URL_TEMPLATE = "https://www.onetcenter.org/dl_files/database/{version}_text/Task%20Statements.txt"


class OnetTasks(Source):
    name = "onet_tasks"
    description = "O*NET task statements (task text -> SOC occupation mapping)"
    cadence = "quarterly database releases; content changes slowly"

    def fetch(self) -> list[Path]:
        for version in VERSIONS:
            url = URL_TEMPLATE.format(version=version)
            head = requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=30)
            if head.status_code == 200:
                self.notes = f"O*NET {version}"
                return [download(url, self.raw_dir / "task_statements.txt")]
        raise RuntimeError("No known O*NET database version responded")

    def transform(self, raw_files: list[Path]) -> dict[str, pd.DataFrame]:
        df = pd.read_csv(raw_files[0], sep="\t")
        df.columns = [
            c.strip().lower().replace(" ", "_").replace("-", "_").replace("*", "")
            for c in df.columns
        ]
        keep = [c for c in ("onet_soc_code", "task_id", "task", "task_type") if c in df.columns]
        return {"statements": df[keep]}
