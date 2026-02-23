"""
_temp_test/test_save_events.py
Quick end-to-end test: scrape up to 10 scrolls, process, save to DB,
then query the DB and print every UMA event — highlighting Satono Diamond.

Run: python _temp_test/test_save_events.py
Output: printed to stdout + _temp_test/save_events_dump.txt (UTF-8)
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.async_api import async_playwright
from uma_handler import parse_event_date, process_events, add_uma_event, UMA_DB_PATH
import aiosqlite

OUT = "_temp_test/save_events_dump.txt"
BASE_URL = "https://uma.moe"
MAX_SCROLLS = 10       # Satono Diamond appears by scroll 7

EXTRACT_JS = """
() => {
    const items = Array.from(document.querySelectorAll('.timeline-item.timeline-event'));
    return items.map(item => {
        const titleEl = item.querySelector('.event-title');
        const descEl  = item.querySelector('.event-description');
        const dateEl  = item.querySelector('.event-date');
        const imgEls  = Array.from(item.querySelectorAll('img'));
        return {
            full_title:     titleEl ? titleEl.innerText.trim() : "",
            full_text:      item.innerText,
            description:    descEl  ? descEl.innerText.trim()  : "",
            date_str:       dateEl  ? dateEl.innerText.trim()  : "",
            raw_image_urls: imgEls.map(img => img.src).filter(Boolean)
        };
    });
}
"""

EVENT_TYPE_KEYWORDS = [
    "CHARACTER BANNER", "SUPPORT CARD BANNER", "PAID BANNER",
    "LEGEND RACE", "CHAMPIONS MEETING", "STORY EVENT",
]

def detect_type(full_text):
    u = full_text.upper()
    for kw in EVENT_TYPE_KEYWORDS:
        if kw in u:
            return kw
    return "UNKNOWN"


def parse_raw(item_data):
    full_title = item_data.get("full_title", "")
    date_str   = item_data.get("date_str", "")
    if not full_title or not date_str:
        return None
    start_date, end_date = parse_event_date(date_str)
    full_text = item_data.get("full_text", "")
    raw_urls  = item_data.get("raw_image_urls", [])
    img_urls  = [
        urljoin(BASE_URL, s) for s in raw_urls
        if any(p in s for p in [
            'chara_stand_', '2021_', '2022_', '2023_', '2024_', '2025_', '2026_',
            'img_bnr_', '/story/', '/paid/', '/support/'
        ])
    ]
    return {
        "full_title":  full_title,
        "full_text":   full_text,
        "description": item_data.get("description", ""),
        "date_str":    date_str,
        "start_date":  start_date,
        "end_date":    end_date,
        "image_url":   img_urls[0] if img_urls else None,
        "image_urls":  img_urls,
        "tags":        [],
        "event_type":  detect_type(full_text),
    }


async def main():
    raw_events  = []
    seen_events = set()

    # ── 1. Scrape ────────────────────────────────────────────────────
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            bypass_csp=True,
        )
        page = await context.new_page()
        await context.set_extra_http_headers({
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        })

        print("Navigating to uma.moe/timeline ...")
        await page.goto("https://uma.moe/timeline", timeout=60000)
        await page.wait_for_load_state("load")
        await asyncio.sleep(5)

        # Close popup if present
        try:
            popup = await page.query_selector(".update-popup-container")
            if popup:
                btn = await page.query_selector(".popup-actions button")
                if btn:
                    await btn.click()
                else:
                    await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
        except Exception:
            pass

        timeline = await page.query_selector(".timeline-container")
        if not timeline:
            print("ERROR: .timeline-container not found")
            await browser.close()
            return

        for _ in range(5):
            await timeline.evaluate("el => el.scrollBy(-800, 0)")
            await asyncio.sleep(0.5)

        for i in range(MAX_SCROLLS):
            prev_scroll = await timeline.evaluate("el => el.scrollLeft")
            await timeline.evaluate("el => el.scrollBy(800, 0)")
            await asyncio.sleep(1.5)
            curr_scroll = await timeline.evaluate("el => el.scrollLeft")

            items_data = await page.evaluate(EXTRACT_JS)
            new_count  = 0
            for item_data in items_data:
                ev = parse_raw(item_data)
                if not ev:
                    continue
                key = (ev["start_date"], ev["full_title"])
                if key not in seen_events:
                    seen_events.add(key)
                    raw_events.append(ev)
                    new_count += 1

            print(f"Scroll {i+1}: +{new_count} new (total {len(raw_events)})")

            if curr_scroll == prev_scroll:
                print(f"Timeline end reached.")
                break

        await browser.close()

    print(f"\nScrape done: {len(raw_events)} unique raw events.")

    satono_raw = any("satono diamond" in ev["full_title"].lower() for ev in raw_events)
    print(f"Satono Diamond in raw_events: {satono_raw}")

    # ── 2. Process ───────────────────────────────────────────────────
    print("\nRunning process_events() ...")
    processed = await process_events(raw_events)
    print(f"process_events returned {len(processed)} events.")

    satono_proc = [ev for ev in processed if "satono" in ev.get("title", "").lower()]
    print(f"Satono Diamond in processed: {bool(satono_proc)}")
    for ev in satono_proc:
        print(f"  -> title={ev['title']!r}  start={ev.get('start')}  end={ev.get('end')}  image={str(ev.get('image',''))[:80]}")

    # ── 3. Save to DB ────────────────────────────────────────────────
    print("\nSaving processed events to DB ...")
    saved = 0
    errors = []
    for event_data in processed:
        try:
            await add_uma_event(event_data)
            saved += 1
        except Exception as e:
            import traceback
            errors.append((event_data.get("title", "?"), str(e), traceback.format_exc()))

    print(f"Saved {saved}/{len(processed)} events. Errors: {len(errors)}")
    for title, err, tb in errors:
        print(f"  ERROR for {title!r}: {err}")
        print(tb)

    # ── 4. Query DB ──────────────────────────────────────────────────
    print(f"\nQuerying DB: {UMA_DB_PATH}")
    now = datetime.now(timezone.utc)
    rows = []
    try:
        async with aiosqlite.connect(UMA_DB_PATH) as conn:
            async with conn.execute(
                "SELECT id, title, category, start_date, end_date, image FROM events "
                "WHERE profile='UMA' ORDER BY start_date ASC"
            ) as cursor:
                rows = await cursor.fetchall()
    except Exception as e:
        print(f"DB query failed: {e}")

    print(f"Total UMA events in DB: {len(rows)}")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"Run: {now.isoformat()}\n")
        f.write(f"Raw scraped: {len(raw_events)} | Processed: {len(processed)} | Errors: {len(errors)}\n\n")

        f.write("ERRORS DURING SAVE\n" + "="*60 + "\n")
        if not errors:
            f.write("  None.\n")
        for title, err, tb in errors:
            f.write(f"  {title!r}: {err}\n{tb}\n")
        f.write("\n")

        f.write("UMA EVENTS IN DB\n" + "="*60 + "\n")
        f.write(f"Total: {len(rows)}\n\n")
        for row in rows:
            event_id, title, category, start, end, image = row
            try:
                start_dt = datetime.fromtimestamp(int(start), tz=timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                start_dt = str(start)
            try:
                end_dt = datetime.fromtimestamp(int(end), tz=timezone.utc).strftime("%Y-%m-%d")
            except Exception:
                end_dt = str(end)
            flag = " <-- FOUND" if "satono" in (title or "").lower() else ""
            f.write(f"  [{event_id}] {category:<16} {start_dt}  {title}{flag}\n")
            f.write(f"       image: {(image or 'None')[:100]}\n")

    print(f"\nDump written to {OUT}")

    satono_in_db = any("satono" in (r[1] or "").lower() for r in rows)
    print(f"Satono Diamond in DB: {satono_in_db}")
    if not satono_in_db and errors:
        print("CHECK ERRORS ABOVE — save failed for some events.")


if __name__ == "__main__":
    asyncio.run(main())
