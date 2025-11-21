import asyncio
import os
import requests
import json
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright
import logging

BASE_URL = "https://uma.moe/"

# Logger
uma_handler_logger = logging.getLogger("uma_handler")
uma_handler_logger.setLevel(logging.INFO)

def parse_event_date(date_str):
    """
    Parses a date string like 'Oct 1 – Oct 8, 2025' or '~Oct 1 – Oct 8, 2025'
    Returns (start_date, end_date) as datetime objects in UTC, or (None, None) if parsing fails.
    All times are set to 10pm UTC (start) and 9:59pm UTC (end).
    """
    date_str = date_str.strip().lstrip('~').strip()
    
    # Try to find a range like 'Oct 1 – Oct 8, 2025'
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
    
    # Try single date format with duration (e.g., 'Nov 24, 2025+4d')
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
    
    # Try simple single date (just the end date)
    simple_match = re.search(r'([A-Za-z]+)\s*(\d{1,2}),?\s*(\d{4})', date_str)
    if simple_match:
        month, day, year = simple_match.groups()
        try:
            end_date = datetime.strptime(f"{month} {day} {year} 21:59", "%b %d %Y %H:%M")
            end_date = end_date.replace(tzinfo=timezone.utc)
            return (None, end_date)
        except Exception:
            pass
    
    return (None, None)

async def download_timeline():
    """
    Downloads Uma Musume timeline events from uma.moe/timeline and processes them.
    Returns a list of parsed events ready to be saved.
    
    Note: Requires Playwright browser binaries. Run: playwright install chromium
    """
    print("[UMA HANDLER] Starting Playwright browser...")
    try:
        async with async_playwright() as p:
            print("[UMA HANDLER] Launching headless Chromium...")
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            uma_handler_logger.info("Navigating to https://uma.moe/timeline ...")
            print("[UMA HANDLER] Navigating to https://uma.moe/timeline ...")
            await page.goto("https://uma.moe/timeline", timeout=60000)
            await page.wait_for_load_state("networkidle")

            timeline = await page.query_selector('.timeline-container')
            if not timeline:
                uma_handler_logger.error("Timeline container not found!")
                await browser.close()
                return []

            # Scroll through timeline to load all events
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
                    _, end_date = parse_event_date(date_str)
                    if end_date and (not max_date or end_date > max_date):
                        max_date = end_date

                uma_handler_logger.info(f"Scroll {i+1}: Latest event date found: {max_date}")

                if max_date and (not latest_event_date or max_date > latest_event_date):
                    latest_event_date = max_date
                    no_new_date_scrolls = 0
                else:
                    no_new_date_scrolls += 1
                    uma_handler_logger.info(f"No newer date found. ({no_new_date_scrolls}/5)")
                    if no_new_date_scrolls >= 5:
                        uma_handler_logger.info("No newer event date found after 5 scrolls, stopping.")
                        break

            # Extract raw events
            raw_events = []
            event_items = await page.query_selector_all('.timeline-item.timeline-event')
            
            for item in event_items:
                # Extract event title and description
                title_tag = await item.query_selector('.event-title')
                if not title_tag:
                    continue
                full_title = (await title_tag.inner_text()).strip()
                
                # Extract event image
                img_tag = await item.query_selector('.event-image img')
                img_url = None
                if img_tag:
                    img_src = await img_tag.get_attribute("src")
                    if img_src:
                        img_url = urljoin(BASE_URL, img_src)
                
                # Extract event date
                date_tag = await item.query_selector('.event-date')
                if not date_tag:
                    continue
                date_str = (await date_tag.inner_text()).strip()
                start_date, end_date = parse_event_date(date_str)
                
                raw_events.append({
                    "full_title": full_title,
                    "image_url": img_url,
                    "start_date": start_date,
                    "end_date": end_date
                })

            await browser.close()
            
            uma_handler_logger.info(f"Downloaded {len(raw_events)} raw events from timeline")
            
            # Process and combine events
            processed_events = process_events(raw_events)
            
            uma_handler_logger.info(f"Processed {len(processed_events)} events from {len(raw_events)} raw events!")
            
            if len(processed_events) == 0:
                uma_handler_logger.warning("No events were processed! Check if timeline structure has changed.")
            return processed_events
    
    except Exception as e:
        uma_handler_logger.error(f"Failed to download timeline: {e}")
        import traceback
        uma_handler_logger.error(traceback.format_exc())
        return []

