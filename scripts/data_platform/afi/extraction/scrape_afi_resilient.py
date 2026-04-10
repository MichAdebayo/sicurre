#!/usr/bin/env python3
"""Run the AFI Wayback scraper as a thin CLI wrapper."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_platform.extractors.afi_wayback import (  # noqa: E402
    AFIWaybackConfig,
    AFIWaybackExtractor,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape AFI Wayback forum threads")
    parser.add_argument(
        "mode",
        nargs="?",
        default="french",
        choices=["french", "all", "stats"],
        help="Scrape French-likely threads, all non-English threads, or print stats only",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--base-delay", type=float)
    parser.add_argument("--backoff-base", type=float)
    parser.add_argument("--max-backoff", type=float)
    parser.add_argument("--max-consecutive-errors", type=int)
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> AFIWaybackConfig:
    overrides = {
        "output_dir": args.output_dir,
        "base_delay": args.base_delay,
        "backoff_base": args.backoff_base,
        "max_backoff": args.max_backoff,
        "max_consecutive_errors": args.max_consecutive_errors,
    }
    return AFIWaybackConfig(
        **{key: value for key, value in overrides.items() if value is not None}
    )


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s"
    )
    extractor = AFIWaybackExtractor(config=build_config(args))
    result = extractor.run(mode=args.mode)

    print(f"Mode                    : {result.mode}")
    print(f"Inventory threads       : {result.inventory_count:,}")
    print(f"Candidates              : {result.candidate_count:,}")
    print(f"Pending                 : {result.pending_count:,}")
    print(f"Completed               : {result.completed_count:,}")
    print(f"Failed                  : {result.failed_count:,}")
    print(f"Fetched                 : {result.fetched_count:,}")
    print(f"Messages                : {result.message_count:,}")
    print(f"French                  : {result.french_count:,}")
    print(f"Errors                  : {result.error_count:,}")
    print(f"CSV                     : {result.csv_path}")
    print(f"Inventory               : {result.inventory_path}")
    print(f"Progress                : {result.progress_path}")
    print("Inventory language counts:")
    for label, count in sorted(
        result.inventory_language_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        print(f"  {label:12s} {count:>6d}")


if __name__ == "__main__":
    main()
