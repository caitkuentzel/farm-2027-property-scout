from decimal import Decimal
from pathlib import Path

from farm2027_scout.adapters.jackson_county.qpublic import parse_property_report


def test_parse_qpublic_report() -> None:
    html = Path("tests/fixtures/jackson_qpublic_report.html").read_text()
    record = parse_property_report(html, "02-2N-11-0083-00F0-0120", "https://example.test")

    assert record.owner == "YOON EUN HEE"
    assert record.acreage == Decimal("1.136")
    assert record.property_use == "VACANT RESIDENTIAL"
    assert record.building_value == Decimal("0")
    assert record.extra_features_value == Decimal("0")
    assert record.market_value == Decimal("4430")
    assert record.vacant_improved == "VACANT"

