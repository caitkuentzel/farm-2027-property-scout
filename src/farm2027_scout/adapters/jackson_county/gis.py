"""Official Florida DOR cadastral geometry lookup for Jackson County parcels."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from farm2027_scout.http import load_json_with_retries

GIS_LAYER_URL = (
    "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/"
    "Florida_Statewide_Cadastral/FeatureServer/0"
)
GIS_QUERY_URL = f"{GIS_LAYER_URL}/query"
JACKSON_DOR_COUNTY_NUMBER = 42
SQUARE_METERS_PER_ACRE = Decimal("4046.8564224")


@dataclass(frozen=True, slots=True)
class GISParcelRecord:
    parcel_id: str
    matched_parcel_id: str
    geometry_acres: Decimal | None
    land_square_feet: Decimal | None
    land_units: Decimal | None
    centroid_latitude: Decimal | None
    centroid_longitude: Decimal | None
    geometry_rings: list[list[list[float]]]
    mapped_address: str | None
    mapped_city: str | None
    geometry_status: str
    source_url: str
    data_vintage: str

    def to_dict(self) -> dict[str, Any]:
        values = asdict(self)
        for field in (
            "geometry_acres",
            "land_square_feet",
            "land_units",
            "centroid_latitude",
            "centroid_longitude",
        ):
            value = values[field]
            values[field] = str(value) if value is not None else None
        return values


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _centroid(geometry: dict[str, Any] | None) -> tuple[Decimal | None, Decimal | None]:
    if not geometry:
        return None, None
    points = [point for ring in geometry.get("rings", []) for point in ring]
    if not points:
        return None, None
    longitude = sum(Decimal(str(point[0])) for point in points) / len(points)
    latitude = sum(Decimal(str(point[1])) for point in points) / len(points)
    return latitude.quantize(Decimal("0.000001")), longitude.quantize(Decimal("0.000001"))


def parse_gis_response(payload: dict[str, Any], parcel_id: str, source_url: str) -> GISParcelRecord:
    """Parse one exact cadastral polygon response and reject ambiguous matches."""
    if payload.get("error"):
        raise RuntimeError(f"Florida cadastral service error: {payload['error']}")
    features = payload.get("features", [])
    if not features:
        return GISParcelRecord(
            parcel_id=parcel_id,
            matched_parcel_id=parcel_id,
            geometry_acres=None,
            land_square_feet=None,
            land_units=None,
            centroid_latitude=None,
            centroid_longitude=None,
            geometry_rings=[],
            mapped_address=None,
            mapped_city=None,
            geometry_status="NOT_FOUND_IN_DOR_LAYER",
            source_url=source_url,
            data_vintage="Florida DOR cadastral 2025; service updated June 2026",
        )

    feature = features[0]
    attributes = feature.get("attributes", {})
    matched_ids = {
        str(item.get("attributes", {}).get("PARCELNO"))
        for item in features
        if item.get("attributes", {}).get("PARCELNO")
    }
    if len(matched_ids) > 1:
        raise RuntimeError(f"GIS query for {parcel_id} returned multiple parcel IDs")
    shape_area = sum(
        (_decimal(item.get("attributes", {}).get("Shape__Area")) or Decimal(0)) for item in features
    )
    geometry_acres = shape_area / SQUARE_METERS_PER_ACRE if shape_area else None
    if geometry_acres is not None:
        geometry_acres = geometry_acres.quantize(Decimal("0.001"))
    geometry = {
        "rings": [
            ring for item in features for ring in (item.get("geometry") or {}).get("rings", [])
        ]
    }
    latitude, longitude = _centroid(geometry)
    matched = next(
        (
            str(attributes[field])
            for field in ("PARCELNO", "PARCEL_ID", "PARCEL_ID_")
            if attributes.get(field)
        ),
        parcel_id,
    )
    return GISParcelRecord(
        parcel_id=parcel_id,
        matched_parcel_id=matched,
        geometry_acres=geometry_acres,
        land_square_feet=_decimal(attributes.get("LND_SQFOOT")),
        land_units=_decimal(attributes.get("NO_LND_UNT")),
        centroid_latitude=latitude,
        centroid_longitude=longitude,
        geometry_rings=geometry["rings"],
        mapped_address=attributes.get("PHY_ADDR1"),
        mapped_city=attributes.get("PHY_CITY"),
        geometry_status=(
            "MULTIPART_POLYGON_CONFIRMED"
            if len(features) > 1 and geometry["rings"]
            else "POLYGON_CONFIRMED"
            if geometry["rings"]
            else "ATTRIBUTES_ONLY"
        ),
        source_url=source_url,
        data_vintage="Florida DOR cadastral 2025; service updated June 2026",
    )


def fetch_gis_parcel(parcel_id: str, *, timeout_seconds: int = 120) -> GISParcelRecord:
    """Retrieve one Jackson County parcel polygon from the official DOR layer."""
    compact = parcel_id.replace("-", "")
    where = f"CO_NO={JACKSON_DOR_COUNTY_NUMBER} AND PARCELNO='{compact}'"
    params = {
        "where": where,
        "outFields": (
            "PARCELNO,PARCEL_ID,PARCEL_ID_,NO_LND_UNT,LND_SQFOOT,PHY_ADDR1,PHY_CITY,Shape__Area"
        ),
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    source_url = f"{GIS_QUERY_URL}?{urlencode(params)}"
    payload = load_json_with_retries(source_url, timeout_seconds=timeout_seconds)
    return parse_gis_response(payload, parcel_id, source_url)
