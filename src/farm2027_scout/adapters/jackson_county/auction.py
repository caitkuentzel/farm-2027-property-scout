"""Jackson County RealAuction public inventory adapter."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright

from farm2027_scout.models import AuctionRecord

BASE_URL = "https://jackson.realtaxdeed.com/"
CALENDAR_URL = urljoin(BASE_URL, "index.cfm?zaction=USER&zmethod=CALENDAR")

LABELS = {
    "auction_date": ("Auction Starts", "Auction Date", "Sale Date"),
    "case_number": ("Case #", "Case Number", "Case No."),
    "certificate_number": ("Certificate #", "Certificate Number", "Certificate No."),
    "parcel_id": ("Parcel ID", "Parcel #", "Parcel Number"),
    "property_address": ("Property Address", "Property Location", "Location"),
    "opening_bid": ("Opening Bid", "Minimum Bid"),
    "assessed_value": ("Assessed Value",),
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :\t\r\n")


def _field(text: str, labels: tuple[str, ...]) -> str | None:
    all_labels = tuple(label for group in LABELS.values() for label in group)
    stop = "|".join(re.escape(label) for label in sorted(all_labels, key=len, reverse=True))
    for label in labels:
        pattern = rf"(?is)\b{re.escape(label)}\s*:?\s*(.+?)(?=\s+(?:{stop})\s*:?|$)"
        match = re.search(pattern, text)
        if match:
            value = _clean(match.group(1))
            if value:
                return value
    return None


def _money(value: str | None) -> Decimal | None:
    if not value:
        return None
    match = re.search(r"\$?\s*([0-9][0-9,]*(?:\.\d{1,2})?)", value)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})(?:\s+(\d{1,2}:\d{2}\s*[AP]M))?", value, re.I)
    if not match:
        return None
    candidate = " ".join(part for part in match.groups() if part)
    fmt = "%m/%d/%Y %I:%M %p" if match.group(2) else "%m/%d/%Y"
    return datetime.strptime(candidate.upper(), fmt)


def parse_auction_detail(html: str, source_url: str, retrieved_at: datetime | None = None) -> AuctionRecord:
    """Parse one public RealAuction detail page into a normalized record."""
    soup = BeautifulSoup(html, "html.parser")
    text = _clean(soup.get_text(" ", strip=True))
    retrieved_at = retrieved_at or datetime.now(UTC)
    return AuctionRecord(
        auction_date=_date(_field(text, LABELS["auction_date"])),
        case_number=_field(text, LABELS["case_number"]),
        parcel_id=_field(text, LABELS["parcel_id"]),
        property_address=_field(text, LABELS["property_address"]),
        opening_bid=_money(_field(text, LABELS["opening_bid"])),
        assessed_value=_money(_field(text, LABELS["assessed_value"])),
        source_url=source_url,
        retrieved_at=retrieved_at,
    )


def parse_auction_preview(html: str, source_url: str) -> list[AuctionRecord]:
    """Parse every auction record embedded in a RealAuction preview page."""
    text = _clean(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    retrieved_at = datetime.now(UTC)
    records = []
    for segment in re.split(r"(?=\bAuction Starts\b)", text, flags=re.I):
        if not re.search(r"\bParcel (?:ID|#|Number)\b", segment, re.I):
            continue
        if not re.search(r"\b(?:Opening|Minimum) Bid\b", segment, re.I):
            continue
        records.append(parse_auction_detail(segment, source_url, retrieved_at))
    return records


def _detail_links(page: Page, auction_date: str | None) -> list[str]:
    page.goto(CALENDAR_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    if auction_date:
        preview = urljoin(
            BASE_URL,
            f"index.cfm?zaction=AUCTION&zmethod=PREVIEW&AUCTIONDATE={auction_date}",
        )
        page.goto(preview, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    hrefs = page.locator("a[href]").evaluate_all(
        "els => els.map(el => el.href).filter(href => "
        "href.toLowerCase().includes('zaction=auction') && "
        "href.toLowerCase().includes('zmethod=details'))"
    )
    return list(dict.fromkeys(hrefs))


def _embedded_records(page: Page) -> list[AuctionRecord]:
    """Extract preview cards anchored by their parcel-specific qPublic links."""
    page_text = _clean(page.locator("body").inner_text())
    auction_date = _date(_field(page_text, LABELS["auction_date"]))
    parcel_links = page.locator("a[href*='KeyValue=']")
    expected_parcels = set(
        parcel_links.evaluate_all(
            "els => els.map(el => new URL(el.href).searchParams.get('KeyValue')).filter(Boolean)"
        )
    )
    records: list[AuctionRecord] = []
    seen: set[str] = set()
    for index in range(parcel_links.count()):
        card_html = parcel_links.nth(index).evaluate(
            """el => {
                let node = el;
                while (node && node !== document.body) {
                    const text = node.innerText || '';
                    if (/Opening Bid/i.test(text) && /Assessed Value/i.test(text) && /Case #/i.test(text)) {
                        return node.outerHTML;
                    }
                    node = node.parentElement;
                }
                return el.parentElement.outerHTML;
            }"""
        )
        record = parse_auction_detail(card_html, page.url)
        if record.auction_date is None and auction_date is not None:
            record = replace(record, auction_date=auction_date)
        if record.parcel_id and record.parcel_id not in seen:
            seen.add(record.parcel_id)
            records.append(record)
    if seen != expected_parcels:
        missing = sorted(expected_parcels - seen)
        raise RuntimeError(f"Failed to parse {len(missing)} linked parcels: {missing}")
    return records


def fetch_inventory(auction_date: str | None = None, *, headless: bool = True) -> list[AuctionRecord]:
    """Retrieve current/upcoming Jackson County public tax-deed inventory."""
    records: list[AuctionRecord] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            )
        )
        links = _detail_links(page, auction_date)
        if links:
            for link in links:
                page.goto(link, wait_until="domcontentloaded")
                page.wait_for_timeout(500)
                records.append(parse_auction_detail(page.content(), page.url))
        else:
            records.extend(_embedded_records(page))
            if not records:
                records.extend(parse_auction_preview(page.content(), page.url))
        browser.close()
    return records
