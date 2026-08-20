"""Parcel coverage calculations for official FEMA and USFWS mapped hazards."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from shapely.geometry import GeometryCollection, Polygon, shape
from shapely.ops import transform, unary_union

from farm2027_scout.adapters.fema import FLOOD_HAZARD_QUERY_URL
from farm2027_scout.adapters.wetlands import NWI_QUERY_URL


@dataclass(frozen=True, slots=True)
class HazardOverlapRecord:
    parcel_id: str
    overlap_status: str
    fema_sfha_coverage_percent: float | None
    mapped_wetlands_coverage_percent: float | None
    combined_mapped_constraint_percent: float | None
    outside_mapped_flood_and_wetland_percent: float | None
    evidence_scope: str
    source_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _signed_area(ring: list[list[float]]) -> float:
    return (
        sum(
            ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1]
            for index in range(len(ring) - 1)
        )
        / 2
    )


def _parcel_geometry(rings: list[list[list[float]]]):
    outer_rings = [Polygon(ring) for ring in rings if _signed_area(ring) < 0]
    hole_rings = [Polygon(ring) for ring in rings if _signed_area(ring) >= 0]
    geometry = unary_union(outer_rings)
    if hole_rings:
        geometry = geometry.difference(unary_union(hole_rings))
    return geometry


def _feature_geometry(payload: dict[str, Any]):
    if payload.get("error"):
        raise RuntimeError(f"Hazard geometry service error: {payload['error']}")
    geometries = [
        shape(feature["geometry"])
        for feature in payload.get("features", [])
        if feature.get("geometry")
    ]
    return unary_union(geometries) if geometries else GeometryCollection()


def _project_meters(geometry, latitude: float):
    longitude_factor = 111_320.0 * math.cos(math.radians(latitude))
    return transform(lambda x, y, z=None: (x * longitude_factor, y * 110_540.0), geometry)


def calculate_hazard_overlap(
    parcel_id: str,
    rings: list[list[list[float]]],
    sfha_payload: dict[str, Any],
    wetlands_payload: dict[str, Any],
    source_urls: list[str],
) -> HazardOverlapRecord:
    """Calculate non-double-counted parcel coverage from returned hazard polygons."""
    parcel = _parcel_geometry(rings)
    if parcel.is_empty or parcel.area == 0:
        raise RuntimeError(f"Parcel {parcel_id} has unusable polygon geometry")
    latitude = parcel.centroid.y
    parcel_meters = _project_meters(parcel, latitude)
    sfha = _project_meters(_feature_geometry(sfha_payload), latitude).intersection(parcel_meters)
    wetlands = _project_meters(_feature_geometry(wetlands_payload), latitude).intersection(
        parcel_meters
    )
    combined = unary_union((sfha, wetlands)).intersection(parcel_meters)
    parcel_area = parcel_meters.area

    def percent(geometry) -> float:
        return round(min(100.0, max(0.0, geometry.area / parcel_area * 100)), 1)

    combined_percent = percent(combined)
    return HazardOverlapRecord(
        parcel_id=parcel_id,
        overlap_status="COVERAGE_CALCULATED",
        fema_sfha_coverage_percent=percent(sfha),
        mapped_wetlands_coverage_percent=percent(wetlands),
        combined_mapped_constraint_percent=combined_percent,
        outside_mapped_flood_and_wetland_percent=round(100.0 - combined_percent, 1),
        evidence_scope="MAP_OVERLAP_SCREEN_ONLY",
        source_urls=source_urls,
    )


def _query_url(base_url: str, where: str, rings: list[list[list[float]]]) -> str:
    geometry = json.dumps(
        {"rings": rings, "spatialReference": {"wkid": 4326}}, separators=(",", ":")
    )
    params = {
        "where": where,
        "geometry": geometry,
        "geometryType": "esriGeometryPolygon",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    return f"{base_url}?{urlencode(params)}"


def fetch_hazard_overlap(
    parcel_id: str, rings: list[list[list[float]]], *, timeout_seconds: int = 120
) -> HazardOverlapRecord:
    """Retrieve hazard polygons and calculate their parcel coverage."""
    if not rings:
        return unresolved_hazard_overlap(parcel_id)
    urls = [
        _query_url(FLOOD_HAZARD_QUERY_URL, "SFHA_TF='T'", rings),
        _query_url(NWI_QUERY_URL, "1=1", rings),
    ]
    payloads = []
    for source_url in urls:
        with urlopen(source_url, timeout=timeout_seconds) as response:
            payloads.append(json.load(response))
    return calculate_hazard_overlap(parcel_id, rings, payloads[0], payloads[1], urls)


def unresolved_hazard_overlap(parcel_id: str) -> HazardOverlapRecord:
    return HazardOverlapRecord(
        parcel_id=parcel_id,
        overlap_status="UNRESOLVED_NO_PARCEL_GEOMETRY",
        fema_sfha_coverage_percent=None,
        mapped_wetlands_coverage_percent=None,
        combined_mapped_constraint_percent=None,
        outside_mapped_flood_and_wetland_percent=None,
        evidence_scope="MAP_OVERLAP_SCREEN_ONLY",
        source_urls=[],
    )
