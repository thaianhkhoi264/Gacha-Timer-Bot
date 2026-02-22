import asyncio
import os
import aiohttp
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
    
    # Try simple single date (return as both start and end for compatibility)
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

            # Create context with realistic user agent and cache bypass
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                bypass_csp=True
            )
            page = await context.new_page()

            # Disable cache to force fresh data
            await context.set_extra_http_headers({
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            })

            uma_handler_logger.info("Navigating to https://uma.moe/timeline ...")
            print("[UMA HANDLER] Navigating to https://uma.moe/timeline ...")
            await page.goto("https://uma.moe/timeline", timeout=60000)
            await page.wait_for_load_state("load")
            # Wait for Angular to finish rendering (site has background polling so networkidle never fires)
            await asyncio.sleep(5)

            # Check for and close update popup if it exists
            try:
                print("[UMA HANDLER] Checking for update popup...")
                popup = await page.query_selector('.update-popup-container')
                if popup:
                    print("[UMA HANDLER] Update popup detected, closing...")
                    # Try to find and click the action button
                    close_button = await page.query_selector('.popup-actions button, .popup-actions [role="button"]')
                    if close_button:
                        await close_button.click()
                        await asyncio.sleep(0.5)
                        print("[UMA HANDLER] Update popup closed via button")
                    else:
                        # If no action button, try pressing Escape
                        await page.keyboard.press('Escape')
                        await asyncio.sleep(0.5)
                        print("[UMA HANDLER] Update popup closed via Escape key")
                else:
                    print("[UMA HANDLER] No update popup detected")
            except Exception as e:
                print(f"[UMA HANDLER] Error handling popup (non-critical): {e}")

            timeline = await page.query_selector('.timeline-container')
            if not timeline:
                uma_handler_logger.error("Timeline container not found!")
                await browser.close()
                return []

            # Check initial event count
            initial_events = await page.query_selector_all('.timeline-item.timeline-event')
            print(f"[UMA HANDLER] Initial event count on page load: {len(initial_events)}")
            uma_handler_logger.info(f"Initial event count: {len(initial_events)}")
            
            # Take screenshot for debugging
            await page.screenshot(path="uma_timeline_initial.png")
            print("[UMA HANDLER] Screenshot saved: uma_timeline_initial.png")

            # === SCROLL LEFT FIRST (to find past events as reference) ===
            print("[UMA HANDLER] Phase 1: Scrolling LEFT to find past events...")
            scroll_amount = -600
            max_left_scrolls = 10  # Only need a few scrolls to find past events
            found_past_event = False

            for i in range(max_left_scrolls):
                await timeline.evaluate(f"el => el.scrollBy({scroll_amount}, 0)")
                await asyncio.sleep(2.0)  # Shorter wait since we're just checking dates
                event_items = await page.query_selector_all('.timeline-item.timeline-event')

                # Check if any visible events have ended (quick date check)
                # We just need to find ONE past event to establish our position
                for item in event_items[:5]:  # Check first 5 events only
                    date_tag = await item.query_selector('.event-date')
                    if date_tag:
                        date_str = (await date_tag.inner_text()).strip()
                        # Check if this event has already ended (end date is in the past)
                        _, end_dt = parse_event_date(date_str)
                        if end_dt and end_dt < datetime.now(timezone.utc):
                            found_past_event = True
                            print(f"[UMA HANDLER] LEFT scroll {i+1}: Found past event reference, stopping LEFT scroll")
                            break

                if found_past_event:
                    break

                print(f"[UMA HANDLER] Scroll LEFT {i+1}: {len(event_items)} events visible, looking for past events...")

            if not found_past_event:
                print(f"[UMA HANDLER] LEFT scroll complete: No past events found (all events might be future)")

            current_count = len(event_items)

            # === HELPER FUNCTION: Extract single event from DOM element ===
            async def extract_single_event(item):
                """Extract event data from a single timeline item DOM element."""
                # Extract event title
                title_tag = await item.query_selector('.event-title')
                if not title_tag:
                    return None
                full_title = (await title_tag.inner_text()).strip()

                # Extract character/event tags from text content
                # Character names appear on separate lines after the event type and date
                tags = []
                full_text = await item.inner_text()
                lines = [line.strip() for line in full_text.split('\n') if line.strip()]

                # For CHARACTER BANNER or SUPPORT CARD BANNER:
                # Structure is: [type] [title with +1 more] [date] [name1] [name2] ...
                full_text_upper = full_text.upper()
                if "CHARACTER BANNER" in full_text_upper or "SUPPORT CARD BANNER" in full_text_upper:
                    # Find the date line (contains " – " and year)
                    date_idx = None
                    for i, line in enumerate(lines):
                        if "–" in line and "202" in line:
                            date_idx = i
                            break

                    if date_idx is not None:
                        # Character names are on lines after the date
                        # Collect lines that look like character names (not too long, not special keywords)
                        for i in range(date_idx + 1, min(date_idx + 5, len(lines))):
                            name = lines[i]
                            # Stop if we hit a new section or empty line
                            if not name or len(name) > 50:
                                break
                            # Skip if it's a common non-name line
                            if name in ["CHARACTERS:", "SUPPORT CARDS:", "CHARACTER BANNER", "SUPPORT CARD BANNER"]:
                                continue
                            tags.append(name)

                # Extract event description/subtitle
                description = ""
                desc_tag = await item.query_selector('.event-description')
                if desc_tag:
                    description = (await desc_tag.inner_text()).strip()

                # Extract ALL event images (Legend Race can have 3-4 character images)
                img_urls = []

                # Get ALL img tags within this event item
                all_imgs = await item.query_selector_all('img')

                for img_tag in all_imgs:
                    img_src = await img_tag.get_attribute("src")
                    if img_src:
                        full_url = urljoin(BASE_URL, img_src)
                        # Add all relevant game images (banner IDs, character images)
                        if any(pattern in img_src for pattern in ['chara_stand_', '2021_', '2022_', '2023_', '2024_', '2025_', '2026_', 'img_bnr_', '/story/', '/paid/', '/support/']):
                            if full_url not in img_urls:  # Avoid duplicates
                                img_urls.append(full_url)

                # Primary image URL (first one, for backwards compatibility)
                img_url = img_urls[0] if img_urls else None

                # Extract event date
                date_tag = await item.query_selector('.event-date')
                if not date_tag:
                    return None
                date_str = (await date_tag.inner_text()).strip()

                start_date, end_date = parse_event_date(date_str)

                # Return event data
                return {
                    "full_title": full_title,
                    "full_text": full_text,  # Store full text for event type detection
                    "tags": tags,
                    "description": description,
                    "image_url": img_url,  # Primary image (first one)
                    "image_urls": img_urls,  # ALL images for this event
                    "start_date": start_date,
                    "end_date": end_date,
                    "date_str": date_str
                }

            # === Helper function to build proper title for logging ===
            def build_proper_title(event_data):
                """Build proper combined title like 'Oguri Cap & Biwa Hayahide Banner'."""
                full_title = event_data.get("full_title", "")
                tags = event_data.get("tags", [])
                full_text = event_data.get("full_text", "")

                # If title has "+ X more" and we have character names, build combined title
                if "+" in full_title and "more" in full_title and tags:
                    # Determine event type
                    if "CHARACTER BANNER" in full_text:
                        event_type = "Banner"
                    elif "SUPPORT CARD BANNER" in full_text:
                        event_type = "Support Banner"
                    else:
                        event_type = "Event"

                    # Combine character names
                    if len(tags) >= 2:
                        return f"{tags[0]} & {tags[1]} {event_type}"
                    elif len(tags) == 1:
                        return f"{tags[0]} {event_type}"

                # Otherwise, use the original title
                return full_title

            # === THEN SCROLL RIGHT (to future/newer events) ===
            print("[UMA HANDLER] Phase 2: Scrolling RIGHT to load future events and extracting during scroll...")
            scroll_amount = 600  # Scroll RIGHT (increased from 400)
            max_scrolls = 200  # Max iterations for RIGHT scroll
            no_new_events_count = 0

            # Track unique events by (start_date, title) to avoid duplicates
            seen_events = set()
            raw_events = []

            for i in range(max_scrolls):
                await timeline.evaluate(f"el => el.scrollBy({scroll_amount}, 0)")
                await asyncio.sleep(3.0)  # Wait for lazy loading + DOM updates

                # Extract events from current visible DOM
                event_items = await page.query_selector_all('.timeline-item.timeline-event')

                new_count = 0
                for item in event_items:
                    event_data = await extract_single_event(item)
                    if not event_data:
                        continue

                    # Create unique key (start_date, title)
                    event_key = (event_data['start_date'], event_data['full_title'])

                    # Check if this is a new unique event
                    if event_key not in seen_events:
                        seen_events.add(event_key)
                        raw_events.append(event_data)
                        new_count += 1

                        # Log with PROPER title (e.g., "Oguri Cap & Biwa Hayahide Banner")
                        proper_title = build_proper_title(event_data)
                        date_str = event_data.get('date_str', 'NO DATE')
                        print(f"[UMA SCROLL] Found new event: {proper_title} (date: {date_str})")

                # Update counter
                if new_count > 0:
                    print(f"[UMA HANDLER] Scroll RIGHT {i+1}: Found {new_count} new events (total unique: {len(seen_events)})")
                    no_new_events_count = 0
                else:
                    no_new_events_count += 1
                    print(f"[UMA HANDLER] Scroll RIGHT {i+1}: No new events (total unique: {len(seen_events)})")
                    if no_new_events_count >= 30:
                        print(f"[UMA HANDLER] No new events after 30 RIGHT scrolls. Total unique events: {len(seen_events)}")
                        break

            print(f"[UMA HANDLER] Scrolling complete. Captured {len(raw_events)} unique events.")

            await context.close()
            await browser.close()

            uma_handler_logger.info(f"Downloaded {len(raw_events)} raw events from timeline")

            # Debug: Log ALL raw event dates to verify we're capturing future events
            print(f"[UMA HANDLER DEBUG] Showing ALL {len(raw_events)} raw event dates:")
            for i, event in enumerate(raw_events):
                date_str = event.get("date_str", "NO DATE")
                title = event.get("full_title", "NO TITLE")[:40]
                print(f"  [{i+1}] {title}... | Date: {date_str}")

            # Process and combine events
            processed_events = await process_events(raw_events)

            # Filter out events that have already ended
            # This prevents adding expired events to the database
            now = int(datetime.now(timezone.utc).timestamp())
            filtered_events = []
            filtered_count = 0

            for event in processed_events:
                event_end = event.get("end")
                if event_end and event_end < now:
                    # Event has already ended, skip it
                    filtered_count += 1
                    event_title = event.get("title", "Unknown")
                    end_dt = datetime.fromtimestamp(event_end, tz=timezone.utc)
                    print(f"[UMA HANDLER] FILTERED (already ended): '{event_title}' ended at {end_dt}")
                    uma_handler_logger.info(f"[Parse Filter] Skipped ended event: {event_title} (ended {end_dt})")
                else:
                    # Event is still ongoing or upcoming, keep it
                    filtered_events.append(event)

            if filtered_count > 0:
                print(f"[UMA HANDLER] Filtered out {filtered_count} events that already ended")
                uma_handler_logger.info(f"[Parse Filter] Filtered {filtered_count} ended events from {len(processed_events)} total")

            processed_events = filtered_events  # Replace with filtered list

            uma_handler_logger.info(f"Processed {len(processed_events)} events from {len(raw_events)} raw events (after filtering)!")
            
            if len(processed_events) == 0:
                uma_handler_logger.warning("No events were processed! Check if timeline structure has changed.")
            return processed_events
    
    except Exception as e:
        uma_handler_logger.error(f"Failed to download timeline: {e}")
        import traceback
        uma_handler_logger.error(traceback.format_exc())
        return []

