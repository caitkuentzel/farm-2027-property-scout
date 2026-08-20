from farm2027_scout.screening import screen_properties, screen_property


def _row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "parcel_id": "A",
        "opening_bid": "2000",
        "acreage": "1.0",
        "qpublic_assessed_value": "5000",
        "auction_assessed_value": "4500",
        "vacant_improved": "VACANT",
    }
    row.update(changes)
    return row


def test_keep_for_confirmed_land_with_large_bid_discount() -> None:
    result = screen_property(_row())

    assert result["screening_decision"] == "KEEP"
    assert result["screening_score"] == 100
    assert result["bid_to_assessed_value_ratio"] == "0.400"
    assert result["acreage_status"] == "CONFIRMED_1_PLUS_ACRE"


def test_zero_acreage_is_unknown_instead_of_no_land() -> None:
    result = screen_property(_row(acreage="0", opening_bid="2300"))

    assert result["screening_decision"] == "REVIEW"
    assert result["acreage_status"] == "UNKNOWN_REQUIRES_GIS"
    assert any("GIS" in flag for flag in result["screening_flags"])


def test_kill_for_unknown_acreage_and_weak_discount() -> None:
    result = screen_property(
        _row(acreage="0", opening_bid="2100", qpublic_assessed_value="2400")
    )

    assert result["screening_decision"] == "KILL"
    assert result["screening_score"] == 15


def test_results_are_sorted_by_score() -> None:
    rows = screen_properties(
        [
            _row(parcel_id="weak", acreage="0", opening_bid="2100", qpublic_assessed_value="2400"),
            _row(parcel_id="strong"),
        ]
    )

    assert [row["parcel_id"] for row in rows] == ["strong", "weak"]
