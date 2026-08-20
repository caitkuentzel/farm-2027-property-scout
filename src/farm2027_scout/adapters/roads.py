"""Physical road-centerline screening using the official Census TIGERweb service."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

ROAD_SERVICE_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/Transportation_LargeScale/MapServer"
)
ROAD_LAYERS = ((0, "PRIMARY"), (1, "SECONDARY"), (2, "LOCAL"))
SEARCH_DISTANCE_METERS = 150.0
LIKELY_FRONTAGE_DISTANCE_METERS = 30.0


@dataclass(frozen=True, slots=True)
class RoadAccessRecord:
    parcel_id: str
    physical_access_status: str
    nearest_road_name: str | None
    nearest_road_class: str | None
    nearest_road_distance_meters: float | None
    legal_access_status: str
    evidence_scope: str
    source_url: str
    data_vintage: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _xy(point: list[float], latitude: float) -> tuple[float, float]:
    longitude, point_latitude = point
    return (
        longitude * 111_320.0 * math.cos(math.radians(latitude)),
        point_latitude * 110_540.0,
    )


def _point_segment_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == dy == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    position = max(
        0.0,
        min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)),
    )
    nearest = (start[0] + position * dx, start[1] + position * dy)
    return math.hypot(point[0] - nearest[0], point[1] - nearest[1])


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]
) -> bool:
    bounding_boxes_overlap = max(min(a[0], b[0]), min(c[0], d[0])) <= min(
        max(a[0], b[0]), max(c[0], d[0])
    ) and max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1]))
    return (
        bounding_boxes_overlap
        and _orientation(a, b, c) * _orientation(a, b, d) <= 0
        and _orientation(c, d, a) * _orientation(c, d, b) <= 0
    )


def _segment_distance(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]
) -> float:
    if _segments_intersect(a, b, c, d):
        return 0.0
    return min(
        _point_segment_distance(a, c, d),
        _point_segment_distance(b, c, d),
        _point_segment_distance(c, a, b),
        _point_segment_distance(d, a, b),
    )


def polygon_to_paths_distance(
    rings: list[list[list[float]]], paths: list[list[list[float]]]
) -> float:
    """Return approximate minimum geodesic distance between polygon and road segments."""
    latitude = sum(point[1] for ring in rings for point in ring) / sum(len(ring) for ring in rings)
    polygon_segments = [
        (_xy(ring[index], latitude), _xy(ring[index + 1], latitude))
        for ring in rings
        for index in range(len(ring) - 1)
    ]
    road_segments = [
        (_xy(path[index], latitude), _xy(path[index + 1], latitude))
        for path in paths
        for index in range(len(path) - 1)
    ]
    return min(
        _segment_distance(*parcel, *road) for parcel in polygon_segments for road in road_segments
    )


def _query_url(layer: int, rings: list[list[list[float]]]) -> str:
    points = [point for ring in rings for point in ring]
    mean_latitude = sum(point[1] for point in points) / len(points)
    latitude_buffer = SEARCH_DISTANCE_METERS / 110_540.0
    longitude_buffer = SEARCH_DISTANCE_METERS / (111_320.0 * math.cos(math.radians(mean_latitude)))
    longitudes, latitudes = [p[0] for p in points], [p[1] for p in points]
    envelope = ",".join(
        str(value)
        for value in (
            min(longitudes) - longitude_buffer,
            min(latitudes) - latitude_buffer,
            max(longitudes) + longitude_buffer,
            max(latitudes) + latitude_buffer,
        )
    )
    params = {
        "where": "1=1",
        "geometry": envelope,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "NAME,BASENAME,MTFCC",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    return f"{ROAD_SERVICE_URL}/{layer}/query?{urlencode(params)}"


def fetch_road_access(
    parcel_id: str, rings: list[list[list[float]]], *, timeout_seconds: int = 120
) -> RoadAccessRecord:
    """Find the nearest official mapped road; this does not establish legal access."""
    if not rings:
        return unresolved_road_access(parcel_id)
    candidates: list[tuple[float, str | None, str, str]] = []
    for layer, road_class in ROAD_LAYERS:
        source_url = _query_url(layer, rings)
        with urlopen(source_url, timeout=timeout_seconds) as response:
            payload = json.load(response)
        if payload.get("error"):
            raise RuntimeError(f"Census TIGERweb service error: {payload['error']}")
        for feature in payload.get("features", []):
            paths = (feature.get("geometry") or {}).get("paths", [])
            if paths:
                attributes = feature.get("attributes", {})
                candidates.append(
                    (
                        polygon_to_paths_distance(rings, paths),
                        attributes.get("NAME") or attributes.get("BASENAME"),
                        road_class,
                        source_url,
                    )
                )
    if not candidates:
        return RoadAccessRecord(
            parcel_id,
            "NO_MAPPED_ROAD_WITHIN_150M",
            None,
            None,
            None,
            "UNVERIFIED",
            "PHYSICAL_MAP_SCREEN_ONLY",
            ROAD_SERVICE_URL,
            "TIGERweb roads; current service response",
        )
    distance, name, road_class, source_url = min(candidates, key=lambda candidate: candidate[0])
    status = (
        "LIKELY_PHYSICAL_FRONTAGE"
        if distance <= LIKELY_FRONTAGE_DISTANCE_METERS
        else "MAPPED_ROAD_NEARBY_REVIEW"
    )
    return RoadAccessRecord(
        parcel_id,
        status,
        name,
        road_class,
        round(distance, 1),
        "UNVERIFIED",
        "PHYSICAL_MAP_SCREEN_ONLY",
        source_url,
        "TIGERweb roads; current service response",
    )


def unresolved_road_access(parcel_id: str) -> RoadAccessRecord:
    return RoadAccessRecord(
        parcel_id,
        "UNRESOLVED_NO_PARCEL_GEOMETRY",
        None,
        None,
        None,
        "UNVERIFIED",
        "PHYSICAL_MAP_SCREEN_ONLY",
        ROAD_SERVICE_URL,
        "TIGERweb roads; not queried without parcel geometry",
    )
