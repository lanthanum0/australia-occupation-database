#\!/usr/bin/env python3
"""
Parse downloaded state/territory occupation lists into a unified SQLite table
and CSV export.

Usage:
    1. First run: python3 scripts/scrape_state_lists.py
    2. Then run:  python3 scripts/parse_state_lists.py

This adds a `state_nominations` table to the existing australia_migration.db.
"""

import csv
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Please install: pip install beautifulsoup4")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "states"
OUT_DIR = ROOT / "data" / "processed"
DB_PATH = OUT_DIR / "australia_migration.db"


@dataclass
class StateOccupation:
    state_code: str           # nsw, vic, qld, sa, wa, tas, nt, act
    state_name: str           # Full name
    anzsco_code: str          # 6-digit ANZSCO code
    occupation_title: str     # Occupation title
    visa_subclass: str        # 190, 491, or both
    stream: Optional[str]     # e.g. "offshore", "onshore", specific stream name
    priority: Optional[str]   # e.g. "high", "medium", "critical skills"
    conditions: Optional[str] # Additional requirements or caveats
    source_url: str           # URL of the state page


# ---------------------------------------------------------------------------
# Parsers for each state. Each returns a list of StateOccupation.
# These are TEMPLATES — each state's website has a different structure,
# so parsers will need to be refined once we see the actual downloaded HTML.
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Normalize whitespace in extracted text."""
    return re.sub(r'\s+', ' ', text).strip()


def parse_nsw(html_path: Path) -> list[StateOccupation]:
    """Parse NSW skilled occupation list."""
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    results = []

    # NSW has two tables: one under "Skilled Nominated visa (subclass 190)"
    # and one under "Skilled Work Regional visa (subclass 491)".
    # Columns: ANZSCO Code (4-digit unit group) | Unit Group Name
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Determine which visa this table is for from the preceding heading
        prev_heading = table.find_previous(["h1", "h2", "h3", "h4", "h5"])
        heading_text = prev_heading.get_text().strip() if prev_heading else ""
        if "190" in heading_text:
            visa = "190"
        elif "491" in heading_text:
            visa = "491"
        else:
            visa = "190/491"

        # Detect header columns
        header_cells = rows[0].find_all(["th", "td"])
        headers = [_clean(c.get_text()).lower() for c in header_cells]

        code_idx = next((i for i, h in enumerate(headers) if "anzsco" in h or "code" in h), None)
        title_idx = next((i for i, h in enumerate(headers) if "group" in h or "occupation" in h or "name" in h), None)

        if code_idx is None or title_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(code_idx, title_idx):
                continue

            code = _clean(cells[code_idx].get_text())
            title = _clean(cells[title_idx].get_text())

            # NSW uses 4-digit ANZSCO unit group codes
            if not re.match(r'^\d{4}$', code):
                continue

            results.append(StateOccupation(
                state_code="nsw",
                state_name="New South Wales",
                anzsco_code=code,
                occupation_title=title,
                visa_subclass=visa,
                stream=None,
                priority=None,
                conditions="Unit group (4-digit ANZSCO)",
                source_url="https://www.nsw.gov.au/visas-and-migration/skilled-visas/nsw-skills-lists",
            ))

    return results


def parse_vic(html_path: Path) -> list[StateOccupation]:
    """Parse Victoria occupation list."""
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    results = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [_clean(c.get_text()).lower() for c in header_cells]

        code_idx = next((i for i, h in enumerate(headers) if "anzsco" in h or "code" in h), None)
        title_idx = next((i for i, h in enumerate(headers) if "occupation" in h or "title" in h), None)

        if code_idx is None or title_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(code_idx, title_idx):
                continue

            code = _clean(cells[code_idx].get_text())
            title = _clean(cells[title_idx].get_text())

            if not re.match(r'^\d{6}$', code):
                continue

            extra = " | ".join(_clean(cells[i].get_text()) for i in range(len(cells))
                              if i not in (code_idx, title_idx) and _clean(cells[i].get_text()))

            results.append(StateOccupation(
                state_code="vic",
                state_name="Victoria",
                anzsco_code=code,
                occupation_title=title,
                visa_subclass="190/491",
                stream=None,
                priority=None,
                conditions=extra or None,
                source_url="https://liveinmelbourne.vic.gov.au/migrate/skilled-migration-visas/visa-nomination-occupation-list",
            ))

    return results


def parse_qld(html_path: Path) -> list[StateOccupation]:
    """Parse Queensland QSOL.

    QLD table has columns:
    ANZSCO Code | Occupation | Skilled Work Regional visa (subclass 491) | Skilled Nominated visa (subclass 190) | Additional information
    """
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    results = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [_clean(c.get_text()).lower() for c in header_cells]

        code_idx = next((i for i, h in enumerate(headers) if "anzsco" in h or "code" in h), None)
        title_idx = next((i for i, h in enumerate(headers) if "occupation" in h or "title" in h), None)
        idx_491 = next((i for i, h in enumerate(headers) if "491" in h), None)
        idx_190 = next((i for i, h in enumerate(headers) if "190" in h), None)
        info_idx = next((i for i, h in enumerate(headers) if "additional" in h or "info" in h), None)

        if code_idx is None or title_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(code_idx, title_idx):
                continue

            code = _clean(cells[code_idx].get_text())
            title = _clean(cells[title_idx].get_text())

            if not re.match(r'^\d{6}$', code):
                continue

            has_491 = idx_491 is not None and idx_491 < len(cells) and _clean(cells[idx_491].get_text()).lower() in ("yes", "✓", "✔")
            has_190 = idx_190 is not None and idx_190 < len(cells) and _clean(cells[idx_190].get_text()).lower() in ("yes", "✓", "✔")
            info = _clean(cells[info_idx].get_text()) if info_idx and info_idx < len(cells) else None

            if has_491 and has_190:
                visa = "190/491"
            elif has_190:
                visa = "190"
            elif has_491:
                visa = "491"
            else:
                visa = "190/491"  # fallback

            results.append(StateOccupation(
                state_code="qld",
                state_name="Queensland",
                anzsco_code=code,
                occupation_title=title,
                visa_subclass=visa,
                stream=None,
                priority=None,
                conditions=info or None,
                source_url="https://migration.qld.gov.au/skilled-occupation-lists/",
            ))

    return results


def parse_sa(html_path: Path) -> list[StateOccupation]:
    """Parse South Australia occupation list."""
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    results = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [_clean(c.get_text()).lower() for c in header_cells]

        code_idx = next((i for i, h in enumerate(headers) if "anzsco" in h or "code" in h), None)
        title_idx = next((i for i, h in enumerate(headers) if "occupation" in h or "title" in h), None)

        if code_idx is None or title_idx is None:
            continue

        # SA often has a "status" or "availability" column
        status_idx = next((i for i, h in enumerate(headers) if "status" in h or "avail" in h), None)

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(code_idx, title_idx):
                continue

            code = _clean(cells[code_idx].get_text())
            title = _clean(cells[title_idx].get_text())

            if not re.match(r'^\d{6}$', code):
                continue

            status = _clean(cells[status_idx].get_text()) if status_idx and status_idx < len(cells) else None

            extra = " | ".join(_clean(cells[i].get_text()) for i in range(len(cells))
                              if i not in (code_idx, title_idx, status_idx) and _clean(cells[i].get_text()))

            results.append(StateOccupation(
                state_code="sa",
                state_name="South Australia",
                anzsco_code=code,
                occupation_title=title,
                visa_subclass="190/491",
                stream=None,
                priority=status,
                conditions=extra or None,
                source_url="https://www.migration.sa.gov.au/occupation-lists/skilled-occupation-list",
            ))

    return results


def parse_wa(html_path: Path) -> list[StateOccupation]:
    """Parse Western Australia WASMOL."""
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    results = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [_clean(c.get_text()).lower() for c in header_cells]

        code_idx = next((i for i, h in enumerate(headers) if "anzsco" in h or "code" in h), None)
        title_idx = next((i for i, h in enumerate(headers) if "occupation" in h or "title" in h), None)

        if code_idx is None or title_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(code_idx, title_idx):
                continue

            code = _clean(cells[code_idx].get_text())
            title = _clean(cells[title_idx].get_text())

            if not re.match(r'^\d{6}$', code):
                continue

            extra = " | ".join(_clean(cells[i].get_text()) for i in range(len(cells))
                              if i not in (code_idx, title_idx) and _clean(cells[i].get_text()))

            results.append(StateOccupation(
                state_code="wa",
                state_name="Western Australia",
                anzsco_code=code,
                occupation_title=title,
                visa_subclass="190/491",
                stream=None,
                priority=None,
                conditions=extra or None,
                source_url="https://migration.wa.gov.au/services/skilled-migration-western-australia/occupation-list",
            ))

    return results


def parse_tas(html_path: Path) -> list[StateOccupation]:
    """Parse Tasmania occupation list."""
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    results = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [_clean(c.get_text()).lower() for c in header_cells]

        code_idx = next((i for i, h in enumerate(headers) if "anzsco" in h or "code" in h), None)
        title_idx = next((i for i, h in enumerate(headers) if "occupation" in h or "title" in h), None)

        if code_idx is None or title_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(code_idx, title_idx):
                continue

            code = _clean(cells[code_idx].get_text())
            title = _clean(cells[title_idx].get_text())

            if not re.match(r'^\d{6}$', code):
                continue

            extra = " | ".join(_clean(cells[i].get_text()) for i in range(len(cells))
                              if i not in (code_idx, title_idx) and _clean(cells[i].get_text()))

            results.append(StateOccupation(
                state_code="tas",
                state_name="Tasmania",
                anzsco_code=code,
                occupation_title=title,
                visa_subclass="190/491",
                stream=None,
                priority=None,
                conditions=extra or None,
                source_url="https://www.migration.tas.gov.au/skilled_migrants/skilled_occupation_lists",
            ))

    return results


def parse_nt(html_path: Path) -> list[StateOccupation]:
    """Parse Northern Territory occupation list."""
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    results = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [_clean(c.get_text()).lower() for c in header_cells]

        code_idx = next((i for i, h in enumerate(headers) if "anzsco" in h or "code" in h), None)
        title_idx = next((i for i, h in enumerate(headers) if "occupation" in h or "title" in h), None)

        if code_idx is None or title_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(code_idx, title_idx):
                continue

            code = _clean(cells[code_idx].get_text())
            title = _clean(cells[title_idx].get_text())

            if not re.match(r'^\d{6}$', code):
                continue

            extra = " | ".join(_clean(cells[i].get_text()) for i in range(len(cells))
                              if i not in (code_idx, title_idx) and _clean(cells[i].get_text()))

            results.append(StateOccupation(
                state_code="nt",
                state_name="Northern Territory",
                anzsco_code=code,
                occupation_title=title,
                visa_subclass="190/491",
                stream=None,
                priority=None,
                conditions=extra or None,
                source_url="https://theterritory.com.au/migrate/nominating-for-a-visa/skilled-occupation-list",
            ))

    return results


def parse_act(html_path: Path) -> list[StateOccupation]:
    """Parse ACT occupation list."""
    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    results = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all(["th", "td"])
        headers = [_clean(c.get_text()).lower() for c in header_cells]

        code_idx = next((i for i, h in enumerate(headers) if "anzsco" in h or "code" in h), None)
        title_idx = next((i for i, h in enumerate(headers) if "occupation" in h or "title" in h), None)

        if code_idx is None or title_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(code_idx, title_idx):
                continue

            code = _clean(cells[code_idx].get_text())
            title = _clean(cells[title_idx].get_text())

            if not re.match(r'^\d{6}$', code):
                continue

            extra = " | ".join(_clean(cells[i].get_text()) for i in range(len(cells))
                              if i not in (code_idx, title_idx) and _clean(cells[i].get_text()))

            results.append(StateOccupation(
                state_code="act",
                state_name="Australian Capital Territory",
                anzsco_code=code,
                occupation_title=title,
                visa_subclass="190/491",
                stream=None,
                priority=None,
                conditions=extra or None,
                source_url="https://www.act.gov.au/migration/skilled-migrants/act-skilled-nominated-visa-subclass-190/occupation-list",
            ))

    return results


# Registry of parsers
PARSERS = {
    "nsw": parse_nsw,
    "vic": parse_vic,
    "qld": parse_qld,
    "sa": parse_sa,
    "wa": parse_wa,
    "tas": parse_tas,
    "nt": parse_nt,
    "act": parse_act,
}


def build_database(all_records: list[StateOccupation]):
    """Insert state nomination records into the database."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Create table (drop if rebuilding)
    cur.execute("DROP TABLE IF EXISTS state_nominations")
    cur.execute("""
        CREATE TABLE state_nominations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state_code TEXT NOT NULL,
            state_name TEXT NOT NULL,
            anzsco_code TEXT NOT NULL,
            occupation_title TEXT NOT NULL,
            visa_subclass TEXT,
            stream TEXT,
            priority TEXT,
            conditions TEXT,
            source_url TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX idx_state_nom_code ON state_nominations(anzsco_code)")
    cur.execute("CREATE INDEX idx_state_nom_state ON state_nominations(state_code)")

    for rec in all_records:
        cur.execute("""
            INSERT INTO state_nominations
            (state_code, state_name, anzsco_code, occupation_title, visa_subclass,
             stream, priority, conditions, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rec.state_code, rec.state_name, rec.anzsco_code, rec.occupation_title,
            rec.visa_subclass, rec.stream, rec.priority, rec.conditions, rec.source_url
        ))

    conn.commit()
    print(f"\nDatabase updated: {cur.execute('SELECT COUNT(*) FROM state_nominations').fetchone()[0]} records")

    # Export CSV
    csv_path = OUT_DIR / "state_nominations.csv"
    cur.execute("SELECT * FROM state_nominations")
    columns = [desc[0] for desc in cur.description]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(cur.fetchall())
    print(f"CSV exported: {csv_path.relative_to(ROOT)}")

    conn.close()


def main():
    print("=" * 60)
    print("Parsing state/territory occupation lists")
    print("=" * 60)

    all_records = []

    for code, parser_fn in PARSERS.items():
        html_path = RAW_DIR / f"{code}_occupation_list.html"
        if not html_path.exists():
            print(f"  [{code.upper()}] File not found: {html_path.name} — skipping")
            continue

        print(f"  [{code.upper()}] Parsing {html_path.name}... ", end="", flush=True)
        try:
            records = parser_fn(html_path)
            all_records.extend(records)
            print(f"{len(records)} occupations found")
        except Exception as e:
            print(f"ERROR: {e}")

    if not all_records:
        print("\nNo records parsed. The HTML structure may have changed.")
        print("Check the downloaded files in data/raw/states/ and update parsers.")
        sys.exit(1)

    build_database(all_records)

    # Summary
    print("\n" + "=" * 60)
    print("Summary by state:")
    from collections import Counter
    counts = Counter(r.state_code for r in all_records)
    for code, count in sorted(counts.items()):
        print(f"  {code.upper():4s} {count:5d} occupations")
    print(f"  {'TOTAL':4s} {len(all_records):5d}")


if __name__ == "__main__":
    main()