def extract_banner_id_from_image_url(img_url):
    """
    Extract banner ID from uma.moe image URLs.

    Args:
        img_url: Image URL like "https://uma.moe/assets/images/character/banner/2021_30048.png"

    Returns:
        str: Banner ID (e.g., "30048") or None if not found
    """
    if not img_url:
        uma_handler_logger.debug(f"[Banner ID Extract] No image URL provided")
        return None

    uma_handler_logger.debug(f"[Banner ID Extract] Processing: {img_url}")

    # Pattern: 202X_XXXXX.png where X is any digit (2020-2029) and XXXXX is the banner ID
    match = re.search(r'202\d_(\d+)\.png', img_url)
    if match:
        banner_id = match.group(1)
        uma_handler_logger.info(f"[Banner ID Extract] ✓ Extracted banner_id={banner_id}")
        return banner_id

    uma_handler_logger.warning(f"[Banner ID Extract] ✗ No match in URL: {img_url}")
    return None

def extract_character_ids_from_legend_images(image_urls):
    """
    Extract character IDs from Legend Race image URLs.
    
    Args:
        image_urls: List of image URLs like "https://uma.moe/assets/images/legend/boss/chara_stand_105601.png"
    
    Returns:
        list: List of character IDs (e.g., ["105601", "102001", "102301"])
    """
    character_ids = []
    
    for img_url in image_urls:
        # Pattern: chara_stand_XXXXXX.png where XXXXXX is the character ID
        match = re.search(r'chara_stand_(\d+)\.png', img_url)
        if match:
            character_ids.append(match.group(1))
    
    return character_ids

async def get_legend_race_characters(character_ids):
    """
    Get character names and links for Legend Race from GameTora database.
    
    Args:
        character_ids: List of character IDs (e.g., ["105601", "102001"])
    
    Returns:
        str: Formatted string with clickable character links, or empty string if no data
    """
    # Check if database exists
    if not os.path.exists(GAMETORA_DB_PATH):
        uma_handler_logger.debug(f"[GameTora] Database not found, skipping Legend Race enrichment")
        return ""
    
    try:
        async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
            character_links = []
            
            for char_id in character_ids:
                # Query for this character ID
                async with conn.execute("""
                    SELECT name, link
                    FROM characters
                    WHERE character_id = ?
                """, (char_id,)) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        name, link = row
                        full_link = f"https://gametora.com{link}"
                        character_links.append(f"[{name}]({full_link})")
                        uma_handler_logger.info(f"[GameTora] Legend Race char {char_id}: {name}")
                    else:
                        uma_handler_logger.warning(f"[GameTora] Legend Race char {char_id} NOT FOUND in database")
                        # Try without leading zeros if ID is 6 digits
                        if len(char_id) == 6 and char_id.startswith('10'):
                            # Try stripping potential leading zero or reformatting
                            alt_id = str(int(char_id))  # Remove leading zeros
                            async with conn.execute("""
                                SELECT name, link
                                FROM characters
                                WHERE character_id = ?
                            """, (alt_id,)) as cursor2:
                                row2 = await cursor2.fetchone()
                                if row2:
                                    name, link = row2
                                    full_link = f"https://gametora.com{link}"
                                    character_links.append(f"[{name}]({full_link})")
                                    uma_handler_logger.info(f"[GameTora] Found with alt ID {alt_id}: {name}")
            
            if character_links:
                result = ", ".join(character_links)
                uma_handler_logger.info(f"[GameTora] Legend Race result: {len(character_links)} chars found out of {len(character_ids)} requested")
                return result
            else:
                uma_handler_logger.warning(f"[GameTora] No Legend Race characters found for IDs: {character_ids}")
                return ""
    
    except Exception as e:
        uma_handler_logger.error(f"[GameTora] Error querying Legend Race characters: {e}")
        return ""

