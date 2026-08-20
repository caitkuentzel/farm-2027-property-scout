from farm2027_scout.adapters.hazard_overlap import calculate_hazard_overlap


def _feature(coordinates):
    return {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
    }


def test_overlap_percentages_do_not_double_count_shared_area() -> None:
    parcel = [[[0, 1], [1, 1], [1, 0], [0, 0], [0, 1]]]
    sfha = {"features": [_feature([[0, 0], [0.6, 0], [0.6, 1], [0, 1], [0, 0]])]}
    wetlands = {"features": [_feature([[0.4, 0], [0.8, 0], [0.8, 1], [0.4, 1], [0.4, 0]])]}

    result = calculate_hazard_overlap("A", parcel, sfha, wetlands, ["fema", "nwi"])

    assert result.fema_sfha_coverage_percent == 60.0
    assert result.mapped_wetlands_coverage_percent == 40.0
    assert result.combined_mapped_constraint_percent == 80.0
    assert result.outside_mapped_flood_and_wetland_percent == 20.0


def test_empty_hazard_layers_leave_entire_parcel_outside_constraints() -> None:
    parcel = [[[0, 1], [1, 1], [1, 0], [0, 0], [0, 1]]]

    result = calculate_hazard_overlap(
        "A", parcel, {"features": []}, {"features": []}, ["fema", "nwi"]
    )

    assert result.combined_mapped_constraint_percent == 0.0
    assert result.outside_mapped_flood_and_wetland_percent == 100.0


def test_hazard_service_errors_are_rejected() -> None:
    parcel = [[[0, 1], [1, 1], [1, 0], [0, 0], [0, 1]]]

    try:
        calculate_hazard_overlap(
            "A", parcel, {"error": {"message": "failed"}}, {"features": []}, []
        )
    except RuntimeError as error:
        assert "Hazard geometry service error" in str(error)
    else:
        raise AssertionError("Hazard service error was accepted")
