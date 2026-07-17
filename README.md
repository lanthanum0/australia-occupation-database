# Australia Migration Visa and Occupation Database

Snapshot built on 2026-07-16 from official Australian Government sources.

This project creates a local SQLite database and CSV exports for:

- the Department of Home Affairs visa listing, including current and repealed visa categories
- skilled visa occupation-list records from the relevant Federal Register legislative instruments
- ANZSCO code, occupation title, occupation list, visa subclass/stream, assessing authority, and applicable circumstance/caveat where the source provides it

This is a data aid, not migration or legal advice. Always re-check the linked official source before relying on a result.

## Files

- `data/processed/australia_migration.db` - SQLite database
- `data/processed/*.csv` - CSV export of each table/view
- `preview/index.html` - self-contained browser preview with multi-select filters, sorting, pagination and CSV export
- `data/raw/*.docx` - downloaded Federal Register source documents
- `data/raw/homeaffairs_visa_listing.html` - downloaded Home Affairs visa-list source page
- `scripts/build_au_migration_db.py` - rebuilds the database from `data/raw`
- `scripts/build_html_preview.py` - rebuilds the static HTML preview from the SQLite database
- `scripts/inspect_docx_tables.py` - helper for checking Word table extraction
- `queries.sql` - example queries
- `scripts/scrape_state_lists.py` - downloads state/territory occupation nomination lists
- `scripts/parse_state_lists.py` - parses downloaded state lists into the database

## Official Sources

- Home Affairs Visa list: https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing
- Home Affairs Skilled occupation list: https://immi.homeaffairs.gov.au/visas/working-in-australia/skill-occupation-list
- Home Affairs Working in Australia legislative instruments: https://immi.homeaffairs.gov.au/what-we-do/skilled-migration-program/visa-options/legislative-instruments
- LIN 19/051 for subclasses 189, 190, 491 and 485: https://www.legislation.gov.au/F2019L00278/latest
- LIN 19/050 for subclass 407: https://www.legislation.gov.au/F2019L00277/latest
- LIN 24/089 for subclass 482: https://www.legislation.gov.au/F2024L01620/latest
- LIN 24/093 for subclass 186: https://www.legislation.gov.au/F2024L01618/latest
- LIN 19/219 for subclass 494 occupations: https://www.legislation.gov.au/F2019L01403/latest
- LIN 19/260 for subclass 494 assessing authorities: https://www.legislation.gov.au/F2019L01405/latest

## Tables

- `sources`: official source metadata, local raw file path, effective date/register ID where available
- `visa_categories`: Home Affairs visa-list category names
- `visas`: one row per Home Affairs visa-list item
- `visa_subclasses`: normalized subclass numbers extracted from each visa item
- `occupation_lists`: CSOL, MLTSSL, STSOL and ROL labels
- `occupation_records`: visa-to-occupation rows
- `visa_occupation_summary`: summary view by visa subclass, stream and occupation list

## Skilled Occupation Coverage

The occupation records currently cover the skilled visa occupation lists specified by the official legislative-instrument page:

- subclass 186, Direct Entry stream: CSOL, ANZSCO 2022
- subclass 482, Core Skills stream: CSOL, ANZSCO 2022
- subclass 189, Points-tested stream: MLTSSL, ANZSCO 2013
- subclass 190, State or Territory nominated: MLTSSL and STSOL, ANZSCO 2013
- subclass 491, nominated and non-nominated pathways: MLTSSL/STSOL/ROL according to the instrument, ANZSCO 2013
- subclass 485, Post-Vocational Education Work stream: MLTSSL, ANZSCO 2013
- subclass 407: MLTSSL, STSOL and ROL, ANZSCO 2013
- subclass 494: MLTSSL and ROL, ANZSCO 2013

Some visas on the Home Affairs visa list do not have an occupation list. They remain in `visas`, but have no `occupation_records`.

## State/Territory Nomination Lists

In addition to the federal occupation lists, each state and territory publishes their own nomination priority lists for visa subclasses 190 and 491. These are stored in the `state_nominations` table.

Covered states: NSW, VIC, QLD, SA, WA, TAS, NT, ACT

To download and parse state lists:

```bash
pip install requests beautifulsoup4
python3 scripts/scrape_state_lists.py
python3 scripts/parse_state_lists.py
```

The state lists change frequently. Re-run the scripts to refresh.

## Rebuild

```bash
python3 scripts/build_au_migration_db.py
python3 scripts/build_html_preview.py
```

The script only uses the Python standard library. To refresh from the web, download the official pages/documents into `data/raw` using the same filenames, then rerun the build script.

Open `preview/index.html` directly in a browser to inspect and filter the data.