async def enrich_with_gametora_data(char_names, support_names, img_url):
    """
    Enrich character and support names with GameTora data (clickable links).
    Also check if GameTora has a better banner image.

    Args:
        char_names: Plain text character names from uma.moe (e.g., "Name1 & Name2")
        support_names: Plain text support names from uma.moe
        img_url: Current image URL from uma.moe

    Returns:
        tuple: (enriched_char_text, enriched_support_text, best_image_url)
    """
    uma_handler_logger.debug(f"[Enrich] Starting enrichment for image: {img_url}")

    # Extract banner ID from image URL
    banner_id = extract_banner_id_from_image_url(img_url)

    if not banner_id:
        # No banner ID found, return original data
        uma_handler_logger.debug(f"[Enrich] No banner ID extracted, skipping enrichment")
        return char_names, support_names, img_url

    # Query GameTora database
    gametora_data = await get_gametora_banner_data(banner_id)

    if not gametora_data:
        # No GameTora data available, return original
        uma_handler_logger.warning(f"[Enrich] No GameTora data for banner {banner_id}, using original data")
        return char_names, support_names, img_url

    # Build enriched character names with links
    enriched_chars = char_names  # Default to original
    gametora_chars = gametora_data.get("characters", [])
    if gametora_chars:
        char_links = []
        for name, link in gametora_chars:
            full_link = f"https://gametora.com{link}"
            char_links.append(f"[{name}]({full_link})")
        enriched_chars = ", ".join(char_links)
        uma_handler_logger.info(f"[Enrich] Enriched {len(gametora_chars)} character names")

    # Build enriched support names with links
    enriched_supports = support_names  # Default to original
    gametora_supports = gametora_data.get("supports", [])
    if gametora_supports:
        support_links = []
        for name, link in gametora_supports:
            full_link = f"https://gametora.com{link}"
            support_links.append(f"[{name}]({full_link})")
        enriched_supports = ", ".join(support_links)
        uma_handler_logger.info(f"[Enrich] Enriched {len(gametora_supports)} support names")

    # Check if GameTora has a banner image
    best_image = img_url  # Default to uma.moe image
    banner_image = gametora_data.get("banner_image")
    if banner_image:
        # GameTora image path
        gametora_img_path = os.path.join(GAMETORA_IMAGES_PATH, banner_image)
        if os.path.exists(gametora_img_path):
            best_image = gametora_img_path
            uma_handler_logger.info(f"[Enrich] ✓ Using EN image: {banner_image}")
        else:
            uma_handler_logger.warning(f"[Enrich] ✗ EN image file not found: {gametora_img_path}")
    else:
        uma_handler_logger.debug(f"[Enrich] No EN image in database for banner {banner_id}")

    return enriched_chars, enriched_supports, best_image

