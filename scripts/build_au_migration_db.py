#!/usr/bin/env python3
import csv
import html
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from inspect_docx_tables import tables

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
DB_PATH = OUT_DIR / "australia_migration.db"

HOMEAFFAIRS_BASE = "https://immi.homeaffairs.gov.au"


SOURCES = [
    {
        "id": "homeaffairs_visa_listing",
        "title": "Visa list",
        "publisher": "Australian Government Department of Home Affairs",
        "source_type": "homeaffairs_page",
        "official_url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing",
        "local_file": "data/raw/homeaffairs_visa_listing.html",
        "last_updated": "2025-10-09 12:39",
        "effective_from": None,
        "register_id": None,
    },
    {
        "id": "homeaffairs_skill_occupation_list",
        "title": "Skilled occupation list",
        "publisher": "Australian Government Department of Home Affairs",
        "source_type": "homeaffairs_page",
        "official_url": "https://immi.homeaffairs.gov.au/visas/working-in-australia/skill-occupation-list",
        "local_file": "data/raw/homeaffairs_skill_occupation_list.html",
        "last_updated": "2025-08-06 13:33",
        "effective_from": None,
        "register_id": None,
    },
    {
        "id": "homeaffairs_legislative_instruments",
        "title": "Working in Australia legislative instruments",
        "publisher": "Australian Government Department of Home Affairs",
        "source_type": "homeaffairs_page",
        "official_url": "https://immi.homeaffairs.gov.au/what-we-do/skilled-migration-program/visa-options/legislative-instruments",
        "local_file": None,
        "last_updated": "2025-01-17 11:12",
        "effective_from": None,
        "register_id": None,
    },
    {
        "id": "lin_19_051",
        "title": "Migration (LIN 19/051: Specification of Occupations and Relevant Assessing Authorities) Instrument 2019",
        "publisher": "Federal Register of Legislation",
        "source_type": "legislative_instrument",
        "official_url": "https://www.legislation.gov.au/F2019L00278/latest",
        "local_file": "data/raw/lin_19_051.docx",
        "last_updated": None,
        "effective_from": "2026-03-28",
        "register_id": "F2026C00265",
    },
    {
        "id": "lin_19_050_407",
        "title": "Migration (LIN 19/050: Specification of Occupations--Subclass 407 Visa) Instrument 2019",
        "publisher": "Federal Register of Legislation",
        "source_type": "legislative_instrument",
        "official_url": "https://www.legislation.gov.au/F2019L00277/latest",
        "local_file": "data/raw/lin_19_050_407.docx",
        "last_updated": None,
        "effective_from": "2024-12-14",
        "register_id": "F2025C00058",
    },
    {
        "id": "lin_24_089_482",
        "title": "Migration (Specification of Occupations--Subclass 482 Visa) Instrument 2024",
        "publisher": "Federal Register of Legislation",
        "source_type": "legislative_instrument",
        "official_url": "https://www.legislation.gov.au/F2024L01620/latest",
        "local_file": "data/raw/lin_24_089_482.docx",
        "last_updated": None,
        "effective_from": "2025-11-07",
        "register_id": "F2025C01064",
    },
    {
        "id": "lin_24_093_186",
        "title": "Migration (Specification of Occupations and Relevant Assessing Authorities--Subclass 186 Visa) Instrument 2024",
        "publisher": "Federal Register of Legislation",
        "source_type": "legislative_instrument",
        "official_url": "https://www.legislation.gov.au/F2024L01618/latest",
        "local_file": "data/raw/lin_24_093_186.docx",
        "last_updated": None,
        "effective_from": "2026-03-28",
        "register_id": "F2026C00263",
    },
    {
        "id": "lin_19_219_494_occupations",
        "title": "Migration (LIN 19/219: Occupations for Subclass 494 Visas) Instrument 2019",
        "publisher": "Federal Register of Legislation",
        "source_type": "legislative_instrument",
        "official_url": "https://www.legislation.gov.au/F2019L01403/latest",
        "local_file": "data/raw/lin_19_219_494_occupations.docx",
        "last_updated": None,
        "effective_from": "2024-12-14",
        "register_id": "F2025C00059",
    },
    {
        "id": "lin_19_260_494_assessing",
        "title": "Migration (LIN 19/260: Assessing Authorities for Subclass 494 Visas) Instrument 2019",
        "publisher": "Federal Register of Legislation",
        "source_type": "legislative_instrument",
        "official_url": "https://www.legislation.gov.au/F2019L01405/latest",
        "local_file": "data/raw/lin_19_260_494_assessing.docx",
        "last_updated": None,
        "effective_from": "2026-03-28",
        "register_id": "F2026C00264",
    },
]

