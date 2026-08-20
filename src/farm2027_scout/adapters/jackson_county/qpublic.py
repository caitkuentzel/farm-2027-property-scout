"""Jackson County qPublic property-report adapter."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

QPUBLIC_URL = (
    "https://qpublic.schneidercorp.com/Application.aspx?"
    "AppID=851&LayerID=15884&PageTypeID=4&KeyValue={parcel_id}"
)


@dataclass(frozen=True, slots=True)
class PropertyRecord:
    parcel_id: str
    owner: str | None
    property_address: str | None
    legal_description: str | None
    property_use: str | None
    acreage: Decimal | None
    building_value: Decimal | None
    extra_features_value: Decimal | None
    land_value: Decimal | None
    agricultural_value: Decimal | None
    market_value: Decimal | None
    assessed_value: Decimal | None
    homestead_status: str | None
    vacant_improved: str | None
    source_url: str
    retrieved_at: datetime

    def to_dict(self) -> dict[str, str | None]:
        values = asdict(self)
        for field in (
            "acreage",
            "building_value",
            "extra_features_value",
            "land_value",
            "agricultural_value",
            "market_value",
            "assessed_value",
        ):
            value = values[field]
            values[field] = str(value) if value is not None else None
        values["retrieved_at"] = self.retrieved_at.isoformat()
        return values


FIELD_ALIASES = {
    "owner": ("owner", "owner name"),
    "property_address": ("location address", "property address", "physical address"),
    "legal_description": ("brief tax description", "legal description"),
    "property_use": ("property use", "property use code", "class"),
    "acreage": ("acreage", "acres"),
    "building_value": ("building value",),
    "extra_features_value": ("extra features value", "extra feature value"),
    "land_value": ("land value",),
    "agricultural_value": ("land agricultural value", "agricultural value"),
    "market_value": ("just (market) value", "market value"),
    "assessed_value": ("assessed value",),
    "homestead_status": ("homestead", "homestead status"),
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :\t\r\n")


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _table_fields(soup: BeautifulSoup) -> dict[str, str]:
    fields: dict[str, str] = {}
    for row in soup.select("tr"):
        cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.select("th, td")]
        cells = [cell for cell in cells if cell]
        if len(cells) >= 2:
            fields.setdefault(_normalize_label(cells[0]), cells[1])
    return fields


def _text_field(text: str, aliases: tuple[str, ...]) -> str | None:
    labels = tuple(label for group in FIELD_ALIASES.values() for label in group)
    stop = "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
    for label in aliases:
        match = re.search(
            rf"(?is)\b{re.escape(label)}\b\s*:?\s*(.+?)(?=\s+(?:{stop})\b\s*:?|$)",
            text,
        )
        if match:
            return _clean(match.group(1))
    return None


def _value(fields: dict[str, str], text: str, name: str) -> str | None:
    for alias in FIELD_ALIASES[name]:
        normalized = _normalize_label(alias)
        if normalized in fields:
            return fields[normalized]
    return _text_field(text, FIELD_ALIASES[name])


def _without_note(value: str | None) -> str | None:
    if not value:
        return value
    return _clean(re.split(r"\s*\(Note:", value, maxsplit=1, flags=re.I)[0])


def _primary_owner(soup: BeautifulSoup) -> str | None:
    lines = [_clean(line) for line in soup.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if line]
    for index, line in enumerate(lines[:-1]):
        if _normalize_label(line) == "primary owner":
            return lines[index + 1]
    return None


def _decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    match = re.search(r"-?[0-9][0-9,]*(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return Decimal(match.group().replace(",", ""))
    except InvalidOperation:
        return None


def parse_property_report(html: str, parcel_id: str, source_url: str) -> PropertyRecord:
    """Parse one qPublic property report without filling unknown fields."""
    soup = BeautifulSoup(html, "html.parser")
    text = _clean(soup.get_text(" ", strip=True))
    fields = _table_fields(soup)
    property_use = _value(fields, text, "property_use")
    building_value = _decimal(_value(fields, text, "building_value"))
    extra_features_value = _decimal(_value(fields, text, "extra_features_value"))
    vacant_improved = None
    if property_use and "vac" in property_use.lower():
        vacant_improved = "VACANT"
    elif building_value is not None and building_value > 0:
        vacant_improved = "IMPROVED"
    return PropertyRecord(
        parcel_id=parcel_id,
        owner=_primary_owner(soup) or _value(fields, text, "owner"),
        property_address=_value(fields, text, "property_address"),
        legal_description=_without_note(_value(fields, text, "legal_description")),
        property_use=_without_note(property_use),
        acreage=_decimal(_value(fields, text, "acreage")),
        building_value=building_value,
        extra_features_value=extra_features_value,
        land_value=_decimal(_value(fields, text, "land_value")),
        agricultural_value=_decimal(_value(fields, text, "agricultural_value")),
        market_value=_decimal(_value(fields, text, "market_value")),
        assessed_value=_decimal(_value(fields, text, "assessed_value")),
        homestead_status=_value(fields, text, "homestead_status"),
        vacant_improved=vacant_improved,
        source_url=source_url,
        retrieved_at=datetime.now(UTC),
    )


def fetch_properties(parcel_ids: list[str], *, headless: bool = True) -> list[PropertyRecord]:
    """Retrieve public Jackson County qPublic reports in one browser session."""
    records: list[PropertyRecord] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            )
        )
        for parcel_id in parcel_ids:
            url = QPUBLIC_URL.format(parcel_id=quote(parcel_id, safe="-"))
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2500)
            body = _clean(page.locator("body").inner_text())
            if "sorry, you have been blocked" in body.lower():
                raise RuntimeError("qPublic blocked the browser session")
            records.append(parse_property_report(page.content(), parcel_id, page.url))
        browser.close()
    return records


def fetch_property(parcel_id: str, *, headless: bool = True) -> PropertyRecord:
    """Retrieve one public Jackson County qPublic report."""
    return fetch_properties([parcel_id], headless=headless)[0]
