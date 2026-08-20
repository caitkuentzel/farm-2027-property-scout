"""Rate-safe, resumable enrichment of auction records."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from farm2027_scout.adapters.jackson_county.qpublic import PropertyRecord, fetch_property
from farm2027_scout.models import AuctionRecord

FetchProperty = Callable[[str], PropertyRecord]
Sleep = Callable[[float], None]


def _read_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row["parcel_id"]: row for row in rows if row.get("parcel_id")}


def _write_checkpoint(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Replace a checkpoint only after its complete successor is on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(list(rows), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _combined(auction: AuctionRecord, property_record: PropertyRecord) -> dict[str, Any]:
    auction_data = auction.to_dict()
    property_data = property_record.to_dict()
    auction_assessed_value = auction_data.pop("assessed_value")
    auction_source_url = auction_data.pop("source_url")
    auction_retrieved_at = auction_data.pop("retrieved_at")
    qpublic_assessed_value = property_data.pop("assessed_value")
    qpublic_source_url = property_data.pop("source_url")
    qpublic_retrieved_at = property_data.pop("retrieved_at")
    return {
        **auction_data,
        "auction_assessed_value": auction_assessed_value,
        "auction_source_url": auction_source_url,
        "auction_retrieved_at": auction_retrieved_at,
        **property_data,
        "qpublic_assessed_value": qpublic_assessed_value,
        "qpublic_source_url": qpublic_source_url,
        "qpublic_retrieved_at": qpublic_retrieved_at,
    }


def research_properties(
    auctions: Iterable[AuctionRecord],
    checkpoint_path: Path,
    *,
    fetch: FetchProperty = fetch_property,
    sleep: Sleep = time.sleep,
    delay_seconds: float = 15,
    max_retries: int = 3,
    backoff_seconds: float = 30,
) -> list[dict[str, Any]]:
    """Enrich parcels sequentially, checkpointing each success and resuming safely."""
    if delay_seconds < 0 or backoff_seconds < 0 or max_retries < 1:
        raise ValueError("Delays must be non-negative and max_retries must be positive")

    completed = _read_checkpoint(checkpoint_path)
    pending = [auction for auction in auctions if auction.parcel_id not in completed]

    for position, auction in enumerate(pending):
        if not auction.parcel_id:
            continue
        if position:
            sleep(delay_seconds)
        for attempt in range(max_retries):
            try:
                property_record = fetch(auction.parcel_id)
                completed[auction.parcel_id] = _combined(auction, property_record)
                _write_checkpoint(checkpoint_path, completed.values())
                break
            except RuntimeError:
                if attempt + 1 == max_retries:
                    raise
                sleep(backoff_seconds * (2**attempt))

    return list(completed.values())
