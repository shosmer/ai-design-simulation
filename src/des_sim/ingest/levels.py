"""Levels.fyi — designer compensation by company and level.

Stub: the official API requires requested access (https://www.levels.fyi/api-access/).
Once granted, set LEVELS_FYI_API_KEY and fill in the endpoint calls below for
the Product Designer job family.
"""
from __future__ import annotations

import os
from pathlib import Path

from .base import Source


class LevelsFyi(Source):
    name = "levels_fyi"
    description = "Product designer compensation by company/level (official API, access-gated)"
    cadence = "continuous"

    def fetch(self) -> list[Path]:
        if not os.environ.get("LEVELS_FYI_API_KEY"):
            self.notes = (
                "LEVELS_FYI_API_KEY not set. Request access at "
                "https://www.levels.fyi/api-access/, then implement the "
                "Product Designer endpoints in this adapter."
            )
            return []
        self.notes = "API key present but adapter not yet implemented (endpoint schema TBD on access grant)."
        return []
