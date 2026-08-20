"""Transparent first-pass KEEP / REVIEW / KILL screening."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def screen_property(row: dict[str, Any]) -> dict[str, Any]:
    """Score one researched parcel without inventing missing facts."""
    score = 50
    reasons: list[str] = []
    flags: list[str] = []

    acreage = _decimal(row.get("acreage"))
    if acreage is None or acreage == 0:
        acreage_status = "UNKNOWN_REQUIRES_GIS"
        score -= 10
        flags.append("qPublic acreage is missing or zero; verify parcel dimensions in GIS")
    elif acreage >= 1:
        acreage_status = "CONFIRMED_1_PLUS_ACRE"
        score += 25
        reasons.append("qPublic reports at least 1 acre")
    elif acreage >= Decimal("0.5"):
        acreage_status = "CONFIRMED_HALF_PLUS_ACRE"
        score += 20
        reasons.append("qPublic reports at least 0.5 acre")
    else:
        acreage_status = "CONFIRMED_UNDER_HALF_ACRE"
        score += 10
        reasons.append("qPublic reports less than 0.5 acre")

    opening_bid = _decimal(row.get("opening_bid"))
    conservative_value = _decimal(row.get("qpublic_assessed_value"))
    bid_ratio: Decimal | None = None
    if opening_bid is None or conservative_value is None or conservative_value <= 0:
        score -= 25
        flags.append("bid-to-value ratio cannot be calculated")
    else:
        bid_ratio = opening_bid / conservative_value
        if bid_ratio <= Decimal("0.50"):
            score += 25
            reasons.append("opening bid is no more than 50% of current assessed value")
        elif bid_ratio <= Decimal("0.60"):
            score += 15
            reasons.append("opening bid is no more than 60% of current assessed value")
        elif bid_ratio > Decimal("0.75"):
            score -= 25
            flags.append("opening bid exceeds 75% of current assessed value")
        else:
            flags.append("opening bid has only a modest assessed-value discount")

    if row.get("vacant_improved") == "IMPROVED":
        score += 10
        reasons.append("qPublic reports an improvement")
    elif row.get("vacant_improved") == "VACANT":
        reasons.append("qPublic classifies the parcel as vacant")

    auction_value = _decimal(row.get("auction_assessed_value"))
    if auction_value and conservative_value:
        difference = abs(conservative_value - auction_value) / auction_value
        if difference >= Decimal("0.10"):
            flags.append("auction and current qPublic assessed values differ by at least 10%")

    score = max(0, min(100, score))
    if score >= 75:
        decision = "KEEP"
    elif score <= 25:
        decision = "KILL"
    else:
        decision = "REVIEW"

    return {
        **row,
        "screening_decision": decision,
        "screening_score": score,
        "bid_to_assessed_value_ratio": (
            str(bid_ratio.quantize(Decimal("0.001"))) if bid_ratio is not None else None
        ),
        "acreage_status": acreage_status,
        "screening_reasons": reasons,
        "screening_flags": flags,
    }


def screen_properties(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Screen researched parcels and sort the strongest candidates first."""
    screened = [screen_property(row) for row in rows]
    return sorted(screened, key=lambda row: (-row["screening_score"], row["parcel_id"]))
