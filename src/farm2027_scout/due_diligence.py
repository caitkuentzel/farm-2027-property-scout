"""Due-diligence enrichment for screened property candidates."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from farm2027_scout.adapters.jackson_county.gis import GISParcelRecord, fetch_gis_parcel
from farm2027_scout.adapters.roads import (
    RoadAccessRecord,
    fetch_road_access,
    unresolved_road_access,
)

FetchGIS = Callable[[str], GISParcelRecord]
FetchRoadAccess = Callable[[str, list[list[list[float]]]], RoadAccessRecord]


def verify_keep_parcels_gis(
    rows: list[dict[str, Any]], *, fetch: FetchGIS = fetch_gis_parcel
) -> list[dict[str, Any]]:
    """Attach official GIS facts to KEEP parcels without researching rejected rows."""
    verified = []
    for row in rows:
        if row.get("screening_decision") != "KEEP":
            verified.append(row)
            continue
        parcel_id = row.get("parcel_id")
        if not parcel_id:
            raise RuntimeError("A KEEP row is missing its parcel ID")
        gis = fetch(parcel_id).to_dict()
        qpublic_acres = row.get("acreage")
        gis_acres = gis.get("geometry_acres")
        acreage_match = None
        if qpublic_acres not in (None, "", "0") and gis_acres is not None:
            acreage_match = abs(float(qpublic_acres) - float(gis_acres)) <= 0.02
        verified.append(
            {
                **row,
                "gis": gis,
                "gis_acreage_matches_qpublic": acreage_match,
            }
        )
    return verified


def verify_keep_parcels_road_access(
    rows: list[dict[str, Any]], *, fetch: FetchRoadAccess = fetch_road_access
) -> list[dict[str, Any]]:
    """Attach physical mapped-road evidence to KEEP parcels with GIS geometry."""
    verified = []
    for row in rows:
        if row.get("screening_decision") != "KEEP":
            verified.append(row)
            continue
        parcel_id = row.get("parcel_id")
        if not parcel_id:
            raise RuntimeError("A KEEP row is missing its parcel ID")
        rings = (row.get("gis") or {}).get("geometry_rings", [])
        result = fetch(parcel_id, rings) if rings else unresolved_road_access(parcel_id)
        verified.append({**row, "road_access": result.to_dict()})
    return verified
