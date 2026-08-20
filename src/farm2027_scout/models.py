"""Normalized public auction records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AuctionRecord:
    """One property offered in a public tax-deed auction."""

    auction_date: datetime | None
    case_number: str | None
    parcel_id: str | None
    property_address: str | None
    opening_bid: Decimal | None
    assessed_value: Decimal | None
    source_url: str
    retrieved_at: datetime

    def to_dict(self) -> dict[str, str | None]:
        """Return a JSON-safe representation without inventing missing values."""
        values = asdict(self)
        for field in ("auction_date", "retrieved_at"):
            value = values[field]
            values[field] = value.isoformat() if value else None
        for field in ("opening_bid", "assessed_value"):
            value = values[field]
            values[field] = str(value) if value is not None else None
        return values

