#!/usr/bin/env python3
"""
Playwright-based scraper for state/territory occupation lists.

Uses a real Chromium browser to bypass anti-bot protections and handle
JavaScript-rendered pages (SPAs like SA, Cloudflare like ACT).

Usage:
    pip install playwright
    playwright install chromium
    python3 scripts/scrape_state_lists_playwright.py
"""

import json
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
except ImportError:
    sys.exit("Please install: pip install playwright && playwright install chromium")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "states"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# For each state, list candidate URLs to try. The first URL that yields
# a page with ANZSCO codes (6-digit or 4-digit numbers in the text)
# will be saved.
# For each state, list starting URLs. The scraper will explore each,
# and if occupation data isn't on the landing page, will look at all links
# on the page and follow any that look like they might lead to occupation
# lists (containing "occupation", "skilled", "list", etc.)
STATES = {
    "nsw": {
        "name": "New South Wales",
        "start_urls": [
            "https://www.nsw.gov.au/visas-and-migration/skilled-visas/nsw-skills-lists",
        ],
    },
    "vic": {
        "name": "Victoria",
        "start_urls": [
            "https://liveinmelbourne.vic.gov.au/",
            "https://liveinmelbourne.vic.gov.au/migrate/skilled-migration-visas",
        ],
    },
    "qld": {
        "name": "Queensland",
        "start_urls": [
            "https://migration.qld.gov.au/skilled-occupation-lists/",
        ],
    },
    "sa": {
        "name": "South Australia",
        "start_urls": [
            "https://migration.sa.gov.au/before-applying/work-in-sa/occupation-lists/occupations-list",
            "https://migration.sa.gov.au/before-applying/work-in-sa/occupation-lists",
        ],
    },
    "wa": {
        "name": "Western Australia",
        "start_urls": [
            "https://migration.wa.gov.au/",
            "https://migration.wa.gov.au/our-services-support/state-nominated-migration-program",
        ],
    },
    "tas": {
        "name": "Tasmania",
        "start_urls": [
            "https://www.migration.tas.gov.au/",
            "https://www.migration.tas.gov.au/skilled_migration",
        ],
    },
    "nt": {
        "name": "Northern Territory",
        "start_urls": [
            "https://theterritory.com.au/",
            "https://theterritory.com.au/migrate",
        ],
    },
    "act": {
        "name": "Australian Capital Territory",
        "start_urls": [
            "https://www.act.gov.au/migration",
            "https://www.act.gov.au/migration/skilled-migrants",
        ],
    },
}

# Keywords that suggest a link leads to occupation list data
OCC_LINK_KEYWORDS = [
    "occupation", "skilled occupation", "nomination", "skills list",
    "eligible occupation", "priority list", "in-demand", "in demand",
]


def has_occupation_data(text: str) -> bool:
    """Check if the page text likely contains occupation list data."""
    # Look for ANZSCO 6-digit codes (federal codes) or 4-digit unit group codes
    if len(re.findall(r'\b\d{6}\b', text)) >= 5:
        return True
    if len(re.findall(r'\b\d{4}\b', text)) >= 10 and "anzsco" in text.lower():
        return True
    return False


