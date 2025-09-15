import asyncio
import os
import requests
import json
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "https://uma.moe/"

def parse_event_date(date_str):
    """
    Parses a date string like 'Oct 1 – Oct 8, 2025' or '~Oct 1 – Oct 8, 2025'
    Returns the latest date as a datetime object, or None if parsing fails.
    """
    # Remove leading ~ and whitespace
    date_str = date_str.strip().lstrip('~').strip()
    # Try to find the last date in the string
    match = re.search(r'([A-Za-z]+)\s*(\d{1,2}),?\s*(\d{4})', date_str)
    if not match:
        # Try to find a range like 'Oct 1 – Oct 8, 2025'
        match = re.search(r'([A-Za-z]+)\s*\d{1,2}\s*–\s*([A-Za-z]+)\s*(\d{1,2}),?\s*(\d{4})', date_str)
        if match:
            month, day, year = match.group(2), match.group(3), match.group(4)
            try:
                return datetime.strptime(f"{month} {day} {year}", "%b %d %Y")
            except Exception:
                return None
        return None
    month, day, year = match.group(1), match.group(2), match.group(3)
    try:
        return datetime.strptime(f"{month} {day} {year}", "%b %d %Y")
    except Exception:
        return None

async def download_timeline():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        print("Navigating to https://uma.moe/timeline ...")
        await page.goto("https://uma.moe/timeline", timeout=60000)
        await page.wait_for_load_state("networkidle")

        timeline = await page.query_selector('.timeline-container')
        if not timeline:
            print("Timeline container not found!")
            await browser.close()
            return

        scroll_amount = 400
        max_scrolls = 60
        no_new_date_scrolls = 0
        latest_event_date = None

        for i in range(max_scrolls):
            await timeline.evaluate(f"el => el.scrollBy({scroll_amount}, 0)")
            await asyncio.sleep(1.2)
            event_items = await page.query_selector_all('.timeline-item.timeline-event')

            # Find the latest event date currently visible
            max_date = None
            for item in event_items:
                date_tag = await item.query_selector('.event-date')
                if not date_tag:
                    continue
                date_str = (await date_tag.inner_text()).strip()
                event_date = parse_event_date(date_str)
                if event_date and (not max_date or event_date > max_date):
                    max_date = event_date

            print(f"Scroll {i+1}: Latest event date found: {max_date}")

            if max_date and (not latest_event_date or max_date > latest_event_date):
                latest_event_date = max_date
                no_new_date_scrolls = 0
            else:
                no_new_date_scrolls += 1
                print(f"No newer date found. ({no_new_date_scrolls}/5)")
                if no_new_date_scrolls >= 5:
                    print("No newer event date found after 5 scrolls, stopping.")
                    break

        # Extract events and images using Playwright's DOM API
        events = []
        event_items = await page.query_selector_all('.timeline-item.timeline-event')
        for item in event_items:
            title_tag = await item.query_selector('.event-title')
            img_tag = await item.query_selector('.event-image img')
            date_tag = await item.query_selector('.event-date')
            if not title_tag or not img_tag or not date_tag:
                continue
            title = (await title_tag.inner_text()).strip()
            img_src = await img_tag.get_attribute("src")
            date_str = (await date_tag.inner_text()).strip()
            if not img_src:
                continue
            img_url = urljoin(BASE_URL, img_src)
            parsed = urlparse(img_src)
            local_img_path = os.path.join("downloaded_assets", parsed.path.lstrip("/"))
            os.makedirs(os.path.dirname(local_img_path), exist_ok=True)
            if not os.path.exists(local_img_path):
                print(f"Downloading {img_url} -> {local_img_path}")
                try:
                    r = requests.get(img_url)
                    r.raise_for_status()
                    with open(local_img_path, "wb") as out:
                        out.write(r.content)
                except Exception as e:
                    print(f"Failed to download {img_url}: {e}")
            events.append({"title": title, "image": local_img_path, "date": date_str})

        # Save event-image-date mapping
        with open("event_image_map.json", "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        print("Saved event-image mapping to event_image_map.json")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(download_timeline())