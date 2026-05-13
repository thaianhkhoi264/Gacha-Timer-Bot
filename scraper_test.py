
import asyncio
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright
import logging

# Configure logger for the test script
test_logger = logging.getLogger("scraper_test")
test_logger.setLevel(logging.INFO)
stream_handler = logging.StreamHandler()
test_logger.addHandler(stream_handler)

BASE_URL = "https://uma.moe/"

def parse_event_date(date_str):
    """
    Parses a date string like 'Oct 1 – Oct 8, 2025' or '~Oct 1 – Oct 8, 2025'
    or 'Dec 28, 2025 – Jan 7, 2026' (with years for both dates)
    Returns (start_date, end_date) as datetime objects in UTC, or (None, None) if parsing fails.
    All times are set to 10pm UTC (start) and 9:59pm UTC (end).
    """
    date_str = date_str.strip().lstrip('~').strip()

    # Try format with years for both dates: 'Dec 28, 2025 – Jan 7, 2026'
    full_range_match = re.search(r'([A-Za-z]+)\s*(\d{1,2}),?\s*(\d{4})\s*–\s*([A-Za-z]+)\s*(\d{1,2}),?\s*(\d{4})', date_str)
    if full_range_match:
        start_month, start_day, start_year, end_month, end_day, end_year = full_range_match.groups()
        try:
            start_date = datetime.strptime(f"{start_month} {start_day} {start_year} 22:00", "%b %d %Y %H:%M")
            end_date = datetime.strptime(f"{end_month} {end_day} {end_year} 21:59", "%b %d %Y %H:%M")
            # Set to UTC timezone
            start_date = start_date.replace(tzinfo=timezone.utc)
            end_date = end_date.replace(tzinfo=timezone.utc)
            return (start_date, end_date)
        except Exception:
            pass

    # Try to find a range like 'Oct 1 – Oct 8, 2025' (year only at end)
    range_match = re.search(r'([A-Za-z]+)\s*(\d{1,2})\s*–\s*([A-Za-z]+)\s*(\d{1,2}),?\s*(\d{4})', date_str)
    if range_match:
        start_month, start_day, end_month, end_day, year = range_match.groups()
        try:
            start_date = datetime.strptime(f"{start_month} {start_day} {year} 22:00", "%b %d %Y %H:%M")
            end_date = datetime.strptime(f"{end_month} {end_day} {year} 21:59", "%b %d %Y %H:%M")
            # Set to UTC timezone
            start_date = start_date.replace(tzinfo=timezone.utc)
            end_date = end_date.replace(tzinfo=timezone.utc)
            return (start_date, end_date)
        except Exception:
            pass
    
    # Try duration format
    duration_match = re.search(r'([A-Za-z]+)\s*(\d{1,2}),?\s*(\d{4})\+(\d+)d', date_str)
    if duration_match:
        month, day, year, duration = duration_match.groups()
        try:
            start_date = datetime.strptime(f"{month} {day} {year} 22:00", "%b %d %Y %H:%M")
            start_date = start_date.replace(tzinfo=timezone.utc)
            end_date = start_date + timedelta(days=int(duration))
            end_date = end_date.replace(hour=21, minute=59)
            return (start_date, end_date)
        except Exception:
            pass
    
    # Try simple single date
    simple_match = re.search(r'([A-Za-z]+)\s*(\d{1,2}),?\s*(\d{4})', date_str)
    if simple_match:
        month, day, year = simple_match.groups()
        try:
            # Use the date as END date, estimate START as 7 days before
            end_date = datetime.strptime(f"{month} {day} {year} 21:59", "%b %d %Y %H:%M")
            end_date = end_date.replace(tzinfo=timezone.utc)
            start_date = end_date - timedelta(days=7)
            start_date = start_date.replace(hour=22, minute=0)
            return (start_date, end_date)
        except Exception:
            pass
    
    return (None, None)

async def test_scraper():
    """
    Downloads Uma Musume timeline, parses events, and searches for a specific character.
    """
    test_logger.info("=== Starting Scraper Test ===")
    
    # Calculate the date 2 months from now
    two_months_later = datetime.now(timezone.utc) + timedelta(days=60)
    
    try:
        async with async_playwright() as p:
            test_logger.info("Launching headless Chromium...")
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            )
            page = await context.new_page()

            test_logger.info("Navigating to https://uma.moe/timeline ...")
            await page.goto("https://uma.moe/timeline", timeout=60000)
            await page.wait_for_load_state("load")
            await asyncio.sleep(5)

            timeline = await page.query_selector('.timeline-container')
            if not timeline:
                test_logger.error("Timeline container not found!")
                await browser.close()
                return

            # Scroll to the right to find future events
            test_logger.info("Scrolling right to load future events...")
            max_scrolls = 200 
            seen_events = set()
            raw_events = []
            
            extract_js = """
            () => {
                const items = Array.from(document.querySelectorAll('.timeline-item.timeline-event'));
                return items.map(item => {
                    const titleEl = item.querySelector('.event-title');
                    const dateEl = item.querySelector('.event-date');
                    return {
                        full_title: titleEl ? titleEl.innerText.trim() : "",
                        full_text: item.innerText,
                        date_str: dateEl ? dateEl.innerText.trim() : "",
                    };
                });
            }
            """

            for i in range(max_scrolls):
                prev_scroll = await timeline.evaluate("el => el.scrollLeft")
                await timeline.evaluate("el => el.scrollBy(800, 0)")
                await asyncio.sleep(1.5)
                curr_scroll = await timeline.evaluate("el => el.scrollLeft")

                raw_items_data = await page.evaluate(extract_js)

                new_count = 0
                for item_data in raw_items_data:
                    full_title = item_data.get("full_title", "")
                    date_str = item_data.get("date_str", "")
                    if not full_title or not date_str:
                        continue

                    start_date, end_date = parse_event_date(date_str)
                    event_key = (start_date, full_title)

                    if event_key not in seen_events:
                        seen_events.add(event_key)
                        raw_events.append(item_data)
                        new_count += 1
                
                test_logger.info(f"Scroll {i+1}: Found {new_count} new events.")

                if curr_scroll == prev_scroll:
                    test_logger.info("End of timeline reached.")
                    break
            
            await browser.close()

            test_logger.info(f"Found a total of {len(raw_events)} unique events.")
            
            found_character = False
            
            test_logger.info("
--- Analyzing Scraped Banners (next 2 months) ---")
            
            for event in raw_events:
                date_str = event.get("date_str", "NO DATE")
                start_date, end_date = parse_event_date(date_str)

                if start_date and start_date > two_months_later:
                    continue # Skip events further than 2 months away

                full_text = event.get("full_text", "")
                
                # Check for "CHARACTER BANNER" and the specific character name
                if "CHARACTER BANNER" in full_text.upper():
                    # The name is usually on a line after the date
                    lines = full_text.split('
')
                    
                    test_logger.info(f"Checking Banner: {event.get('full_title', 'No Title')} ({date_str})")

                    if "Satono Diamond" in full_text:
                        test_logger.info(f"  -> Found 'Satono Diamond' in banner: {event.get('full_title')}")
                        found_character = True

            if not found_character:
                test_logger.info("
--- Conclusion ---")
                test_logger.info("'Satono Diamond' was not found in any of the scraped character banners for the next 2 months.")

async def main():
    await test_scraper()

if __name__ == "__main__":
    asyncio.run(main())