OCCUPATION_LISTS = {
    "CSOL": "Core Skills Occupation List",
    "MLTSSL": "Medium and Long-term Strategic Skills List",
    "STSOL": "Short-term Skilled Occupation List",
    "ROL": "Regional Occupation List",
}


@dataclass
class Occupation:
    title: str
    anzsco_code: str
    source_row: int


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            self._href = attrs.get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            if text:
                self.links.append((self._href, text))
            self._href = None
            self._text = []


def normalize_title(value):
    return " ".join((value or "").strip().lower().split())


def source_path(source_id):
    item = next(src for src in SOURCES if src["id"] == source_id)
    return ROOT / item["local_file"]


def load_docx_tables(source_id):
    path = source_path(source_id)
    if not path.exists():
        raise FileNotFoundError(path)
    return list(tables(path))


def parse_occupation_table(rows):
    records = []
    for row in rows:
        if not row or not row[0].strip().isdigit():
            continue
        if len(row) < 3:
            continue
        records.append(Occupation(title=row[1].strip(), anzsco_code=row[2].strip(), source_row=int(row[0])))
    return records


def parse_authority_table(rows, has_code=True):
    authority_by_code_title = {}
    authority_by_title = {}
    for row in rows:
        if not row or not row[0].strip().isdigit():
            continue
        if has_code and len(row) >= 4:
            title = row[1].strip()
            code = row[2].strip()
            authority = row[3].strip()
            authority_by_code_title[(code, normalize_title(title))] = authority
            authority_by_title[normalize_title(title)] = authority
        elif not has_code and len(row) >= 3:
            title = row[1].strip()
            authority = row[2].strip()
            authority_by_title[normalize_title(title)] = authority
    return authority_by_code_title, authority_by_title


def parse_abbreviations(rows):
    abbreviations = {}
    for row in rows:
        if not row or not row[0].strip().isdigit() or len(row) < 3:
            continue
        abbreviations[row[1].strip()] = row[2].strip()
    return abbreviations


def expand_authority(raw, abbreviations):
    if not raw:
        return None
    expanded = raw
    for code, full in sorted(abbreviations.items(), key=lambda item: -len(item[0])):
        expanded = re.sub(rf"\b{re.escape(code)}\b", f"{code} ({full})", expanded)
    return expanded


def parse_circumstances(rows):
    items = {}
    for row in rows:
        if row and row[0].strip().isdigit() and len(row) >= 2:
            items[row[0].strip()] = row[1].strip()
    return items


def extract_hidden_schema(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r'id="ctl00_PlaceHolderMain_PageSchemaHiddenField_Input"\s+value="([^"]*)"',
        text,
    )
    if not match:
        raise ValueError(f"Could not find PageSchemaHiddenField in {path}")
    return json.loads(html.unescape(match.group(1)))


def parse_visa_listing():
    schema = extract_hidden_schema(RAW_DIR / "homeaffairs_visa_listing.html")
    categories = []
    for order, block in enumerate(schema.get("content", []), 1):
        category = " ".join(html.unescape(block.get("text", "")).split())
        if not category:
            continue
        parser = AnchorParser()
        parser.feed(html.unescape(block.get("block", "")))
        visas = []
        for href, name in parser.links:
            subclasses = re.findall(r"\b\d{3}\b", name)
            official_url = href
            if official_url.startswith("/"):
                official_url = HOMEAFFAIRS_BASE + official_url
            visas.append(
                {
                    "category": category,
                    "name": html.unescape(name).replace("\u00a0", " "),
                    "official_url": official_url,
                    "subclasses": subclasses,
                    "status": "repealed"
                    if category.lower() == "repealed visas" or "/repealed-visas/" in href
                    else "current",
                }
            )
        categories.append({"name": category, "sort_order": order, "visas": visas})
    return categories


