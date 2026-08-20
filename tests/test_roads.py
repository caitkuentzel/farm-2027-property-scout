from farm2027_scout.adapters.roads import RoadAccessRecord, polygon_to_paths_distance
from farm2027_scout.due_diligence import verify_keep_parcels_road_access


def test_polygon_to_road_distance_is_measured_from_boundary() -> None:
    parcel = [[[-85.0, 30.0], [-84.999, 30.0], [-84.999, 30.001], [-85.0, 30.001], [-85.0, 30.0]]]
    road = [[[-85.0001, 30.0], [-85.0001, 30.001]]]

    distance = polygon_to_paths_distance(parcel, road)

    assert 9.0 < distance < 10.0


def test_only_keep_rows_receive_road_screening() -> None:
    rings = [[[-85.0, 30.0], [-84.99, 30.0], [-84.99, 30.01], [-85.0, 30.0]]]
    rows = [
        {"parcel_id": "A", "screening_decision": "KEEP", "gis": {"geometry_rings": rings}},
        {"parcel_id": "B", "screening_decision": "REVIEW"},
    ]
    called = []

    def fake_fetch(parcel_id, geometry_rings):
        called.append((parcel_id, geometry_rings))
        return RoadAccessRecord(
            parcel_id,
            "LIKELY_PHYSICAL_FRONTAGE",
            "Cypress Dr",
            "LOCAL",
            7.2,
            "UNVERIFIED",
            "PHYSICAL_MAP_SCREEN_ONLY",
            "https://example.test",
            "test",
        )

    verified = verify_keep_parcels_road_access(rows, fetch=fake_fetch)

    assert called == [("A", rings)]
    assert verified[0]["road_access"]["nearest_road_name"] == "Cypress Dr"
    assert "road_access" not in verified[1]


def test_missing_geometry_is_explicitly_unresolved() -> None:
    rows = [{"parcel_id": "A", "screening_decision": "KEEP", "gis": {"geometry_rings": []}}]

    verified = verify_keep_parcels_road_access(rows)

    assert verified[0]["road_access"]["physical_access_status"] == "UNRESOLVED_NO_PARCEL_GEOMETRY"
    assert verified[0]["road_access"]["legal_access_status"] == "UNVERIFIED"
