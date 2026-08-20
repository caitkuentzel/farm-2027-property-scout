"""Command-line entry point."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from farm2027_scout.adapters.jackson_county.auction import fetch_inventory
from farm2027_scout.due_diligence import (
    verify_keep_parcels_flood_hazard,
    verify_keep_parcels_gis,
    verify_keep_parcels_road_access,
    verify_keep_parcels_wetlands,
)
from farm2027_scout.research_queue import research_inventory
from farm2027_scout.screening import screen_properties

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
    parser.add_argument(
        "--include-qpublic",
        action="store_true",
        help="Enrich every auction parcel through the rate-safe qPublic queue",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=20,
        help="Seconds to wait between qPublic parcels (default: 20)",
    )
    parser.add_argument(
        "--screen",
        action="store_true",
        help="Add transparent KEEP / REVIEW / KILL screening to enriched parcels",
    )
    parser.add_argument(
        "--verify-gis",
        action="store_true",
        help="Verify official parcel geometry for KEEP candidates",
    )
    parser.add_argument(
        "--verify-road-access",
        action="store_true",
        help="Screen KEEP parcel geometry against official mapped road centerlines",
    )
    parser.add_argument(
        "--verify-flood-hazard",
        action="store_true",
        help="Screen KEEP parcel geometry against official FEMA flood zones",
    )
    parser.add_argument(
        "--verify-wetlands",
        action="store_true",
        help="Screen KEEP parcel geometry against official USFWS mapped wetlands",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.include_qpublic:
        if args.format != "json":
            raise SystemExit("--include-qpublic currently supports JSON output only")
        if not args.output:
            raise SystemExit("--include-qpublic requires --output for resumable checkpoints")
        rows = research_inventory(
            args.auction_date,
            args.output,
            delay_seconds=args.delay_seconds,
        )
        if args.screen:
            rows = screen_properties(rows)
        if args.verify_gis:
            if not args.screen:
                raise SystemExit("--verify-gis requires --screen")
            rows = verify_keep_parcels_gis(rows)
        if args.verify_road_access:
            if not args.verify_gis:
                raise SystemExit("--verify-road-access requires --verify-gis")
            rows = verify_keep_parcels_road_access(rows)
        if args.verify_flood_hazard:
            if not args.verify_gis:
                raise SystemExit("--verify-flood-hazard requires --verify-gis")
            rows = verify_keep_parcels_flood_hazard(rows)
        if args.verify_wetlands:
            if not args.verify_gis:
                raise SystemExit("--verify-wetlands requires --verify-gis")
            rows = verify_keep_parcels_wetlands(rows)
    else:
        if any(
            (
                args.screen,
                args.verify_gis,
                args.verify_road_access,
                args.verify_flood_hazard,
                args.verify_wetlands,
            )
        ):
            raise SystemExit("research flags require --include-qpublic")
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