def setup_db(conn):
    conn.executescript(
        """
        DROP VIEW IF EXISTS visa_occupation_summary;
        DROP TABLE IF EXISTS occupation_records;
        DROP TABLE IF EXISTS occupation_lists;
        DROP TABLE IF EXISTS visa_subclasses;
        DROP TABLE IF EXISTS visas;
        DROP TABLE IF EXISTS visa_categories;
        DROP TABLE IF EXISTS sources;

        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            publisher TEXT NOT NULL,
            source_type TEXT NOT NULL,
            official_url TEXT NOT NULL,
            local_file TEXT,
            last_updated TEXT,
            effective_from TEXT,
            register_id TEXT,
            retrieved_at TEXT NOT NULL
        );

        CREATE TABLE visa_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL
        );

        CREATE TABLE visas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            official_url TEXT NOT NULL,
            source_id TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES visa_categories(id),
            FOREIGN KEY (source_id) REFERENCES sources(id)
        );

        CREATE TABLE visa_subclasses (
            visa_id INTEGER NOT NULL,
            subclass TEXT NOT NULL,
            PRIMARY KEY (visa_id, subclass),
            FOREIGN KEY (visa_id) REFERENCES visas(id)
        );

        CREATE TABLE occupation_lists (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE occupation_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visa_subclass TEXT NOT NULL,
            visa_name TEXT NOT NULL,
            visa_stream TEXT,
            list_code TEXT NOT NULL,
            list_name TEXT NOT NULL,
            anzsco_version TEXT,
            occupation_title TEXT NOT NULL,
            anzsco_code TEXT NOT NULL,
            assessing_authority TEXT,
            assessing_authority_expanded TEXT,
            applicable_circumstance_code TEXT,
            applicable_circumstance_text TEXT,
            source_id TEXT NOT NULL,
            source_table TEXT,
            source_row INTEGER,
            FOREIGN KEY (list_code) REFERENCES occupation_lists(code),
            FOREIGN KEY (source_id) REFERENCES sources(id)
        );

        CREATE INDEX idx_visas_name ON visas(name);
        CREATE INDEX idx_visa_subclasses_subclass ON visa_subclasses(subclass);
        CREATE INDEX idx_occ_code ON occupation_records(anzsco_code);
        CREATE INDEX idx_occ_title ON occupation_records(occupation_title);
        CREATE INDEX idx_occ_visa ON occupation_records(visa_subclass, visa_stream);
        CREATE INDEX idx_occ_list ON occupation_records(list_code);

        CREATE VIEW visa_occupation_summary AS
        SELECT
            visa_subclass,
            visa_name,
            visa_stream,
            list_code,
            list_name,
            COUNT(*) AS occupation_count
        FROM occupation_records
        GROUP BY visa_subclass, visa_name, visa_stream, list_code, list_name
        ORDER BY CAST(visa_subclass AS INTEGER), visa_stream, list_code;
        """
    )


def insert_sources(conn):
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for source in SOURCES:
        conn.execute(
            """
            INSERT INTO sources (
                id, title, publisher, source_type, official_url, local_file,
                last_updated, effective_from, register_id, retrieved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source["id"],
                source["title"],
                source["publisher"],
                source["source_type"],
                source["official_url"],
                source["local_file"],
                source["last_updated"],
                source["effective_from"],
                source["register_id"],
                retrieved_at,
            ),
        )
    for code, name in OCCUPATION_LISTS.items():
        conn.execute("INSERT INTO occupation_lists (code, name) VALUES (?, ?)", (code, name))


def insert_visas(conn, categories):
    subclass_lookup = {}
    for category in categories:
        cursor = conn.execute(
            "INSERT INTO visa_categories (name, sort_order) VALUES (?, ?)",
            (category["name"], category["sort_order"]),
        )
        category_id = cursor.lastrowid
        for visa in category["visas"]:
            cursor = conn.execute(
                """
                INSERT INTO visas (category_id, name, status, official_url, source_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    category_id,
                    visa["name"],
                    visa["status"],
                    visa["official_url"],
                    "homeaffairs_visa_listing",
                ),
            )
            visa_id = cursor.lastrowid
            for subclass in visa["subclasses"]:
                conn.execute(
                    "INSERT OR IGNORE INTO visa_subclasses (visa_id, subclass) VALUES (?, ?)",
                    (visa_id, subclass),
                )
                subclass_lookup.setdefault(subclass, visa["name"])
    return subclass_lookup