async def process_events(raw_events):
    """
    Processes raw events from the timeline and combines related events.
    Returns a list of finalized event dicts ready for database insertion.
    """
    processed = []
    skip_indices = set()
    skipped_no_date = 0
    
    print(f"[UMA HANDLER] Processing {len(raw_events)} raw events...")
    
    for i, event in enumerate(raw_events):
        if i in skip_indices:
            continue
        
        full_title = event["full_title"]
        full_text = event.get("full_text", "")  # Full text content for event type detection
        tags = event.get("tags", [])
        description = event.get("description", "")
        start_date = event["start_date"]
        end_date = event["end_date"]
        img_url = event["image_url"]
        
        # Skip events without dates (but count them)
        if not end_date and not start_date:
            skipped_no_date += 1
            print(f"[UMA HANDLER] Skipped (no date): {full_title[:60]}")
            continue
        
        # Detect event type from full_text (contains labels like "CHARACTER BANNER", "STORY EVENT", etc.)
        full_text_upper = full_text.upper()
        
        # Determine the event type
        event_type = "UNKNOWN"
        if "CHARACTER BANNER" in full_text_upper:
            event_type = "CHARACTER_BANNER"
        elif "SUPPORT CARD BANNER" in full_text_upper:
            event_type = "SUPPORT_BANNER"
        elif "STORY EVENT" in full_text_upper:
            event_type = "STORY_EVENT"
        elif "LEGEND RACE" in full_text_upper:
            event_type = "LEGEND_RACE"
        elif "CHAMPIONS MEETING" in full_text_upper:
            event_type = "CHAMPIONS_MEETING"
        elif "PAID BANNER" in full_text_upper:
            event_type = "PAID_BANNER"
        
        print(f"[UMA HANDLER] Processing: {full_title[:50]}... | Type: {event_type} | Tags: {tags}")
        
        # === SUPPORT BANNER (standalone or for combination) ===
        if event_type == "SUPPORT_BANNER":
            # Use tags for support card names - tags are the actual character names
            support_names = " & ".join(tags) if tags else ""
            if not support_names:
                # Fallback: use title without "+X more"
                support_names = re.sub(r"\s*\+\s*\d+\s*more", "", full_title).strip()
                if not support_names:
                    support_names = "Support Cards"
            
            print(f"[UMA HANDLER] Support banner found - Tags: {tags}, Names: {support_names}")
            
            # Check if there's a matching Character banner (look backward and forward)
            char_banner_idx = None
            for j in range(max(0, i-5), min(i+5, len(raw_events))):
                if j == i or j in skip_indices:
                    continue
                check_event = raw_events[j]
                check_full_text = check_event.get("full_text", "").upper()
                if "CHARACTER BANNER" in check_full_text and "SUPPORT" not in check_full_text:
                    # Check if dates match within 24 hours
                    if (check_event["start_date"] and abs((check_event["start_date"] - start_date).total_seconds()) < 86400 and
                        check_event["end_date"] and abs((check_event["end_date"] - end_date).total_seconds()) < 86400):
                        char_banner_idx = j
                        break
            
            # If no matching character banner, create standalone support banner
            if char_banner_idx is None:
                # Enrich with GameTora data
                _, enriched_supports, best_img = await enrich_with_gametora_data(
                    "", support_names, img_url
                )
                
                processed.append({
                    "title": f"{support_names} Support Banner",
                    "start": int(start_date.timestamp()),
                    "end": int(end_date.timestamp()),
                    "image": best_img,  # Use GameTora image if available
                    "category": "Banner",
                    "description": f"**Support Cards:** {enriched_supports}"
                })
                print(f"[UMA HANDLER] Created standalone support banner: {support_names}")
                continue
            else:
                # Skip this support banner, will be combined with character banner
                skip_indices.add(i)
                print(f"[UMA HANDLER] Support banner will be combined with character banner")
                continue
        
        # === CHARACTER + SUPPORT BANNER COMBINATION ===
        if event_type == "CHARACTER_BANNER":
            # Use tags for character names (more accurate than truncated title)
            print(f"[UMA HANDLER] Character banner found - Tags: {tags}, Title: {full_title[:80]}")
            char_names = " & ".join(tags) if tags else ""
            if not char_names:
                # Fallback: use title without "+X more"
                char_names = re.sub(r"\s*\+\s*\d+\s*more", "", full_title).strip()
                if not char_names:
                    char_names = "Character Banner"
                print(f"[UMA HANDLER] No tags found, using parsed name: {char_names}")

            # Look for matching Support banner (search backward and forward)
            support_names = ""
            support_img = None
            support_tags = []
            for j in range(max(0, i-5), min(i+5, len(raw_events))):
                if j == i or j in skip_indices:
                    continue
                next_event = raw_events[j]
                next_full_text = next_event.get("full_text", "").upper()
                if "SUPPORT CARD BANNER" in next_full_text:
                    # Check if dates match
                    if (next_event["start_date"] and abs((next_event["start_date"] - start_date).total_seconds()) < 86400 and
                        next_event["end_date"] and abs((next_event["end_date"] - end_date).total_seconds()) < 86400):
                        support_tags = next_event.get("tags", [])
                        support_names = " & ".join(support_tags) if support_tags else ""
                        print(f"[UMA HANDLER] Found matching support banner - Tags: {support_tags}, Title: {next_event['full_title'][:80]}")
                        if not support_names:
                            support_match = re.search(r"SUPPORT CARDS?:\s*(.+)", next_event["full_title"], re.IGNORECASE)
                            support_names = support_match.group(1).strip() if support_match else ""
                            print(f"[UMA HANDLER] No support tags, using parsed name: {support_names}")
                        support_img = next_event["image_url"]
                        skip_indices.add(j)
                        break

            # ===== NEW ORDER: ENRICH FIRST, THEN COMBINE =====

            # Step 1: Enrich character banner image (gets EN if available, JP as fallback)
            enriched_chars, _, enriched_char_img = await enrich_with_gametora_data(
                char_names, "", img_url
            )
            uma_handler_logger.info(f"[Process] Character enrichment complete: {enriched_char_img[:50]}...")

            # Step 2: Enrich support banner image (gets EN if available, JP as fallback)
            enriched_supports = support_names  # Default to original
            enriched_support_img = None
            if support_names and support_img:
                _, enriched_supports, enriched_support_img = await enrich_with_gametora_data(
                    "", support_names, support_img
                )
                uma_handler_logger.info(f"[Process] Support enrichment complete: {enriched_support_img[:50] if enriched_support_img else 'None'}...")

            # Step 3: THEN combine enriched images (EN if available, JP as fallback)
            # At this point, enriched_char_img and enriched_support_img are the BEST available images
            # (EN from GameTora if exists, otherwise original JP from uma.moe)
            final_img = enriched_char_img
            if enriched_support_img:
                from uma_module import combine_images_vertically
                combined_path = await combine_images_vertically(enriched_char_img, enriched_support_img)
                if combined_path:
                    final_img = combined_path
                    uma_handler_logger.info(f"[Process] ✓ Combined enriched images: {combined_path}")
                else:
                    uma_handler_logger.warning(f"[Process] ✗ Image combination failed, using character image only")

            # Create combined event
            title = f"{char_names} Banner"  # Keep original names in title
            event_desc = f"**Characters:** {enriched_chars}\n**Support Cards:** {enriched_supports}" if enriched_supports else f"**Characters:** {enriched_chars}"

            print(f"[UMA HANDLER] Created banner - Chars: {enriched_chars[:60]}...")
            print(f"[UMA HANDLER] Supports: {enriched_supports[:60] if enriched_supports else 'None'}...")
            
            processed.append({
                "title": title,
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "image": final_img,  # Use best available image
                "category": "Banner",
                "description": event_desc
            })
            continue
        
        # === PAID BANNER COMBINATION ===
        if event_type == "PAID_BANNER":
            # Look for another Paid Banner at the same time
            paired_img = None
            for j in range(i+1, min(i+3, len(raw_events))):
                next_event = raw_events[j]
                if "PAID BANNER" in next_event.get("full_text", "").upper():
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
                combined_path = await combine_images_vertically(img_url, paired_img)
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
        if event_type == "STORY_EVENT":
            # Title is directly the story name (e.g., "Make up in Halloween!")
            story_name = full_title.strip()
            
            # Use description if available
            event_desc = description if description else ""
            
            processed.append({
                "title": story_name,
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "image": img_url,
                "category": "Event",
                "description": event_desc
            })
            continue
        
        # === LEGEND RACE ===
        if event_type == "LEGEND_RACE":
            # Extract race details from lines (e.g., "1600m - Mile - Turf")
            lines = [line.strip() for line in full_text.split('\n') if line.strip()]
            details = ""
            for line in lines:
                # Look for track details line (contains distance and surface)
                if re.match(r'\d+m\s*-', line):
                    details = line
                    break
            
            # Use full_title as race name (e.g., "Asahi Hai Futurity Stakes Legend Race")
            race_name = full_title.strip() if full_title else "Legend Race"
            
            # Get ALL images from this event element (Legend Race has 3-4 character images)
            legend_images = event.get("image_urls", [])
            if not legend_images and img_url:
                legend_images = [img_url]
            
            print(f"[UMA HANDLER] Legend Race '{race_name}' found with {len(legend_images)} images: {legend_images}")
            
            # Extract character IDs from image URLs (e.g., chara_stand_105601.png -> 105601)
            character_ids = extract_character_ids_from_legend_images(legend_images)
            print(f"[UMA HANDLER] Extracted character IDs: {character_ids}")
            
            # Get character names with clickable links from GameTora
            character_links_str = await get_legend_race_characters(character_ids)
            
            # Build description with character links and race details
            event_desc = ""
            if character_links_str:
                event_desc = f"**Characters:** {character_links_str}"
                print(f"[UMA HANDLER] Legend Race characters: {character_links_str[:80]}...")
            if details:
                if event_desc:
                    event_desc += f"\n{details}"
                else:
                    event_desc = details
            
            # Combine images horizontally if multiple
            combined_img = img_url
            if len(legend_images) > 1:
                from uma_module import combine_images_horizontally
                combined_path = await combine_images_horizontally(legend_images)
                if combined_path:
                    combined_img = combined_path
                    print(f"[UMA HANDLER] Combined {len(legend_images)} Legend Race images into: {combined_path}")
            elif legend_images:
                combined_img = legend_images[0]
            
            processed.append({
                "title": race_name,
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "image": combined_img,
                "category": "Event",
                "description": event_desc
            })
            continue
        
        # === CHAMPIONS MEETING ===
        if event_type == "CHAMPIONS_MEETING":
            # Title is directly the cup name (e.g., "Champions Meeting: Virgo Cup")
            cup_name = full_title.strip() if full_title else "Champions Meeting"
            
            # Extract ALL detail lines from raw lines
            lines = [line.strip() for line in full_text.split('\n') if line.strip()]
            detail_lines = []
            
            # Skip known non-detail lines
            skip_keywords = ['emoji_events', 'CHAMPIONS MEETING', cup_name, 'Champions Meeting']
            
            for line in lines:
                # Skip icon names, event type label, and title
                if any(skip in line for skip in skip_keywords):
                    continue
                # Skip date line
                if '–' in line and '202' in line:
                    continue
                # Skip very short lines (likely icons)
                if len(line) < 3:
                    continue
                # This is likely a detail line (track, distance, conditions, etc.)
                detail_lines.append(line)
            
            # Join all detail lines
            details = "\n".join(detail_lines) if detail_lines else ""
            print(f"[UMA HANDLER] Champions Meeting '{cup_name}' details: {detail_lines}")
            
            processed.append({
                "title": cup_name,
                "start": int(start_date.timestamp()) if start_date else int(end_date.timestamp()) - (7*24*60*60),
                "end": int(end_date.timestamp()),
                "image": img_url,
                "category": "Event",
                "description": details if details else ""
            })
            continue
        
        # === FALLBACK: Store all other events with their original titles ===
        # This ensures we don't lose events that don't match specific patterns
        processed.append({
            "title": full_title[:100],  # Limit title length
            "start": int(start_date.timestamp()) if start_date else int(end_date.timestamp()) - (7*24*60*60),
            "end": int(end_date.timestamp()),
            "image": img_url,
            "category": "Event",
            "description": ""
        })
    
    print(f"[UMA HANDLER] Processed: {len(processed)} events | Skipped (no date): {skipped_no_date} | Combined/Skipped: {len(skip_indices)}")
    uma_handler_logger.info(f"Processing complete - {len(processed)} events ready for database")
    
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
    
    # Add or update events in database
    added_count = 0
    updated_count = 0
    skipped_count = 0
    
    for event_data in events:
        try:
            result = await add_uma_event(ctx, event_data)
            added_count += 1
        except Exception as e:
            uma_handler_logger.error(f"Failed to process event '{event_data.get('title', 'Unknown')}': {e}")
            import traceback
            uma_handler_logger.error(traceback.format_exc())
    
    uma_handler_logger.info(f"Processed {added_count}/{len(events)} events.")
    print(f"[UMA HANDLER] Processed {added_count}/{len(events)} events.")
    
    # Refresh dashboard to display new events
    print(f"[UMA HANDLER] Refreshing dashboard to display events...")
    try:
        await uma_update_timers()
        print(f"[UMA HANDLER] Dashboard refreshed successfully!")
    except Exception as e:
        uma_handler_logger.error(f"Failed to refresh dashboard: {e}")
        print(f"[UMA HANDLER] ERROR: Failed to refresh dashboard: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"[UMA HANDLER] Event update complete!")

# ==================== GAMETORA DATABASE SCRAPING ====================

import aiosqlite

GAMETORA_DB_PATH = os.path.join("data", "JP_Data", "uma_jp_data.db")
GAMETORA_IMAGES_PATH = os.path.join("data", "JP_Data", "banner_images")

async def init_gametora_db():
    """Initialize the GameTora database with required tables."""
    os.makedirs(os.path.dirname(GAMETORA_DB_PATH), exist_ok=True)
    os.makedirs(GAMETORA_IMAGES_PATH, exist_ok=True)
    
    async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
        # Banners table (JP server data)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS banners (
                id INTEGER PRIMARY KEY,
                banner_id TEXT UNIQUE NOT NULL,
                banner_type TEXT NOT NULL,
                description TEXT,
                server TEXT NOT NULL DEFAULT 'JP'
            )
        ''')
        
        # Banner characters/cards junction table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS banner_items (
                id INTEGER PRIMARY KEY,
                banner_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                FOREIGN KEY (banner_id) REFERENCES banners(banner_id),
                UNIQUE(banner_id, item_id)
            )
        ''')
        
        # Characters table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY,
                character_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                link TEXT NOT NULL
            )
        ''')
        
        # Support cards table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS support_cards (
                id INTEGER PRIMARY KEY,
                card_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                link TEXT NOT NULL
            )
        ''')
        
        # Global banner images table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS global_banner_images (
                id INTEGER PRIMARY KEY,
                banner_id TEXT UNIQUE NOT NULL,
                image_filename TEXT NOT NULL
            )
        ''')
        
        # Metadata table for tracking last update
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        await conn.commit()
        uma_handler_logger.info(f"[GameTora DB] Database initialized at: {GAMETORA_DB_PATH}")

async def get_existing_banner_ids(server: str = "JP"):
    """Get all existing banner IDs from the database for a given server."""
    await init_gametora_db()
    async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
        if server == "JP":
            # Check both 'JP' and 'JA' for backwards compatibility
            async with conn.execute("SELECT banner_id FROM banners WHERE server IN ('JP', 'JA')") as cursor:
                rows = await cursor.fetchall()
                return {row[0] for row in rows}
        else:
            async with conn.execute("SELECT banner_id FROM global_banner_images") as cursor:
                rows = await cursor.fetchall()
                return {row[0] for row in rows}

async def get_website_banner_ids(page, server: str = "JP"):
    """
    Quick check to get banner IDs from the website without full parsing.
    Returns a set of banner IDs found on the page.
    """
    banner_ids = set()
    
    # Find all banner images
    img_tags = await page.query_selector_all('img[src*="img_bnr_gacha_"]')
    
    for img_tag in img_tags:
        img_src = await img_tag.get_attribute('src')
        if img_src:
            banner_id_match = re.search(r'img_bnr_gacha_(\d+)\.png', img_src)
            if banner_id_match:
                banner_ids.add(banner_id_match.group(1))
    
    return banner_ids

async def get_gametora_banner_data(banner_id: str):
    """
    Query GameTora database for banner data including character/support card names and links.

    Args:
        banner_id: The banner ID to look up (e.g., "30048")

    Returns:
        dict: {
            "characters": [(name, link), ...],
            "supports": [(name, link), ...],
            "banner_image": filename or None
        }
        Returns empty dict if database doesn't exist or banner not found.
    """
    uma_handler_logger.info(f"[GameTora] Looking up banner_id={banner_id}")

    # Check if database exists
    if not os.path.exists(GAMETORA_DB_PATH):
        uma_handler_logger.warning(f"[GameTora] ✗ DATABASE NOT FOUND: {GAMETORA_DB_PATH}")
        uma_handler_logger.warning(f"[GameTora] Run !uma_gametora_refresh to populate database")
        return {}

    try:
        async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
            # Get characters for this banner
            characters = []
            async with conn.execute("""
                SELECT c.name, c.link
                FROM banner_items bi
                JOIN characters c ON bi.item_id = c.character_id
                WHERE bi.banner_id = ? AND bi.item_type = 'Character'
            """, (banner_id,)) as cursor:
                rows = await cursor.fetchall()
                characters = [(name, link) for name, link in rows]

            # Get support cards for this banner
            supports = []
            async with conn.execute("""
                SELECT s.name, s.link
                FROM banner_items bi
                JOIN support_cards s ON bi.item_id = s.card_id
                WHERE bi.banner_id = ? AND bi.item_type = 'Support'
            """, (banner_id,)) as cursor:
                rows = await cursor.fetchall()
                supports = [(name, link) for name, link in rows]

            # Get banner image if available
            banner_image = None
            async with conn.execute("""
                SELECT image_filename
                FROM global_banner_images
                WHERE banner_id = ?
            """, (banner_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    banner_image = row[0]

            # Log results with clear status indicators
            uma_handler_logger.info(
                f"[GameTora] Banner {banner_id}: "
                f"{len(characters)} chars, {len(supports)} supports, "
                f"image={'✓ ' + banner_image if banner_image else '✗ None'}"
            )

            return {
                "characters": characters,
                "supports": supports,
                "banner_image": banner_image
            }

    except Exception as e:
        uma_handler_logger.error(f"[GameTora] Error querying banner {banner_id}: {e}")
        import traceback
        uma_handler_logger.error(traceback.format_exc())
        return {}

async def scrape_gametora_jp_banners(force_full_scan: bool = False, max_retries: int = 3):
    """
    Step 1: Scrape JP server banners from GameTora.
    Extracts banner ID, type, description, and linked characters/support cards.
    
    If force_full_scan is False, will first check for new banners and skip if none found.
    """
    print("[GameTora] Starting JP banner check...")
    uma_handler_logger.info("[GameTora] Starting JP banner check...")
    
    await init_gametora_db()
    
    url = "https://gametora.com/umamusume/gacha/history?server=ja&type=all&year=all"
    last_error = None
    
    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Set longer default timeout for slow connections (Raspberry Pi)
                page.set_default_timeout(90000)
                
                # Navigate to JP server, all years, all types
                print(f"[GameTora] Navigating to {url} (attempt {attempt + 1}/{max_retries})")
                await page.goto(url, timeout=90000, wait_until="domcontentloaded")
                
                # Wait for initial content to render
                await asyncio.sleep(5)
                
                # Check what's actually loaded
                page_url = page.url
                print(f"[GameTora] Current page URL: {page_url}")
                
                # Wait for banner containers to appear
                try:
                    await page.wait_for_selector('.sc-37bc0b3c-0', timeout=30000)
                except Exception as selector_err:
                    print(f"[GameTora] Warning: No banner containers found, page may not have loaded correctly: {selector_err}")
                    uma_handler_logger.warning(f"[GameTora] No banner containers found: {selector_err}")
                
                # Get initial count before scrolling
                initial_containers = await page.query_selector_all('.sc-37bc0b3c-0')
                print(f"[GameTora] Initial banners loaded: {len(initial_containers)}")
                
                # Scroll DOWN progressively to load all banners (lazy loading)
                print("[GameTora] Scrolling to load all banners...")
                
                previous_count = len(initial_containers)
                no_change_count = 0
                scroll_iteration = 0
                max_iterations = 50  # Prevent infinite loop
                
                while scroll_iteration < max_iterations:
                    # Get current banner count
                    current_containers = await page.query_selector_all('.sc-37bc0b3c-0')
                    current_count = len(current_containers)
                    
                    print(f"[GameTora] Scroll iteration {scroll_iteration + 1}: {current_count} banners loaded")
                    
                    # If count hasn't changed, increment no-change counter
                    if current_count == previous_count:
                        no_change_count += 1
                        # If no new banners after 5 scroll attempts, we're done
                        if no_change_count >= 5:
                            print(f"[GameTora] No new banners loaded after 5 attempts, stopping scroll")
                            break
                    else:
                        no_change_count = 0  # Reset when new content loads
                    
                    previous_count = current_count
                    
                    # Scroll down to bottom to trigger lazy load
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    
                    # Wait for new content to load (important!)
                    await asyncio.sleep(3)
                    
                    scroll_iteration += 1
                
                # Quick check: Get banner IDs from website
                website_banner_ids = await get_website_banner_ids(page, "JP")
                print(f"[GameTora] Found {len(website_banner_ids)} banners on website after scrolling")
                
                # Get existing banner IDs from database
                existing_banner_ids = await get_existing_banner_ids("JP")
                print(f"[GameTora] Have {len(existing_banner_ids)} banners in database")
                
                # Find new banners
                new_banner_ids = website_banner_ids - existing_banner_ids
                
                if not new_banner_ids and not force_full_scan:
                    print(f"[GameTora] No new JP banners found. Skipping full scan.")
                    uma_handler_logger.info("[GameTora] No new JP banners found. Skipping full scan.")
                    await browser.close()
                    return {"banners": 0, "characters": 0, "support_cards": 0, "skipped": True}
                
                if new_banner_ids:
                    print(f"[GameTora] Found {len(new_banner_ids)} NEW banners: {new_banner_ids}")
                elif force_full_scan:
                    print(f"[GameTora] Force full scan requested.")
                
                # Find all banner containers using the actual CSS class
                banner_containers = await page.query_selector_all('.sc-37bc0b3c-0')
                print(f"[GameTora] Processing {len(banner_containers)} banner containers...")
                
                banners_added = 0
                characters_added = 0
                supports_added = 0
                
                async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
                    for container in banner_containers:
                        try:
                            # Get banner image to extract ID
                            img_tag = await container.query_selector('img[src*="img_bnr_gacha_"]')
                            if not img_tag:
                                continue
                            
                            img_src = await img_tag.get_attribute('src')
                            if not img_src:
                                continue
                            
                            # Extract banner ID from image URL (e.g., img_bnr_gacha_30380.png -> 30380)
                            banner_id_match = re.search(r'img_bnr_gacha_(\d+)\.png', img_src)
                            if not banner_id_match:
                                continue
                            
                            banner_id = banner_id_match.group(1)
                            
                            # Skip if already in database and not force scanning
                            if banner_id in existing_banner_ids and not force_full_scan:
                                continue
                            
                            # Get the character/support list to determine banner type
                            banner_type = "Unknown"
                            description = ""
                            
                            # Get all character/support names and IDs from the list (ul.sc-37bc0b3c-3)
                            items_list = await container.query_selector('ul.sc-37bc0b3c-3')
                            item_names = []
                            item_data = []  # List of (name, id, link) tuples
                            
                            if items_list:
                                # Get all list items
                                list_items = await items_list.query_selector_all('li')
                                
                                for li in list_items:
                                    # Get the clickable span that triggers tooltip
                                    clickable_span = await li.query_selector('.gacha_link_alt__mZW_P')
                                    if not clickable_span:
                                        continue
                                    
                                    # Get name from span
                                    name_text = (await clickable_span.inner_text()).strip()
                                    if not name_text:
                                        continue
                                    
                                    # Hover to reveal tooltip with link
                                    await clickable_span.hover()
                                    await asyncio.sleep(0.5)  # Wait for tooltip to appear
                                    
                                    # Find tooltip and extract link
                                    item_id = None
                                    item_link = ""
                                    
                                    tooltip = await page.query_selector('[role="tooltip"]')
                                    if tooltip:
                                        # Find link in tooltip (characters or supports)
                                        link_elem = await tooltip.query_selector('a[href*="character"], a[href*="support"]')
                                        if link_elem:
                                            href = await link_elem.get_attribute('href')
                                            if href:
                                                item_link = href
                                                # Extract ID from /characters/XXXXX or /supports/XXXXX
                                                id_match = re.search(r'/(?:characters|supports)/(\d+)', href)
                                                if id_match:
                                                    item_id = id_match.group(1)
                                    
                                    # Move mouse away to close tooltip
                                    await page.mouse.move(0, 0)
                                    await asyncio.sleep(0.2)
                                    
                                    item_names.append(name_text)
                                    item_data.append((name_text, item_id, item_link))
                                
                                # Determine if it's Character or Support based on container text
                                container_text = await container.inner_text()
                                if "Support Card" in container_text or "サポートカード" in container_text:
                                    banner_type = "Support"
                                elif "Character" in container_text or "キャラクター" in container_text:
                                    banner_type = "Character"
                                else:
                                    # Fallback: check for rate-up markers (usually only on character banners)
                                    if any("New" in name or "Rerun" in name for name in item_names):
                                        banner_type = "Character"
                                    else:
                                        banner_type = "Unknown"
                                
                                # Clean names for description (remove " New" or " Rerun" from end)
                                clean_names = []
                                for name in item_names:  # ALL items
                                    # Remove " New" or " Rerun" from end, along with any trailing rate info
                                    clean = re.sub(r'\s+(New|Rerun)(?:,?\s*[\d.]+%)?\s*$', '', name).strip()
                                    if clean:
                                        clean_names.append(clean)
                                
                                description = ", ".join(clean_names)
                            
                            # Insert banner into database
                            await conn.execute('''
                                INSERT OR REPLACE INTO banners (banner_id, banner_type, description, server)
                                VALUES (?, ?, ?, 'JA')
                            ''', (banner_id, banner_type, description))
                            banners_added += 1
                            # Truncate only for display, not for storage
                            display_desc = description if len(description) <= 80 else description[:77] + "..."
                            print(f"[GameTora] Added banner {banner_id} ({banner_type}): {display_desc}")
                            
                            # Store character/support names with actual IDs from links
                            for item_name, item_id, item_link in item_data:
                                # Clean up name - remove " New" or " Rerun" from end with optional rate info
                                clean_name = re.sub(r'\s+(New|Rerun)(?:,?\s*[\d.]+%)?\s*$', '', item_name).strip()
                                
                                if not clean_name:
                                    continue
                                
                                # Use extracted ID if available, otherwise fall back to hash
                                if not item_id:
                                    item_id = str(abs(hash(clean_name)) % 1000000)
                                    uma_handler_logger.warning(f"[GameTora] No ID found for {clean_name}, using hash: {item_id}")
                                
                                if banner_type == "Character":
                                    await conn.execute('''
                                        INSERT OR IGNORE INTO characters (character_id, name, link)
                                        VALUES (?, ?, ?)
                                    ''', (item_id, clean_name, item_link))
                                    characters_added += 1
                                    
                                    await conn.execute('''
                                        INSERT OR IGNORE INTO banner_items (banner_id, item_id, item_type)
                                        VALUES (?, ?, 'Character')
                                    ''', (banner_id, item_id))
                                else:
                                    await conn.execute('''
                                        INSERT OR IGNORE INTO support_cards (card_id, name, link)
                                        VALUES (?, ?, ?)
                                    ''', (item_id, clean_name, item_link))
                                    supports_added += 1
                                    
                                    await conn.execute('''
                                        INSERT OR IGNORE INTO banner_items (banner_id, item_id, item_type)
                                        VALUES (?, ?, 'Support')
                                    ''', (banner_id, item_id))
                            
                        except Exception as e:
                            uma_handler_logger.warning(f"[GameTora] Error processing banner container: {e}")
                            continue
                    
                    # Update last scan timestamp
                    await conn.execute('''
                        INSERT OR REPLACE INTO metadata (key, value)
                        VALUES ('last_jp_scan', ?)
                    ''', (datetime.now(timezone.utc).isoformat(),))
                    
                    await conn.commit()
                
                await browser.close()
                
                print(f"[GameTora] JP scrape complete: {banners_added} banners, {characters_added} characters, {supports_added} support cards")
                uma_handler_logger.info(f"[GameTora] JP scrape complete: {banners_added} banners, {characters_added} chars, {supports_added} supports")
                
                return {
                    "banners": banners_added,
                    "characters": characters_added,
                    "support_cards": supports_added,
                    "skipped": False
                }
                
        except Exception as e:
            last_error = e
            uma_handler_logger.warning(f"[GameTora] JP scrape attempt {attempt + 1}/{max_retries} failed: {e}")
            print(f"[GameTora] JP scrape attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10  # 10s, 20s, 30s backoff
                print(f"[GameTora] Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
    
    # All retries failed
    uma_handler_logger.error(f"[GameTora] Failed to scrape JP banners after {max_retries} attempts: {last_error}")
    import traceback
    traceback.print_exc()
    return None

async def scrape_gametora_all_characters(max_retries: int = 3):
    """
    Scrape ALL characters from GameTora's character list page.
    This includes low-rarity characters that never appeared in banners.
    """
    print("[GameTora] Starting ALL characters scrape...")
    uma_handler_logger.info("[GameTora] Starting ALL characters scrape...")
    
    await init_gametora_db()
    
    url = "https://gametora.com/umamusume/characters"
    last_error = None
    
    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                page.set_default_timeout(90000)
                
                print(f"[GameTora] Navigating to {url} (attempt {attempt + 1}/{max_retries})")
                await page.goto(url, timeout=90000, wait_until="domcontentloaded")
                
                # Wait for page to load
                await asyncio.sleep(5)
                
                # Enable "Show Upcoming Characters" checkbox to get JP-exclusive characters
                try:
                    checkboxes = await page.query_selector_all('input[type="checkbox"]')
                    print(f"[GameTora] Found {len(checkboxes)} checkboxes")
                    
                    for cb in checkboxes:
                        # Get parent element to check label text
                        parent = await cb.evaluate_handle('el => el.parentElement')
                        parent_text = await parent.inner_text() if parent else ""
                        
                        if "upcoming" in parent_text.lower() or "show" in parent_text.lower():
                            is_checked = await cb.is_checked()
                            if not is_checked:
                                print("[GameTora] Enabling 'Show Upcoming Characters' checkbox")
                                await cb.click()
                                await asyncio.sleep(3)
                                break
                except Exception as e:
                    print(f"[GameTora] Could not find/toggle upcoming characters checkbox: {e}")
                
                # Scroll to load all characters (lazy loading)
                print("[GameTora] Scrolling to load all characters...")
                previous_count = 0
                no_change_count = 0
                scroll_iteration = 0
                max_iterations = 30
                
                while scroll_iteration < max_iterations:
                    # Find all character links
                    char_links = await page.query_selector_all('a[href*="/umamusume/characters/"]')
                    current_count = len(char_links)
                    
                    if scroll_iteration % 5 == 0:  # Log every 5 iterations
                        print(f"[GameTora] Scroll iteration {scroll_iteration + 1}: {current_count} characters found")
                    
                    if current_count == previous_count:
                        no_change_count += 1
                        if no_change_count >= 3:
                            print(f"[GameTora] No new characters after 3 attempts, stopping scroll")
                            break
                    else:
                        no_change_count = 0
                    
                    previous_count = current_count
                    
                    # Scroll to bottom
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2)
                    scroll_iteration += 1
                
                print(f"[GameTora] Found {current_count} total character links, extracting data...")
                
                # Extract character data
                char_links = await page.query_selector_all('a[href*="/umamusume/characters/"]')
                
                characters_data = []
                for link_elem in char_links:
                    try:
                        # Get link href
                        href = await link_elem.get_attribute('href')
                        if not href or '/profiles' in href:
                            continue
                        
                        # Extract character ID from URL (e.g., /umamusume/characters/101801-air-groove)
                        match = re.search(r'/characters/(\d+)-', href)
                        if not match:
                            continue
                        
                        character_id = match.group(1)
                        
                        # Get full link text (includes stars and name)
                        full_text = (await link_elem.inner_text()).strip()
                        
                        # Text format can be:
                        # 1. "⭐⭐⭐\nCharacter Name" (base characters with stars)
                        # 2. "Event Type\nCharacter Name" (alternate versions like "Festival\nSymboli Rudolf")
                        # 3. "Character Name" (some characters without prefix)
                        
                        # Remove star emojis first
                        text_without_stars = re.sub(r'⭐+', '', full_text).strip()
                        
                        # Split by newlines and get the last non-empty line (that's the actual character name)
                        lines = [line.strip() for line in text_without_stars.split('\n') if line.strip()]
                        
                        if not lines:
                            continue
                        
                        # The character name is always the last line
                        # For "Festival\nSymboli Rudolf" -> "Symboli Rudolf"
                        # For "Eishin Flash" -> "Eishin Flash"
                        name = lines[-1]
                        
                        # If there's a prefix (like "Festival"), include it: "Symboli Rudolf (Festival)"
                        if len(lines) > 1:
                            prefix = lines[0]  # "Festival", "Halloween", "Christmas", etc.
                            name = f"{name} ({prefix})"
                        
                        if not name:
                            continue
                        
                        # Use href as-is (already has full path)
                        full_link = href if href.startswith('/') else f"/{href}"
                        
                        characters_data.append({
                            'character_id': character_id,
                            'name': name,
                            'link': full_link
                        })
                        
                    except Exception as e:
                        print(f"[GameTora] Error extracting character: {e}")
                        continue
                
                await browser.close()
                
                print(f"[GameTora] Extracted {len(characters_data)} characters")
                uma_handler_logger.info(f"[GameTora] Extracted {len(characters_data)} characters")
                
                # Save to database
                if characters_data:
                    async with aiosqlite.connect(GAMETORA_DB_PATH) as db:
                        # First, log some sample characters to verify format
                        sample_chars = characters_data[:5]
                        print(f"[GameTora] Sample character names being saved:")
                        for char in sample_chars:
                            print(f"  ID {char['character_id']}: {char['name']}")
                        
                        # Insert or replace characters (this will overwrite old bad data)
                        updated_count = 0
                        for char in characters_data:
                            await db.execute('''
                                INSERT OR REPLACE INTO characters (character_id, name, link)
                                VALUES (?, ?, ?)
                            ''', (char['character_id'], char['name'], char['link']))
                            updated_count += 1
                        
                        await db.commit()
                        print(f"[GameTora] Saved/updated {updated_count} characters to database")
                        uma_handler_logger.info(f"[GameTora] Saved/updated {updated_count} characters to database")
                
                return len(characters_data)
                
        except Exception as e:
            last_error = e
            print(f"[GameTora] Error during character scrape (attempt {attempt + 1}/{max_retries}): {e}")
            uma_handler_logger.error(f"[GameTora] Error during character scrape: {e}")
            
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10
                print(f"[GameTora] Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
    
    # All retries failed
    uma_handler_logger.error(f"[GameTora] Failed to scrape characters after {max_retries} attempts: {last_error}")
    import traceback
    traceback.print_exc()
    return None

async def scrape_gametora_global_images(force_full_scan: bool = False, max_retries: int = 3):
    """
    Step 2: Scrape Global server banner images from GameTora.
    Downloads banner images and links them to banner IDs.
    
    If force_full_scan is False, will first check for new banners and skip if none found.
    """
    print("[GameTora] Starting Global banner image check...")
    uma_handler_logger.info("[GameTora] Starting Global banner image check...")
    
    await init_gametora_db()
    
    url = "https://gametora.com/umamusume/gacha/history?server=en&type=all&year=all"
    last_error = None
    
    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Set longer default timeout for slow connections (Raspberry Pi)
                page.set_default_timeout(90000)
                
                # Navigate to Global server, all years, all types
                print(f"[GameTora] Navigating to {url} (attempt {attempt + 1}/{max_retries})")
                await page.goto(url, timeout=90000, wait_until="domcontentloaded")
                
                # Wait for initial content to render
                await asyncio.sleep(5)
                
                # Wait for banner containers to appear
                try:
                    await page.wait_for_selector('.sc-37bc0b3c-0', timeout=30000)
                except Exception as selector_err:
                    print(f"[GameTora] Warning: No banner containers found, page may not have loaded correctly: {selector_err}")
                    uma_handler_logger.warning(f"[GameTora] No banner containers found: {selector_err}")
                
                # Scroll DOWN progressively to load all Global banners (lazy loading)
                print("[GameTora] Scrolling to load all Global banners...")
                
                previous_count = 0
                no_change_count = 0
                scroll_iteration = 0
                max_iterations = 50  # Prevent infinite loop
                
                while scroll_iteration < max_iterations:
                    # Get current banner count
                    current_containers = await page.query_selector_all('.sc-37bc0b3c-0')
                    current_count = len(current_containers)
                    
                    print(f"[GameTora] Scroll iteration {scroll_iteration + 1}: {current_count} banners loaded")
                    
                    # If count hasn't changed, increment no-change counter
                    if current_count == previous_count:
                        no_change_count += 1
                        # If no new banners after 5 scroll attempts, we're done
                        if no_change_count >= 5:
                            print(f"[GameTora] No new banners loaded after 5 attempts, stopping scroll")
                            break
                    else:
                        no_change_count = 0  # Reset when new content loads
                    
                    previous_count = current_count
                    
                    # Scroll down to bottom to trigger lazy load
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    
                    # Wait for new content to load (important!)
                    await asyncio.sleep(3)
                    
                    scroll_iteration += 1
                
                # Quick check: Get banner IDs from website
                website_banner_ids = await get_website_banner_ids(page, "Global")
                print(f"[GameTora] Found {len(website_banner_ids)} Global banners on website after scrolling")
                
                # Get existing banner IDs from database
                existing_banner_ids = await get_existing_banner_ids("Global")
                print(f"[GameTora] Have {len(existing_banner_ids)} Global banner images in database")
                
                # Find new banners
                new_banner_ids = website_banner_ids - existing_banner_ids
                
                if not new_banner_ids and not force_full_scan:
                    print(f"[GameTora] No new Global banners found. Skipping image download.")
                    uma_handler_logger.info("[GameTora] No new Global banners found. Skipping image download.")
                    await browser.close()
                    return {"images_saved": 0, "skipped": True}
                
                if new_banner_ids:
                    print(f"[GameTora] Found {len(new_banner_ids)} NEW Global banners to download: {new_banner_ids}")
                elif force_full_scan:
                    print(f"[GameTora] Force full scan requested.")
                
                # Find all banner containers using the actual CSS class
                banner_containers = await page.query_selector_all('.sc-37bc0b3c-0')
                print(f"[GameTora] Processing {len(banner_containers)} Global banner containers...")
                
                images_saved = 0
                
                async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
                  async with aiohttp.ClientSession() as session:
                    for container in banner_containers:
                        try:
                            # Get banner image
                            img_tag = await container.query_selector('img[src*="img_bnr_gacha_"]')
                            if not img_tag:
                                continue
                            
                            img_src = await img_tag.get_attribute('src')
                            if not img_src:
                                continue
                            
                            # Extract banner ID from image URL
                            banner_id_match = re.search(r'img_bnr_gacha_(\d+)\.png', img_src)
                            if not banner_id_match:
                                continue
                            
                            banner_id = banner_id_match.group(1)
                            
                            # Build full image URL
                            if img_src.startswith('/'):
                                full_img_url = f"https://gametora.com{img_src}"
                            elif img_src.startswith('http'):
                                full_img_url = img_src
                            else:
                                full_img_url = f"https://gametora.com/{img_src}"
                            
                            # Download and save image
                            filename = f"banner_{banner_id}.png"
                            filepath = os.path.join(GAMETORA_IMAGES_PATH, filename)
                            
                            # Determine if we should download
                            should_download = False
                            reason = ""
                            
                            if not os.path.exists(filepath):
                                should_download = True
                                reason = "new"
                            elif force_full_scan:
                                should_download = True
                                reason = "force_scan"
                            elif os.path.exists(filepath):
                                # Check file size - if suspiciously small (<10KB), might be placeholder
                                file_size = os.path.getsize(filepath)
                                if file_size < 10240:  # Less than 10KB
                                    should_download = True
                                    reason = f"small_file ({file_size} bytes, likely placeholder)"
                                else:
                                    # Check website image size to see if it's different
                                    try:
                                        # HEAD request to get content-length without downloading full image
                                        async with session.head(full_img_url, timeout=10) as head_response:
                                            if head_response.status == 200 and 'content-length' in head_response.headers:
                                                website_size = int(head_response.headers['content-length'])
                                            
                                                if website_size != file_size:
                                                    should_download = True
                                                    reason = f"size_mismatch (local: {file_size} bytes, website: {website_size} bytes)"
                                            else:
                                                # If HEAD fails, try GET to check size
                                                uma_handler_logger.debug(f"[GameTora] HEAD request failed for {banner_id}, will check during download")
                                    except Exception as size_check_err:
                                        uma_handler_logger.debug(f"[GameTora] Size check failed for {banner_id}: {size_check_err}")
                            
                            if should_download:
                                try:
                                    async with session.get(full_img_url, timeout=30) as response:
                                      if response.status == 200:
                                        new_content = await response.read()
                                        website_size = len(new_content)
                                        
                                        # Check if content is actually different
                                        if os.path.exists(filepath):
                                            with open(filepath, 'rb') as f:
                                                old_content = f.read()
                                            
                                            # Compare content
                                            if new_content == old_content:
                                                print(f"[GameTora] Skipping {filename} (content unchanged despite size check)")
                                                # Link to database even if we didn't update the file
                                                await conn.execute('''
                                                    INSERT OR REPLACE INTO global_banner_images (banner_id, image_filename)
                                                    VALUES (?, ?)
                                                ''', (banner_id, filename))
                                                continue
                                            
                                            # Content is different, log the change
                                            old_size = len(old_content)
                                            size_change = website_size - old_size
                                            size_change_str = f"+{size_change}" if size_change > 0 else str(size_change)
                                            print(f"[GameTora] Updating {filename}: {old_size} → {website_size} bytes ({size_change_str}), reason: {reason}")
                                        else:
                                            print(f"[GameTora] Saving {filename}: {website_size} bytes, reason: {reason}")
                                        
                                        # Save the new image
                                        with open(filepath, 'wb') as f:
                                            f.write(new_content)
                                        
                                        images_saved += 1
                                      else:
                                        uma_handler_logger.warning(f"[GameTora] Failed to download {full_img_url}: HTTP {response.status}")
                                        continue
                                except Exception as dl_err:
                                    uma_handler_logger.warning(f"[GameTora] Failed to download {full_img_url}: {dl_err}")
                                    continue
                            else:
                                # Skip - file exists and size matches
                                if banner_id not in existing_banner_ids:
                                    # New banner but file exists (shouldn't happen, but handle it)
                                    print(f"[GameTora] File exists for new banner {banner_id}, linking to database")
                                    images_saved += 1
                            
                            # Link banner ID to image filename
                            await conn.execute('''
                                INSERT OR REPLACE INTO global_banner_images (banner_id, image_filename)
                                VALUES (?, ?)
                            ''', (banner_id, filename))
                            images_saved += 1
                            
                        except Exception as e:
                            uma_handler_logger.warning(f"[GameTora] Error processing Global banner: {e}")
                            continue
                    
                    # Update last scan timestamp
                    await conn.execute('''
                        INSERT OR REPLACE INTO metadata (key, value)
                        VALUES ('last_global_scan', ?)
                    ''', (datetime.now(timezone.utc).isoformat(),))
                    
                    await conn.commit()
                
                await browser.close()
                
                print(f"[GameTora] Global image scrape complete: {images_saved} images saved")
                uma_handler_logger.info(f"[GameTora] Global image scrape complete: {images_saved} images")
                
                return {"images_saved": images_saved, "skipped": False}
                
        except Exception as e:
            last_error = e
            uma_handler_logger.warning(f"[GameTora] Global scrape attempt {attempt + 1}/{max_retries} failed: {e}")
            print(f"[GameTora] Global scrape attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10  # 10s, 20s, 30s backoff
                print(f"[GameTora] Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
    
    # All retries failed
    uma_handler_logger.error(f"[GameTora] Failed to scrape Global images after {max_retries} attempts: {last_error}")
    import traceback
    traceback.print_exc()
    return None

async def update_gametora_database(force_full_scan: bool = False):
    """
    Main function to update the GameTora database.
    Called on bot startup to sync banner data.
    
    Args:
        force_full_scan: If True, re-scans all banners even if they exist in database
    """
    print("[GameTora] Starting database update...")
    uma_handler_logger.info("[GameTora] Starting database update...")
    
    # Step 1: Scrape ALL characters from character list (includes low-rarity chars)
    chars_result = await scrape_gametora_all_characters()
    
    # Step 2: Scrape JP banners (IDs, types, characters, support cards)
    jp_result = await scrape_gametora_jp_banners(force_full_scan)
    
    # Step 3: Scrape Global banner images
    global_result = await scrape_gametora_global_images(force_full_scan)
    
    # Summary
    jp_skipped = jp_result.get("skipped", False) if jp_result else True
    global_skipped = global_result.get("skipped", False) if global_result else True
    
    if jp_skipped and global_skipped:
        print("[GameTora] Database up to date - no new banners found.")
        uma_handler_logger.info("[GameTora] Database up to date - no new banners found.")
    else:
        print("[GameTora] Database update complete!")
        uma_handler_logger.info("[GameTora] Database update complete!")
    
    return {
        "characters": chars_result,
        "jp": jp_result,
        "global": global_result
    }

# Utility functions to query the database

async def get_character_by_id(character_id: str):
    """Get character info by ID."""
    async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT character_id, name, link FROM characters WHERE character_id = ?",
            (character_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"id": row[0], "name": row[1], "link": row[2]}
    return None

async def get_character_by_name(name: str):
    """Get character info by name (partial match)."""
    async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT character_id, name, link FROM characters WHERE name LIKE ?",
            (f"%{name}%",)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"id": row[0], "name": row[1], "link": row[2]} for row in rows]

async def get_support_card_by_id(card_id: str):
    """Get support card info by ID."""
    async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT card_id, name, link FROM support_cards WHERE card_id = ?",
            (card_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"id": row[0], "name": row[1], "link": row[2]}
    return None

async def get_banner_image(banner_id: str):
    """Get the local image path for a banner."""
    async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT image_filename FROM global_banner_images WHERE banner_id = ?",
            (banner_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return os.path.join(GAMETORA_IMAGES_PATH, row[0])
    return None

async def get_banner_characters(banner_id: str):
    """Get all characters featured in a banner."""
    async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
        async with conn.execute('''
            SELECT c.character_id, c.name, c.link
            FROM banner_items bi
            JOIN characters c ON bi.item_id = c.character_id
            WHERE bi.banner_id = ? AND bi.item_type = 'Character'
        ''', (banner_id,)) as cursor:
            rows = await cursor.fetchall()
            return [{"id": row[0], "name": row[1], "link": row[2]} for row in rows]

async def get_banner_support_cards(banner_id: str):
    """Get all support cards featured in a banner."""
    async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
        async with conn.execute('''
            SELECT s.card_id, s.name, s.link
            FROM banner_items bi
            JOIN support_cards s ON bi.item_id = s.card_id
            WHERE bi.banner_id = ? AND bi.item_type = 'Support'
        ''', (banner_id,)) as cursor:
            rows = await cursor.fetchall()
            return [{"id": row[0], "name": row[1], "link": row[2]} for row in rows]

if __name__ == "__main__":
    asyncio.run(update_uma_events())