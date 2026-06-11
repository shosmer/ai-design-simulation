"""CLI for the ingestion layer: `des-sim-ingest list` / `des-sim-ingest pull [sources...]`."""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from .ingest import SOURCES
from .ingest.base import update_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="des-sim-ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="show available sources and their cadence")

    pull = sub.add_parser("pull", help="fetch + transform sources, update data/manifest.json")
    pull.add_argument("sources", nargs="*", help="source names (default: all)")
    pull.add_argument("--data-dir", default="data", help="data directory (default: ./data)")

    args = parser.parse_args(argv)

    if args.cmd == "list":
        width = max(len(n) for n in SOURCES)
        for name, cls in SOURCES.items():
            print(f"{name:<{width}}  [{cls.cadence}]  {cls.description}")
        return 0

    names = args.sources or list(SOURCES)
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        parser.error(f"unknown source(s): {', '.join(unknown)} — try `des-sim-ingest list`")

    data_dir = Path(args.data_dir)
    failures = 0
    for name in names:
        print(f"==> {name}")
        try:
            result = SOURCES[name](data_dir).pull()
        except Exception:
            failures += 1
            traceback.print_exc(file=sys.stderr)
            print(f"    FAILED (see traceback above)")
            continue
        update_manifest(data_dir, result)
        print(f"    raw: {len(result.raw_files)} file(s)")
        for key, n in result.rows.items():
            print(f"    processed: {name}_{key}.parquet ({n} rows)")
        if result.notes:
            print(f"    note: {result.notes}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
