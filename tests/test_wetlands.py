from farm2027_scout.adapters.wetlands import WetlandsRecord, parse_wetlands_response
from farm2027_scout.due_diligence import verify_keep_parcels_wetlands


def test_intersecting_nwi_types_and_codes_are_preserved() -> None:
    payload = {
        "features": [
            {
                "attributes": {
                    "Wetlands.ATTRIBUTE": "PFO4/SS3B",
                    "Wetlands.WETLAND_TYPE": "Freshwater Forested/Shrub Wetland",
                }
            },
            {
                "attributes": {
                    "Wetlands.ATTRIBUTE": "R5UBH",
                    "Wetlands.WETLAND_TYPE": "Riverine",
                }
            },
        ]
    }

    record = parse_wetlands_response(payload, "A", "https://example.test")

    assert record.intersects_mapped_wetlands is True
    assert record.intersecting_feature_count == 2
    assert record.classification_codes == ["PFO4/SS3B", "R5UBH"]
    assert record.wetland_types == ["Freshwater Forested/Shrub Wetland", "Riverine"]
    assert record.regulatory_delineation_status == "UNVERIFIED"


def test_empty_nwi_response_reports_no_mapped_intersection() -> None:
    record = parse_wetlands_response({"features": []}, "A", "https://example.test")

    assert record.wetlands_screening_status == "NO_MAPPED_WETLAND_INTERSECTION"
    assert record.intersects_mapped_wetlands is False


def test_only_keep_rows_receive_wetlands_screening() -> None:
    rings = [[[-85.0, 30.0], [-84.99, 30.0], [-84.99, 30.01], [-85.0, 30.0]]]
    rows = [
        {"parcel_id": "A", "screening_decision": "KEEP", "gis": {"geometry_rings": rings}},
        {"parcel_id": "B", "screening_decision": "REVIEW"},
    ]

    def fake_fetch(parcel_id, geometry_rings):
        assert geometry_rings == rings
        return WetlandsRecord(
            parcel_id,
            "MAPPED_WETLAND_INTERSECTION",
            True,
            1,
            ["Freshwater Forested/Shrub Wetland"],
            ["PFO4/SS3B"],
            "NWI_MAP_SCREEN_ONLY",
            "UNVERIFIED",
            "https://example.test",
            "test",
        )

    verified = verify_keep_parcels_wetlands(rows, fetch=fake_fetch)

    assert verified[0]["wetlands"]["classification_codes"] == ["PFO4/SS3B"]
    assert "wetlands" not in verified[1]


def test_missing_geometry_is_explicitly_unresolved() -> None:
    rows = [{"parcel_id": "A", "screening_decision": "KEEP", "gis": {"geometry_rings": []}}]

    verified = verify_keep_parcels_wetlands(rows)

    result = verified[0]["wetlands"]
    assert result["wetlands_screening_status"] == "UNRESOLVED_NO_PARCEL_GEOMETRY"
    assert result["intersects_mapped_wetlands"] is None


def test_nwi_service_errors_are_rejected() -> None:
    try:
        parse_wetlands_response({"error": {"message": "failed"}}, "A", "https://example.test")
    except RuntimeError as error:
        assert "USFWS NWI service error" in str(error)
    else:
        raise AssertionError("NWI service error was accepted")
