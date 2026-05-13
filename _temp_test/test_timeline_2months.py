"""
_temp_test/test_timeline_2months.py
Diagnostic: scrapes uma.moe/timeline, logs every event before and after
deduplication, then runs process_events() to show what survives.
Focus: events within the next 1 month. Stops scrolling once an event
past May 1 is seen.

Run: python _temp_test/test_timeline_2months.py
Output: _temp_test/timeline_1month_dump.txt
"""
import asyncio
import sys
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

# Allow importing from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.async_api import async_playwright
from uma_handler import parse_event_date, process_events

OUT = "_temp_test/timeline_1month_dump.txt"
BASE_URL = "https://uma.moe"
NOW = datetime.now(timezone.utc)
ONE_MONTH = NOW + timedelta(days=31)
# Stop scrolling once we've seen events starting after this date
SCROLL_CUTOFF = NOW.replace(month=5, day=1, hour=0, minute=0, second=0, microsecond=0)

# Same JS as download_timeline()
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
    """Mirrors parse_raw_item_data() from uma_handler but minimal."""
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
        "full_title": full_title,
        "full_text":  full_text,
        "description": item_data.get("description", ""),
        "date_str":   date_str,
        "start_date": start_date,
        "end_date":   end_date,
        "image_url":  img_urls[0] if img_urls else None,
        "image_urls": img_urls,
        "tags":       [],
        "event_type": detect_type(full_text),
    }