def process_events(raw_events):
    """
    Processes raw events from the timeline and combines related events.
    Returns a list of finalized event dicts ready for database insertion.
    """
    processed = []
    skip_indices = set()
    
    for i, event in enumerate(raw_events):
        if i in skip_indices:
            continue
        
        full_title = event["full_title"]
        start_date = event["start_date"]
        end_date = event["end_date"]
        img_url = event["image_url"]
        
        # Skip events without end dates
        if not end_date:
            continue
        
        # Parse title components
        title_lower = full_title.lower()
        
        # === CHARACTER + SUPPORT BANNER COMBINATION ===
        if "character banner featuring:" in title_lower:
            # Extract character names
            char_match = re.search(r"Character banner featuring:\s*(.+)", full_title, re.IGNORECASE)
            char_names = char_match.group(1).strip() if char_match else ""
            
            # Look for matching Support banner
            support_names = ""
            support_img = None
            for j in range(i+1, min(i+5, len(raw_events))):
                next_event = raw_events[j]
                if "support" in next_event["full_title"].lower() and "support cards:" in next_event["full_title"].lower():
                    # Check if dates match
                    if (next_event["start_date"] and abs((next_event["start_date"] - start_date).total_seconds()) < 86400 and
                        next_event["end_date"] and abs((next_event["end_date"] - end_date).total_seconds()) < 86400):
                        support_match = re.search(r"SUPPORT CARDS:\s*(.+)", next_event["full_title"], re.IGNORECASE)
                        support_names = support_match.group(1).strip() if support_match else ""
                        support_img = next_event["image_url"]
                        skip_indices.add(j)
                        break
            
            # Combine images if both exist
            combined_img = img_url
            if img_url and support_img:
                from uma_module import combine_images_vertically
                combined_path = combine_images_vertically(img_url, support_img)
                if combined_path:
                    combined_img = combined_path
            
            # Create combined event
            title = f"{char_names} Banner"
            description = f"**Characters:** {char_names}\n**Support Cards:** {support_names}" if support_names else f"**Characters:** {char_names}"
            
            processed.append({
                "title": title,
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "image": combined_img,
                "category": "Banner",
                "description": description
            })
            continue
        
        # === PAID BANNER COMBINATION ===
        if "paid banner" in title_lower:
            # Look for another Paid Banner at the same time
            paired_img = None
            for j in range(i+1, min(i+3, len(raw_events))):
                next_event = raw_events[j]
                if "paid banner" in next_event["full_title"].lower():
                    # Check if dates match
                    if (next_event["start_date"] and abs((next_event["start_date"] - start_date).total_seconds()) < 3600 and
                        next_event["end_date"] and abs((next_event["end_date"] - end_date).total_seconds()) < 3600):
                        paired_img = next_event["image_url"]
                        skip_indices.add(j)
                        break
            
            # Combine images if paired
            combined_img = img_url
            if img_url and paired_img:
                from uma_module import combine_images_vertically
                combined_path = combine_images_vertically(img_url, paired_img)
                if combined_path:
                    combined_img = combined_path
            
            processed.append({
                "title": "Paid Banner",
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "image": combined_img,
                "category": "Offer",
                "description": ""
            })
            continue
        
        # === STORY EVENT ===
        if "story event" in title_lower:
            story_match = re.search(r"Story Event:\s*(.+)", full_title, re.IGNORECASE)
            story_name = story_match.group(1).strip() if story_match else full_title
            
            processed.append({
                "title": story_name,
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "image": img_url,
                "category": "Event",
                "description": ""
            })
            continue
        
        # === LEGEND RACE ===
        if "legend race" in title_lower:
            # Extract race details
            details_match = re.search(r"Legend Race\s+(.+)", full_title)
            details = details_match.group(1).strip() if details_match else ""
            
            processed.append({
                "title": "Legend Race",
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "image": img_url,
                "category": "Event",
                "description": details
            })
            continue
        
        # === CHAMPIONS MEETING ===
        if "champions meeting" in title_lower:
            # Extract meeting details
            details_match = re.search(r"Champions Meeting\s+(.+)", full_title)
            details = details_match.group(1).strip() if details_match else ""
            
            processed.append({
                "title": "Champions Meeting",
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "image": img_url,
                "category": "Event",
                "description": details
            })
            continue
    
    return processed

async def update_uma_events():
    """
    Main function to download timeline and update database.
    This should be called periodically or manually to refresh Uma Musume events.
    """
    uma_handler_logger.info("Starting Uma Musume event update...")
    print("[UMA HANDLER] Starting Uma Musume event update...")
    
    # Download and process events
    print("[UMA HANDLER] Downloading timeline from uma.moe...")
    events = await download_timeline()
    
    if not events:
        uma_handler_logger.warning("No events downloaded.")
        print("[UMA HANDLER] WARNING: No events downloaded!")
        return
    
    print(f"[UMA HANDLER] Downloaded {len(events)} events, adding to database...")
    
    # Import module functions
    from uma_module import add_uma_event, uma_update_timers
    
    # Create a dummy context for add_uma_event
    class DummyCtx:
        author = type('obj', (object,), {'id': '0'})()
        async def send(self, msg, **kwargs):
            uma_handler_logger.info(f"[Event Added] {msg}")
    
    ctx = DummyCtx()
    
    # Add events to database
    added_count = 0
    for event_data in events:
        try:
            await add_uma_event(ctx, event_data)
            added_count += 1
        except Exception as e:
            uma_handler_logger.error(f"Failed to add event '{event_data['title']}': {e}")
    
    uma_handler_logger.info(f"Added {added_count}/{len(events)} events to database.")
    print(f"[UMA HANDLER] Added {added_count}/{len(events)} events to database.")
    
    # Refresh dashboard
    print("[UMA HANDLER] Refreshing Discord dashboards...")
    await uma_update_timers()
    uma_handler_logger.info("Dashboard updated successfully!")
    print("[UMA HANDLER] Dashboard updated successfully!")

if __name__ == "__main__":
    asyncio.run(update_uma_events())