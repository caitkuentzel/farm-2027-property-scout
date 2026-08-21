"""Generate a clickable, decision-oriented PDF from the research JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GREEN = colors.HexColor("#173F35")
CREAM = colors.HexColor("#F7F2E7")
PALE = colors.HexColor("#E8EFEA")
INK = colors.HexColor("#202723")
MUTED = colors.HexColor("#5D6862")
RED = colors.HexColor("#A83E32")

STYLES = getSampleStyleSheet()
STYLES.add(ParagraphStyle(name="Cover", parent=STYLES["Title"], fontSize=27, leading=31, textColor=CREAM))
STYLES.add(ParagraphStyle(name="CoverSub", parent=STYLES["BodyText"], fontSize=11, leading=16, textColor=CREAM))
STYLES.add(ParagraphStyle(name="H1x", parent=STYLES["Heading1"], fontSize=19, leading=23, textColor=GREEN, spaceAfter=9))
STYLES.add(ParagraphStyle(name="H2x", parent=STYLES["Heading2"], fontSize=12, leading=15, textColor=GREEN, spaceBefore=7, spaceAfter=4))
STYLES.add(ParagraphStyle(name="Bodyx", parent=STYLES["BodyText"], fontSize=9, leading=12.5, textColor=INK, spaceAfter=5))
STYLES.add(ParagraphStyle(name="Smallx", parent=STYLES["BodyText"], fontSize=7.2, leading=9.3, textColor=MUTED))
STYLES.add(ParagraphStyle(name="Callout", parent=STYLES["BodyText"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=GREEN))


def p(text, style="Bodyx"):
    return Paragraph(str(text), STYLES[style])


def money(value):
    return f"${float(str(value).replace('$', '').replace(',', '')):,.2f}"


def source_link(url, label):
    if not url:
        return label + " unavailable"
    return f'<link href="{url}" color="#176B55"><u>{label}</u></link>'


def address(row):
    raw = (row.get("property_address") or "Address not supplied").replace("*", "").strip()
    return raw.replace("Marianna", " Marianna").strip()


def outside_percent(row):
    value = (row.get("hazard_overlap") or {}).get("outside_mapped_flood_and_wetland_percent")
    return float(value) if value is not None else -1.0


def disposition(row):
    if row.get("screening_decision") == "KILL":
        return "KILL"
    geometry = (row.get("gis") or {}).get("geometry_status", "")
    if "CONFIRMED" not in geometry:
        return "HOLD"
    outside = outside_percent(row)
    if row.get("screening_decision") == "KEEP" and outside >= 80:
        return "ADVANCE"
    return "REVIEW"


def proof_links(row):
    sources = [
        (row.get("auction_source_url"), "Auction"),
        (row.get("qpublic_source_url"), "qPublic"),
        ((row.get("gis") or {}).get("source_url"), "Parcel GIS"),
        ((row.get("road_access") or {}).get("source_url"), "Road"),
        ((row.get("flood_hazard") or {}).get("source_url"), "FEMA"),
        ((row.get("wetlands") or {}).get("source_url"), "Wetlands"),
    ]
    return " | ".join(source_link(url, label) for url, label in sources)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#CBD5CF"))
    canvas.line(0.62 * inch, 0.52 * inch, 7.88 * inch, 0.52 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.62 * inch, 0.34 * inch, "Farm 2027 Property Scout - No transaction performed")
    canvas.drawRightString(7.88 * inch, 0.34 * inch, f"Page {doc.page}")
    canvas.restoreState()


def make_table(rows, widths, header=True):
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C5CEC9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F4")]),
    ]
    if header:
        commands.extend([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), CREAM)])
    table.setStyle(TableStyle(commands))
    return table


def build_report(rows, output):
    ranked = sorted(rows, key=lambda row: ({"ADVANCE": 4, "REVIEW": 3, "HOLD": 2, "KILL": 1}[disposition(row)], outside_percent(row), row.get("screening_score", 0)), reverse=True)
    lead = ranked[0]
    auction_date = str(lead.get("auction_date", "Unknown")).replace("T", " at ")
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output), pagesize=letter, leftMargin=.62*inch, rightMargin=.62*inch, topMargin=.6*inch, bottomMargin=.68*inch, title="Jackson County Property Fact Checker")
    story = []

    cover = Table([[p("FARM 2027 PROPERTY SCOUT", "CoverSub")], [p("Jackson County Tax-Deed<br/>Property Fact Checker", "Cover")], [p(f"Auction: {auction_date}<br/>{len(rows)} parcels screened with public-source evidence", "CoverSub")]], colWidths=[7.26*inch], rowHeights=[.45*inch, 1.42*inch, .9*inch])
    cover.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), GREEN), ("LEFTPADDING", (0,0), (-1,-1), 24), ("RIGHTPADDING", (0,0), (-1,-1), 24), ("TOPPADDING", (0,0), (-1,-1), 12), ("BOTTOMPADDING", (0,0), (-1,-1), 12), ("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
    story += [cover, Spacer(1, .25*inch), p("BOTTOM LINE", "H2x")]
    box = Table([[p("BEST CURRENT NEXT STEP", "Callout"), p(f"<b>{address(lead)}</b><br/>{lead['parcel_id']}<br/>Opening bid {money(lead['opening_bid'])}")]], colWidths=[2.0*inch, 5.26*inch])
    box.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), PALE), ("BOX", (0,0), (-1,-1), 1, GREEN), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 12), ("RIGHTPADDING", (0,0), (-1,-1), 12), ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 10)]))
    story += [box, p("This means investigate first, not bid. The lead parcel has the strongest combination of completed parcel geometry, first-pass economics and mapped usable-area screening in this inventory."), p("STOP BEFORE BIDDING", "H2x"), p("Verify title and surviving liens, legal access, zoning and permitted use, survey boundaries, septic/soil feasibility, utilities, site elevation, flood requirements and jurisdictional wetland status. Opening bid and assessed value are not total cost or market value."), p("This report is public-source screening, not legal, title, survey, zoning, environmental, insurance, appraisal or investment advice.", "Smallx"), PageBreak()]

    story += [p("Decision Board", "H1x"), p("ADVANCE means spend the next due-diligence dollar. REVIEW means a material issue needs resolution. HOLD means the evidence is incomplete. KILL means the first-pass economics or completeness screen failed.")]
    board = [[p("Rank", "Smallx"), p("Status", "Smallx"), p("Property", "Smallx"), p("Bid / assessed", "Smallx"), p("Fact-check summary", "Smallx")]]
    for index, row in enumerate(ranked, 1):
        outside = outside_percent(row)
        geometry = (row.get("gis") or {}).get("geometry_status", "UNRESOLVED")
        summary = f"Geometry: {geometry}. " + (f"Outside mapped flood/wetland layers: {outside:.1f}%." if outside >= 0 else "Parcel-level overlap unresolved.")
        board.append([p(index, "Smallx"), p(f"<b>{disposition(row)}</b>", "Smallx"), p(f"<b>{address(row)}</b><br/>{row['parcel_id']}<br/>Case {row['case_number']}", "Smallx"), p(f"{money(row['opening_bid'])}<br/>{money(row['qpublic_assessed_value'])}", "Smallx"), p(summary, "Smallx")])
    story += [make_table(board, [.35*inch, .68*inch, 2.25*inch, 1.08*inch, 2.9*inch]), PageBreak()]

    finalists = [row for row in ranked if disposition(row) in {"ADVANCE", "REVIEW", "HOLD"}][:3]
    for idx, row in enumerate(finalists, 1):
        flood = row.get("flood_hazard") or {}
        wet = row.get("wetlands") or {}
        road = row.get("road_access") or {}
        overlap = row.get("hazard_overlap") or {}
        story += [p(f"#{idx} - {address(row)}", "H1x")]
        facts = [[p("Auction facts", "Smallx"), p("Property facts", "Smallx")], [p(f"<b>Case:</b> {row['case_number']}<br/><b>Opening bid:</b> {money(row['opening_bid'])}<br/><b>Auction assessed:</b> {money(row['auction_assessed_value'])}"), p(f"<b>Parcel:</b> {row['parcel_id']}<br/><b>qPublic assessed:</b> {money(row['qpublic_assessed_value'])}<br/><b>Acreage:</b> {row.get('acreage') or 'Not established'}")]]
        story += [make_table(facts, [3.63*inch, 3.63*inch]), p("FACT CHECK", "H2x")]
        findings = [[p("Evidence", "Smallx"), p("Finding", "Smallx")],
                    [p("Parcel", "Smallx"), p((row.get("gis") or {}).get("geometry_status", "Unresolved"), "Smallx")],
                    [p("Road", "Smallx"), p(f"Nearest road: {road.get('nearest_road_name') or 'unresolved'}; legal access: {road.get('legal_access_status', 'unresolved')}", "Smallx")],
                    [p("Flood", "Smallx"), p(f"Zones: {', '.join(flood.get('flood_zones') or []) or 'unresolved'}; SFHA intersection: {flood.get('intersects_special_flood_hazard_area', 'unresolved')}", "Smallx")],
                    [p("Wetlands", "Smallx"), p(f"Mapped intersection: {wet.get('intersects_mapped_wetlands', 'unresolved')}; codes: {', '.join(wet.get('classification_codes') or []) or 'unresolved'}", "Smallx")],
                    [p("Combined", "Smallx"), p(f"Mapped constraint: {overlap.get('combined_mapped_constraint_percent', 'unresolved')}%; outside both layers: {overlap.get('outside_mapped_flood_and_wetland_percent', 'unresolved')}%", "Smallx")]]
        story += [make_table(findings, [1.35*inch, 5.91*inch]), p("PROOF LINKS", "H2x"), p(proof_links(row), "Smallx"), p("Legal description", "H2x"), p(row.get("legal_description") or "Not supplied", "Smallx")]
        if idx < len(finalists):
            story.append(PageBreak())

    story += [PageBreak(), p("Final Gate: Documentary Proof Required", "H1x")]
    gates = [[p("Gate", "Smallx"), p("Required proof before any bid", "Smallx"), p("Status", "Smallx")]]
    for name, proof in [("Title/liens", "Current title search and tax-deed file; identify surviving encumbrances."), ("Legal access", "Recorded frontage/easement confirmation from title and survey."), ("Zoning", "Written county confirmation of use, lot status, setbacks and minimum dwelling."), ("Survey", "Boundary, encroachments, easements and usable area."), ("Septic/soil", "Qualified feasibility review plus well/utility availability."), ("Flood/wetland", "Site elevation and regulatory review; delineation if warranted."), ("Inspection", "Public-right-of-way visit and documented physical condition."), ("Auction re-check", "Reconfirm parcel, case, status, terms and opening bid immediately before auction.")]:
        gates.append([p(f"<b>{name}</b>", "Smallx"), p(proof, "Smallx"), p(f"<font color='#A83E32'><b>OPEN</b></font>", "Smallx")])
    story += [make_table(gates, [1.3*inch, 5.06*inch, .9*inch]), p("Evidence limits", "H2x"), p("FEMA mapping is not an elevation certificate. National Wetlands Inventory mapping is not a jurisdictional delineation. Road-centerline proximity is not legal access. Area outside two mapped layers is not automatically buildable. Assessed value is not market value."), p(f"DECISION: Investigate {address(lead)} first. Do not bid until every gate above is closed with documentary proof.", "Callout")]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = json.loads(args.input.read_text())
    if not rows:
        raise SystemExit("Research JSON contains no property records")
    build_report(rows, args.output)
    if args.output.stat().st_size < 10_000:
        raise SystemExit("Generated PDF is unexpectedly small")


if __name__ == "__main__":
    main()
