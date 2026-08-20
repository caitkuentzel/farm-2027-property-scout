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

Later milestones will add qPublic lookup, screening, scoring, and due diligence as separate components rather than one brittle scraper.

## Local development

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

The live inventory command will be documented when the Jackson County adapter is complete.

## Data handling

- Source URLs and retrieval timestamps are preserved.
- Missing fields remain missing; they are never invented.
- Credentials, cookies, browser sessions, `.env` files, private records, and raw exports are excluded from Git.
