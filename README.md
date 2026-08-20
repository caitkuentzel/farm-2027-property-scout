# Farm 2027 Property Scout

A human-controlled research tool for finding unusually inexpensive Florida tax-deed properties with land, structures, or useful infrastructure.

The first supported county is **Jackson County, Florida**. The project is deliberately built one tested adapter at a time.

## Milestone 1

Retrieve the live Jackson County tax-deed auction inventory and output:

- auction date
- case number
- parcel ID
- property address
- opening bid
- assessed value

## Safety boundary

This software performs public-record research only. It does **not** register for auctions, place bids, submit payments, purchase property, or make legal/title conclusions. Every financially or legally consequential action requires human review outside this tool.

## Architecture

```text
Auction source -> County adapter -> Normalized auction record -> Local export
```

Milestone 2 adds qPublic lookup and a rate-safe research queue. The queue handles
one parcel at a time, waits between requests, backs off and retries temporary
blocks, checkpoints every successful parcel, and resumes without repeating
completed research. Screening, scoring, and due diligence remain separate later
components rather than one brittle scraper.

## Local development

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Install Chromium once, then retrieve an auction by date:

```bash
python -m playwright install chromium
farm2027-scout --auction-date 08/25/2026 --output jackson-auctions.json
```

The JSON output preserves the public RealAuction detail URL and retrieval time for every parcel.

To enrich the entire live inventory with qPublic data, use the resumable queue:

```bash
farm2027-scout --auction-date 08/25/2026 --include-qpublic --screen --verify-gis \
  --output full-property-research.json
```

The first-pass screen ranks researched parcels from 0–100 and labels them
`KEEP`, `REVIEW`, or `KILL`. A `KILL` is only a research-queue rejection, not a
legal, title, zoning, flood, access, or purchase conclusion.

GIS verification uses the official Florida Department of Revenue statewide
cadastral polygon layer. The geometry is useful for screening but is not a
boundary survey and must not be treated as one.

## Data handling

- Source URLs and retrieval timestamps are preserved.
- Missing fields remain missing; they are never invented.
- Credentials, cookies, browser sessions, `.env` files, private records, and raw exports are excluded from Git.
