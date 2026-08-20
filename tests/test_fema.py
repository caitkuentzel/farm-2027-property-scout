from farm2027_scout.adapters.fema import FloodHazardRecord, parse_flood_response
from farm2027_scout.due_diligence import verify_keep_parcels_flood_hazard


def test_all_intersecting_fema_zones_are_preserved() -> None:
    payload = {
        "features": [
            {
                "attributes": {
                    "FLD_ZONE": "X",
                    "ZONE_SUBTY": "AREA OF MINIMAL FLOOD HAZARD",
                    "SFHA_TF": "F",
                }
            },
            {"attributes": {"FLD_ZONE": "AE", "ZONE_SUBTY": None, "SFHA_TF": "T"}},
        ]
    }

    record = parse_flood_response(payload, "A", "https://example.test")

    assert record.flood_zones == ["AE", "X"]
    assert record.intersects_special_flood_hazard_area is True
    assert record.sfha_values == ["F", "T"]


def test_only_keep_rows_receive_flood_screening() -> None:
    rings = [[[-85.0, 30.0], [-84.99, 30.0], [-84.99, 30.01], [-85.0, 30.0]]]
    rows = [
        {"parcel_id": "A", "screening_decision": "KEEP", "gis": {"geometry_rings": rings}},
        {"parcel_id": "B", "screening_decision": "REVIEW"},
    ]

    def fake_fetch(parcel_id, geometry_rings):
        assert geometry_rings == rings
        return FloodHazardRecord(
            parcel_id,
            "FEMA_FLOOD_ZONES_FOUND",
            ["X"],
            ["AREA OF MINIMAL FLOOD HAZARD"],
            False,
            ["F"],
            "FEMA_MAP_SCREEN_ONLY",
            "https://example.test",
            "test",
        )

    verified = verify_keep_parcels_flood_hazard(rows, fetch=fake_fetch)

    assert verified[0]["flood_hazard"]["flood_zones"] == ["X"]
    assert "flood_hazard" not in verified[1]


def test_missing_geometry_is_explicitly_unresolved() -> None:
    rows = [{"parcel_id": "A", "screening_decision": "KEEP", "gis": {"geometry_rings": []}}]

    verified = verify_keep_parcels_flood_hazard(rows)

    result = verified[0]["flood_hazard"]
    assert result["flood_screening_status"] == "UNRESOLVED_NO_PARCEL_GEOMETRY"
    assert result["intersects_special_flood_hazard_area"] is None


def test_fema_service_errors_are_rejected() -> None:
    try:
        parse_flood_response({"error": {"message": "failed"}}, "A", "https://example.test")
    except RuntimeError as error:
        assert "FEMA NFHL service error" in str(error)
    else:
        raise AssertionError("FEMA service error was accepted")


def test_empty_fema_response_does_not_claim_no_sfha() -> None:
    record = parse_flood_response({"features": []}, "A", "https://example.test")

    assert record.flood_screening_status == "NO_FEMA_ZONE_RETURNED"
    assert record.intersects_special_flood_hazard_area is None
