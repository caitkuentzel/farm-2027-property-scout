"""Official FEMA National Flood Hazard Layer parcel screening."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

FEMA_NFHL_SERVICE_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer"
FLOOD_HAZARD_ZONES_LAYER = 28
FLOOD_HAZARD_ZONES_URL = f"{FEMA_NFHL_SERVICE_URL}/{FLOOD_HAZARD_ZONES_LAYER}"
FLOOD_HAZARD_QUERY_URL = f"{FLOOD_HAZARD_ZONES_URL}/query"


@dataclass(frozen=True, slots=True)
class FloodHazardRecord:
    parcel_id: str
    flood_screening_status: str
    flood_zones: list[str]
    zone_subtypes: list[str]
    intersects_special_flood_hazard_area: bool | None
    sfha_values: list[str]
    evidence_scope: str
    source_url: str
    data_vintage: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_flood_response(
    payload: dict[str, Any], parcel_id: str, source_url: str
) -> FloodHazardRecord:
    """Normalize all FEMA flood zones intersecting one parcel polygon."""
    if payload.get("error"):
        raise RuntimeError(f"FEMA NFHL service error: {payload['error']}")
    features = payload.get("features", [])
    attributes = [feature.get("attributes", {}) for feature in features]
    zones = sorted({str(item["FLD_ZONE"]) for item in attributes if item.get("FLD_ZONE")})
    subtypes = sorted({str(item["ZONE_SUBTY"]) for item in attributes if item.get("ZONE_SUBTY")})
    sfha_values = sorted(
        {str(item["SFHA_TF"]).upper() for item in attributes if item.get("SFHA_TF")}
    )
    intersects_sfha = (
        any(value in {"T", "TRUE", "Y", "YES"} for value in sfha_values) if features else None
    )
    return FloodHazardRecord(
        parcel_id=parcel_id,
        flood_screening_status=("FEMA_FLOOD_ZONES_FOUND" if features else "NO_FEMA_ZONE_RETURNED"),
        flood_zones=zones,
        zone_subtypes=subtypes,
        intersects_special_flood_hazard_area=intersects_sfha,
        sfha_values=sfha_values,
        evidence_scope="FEMA_MAP_SCREEN_ONLY",
        source_url=source_url,
        data_vintage="FEMA NFHL; current service response",
    )


def fetch_flood_hazard(
    parcel_id: str, rings: list[list[list[float]]], *, timeout_seconds: int = 120
) -> FloodHazardRecord:
    """Query official FEMA flood-zone polygons intersecting a parcel polygon."""
    if not rings:
        return unresolved_flood_hazard(parcel_id)
    geometry = json.dumps(
        {"rings": rings, "spatialReference": {"wkid": 4326}}, separators=(",", ":")
    )
    params = {
        "where": "1=1",
        "geometry": geometry,
        "geometryType": "esriGeometryPolygon",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF",
        "returnGeometry": "false",
        "f": "json",
    }
    source_url = f"{FLOOD_HAZARD_QUERY_URL}?{urlencode(params)}"
    with urlopen(source_url, timeout=timeout_seconds) as response:
        payload = json.load(response)
    return parse_flood_response(payload, parcel_id, source_url)


def unresolved_flood_hazard(parcel_id: str) -> FloodHazardRecord:
    """Preserve uncertainty when official parcel geometry is unavailable."""
    return FloodHazardRecord(
        parcel_id=parcel_id,
        flood_screening_status="UNRESOLVED_NO_PARCEL_GEOMETRY",
        flood_zones=[],
        zone_subtypes=[],
        intersects_special_flood_hazard_area=None,
        sfha_values=[],
        evidence_scope="FEMA_MAP_SCREEN_ONLY",
        source_url=FLOOD_HAZARD_ZONES_URL,
        data_vintage="FEMA NFHL; not queried without parcel geometry",
    )
