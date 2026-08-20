from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from farm2027_scout.adapters.jackson_county.qpublic import PropertyRecord
from farm2027_scout.models import AuctionRecord
from farm2027_scout.research_queue import research_inventory, research_properties


def _auction(parcel_id: str) -> AuctionRecord:
    return AuctionRecord(
        auction_date=datetime(2026, 8, 25, tzinfo=UTC),
        case_number="1 OF 2026",
        parcel_id=parcel_id,
        property_address="Test Road",
        opening_bid=Decimal(1000),
        assessed_value=Decimal(4000),
        source_url="https://auction.test",
        retrieved_at=datetime.now(UTC),
    )


def _property(parcel_id: str) -> PropertyRecord:
    return PropertyRecord(
        parcel_id=parcel_id,
        owner="TEST OWNER",
        property_address="Test Road",
        legal_description="LOT 1",
        property_use="VACANT RESIDENTIAL",
        acreage=Decimal("1.25"),
        building_value=Decimal(0),
        extra_features_value=Decimal(0),
        land_value=Decimal(5000),
        agricultural_value=Decimal(0),
        market_value=Decimal(5000),
        assessed_value=Decimal(4500),
        homestead_status="N",
        vacant_improved="VACANT",
        source_url="https://qpublic.test",
        retrieved_at=datetime.now(UTC),
    )


def test_queue_delays_checkpoints_and_preserves_both_assessments(tmp_path: Path) -> None:
    checkpoint = tmp_path / "research.json"
    sleeps: list[float] = []
    rows = research_properties(
        [_auction("A"), _auction("B")],
        checkpoint,
        fetch=_property,
        sleep=sleeps.append,
        delay_seconds=12,
    )

    assert checkpoint.exists()
    assert [row["parcel_id"] for row in rows] == ["A", "B"]
    assert sleeps == [12]
    assert rows[0]["auction_assessed_value"] == "4000"
    assert rows[0]["qpublic_assessed_value"] == "4500"
    assert "assessed_value" not in rows[0]


def test_queue_retries_with_exponential_backoff(tmp_path: Path) -> None:
    attempts = 0
    sleeps: list[float] = []

    def blocked_then_ok(parcel_id: str) -> PropertyRecord:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("qPublic blocked the browser session")
        return _property(parcel_id)

    rows = research_properties(
        [_auction("A")],
        tmp_path / "research.json",
        fetch=blocked_then_ok,
        sleep=sleeps.append,
        max_retries=3,
        backoff_seconds=10,
    )

    assert len(rows) == 1
    assert sleeps == [10, 20]


def test_queue_resumes_without_refetching_completed_parcels(tmp_path: Path) -> None:
    checkpoint = tmp_path / "research.json"
    calls: list[str] = []

    def fetch(parcel_id: str) -> PropertyRecord:
        calls.append(parcel_id)
        return _property(parcel_id)

    research_properties([_auction("A")], checkpoint, fetch=fetch, sleep=lambda _: None)
    rows = research_properties(
        [_auction("A"), _auction("B")], checkpoint, fetch=fetch, sleep=lambda _: None
    )

    assert calls == ["A", "B"]
    assert [row["parcel_id"] for row in rows] == ["A", "B"]


def test_live_inventory_is_connected_to_research_queue(tmp_path: Path) -> None:
    inventory_dates: list[str | None] = []
    property_calls: list[str] = []

    def inventory_fetch(auction_date: str | None) -> list[AuctionRecord]:
        inventory_dates.append(auction_date)
        return [_auction("A"), _auction("B")]

    def property_fetch(parcel_id: str) -> PropertyRecord:
        property_calls.append(parcel_id)
        return _property(parcel_id)

    rows = research_inventory(
        "08/25/2026",
        tmp_path / "full-research.json",
        inventory_fetch=inventory_fetch,
        property_fetch=property_fetch,
        sleep=lambda _: None,
    )

    assert inventory_dates == ["08/25/2026"]
    assert property_calls == ["A", "B"]
    assert [row["parcel_id"] for row in rows] == ["A", "B"]