def add_occupation_record(
    conn,
    *,
    visa_subclass,
    visa_name,
    visa_stream,
    list_code,
    occupation,
    anzsco_version,
    source_id,
    source_table,
    authority=None,
    authority_expanded=None,
    circumstance_code=None,
    circumstance_text=None,
):
    conn.execute(
        """
        INSERT INTO occupation_records (
            visa_subclass, visa_name, visa_stream, list_code, list_name,
            anzsco_version, occupation_title, anzsco_code,
            assessing_authority, assessing_authority_expanded,
            applicable_circumstance_code, applicable_circumstance_text,
            source_id, source_table, source_row
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            visa_subclass,
            visa_name,
            visa_stream,
            list_code,
            OCCUPATION_LISTS[list_code],
            anzsco_version,
            occupation.title,
            occupation.anzsco_code,
            authority,
            authority_expanded,
            circumstance_code,
            circumstance_text,
            source_id,
            source_table,
            occupation.source_row,
        ),
    )


def insert_lin_19_051(conn, visa_lookup):
    source_id = "lin_19_051"
    doc_tables = load_docx_tables(source_id)
    list_tables = {
        "MLTSSL": ("table 2", parse_occupation_table(doc_tables[1])),
        "STSOL": ("table 3", parse_occupation_table(doc_tables[2])),
        "ROL": ("table 4", parse_occupation_table(doc_tables[3])),
    }
    authority_by_code_title, authority_by_title = parse_authority_table(doc_tables[5], has_code=True)
    abbreviations = parse_abbreviations(doc_tables[6])

    visa_lists = [
        ("189", "Points-tested stream", ["MLTSSL"]),
        ("491", "Not nominated by a State or Territory government agency", ["MLTSSL"]),
        ("485", "Post-Vocational Education Work stream", ["MLTSSL"]),
        ("190", "State or Territory nominated", ["MLTSSL", "STSOL"]),
        ("491", "State or Territory nominated", ["MLTSSL", "STSOL", "ROL"]),
    ]
    for subclass, stream, list_codes in visa_lists:
        visa_name = visa_lookup.get(subclass, f"Subclass {subclass}")
        for list_code in list_codes:
            table_name, occupations = list_tables[list_code]
            for occupation in occupations:
                authority = authority_by_code_title.get(
                    (occupation.anzsco_code, normalize_title(occupation.title))
                ) or authority_by_title.get(normalize_title(occupation.title))
                add_occupation_record(
                    conn,
                    visa_subclass=subclass,
                    visa_name=visa_name,
                    visa_stream=stream,
                    list_code=list_code,
                    occupation=occupation,
                    anzsco_version="ANZSCO 2013",
                    source_id=source_id,
                    source_table=f"{table_name}; assessing authority table 6",
                    authority=authority,
                    authority_expanded=expand_authority(authority, abbreviations),
                )


def insert_lin_19_050_407(conn, visa_lookup):
    source_id = "lin_19_050_407"
    doc_tables = load_docx_tables(source_id)
    list_tables = {
        "MLTSSL": ("table 1", parse_occupation_table(doc_tables[0])),
        "ROL": ("table 2", parse_occupation_table(doc_tables[1])),
        "STSOL": ("table 3", parse_occupation_table(doc_tables[2])),
    }
    for list_code, (table_name, occupations) in list_tables.items():
        for occupation in occupations:
            add_occupation_record(
                conn,
                visa_subclass="407",
                visa_name=visa_lookup.get("407", "Training visa (subclass 407)"),
                visa_stream="Training visa",
                list_code=list_code,
                occupation=occupation,
                anzsco_version="ANZSCO 2013",
                source_id=source_id,
                source_table=table_name,
            )


def insert_lin_24_089_482(conn, visa_lookup):
    source_id = "lin_24_089_482"
    doc_tables = load_docx_tables(source_id)
    circumstances = parse_circumstances(doc_tables[1])
    for row in doc_tables[0]:
        if not row or not row[0].strip().isdigit() or len(row) < 4:
            continue
        occupation = Occupation(title=row[1].strip(), anzsco_code=row[2].strip(), source_row=int(row[0]))
        circumstance_code = row[3].strip() or None
        add_occupation_record(
            conn,
            visa_subclass="482",
            visa_name=visa_lookup.get("482", "Skills in Demand (subclass 482)"),
            visa_stream="Core Skills stream",
            list_code="CSOL",
            occupation=occupation,
            anzsco_version="ANZSCO 2022",
            source_id=source_id,
            source_table="table 1; applicable circumstances table 2",
            circumstance_code=circumstance_code,
            circumstance_text=circumstances.get(circumstance_code),
        )


def insert_lin_24_093_186(conn, visa_lookup):
    source_id = "lin_24_093_186"
    doc_tables = load_docx_tables(source_id)
    circumstances = parse_circumstances(doc_tables[1])
    abbreviations = parse_abbreviations(doc_tables[2])
    for row in doc_tables[0]:
        if not row or not row[0].strip().isdigit() or len(row) < 5:
            continue
        occupation = Occupation(title=row[1].strip(), anzsco_code=row[2].strip(), source_row=int(row[0]))
        authority = row[3].strip() or None
        circumstance_code = row[4].strip() or None
        add_occupation_record(
            conn,
            visa_subclass="186",
            visa_name=visa_lookup.get("186", "Employer Nomination Scheme (subclass 186)"),
            visa_stream="Direct Entry stream",
            list_code="CSOL",
            occupation=occupation,
            anzsco_version="ANZSCO 2022",
            source_id=source_id,
            source_table="table 1; applicable circumstances table 2; assessing authority abbreviations table 3",
            authority=authority,
            authority_expanded=expand_authority(authority, abbreviations),
            circumstance_code=circumstance_code,
            circumstance_text=circumstances.get(circumstance_code),
        )


def insert_494(conn, visa_lookup):
    occupations_source = "lin_19_219_494_occupations"
    assessing_source = "lin_19_260_494_assessing"
    occupations_tables = load_docx_tables(occupations_source)
    assessing_tables = load_docx_tables(assessing_source)
    occupation_lists = {
        "MLTSSL": ("occupation table 1", parse_occupation_table(occupations_tables[0])),
        "ROL": ("occupation table 2", parse_occupation_table(occupations_tables[1])),
    }
    authority_tables = {
        "MLTSSL": parse_authority_table(assessing_tables[0], has_code=False)[1],
        "ROL": parse_authority_table(assessing_tables[1], has_code=False)[1],
    }
    abbreviations = parse_abbreviations(assessing_tables[3])
    for list_code, (table_name, occupations) in occupation_lists.items():
        authorities = authority_tables[list_code]
        for occupation in occupations:
            authority = authorities.get(normalize_title(occupation.title))
            add_occupation_record(
                conn,
                visa_subclass="494",
                visa_name=visa_lookup.get(
                    "494", "Skilled Employer Sponsored Regional (provisional) visa (subclass 494)"
                ),
                visa_stream="Employer sponsored regional",
                list_code=list_code,
                occupation=occupation,
                anzsco_version="ANZSCO 2013",
                source_id=occupations_source,
                source_table=f"{table_name}; assessing authorities from {assessing_source}",
                authority=authority,
                authority_expanded=expand_authority(authority, abbreviations),
            )


def export_csvs(conn):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tables_to_export = [
        "sources",
        "visa_categories",
        "visas",
        "visa_subclasses",
        "occupation_lists",
        "occupation_records",
        "visa_occupation_summary",
    ]
    for table in tables_to_export:
        cursor = conn.execute(f"SELECT * FROM {table}")
        with (OUT_DIR / f"{table}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in cursor.description])
            writer.writerows(cursor.fetchall())


def build():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    try:
        setup_db(conn)
        insert_sources(conn)
        visa_categories = parse_visa_listing()
        visa_lookup = insert_visas(conn, visa_categories)
        insert_lin_19_051(conn, visa_lookup)
        insert_lin_19_050_407(conn, visa_lookup)
        insert_lin_24_089_482(conn, visa_lookup)
        insert_lin_24_093_186(conn, visa_lookup)
        insert_494(conn, visa_lookup)
        conn.commit()
        export_csvs(conn)
    finally:
        conn.close()


def print_summary():
    conn = sqlite3.connect(DB_PATH)
    try:
        for label, query in [
            ("sources", "SELECT COUNT(*) FROM sources"),
            ("visa categories", "SELECT COUNT(*) FROM visa_categories"),
            ("visa records", "SELECT COUNT(*) FROM visas"),
            ("visa subclasses", "SELECT COUNT(*) FROM visa_subclasses"),
            ("occupation records", "SELECT COUNT(*) FROM occupation_records"),
        ]:
            print(f"{label}: {conn.execute(query).fetchone()[0]}")
        print("\nOccupation records by visa/list:")
        for row in conn.execute("SELECT * FROM visa_occupation_summary"):
            print(" | ".join(str(value) if value is not None else "" for value in row))
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        build()
        print_summary()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