def load_and_extract(page, url: str) -> tuple:
    """Navigate to URL, wait for content, return (html, text) or (None, None)."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except PWTimeoutError:
        return None, None
    except Exception as e:
        print(f"    error: {e}")
        return None, None

    # Wait extra time for Cloudflare challenge and SPA rendering.
    # Cloudflare challenges usually complete within ~10 seconds.
    page.wait_for_timeout(8000)

    # Try to detect "Just a moment" Cloudflare page; if present, wait longer
    try:
        title = page.title()
        if "just a moment" in title.lower() or "checking your browser" in title.lower():
            print(f"    Cloudflare challenge, waiting up to 45s...")
            for _ in range(45):
                page.wait_for_timeout(1000)
                new_title = page.title()
                if "just a moment" not in new_title.lower():
                    break
    except Exception:
        pass

    # Expand accordions, details, and collapsed sections
    try:
        page.evaluate("""() => {
            // Open all <details> elements
            document.querySelectorAll('details').forEach(d => d.open = true);
            // Click any element that looks like an accordion trigger
            document.querySelectorAll('[aria-expanded="false"]').forEach(el => {
                try { el.click(); } catch (e) {}
            });
            // Common accordion classes
            document.querySelectorAll('.accordion-button.collapsed, .accordion__button, .collapse-toggle').forEach(el => {
                try { el.click(); } catch (e) {}
            });
        }""")
        page.wait_for_timeout(3000)
    except Exception:
        pass

    # Scroll to trigger lazy-loading
    try:
        for _ in range(4):
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(1000)
    except Exception:
        pass

    try:
        html = page.content()
        text = page.inner_text("body")
        return html, text
    except Exception as e:
        print(f"    content extract failed: {e}")
        return None, None


def find_occupation_links(page, base_url: str) -> list:
    """Find links on current page that likely lead to occupation lists."""
    try:
        links = page.evaluate("""() => {
            const anchors = Array.from(document.querySelectorAll('a[href]'));
            return anchors.map(a => ({href: a.href, text: (a.innerText || '').trim()}));
        }""")
    except Exception:
        return []

    candidates = []
    seen = set()
    for link in links:
        href = link.get("href", "")
        text = (link.get("text") or "").lower()
        if not href or href in seen:
            continue
        seen.add(href)
        combined = (text + " " + href.lower())
        if any(kw in combined for kw in OCC_LINK_KEYWORDS):
            # Skip external/download links to home affairs (federal, not state)
            if "homeaffairs.gov.au" in href or "immi.gov.au" in href:
                continue
            candidates.append((href, text))
    return candidates


# States that need visible (non-headless) browser to bypass Cloudflare
CLOUDFLARE_STATES = {"nt", "act", "tas"}


def scrape_state(pw, code: str, info: dict) -> dict:
    """Try to find and download the occupation list for a state.

    Strategy:
      1. Visit each start URL
      2. If page has occupation data, save it
      3. Otherwise, find links that look like they lead to occupation lists,
         and follow those (BFS, depth 1)
    """
    print(f"\n[{code.upper()}] {info['name']}")

    # Use visible (headed) browser for Cloudflare-protected sites
    is_headless = code not in CLOUDFLARE_STATES
    if not is_headless:
        print(f"  (using visible browser to bypass Cloudflare)")

    browser = pw.chromium.launch(
        headless=is_headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
        locale="en-AU",
        java_script_enabled=True,
    )
    # Reduce fingerprinting
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-AU', 'en-US', 'en']});
        window.chrome = { runtime: {} };
    """)
    page = context.new_page()

    best = None       # (url, html, text) — best (has data)
    fallback = None   # first successful download even without data

    visited = set()
    queue = list(info["start_urls"])

    max_pages = 8
    pages_visited = 0

    while queue and pages_visited < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        pages_visited += 1

        print(f"  [{pages_visited}] {url}")
        html, text = load_and_extract(page, url)
        if html is None:
            print(f"    failed to load")
            continue

        # Check we didn't get redirected to a "not found" page
        try:
            current_title = page.title()
        except Exception:
            current_title = ""
        if "page not found" in current_title.lower() or "404" in current_title:
            print(f"    (page not found: '{current_title}')")
            continue

        print(f"    title='{current_title[:60]}', body={len(text):,} chars")

        if has_occupation_data(text):
            print(f"    ✓ occupation data detected")
            best = (page.url, html, text)
            break

        if fallback is None:
            fallback = (page.url, html, text)

        # Look for links to follow
        candidates = find_occupation_links(page, url)
        for href, ltext in candidates[:6]:
            if href not in visited:
                print(f"      → queue: '{ltext[:50]}' {href}")
                queue.append(href)

    browser.close()

    picked = best or fallback
    if picked is None:
        return {"downloaded": False, "url": None, "local_file": None}

    used_url, html, text = picked
    out_path = RAW_DIR / f"{code}_occupation_list.html"
    out_path.write_text(html, encoding="utf-8")
    return {
        "downloaded": True,
        "url": used_url,
        "local_file": str(out_path.relative_to(ROOT)),
        "has_occupation_data": has_occupation_data(text),
    }


def main():
    print("=" * 60)
    print("Scraping state/territory occupation lists (Playwright)")
    print("=" * 60)

    results = {}
    with sync_playwright() as pw:
        for code, info in STATES.items():
            try:
                results[code] = {
                    "name": info["name"],
                    **scrape_state(pw, code, info),
                }
            except Exception as e:
                print(f"  [{code.upper()}] fatal error: {e}")
                results[code] = {
                    "name": info["name"],
                    "downloaded": False,
                    "url": None,
                    "local_file": None,
                    "error": str(e),
                }
            time.sleep(1)

    # Save metadata
    meta_path = RAW_DIR / "download_metadata.json"
    meta_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nMetadata saved to {meta_path.relative_to(ROOT)}")

    print("\n" + "=" * 60)
    print("Summary:")
    for code, r in results.items():
        status = "✓" if r.get("has_occupation_data") else ("~" if r.get("downloaded") else "✗")
        print(f"  {status} {code.upper():4s} {r.get('name', ''):30s} {r.get('url', '') or ''}")

    good = sum(1 for r in results.values() if r.get("has_occupation_data"))
    partial = sum(1 for r in results.values() if r.get("downloaded") and not r.get("has_occupation_data"))
    failed = sum(1 for r in results.values() if not r.get("downloaded"))
    print(f"\n✓ with data: {good}   ~ downloaded but empty: {partial}   ✗ failed: {failed}")


if __name__ == "__main__":
    main()
