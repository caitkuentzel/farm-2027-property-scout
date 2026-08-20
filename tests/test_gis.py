import json
from pathlib import Path

from farm2027_scout.adapters.jackson_county.gis import (
    JACKSON_DOR_COUNTY_NUMBER,
    parse_gis_response,
)
from farm2027_scout.due_diligence import verify_keep_parcels_gis


def _gis_record():
    payload = json.loads(Path("tests/fixtures/florida_gis_parcel.json").read_text())
    return parse_gis_response(payload, "02-2N-11-0083-00F0-0120", "https://example.test")


def test_parse_official_gis_polygon() -> None:
    record = _gis_record()

    assert str(record.geometry_acres) == "1.136"
    assert str(record.land_square_feet) == "49484.16"
    assert record.geometry_status == "POLYGON_CONFIRMED"
    assert str(record.centroid_latitude) == "30.704000"
    assert str(record.centroid_longitude) == "-85.196000"
    assert len(record.geometry_rings) == 1
    assert JACKSON_DOR_COUNTY_NUMBER == 42


def test_only_keep_rows_receive_gis_verification() -> None:
    rows = [
        {
            "parcel_id": "02-2N-11-0083-00F0-0120",
            "screening_decision": "KEEP",
            "acreage": "1.136",
        },
        {"parcel_id": "B", "screening_decision": "REVIEW", "acreage": "0"},
    ]

    verified = verify_keep_parcels_gis(rows, fetch=lambda _: _gis_record())

    assert verified[0]["gis"]["geometry_acres"] == "1.136"
    assert verified[0]["gis_acreage_matches_qpublic"] is True
    assert "gis" not in verified[1]


def test_ambiguous_gis_matches_are_rejected() -> None:
    payload = json.loads(Path("tests/fixtures/florida_gis_parcel.json").read_text())
    duplicate = json.loads(json.dumps(payload["features"][0]))
    duplicate["attributes"]["PARCELNO"] = "DIFFERENT"
    payload["features"].append(duplicate)

    try:
        parse_gis_response(payload, "A", "https://example.test")
    except RuntimeError as error:
        assert "multiple parcel IDs" in str(error)
    else:
        raise AssertionError("Ambiguous GIS response was accepted")


def test_same_parcel_polygon_parts_are_combined() -> None:
    payload = json.loads(Path("tests/fixtures/florida_gis_parcel.json").read_text())
    payload["features"].append(json.loads(json.dumps(payload["features"][0])))

    record = parse_gis_response(payload, "A", "https://example.test")

    assert record.geometry_status == "MULTIPART_POLYGON_CONFIRMED"
    assert str(record.geometry_acres) == "2.272"


def test_missing_official_polygon_is_preserved() -> None:
    record = parse_gis_response({"features": []}, "A", "https://example.test")

    assert record.geometry_status == "NOT_FOUND_IN_DOR_LAYER"
    assert record.geometry_acres is None
