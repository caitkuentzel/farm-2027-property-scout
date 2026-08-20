"""Official USFWS National Wetlands Inventory parcel screening."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

NWI_SERVICE_URL = (
    "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer"
)
NWI_WETLANDS_LAYER = 0
NWI_WETLANDS_URL = f"{NWI_SERVICE_URL}/{NWI_WETLANDS_LAYER}"
NWI_QUERY_URL = f"{NWI_WETLANDS_URL}/query"


@dataclass(frozen=True, slots=True)
class WetlandsRecord:
    parcel_id: str
    wetlands_screening_status: str
    intersects_mapped_wetlands: bool | None
    intersecting_feature_count: int | None
    wetland_types: list[str]
    classification_codes: list[str]
    evidence_scope: str
    regulatory_delineation_status: str
    source_url: str
    data_vintage: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _attribute(attributes: dict[str, Any], field: str) -> Any:
    """Read either qualified ArcGIS field names or their short aliases."""
    return next(
        (
            value
            for name, value in attributes.items()
            if name == field or name.rsplit(".", 1)[-1] == field
        ),
        None,
    )


def parse_wetlands_response(
    payload: dict[str, Any], parcel_id: str, source_url: str
) -> WetlandsRecord:
    """Normalize all NWI features intersecting one parcel polygon."""
    if payload.get("error"):
        raise RuntimeError(f"USFWS NWI service error: {payload['error']}")
    features = payload.get("features", [])
    attributes = [feature.get("attributes", {}) for feature in features]
    wetland_types = sorted(
        {str(value) for item in attributes if (value := _attribute(item, "WETLAND_TYPE"))}
    )
    classification_codes = sorted(
        {str(value) for item in attributes if (value := _attribute(item, "ATTRIBUTE"))}
    )
    return WetlandsRecord(
        parcel_id=parcel_id,
        wetlands_screening_status=(
            "MAPPED_WETLAND_INTERSECTION" if features else "NO_MAPPED_WETLAND_INTERSECTION"
        ),
        intersects_mapped_wetlands=bool(features),
        intersecting_feature_count=len(features),
        wetland_types=wetland_types,
        classification_codes=classification_codes,
        evidence_scope="NWI_MAP_SCREEN_ONLY",
        regulatory_delineation_status="UNVERIFIED",
        source_url=source_url,
        data_vintage="USFWS NWI; current service response",
    )


def fetch_wetlands(
    parcel_id: str, rings: list[list[list[float]]], *, timeout_seconds: int = 120
) -> WetlandsRecord:
    """Query official NWI polygons intersecting a confirmed parcel polygon."""
    if not rings:
        return unresolved_wetlands(parcel_id)
    geometry = json.dumps(
        {"rings": rings, "spatialReference": {"wkid": 4326}}, separators=(",", ":")
    )
    params = {
        "where": "1=1",
        "geometry": geometry,
        "geometryType": "esriGeometryPolygon",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "Wetlands.ATTRIBUTE,Wetlands.WETLAND_TYPE",
        "returnGeometry": "false",
        "f": "json",
    }
    source_url = f"{NWI_QUERY_URL}?{urlencode(params)}"
    with urlopen(source_url, timeout=timeout_seconds) as response:
        payload = json.load(response)
    return parse_wetlands_response(payload, parcel_id, source_url)


def unresolved_wetlands(parcel_id: str) -> WetlandsRecord:
    """Preserve uncertainty when official parcel geometry is unavailable."""
    return WetlandsRecord(
        parcel_id=parcel_id,
        wetlands_screening_status="UNRESOLVED_NO_PARCEL_GEOMETRY",
        intersects_mapped_wetlands=None,
        intersecting_feature_count=None,
        wetland_types=[],
        classification_codes=[],
        evidence_scope="NWI_MAP_SCREEN_ONLY",
        regulatory_delineation_status="UNVERIFIED",
        source_url=NWI_WETLANDS_URL,
        data_vintage="USFWS NWI; not queried without parcel geometry",
    )