async def main():
    pre_dedup_log = []    # every JS extract, including dupes
    raw_events    = []    # unique events (after dedup)
    seen_events   = set()
    collisions    = []    # (key, new_title, existing_index)

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

        # Scroll left briefly for past reference
        for _ in range(5):
            await timeline.evaluate("el => el.scrollBy(-800, 0)")
            await asyncio.sleep(0.5)

        # Right scroll loop — mirrors download_timeline() exactly
        scroll_amount = 800
        max_scrolls   = 200
        no_new_count  = 0
        reached_cutoff = False

        for i in range(max_scrolls):
            prev_scroll = await timeline.evaluate("el => el.scrollLeft")
            await timeline.evaluate(f"el => el.scrollBy({scroll_amount}, 0)")
            await asyncio.sleep(1.5)
            curr_scroll = await timeline.evaluate("el => el.scrollLeft")

            # --- always extract before checking end-of-timeline ---
            items_data = await page.evaluate(EXTRACT_JS)
            new_count  = 0

            for item_data in items_data:
                ev = parse_raw(item_data)
                if not ev:
                    continue

                key = (ev["start_date"], ev["full_title"])
                pre_dedup_log.append({
                    "scroll": i + 1,
                    "key":    key,
                    "type":   ev["event_type"],
                    "dupe":   key in seen_events,
                })

                if key not in seen_events:
                    seen_events.add(key)
                    raw_events.append(ev)
                    new_count += 1
                    # Early stop: once we see an event starting past the cutoff date, stop scrolling
                    if ev["start_date"] and ev["start_date"] > SCROLL_CUTOFF:
                        print(f"Scroll {i+1}: reached cutoff ({ev['start_date'].date()}). Stopping.")
                        reached_cutoff = True
                        break
                else:
                    # Log collision details
                    existing_idx = next(
                        (idx for idx, r in enumerate(raw_events) if
                         (r["start_date"], r["full_title"]) == key),
                        None,
                    )
                    collisions.append({
                        "scroll": i + 1,
                        "key":    key,
                        "new_type":      ev["event_type"],
                        "existing_idx":  existing_idx,
                        "existing_type": (
                            raw_events[existing_idx]["event_type"]
                            if existing_idx is not None else "?"
                        ),
                    })

            if reached_cutoff:
                break

            if curr_scroll == prev_scroll:
                print(f"Scroll {i+1}: timeline end reached. Total unique: {len(raw_events)}")
                break

            if new_count > 0:
                print(f"Scroll {i+1}: +{new_count} new (total {len(raw_events)})")
                no_new_count = 0
            else:
                no_new_count += 1
                if no_new_count >= 3:
                    print(f"Scroll {i+1}: 3 empty scrolls, stopping.")
                    break

        await browser.close()

    print(f"Scroll complete. {len(raw_events)} unique raw events, {len(collisions)} collisions.")

    # Filter to next 1 month
    def in_window(ev):
        sd = ev.get("start_date")
        ed = ev.get("end_date")
        if sd and sd <= ONE_MONTH:
            return True
        if ed and ed >= NOW and ed <= ONE_MONTH:
            return True
        return False

    raw_2mo = [ev for ev in raw_events if in_window(ev)]
    print(f"Raw events in next 1 month: {len(raw_2mo)}")

    # Run process_events on ALL raw events (same as download_timeline does)
    print("Running process_events() ...")
    processed = await process_events(raw_events)
    proc_2mo = [ev for ev in processed if
                (ev.get("start") or 0) <= ONE_MONTH.timestamp() and
                (ev.get("end")   or 0) >= NOW.timestamp()]
    print(f"Processed events in next 1 month: {len(proc_2mo)}")

    # Build diff: raw titles in window that aren't in processed
    proc_titles = {ev["title"] for ev in proc_2mo}

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"Run: {NOW.isoformat()}\n")
        f.write(f"Window: now -> {ONE_MONTH.date()}\n\n")

        # --- Collisions ---
        f.write("=" * 70 + "\n")
        f.write(f"DEDUP COLLISIONS ({len(collisions)} total)\n")
        f.write("=" * 70 + "\n")
        if not collisions:
            f.write("  None.\n")
        for c in collisions:
            sd = c["key"][0]
            title = c["key"][1]
            f.write(
                f"  scroll={c['scroll']}  "
                f"start={sd.strftime('%Y-%m-%d') if sd else 'None'}  "
                f"title={title[:60]!r}\n"
                f"    new_type={c['new_type']}  "
                f"existing[{c['existing_idx']}]={c['existing_type']}\n"
            )
        f.write("\n")

        # --- Raw events in window ---
        f.write("=" * 70 + "\n")
        f.write(f"RAW EVENTS — next 1 month ({len(raw_2mo)})\n")
        f.write("=" * 70 + "\n")
        for idx, ev in enumerate(raw_2mo):
            sd = ev["start_date"]
            ed = ev["end_date"]
            f.write(
                f"  [{idx:02d}] {ev['event_type']:<22}  "
                f"{sd.strftime('%Y-%m-%d') if sd else '??'}  "
                f"title={ev['full_title'][:60]!r}\n"
            )
        f.write("\n")

        # --- Processed events in window ---
        f.write("=" * 70 + "\n")
        f.write(f"PROCESSED EVENTS — next 1 month ({len(proc_2mo)})\n")
        f.write("=" * 70 + "\n")
        for idx, ev in enumerate(proc_2mo):
            ts = ev.get("start", 0)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else "??"
            f.write(f"  [{idx:02d}] {ev['category']:<14}  {dt}  title={ev['title'][:60]!r}\n")
        f.write("\n")

        # --- Diff ---
        f.write("=" * 70 + "\n")
        f.write("DIFF: raw events NOT found in processed output\n")
        f.write("=" * 70 + "\n")
        missing_any = False
        for ev in raw_2mo:
            # Check if any processed title contains the raw full_title (approximate)
            raw_t = ev["full_title"].lower()
            matched = any(raw_t in pt.lower() or pt.lower() in raw_t for pt in proc_titles)
            if not matched:
                sd = ev["start_date"]
                f.write(
                    f"  MISSING  {ev['event_type']:<22}  "
                    f"{sd.strftime('%Y-%m-%d') if sd else '??'}  "
                    f"title={ev['full_title'][:60]!r}\n"
                )
                missing_any = True
        if not missing_any:
            f.write("  All raw events accounted for in processed output.\n")

    print(f"Done. Results in {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
