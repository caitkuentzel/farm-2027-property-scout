from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from farm2027_scout.adapters.jackson_county.auction import parse_auction_detail


def test_parse_auction_detail() -> None:
    html = Path("tests/fixtures/jackson_auction_detail.html").read_text()
    retrieved_at = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)

    record = parse_auction_detail(html, "https://example.test/details?AID=1", retrieved_at)

    assert record.auction_date == datetime(2026, 8, 25, 11, 0)
    assert record.case_number == "2026-00123"
    assert record.parcel_id == "02-2N-11-0083-00F0-0120"
    assert record.property_address == "VACANT, COMPASS LAKE DR ALFORD, FL 32420"
    assert record.opening_bid == Decimal("2140.20")
    assert record.assessed_value == Decimal("8675.00")
    assert record.retrieved_at == retrieved_at


def test_missing_fields_remain_missing() -> None:
    record = parse_auction_detail("<p>Parcel ID: 123</p>", "https://example.test")

    assert record.parcel_id == "123"
    assert record.opening_bid is None
    assert record.assessed_value is None

