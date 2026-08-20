"""Command-line entry point."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from farm2027_scout.adapters.jackson_county.auction import fetch_inventory

FIELDS = (
    "auction_date",
    "case_number",
    "parcel_id",
    "property_address",
    "opening_bid",
    "assessed_value",
    "source_url",
    "retrieved_at",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research public Florida tax-deed inventory")
    parser.add_argument("--auction-date", help="MM/DD/YYYY; omit for the current calendar")
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    parser.add_argument("--output", type=Path, help="Write output to a file instead of stdout")
    return parser


def main() -> int:
    args = _parser().parse_args()
    rows = [record.to_dict() for record in fetch_inventory(args.auction_date)]
    if args.format == "json":
        rendered = json.dumps(rows, indent=2)
    else:
        target = args.output.open("w", newline="") if args.output else sys.stdout
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        if args.output:
            target.close()
        return 0
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

