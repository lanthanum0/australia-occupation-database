#\!/usr/bin/env python3
"""
Download state/territory skilled occupation nomination lists.

Each state publishes their own list of occupations they are willing to
nominate for visa subclasses 190 and 491. This script downloads the raw
source pages/files into data/raw/states/ for subsequent parsing.

Usage:
    python3 scripts/scrape_state_lists.py

Requires: requests, beautifulsoup4
    pip install requests beautifulsoup4
"""

import json
import sys
import time
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Please install dependencies: pip install requests beautifulsoup4")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "states"
RAW_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# --- State source URLs ---
# These may change over time; update as needed.

SOURCES = {
    "nsw": {
        "name": "New South Wales",
        "url": "https://www.nsw.gov.au/visas-and-migration/skilled-visas/nsw-skills-lists",
        "type": "html",
        "notes": "Occupation lists for 190 and 491 as HTML tables",
    },
    "vic": {
        "name": "Victoria",
        "url": "https://liveinmelbourne.vic.gov.au/migrate/skilled-migration-visas/visa-nomination-occupation-list",
        "type": "html",
        "notes": "ROI occupation list for 190 and 491",
    },
    "qld": {
        "name": "Queensland",
        "url": "https://migration.qld.gov.au/skilled-occupation-lists/",
        "type": "html",
        "notes": "QSOL for 190 and 491",
    },
    "sa": {
        "name": "South Australia",
        "url": "https://www.migration.sa.gov.au/occupation-lists/skilled-occupation-list",
        "type": "html",
        "notes": "SA skilled occupation list",
    },
    "wa": {
        "name": "Western Australia",
        "url": "https://migration.wa.gov.au/services/skilled-migration-western-australia/occupation-list",
        "type": "html",
        "notes": "WASMOL Graduate and General streams",
    },
    "tas": {
        "name": "Tasmania",
        "url": "https://www.migration.tas.gov.au/skilled_migrants/skilled_occupation_lists",
        "type": "html",
        "notes": "Tasmania skilled occupation list",
    },
    "nt": {
        "name": "Northern Territory",
        "url": "https://theterritory.com.au/migrate/nominating-for-a-visa/skilled-occupation-list",
        "type": "html",
        "notes": "NT MINT nomination occupation list",
    },
    "act": {
        "name": "Australian Capital Territory",
        "url": "https://www.act.gov.au/migration/skilled-migrants/act-skilled-nominated-visa-subclass-190/occupation-list",
        "type": "html",
        "notes": "ACT Critical Skills List / Matrix occupation list",
    },
}


def download_page(state_code: str, info: dict) -> Path:
    """Download a state page and save to disk."""
    url = info["url"]
    out_path = RAW_DIR / f"{state_code}_occupation_list.html"

    print(f"  Downloading {info['name']}... ", end="", flush=True)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        print(f"OK ({len(resp.content):,} bytes)")
        return out_path
    except requests.RequestException as e:
        print(f"FAILED: {e}")
        return None


def main():
    print("=" * 60)
    print("Downloading state/territory occupation lists")
    print("=" * 60)

    results = {}
    for code, info in SOURCES.items():
        path = download_page(code, info)
        results[code] = {
            "name": info["name"],
            "url": info["url"],
            "downloaded": path is not None,
            "local_file": str(path.relative_to(ROOT)) if path else None,
        }
        time.sleep(1)  # polite delay

    # Save metadata
    meta_path = RAW_DIR / "download_metadata.json"
    meta_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nMetadata saved to {meta_path.relative_to(ROOT)}")

    success = sum(1 for v in results.values() if v["downloaded"])
    print(f"\nDone: {success}/{len(results)} states downloaded successfully.")

    if success < len(results):
        print("\nFailed states may need manual download or URL updates.")
        print("Check the URLs in SOURCES dict and update if the sites have changed.")


if __name__ == "__main__":
    main()
