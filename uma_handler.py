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

            # Check initial event count
            initial_events = await page.query_selector_all('.timeline-item.timeline-event')
            print(f"[UMA HANDLER] Initial event count on page load: {len(initial_events)}")
            uma_handler_logger.info(f"Initial event count: {len(initial_events)}")
            
            # Take screenshot for debugging
            await page.screenshot(path="uma_timeline_initial.png")
            print("[UMA HANDLER] Screenshot saved: uma_timeline_initial.png")

            # === SCROLL RIGHT (to future/newer events) ===
            print("[UMA HANDLER] Phase 1: Scrolling RIGHT to load future events...")
            scroll_amount = 400  # Scroll RIGHT
            max_scrolls = 100
            no_new_events_count = 0
            previous_event_count = len(initial_events)

            for i in range(max_scrolls):
                await timeline.evaluate(f"el => el.scrollBy({scroll_amount}, 0)")
                await asyncio.sleep(1.5)  # Wait for lazy loading
                event_items = await page.query_selector_all('.timeline-item.timeline-event')
                current_count = len(event_items)

                print(f"[UMA HANDLER] Scroll RIGHT {i+1}: {current_count} events (+{current_count - previous_event_count})")

                if current_count > previous_event_count:
                    previous_event_count = current_count
                    no_new_events_count = 0
                else:
                    no_new_events_count += 1
                    if no_new_events_count >= 10:
                        print(f"[UMA HANDLER] No new events after 10 RIGHT scrolls. Total: {current_count}")
                        break
            
            # === SCROLL LEFT (to past/older events) ===
            print("[UMA HANDLER] Phase 2: Scrolling LEFT to load past events...")
            scroll_amount = -400  # Scroll LEFT
            no_new_events_count = 0
            
            for i in range(max_scrolls):
                await timeline.evaluate(f"el => el.scrollBy({scroll_amount}, 0)")
                await asyncio.sleep(1.5)
                event_items = await page.query_selector_all('.timeline-item.timeline-event')
                current_count = len(event_items)

                print(f"[UMA HANDLER] Scroll LEFT {i+1}: {current_count} events (+{current_count - previous_event_count})")

                if current_count > previous_event_count:
                    previous_event_count = current_count
                    no_new_events_count = 0
                else:
                    no_new_events_count += 1
                    if no_new_events_count >= 10:
                        print(f"[UMA HANDLER] No new events after 10 LEFT scrolls. Final total: {current_count}")
                        break

            # Extract raw events - grab ALL events without filtering
            raw_events = []
            event_items = await page.query_selector_all('.timeline-item.timeline-event')
            
            print(f"[UMA HANDLER] Extracting {len(event_items)} events from timeline...")
            
            for item in event_items:
                # Extract event title
                title_tag = await item.query_selector('.event-title')
                if not title_tag:
                    continue
                full_title = (await title_tag.inner_text()).strip()
                
                # Extract character/event tags from text content
                # Character names appear on separate lines after the event type and date
                tags = []
                full_text = await item.inner_text()
                lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                
                # Debug: Print structure for character/support banners
                if "+" in full_title and "more" in full_title:
                    print(f"[UMA DEBUG LINES] {lines}")
                
                # For CHARACTER BANNER or SUPPORT CARD BANNER:
                # Structure is: [type] [title with +1 more] [date] [name1] [name2] ...
                if "CHARACTER BANNER" in full_text or "SUPPORT CARD BANNER" in full_text:
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
                        
                        print(f"[UMA DEBUG EXTRACTION] Found {len(tags)} names after date line {date_idx}: {tags}")
                
                # Debug: Show what we extracted
                print(f"[UMA HANDLER DEBUG] Title: {full_title[:60]}... | Tags: {tags}")
                
                # Extract event description/subtitle
                description = ""
                desc_tag = await item.query_selector('.event-description')
                if desc_tag:
                    description = (await desc_tag.inner_text()).strip()
                
                # Extract ALL event images (Legend Race can have 3-4 character images)
                img_tags = await item.query_selector_all('.event-image img')
                img_urls = []
                for img_tag in img_tags:
                    img_src = await img_tag.get_attribute("src")
                    if img_src:
                        img_urls.append(urljoin(BASE_URL, img_src))
                
                # Primary image URL (first one, for backwards compatibility)
                img_url = img_urls[0] if img_urls else None
                
                # Extract event date
                date_tag = await item.query_selector('.event-date')
                if not date_tag:
                    continue
                date_str = (await date_tag.inner_text()).strip()
                start_date, end_date = parse_event_date(date_str)
                
                # Store ALL events - don't skip any here
                raw_events.append({
                    "full_title": full_title,
                    "full_text": full_text,  # Store full text for event type detection
                    "tags": tags,
                    "description": description,
                    "image_url": img_url,  # Primary image (first one)
                    "image_urls": img_urls,  # ALL images for this event
                    "start_date": start_date,
                    "end_date": end_date,
                    "date_str": date_str
                })
                
                # Debug: Print first few events
                if len(raw_events) <= 5:
                    print(f"[UMA HANDLER] Event {len(raw_events)}: {full_title[:50]}... | Tags: {tags} | Date: {date_str}")

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
                processed.append({
                    "title": f"{support_names} Support Banner",
                    "start": int(start_date.timestamp()),
                    "end": int(end_date.timestamp()),
                    "image": img_url,
                    "category": "Banner",
                    "description": f"**Support Cards:** {support_names}"
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
            
            # Combine images if both exist
            combined_img = img_url
            if img_url and support_img:
                from uma_module import combine_images_vertically
                combined_path = combine_images_vertically(img_url, support_img)
                if combined_path:
                    combined_img = combined_path
            
            # Create combined event
            title = f"{char_names} Banner"
            event_desc = f"**Characters:** {char_names}\n**Support Cards:** {support_names}" if support_names else f"**Characters:** {char_names}"
            
            processed.append({
                "title": title,
                "start": int(start_date.timestamp()),
                "end": int(end_date.timestamp()),
                "image": combined_img,
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
            
            # Combine images horizontally if multiple
            combined_img = img_url
            if len(legend_images) > 1:
                from uma_module import combine_images_horizontally
                combined_path = combine_images_horizontally(legend_images)
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
                "description": details if details else ""
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
                            
                            # Get all character/support names from the list (ul.sc-37bc0b3c-3)
                            items_list = await container.query_selector('ul.sc-37bc0b3c-3')
                            item_names = []
                            
                            if items_list:
                                # Get all list items
                                list_items = await items_list.query_selector_all('li')
                                
                                for li in list_items:
                                    # Get the name span (gacha_link_alt__mZW_P)
                                    name_span = await li.query_selector('.gacha_link_alt__mZW_P, span.sc-37bc0b3c-5')
                                    if name_span:
                                        name_text = (await name_span.inner_text()).strip()
                                        if name_text:
                                            item_names.append(name_text)
                                
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
                            
                            # Store character/support names (without links since they're not easily accessible)
                            for item_name in item_names:
                                # Clean up name - remove " New" or " Rerun" from end with optional rate info
                                # Pattern: \s+(New|Rerun)(?:,?\s*[\d.]+%)?\s*$
                                # This matches " New", " New, 0.75%", " Rerun", " Rerun 0.75%" etc. at the end
                                # If a character is legitimately named "X New", rate-up would show "X New New"
                                # so this will only remove one instance from the end
                                clean_name = re.sub(r'\s+(New|Rerun)(?:,?\s*[\d.]+%)?\s*$', '', item_name).strip()
                                
                                if not clean_name:
                                    continue
                                
                                # Since we don't have links, we'll store with a placeholder ID based on name hash
                                # This is not ideal but allows us to track the banner contents
                                name_hash = str(abs(hash(clean_name)) % 1000000)
                                
                                if banner_type == "Character":
                                    await conn.execute('''
                                        INSERT OR IGNORE INTO characters (character_id, name, link)
                                        VALUES (?, ?, ?)
                                    ''', (name_hash, clean_name, ""))
                                    characters_added += 1
                                    
                                    await conn.execute('''
                                        INSERT OR IGNORE INTO banner_items (banner_id, item_id, item_type)
                                        VALUES (?, ?, 'Character')
                                    ''', (banner_id, name_hash))
                                else:
                                    await conn.execute('''
                                        INSERT OR IGNORE INTO support_cards (card_id, name, link)
                                        VALUES (?, ?, ?)
                                    ''', (name_hash, clean_name, ""))
                                    supports_added += 1
                                    
                                    await conn.execute('''
                                        INSERT OR IGNORE INTO banner_items (banner_id, item_id, item_type)
                                        VALUES (?, ?, 'Support')
                                    ''', (banner_id, name_hash))
                            
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
                            
                            # Skip if already in database and not force scanning
                            if banner_id in existing_banner_ids and not force_full_scan:
                                continue
                            
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
                            
                            if not os.path.exists(filepath):
                                try:
                                    response = requests.get(full_img_url, timeout=30)
                                    if response.status_code == 200:
                                        with open(filepath, 'wb') as f:
                                            f.write(response.content)
                                        print(f"[GameTora] Saved image: {filename}")
                                except Exception as dl_err:
                                    uma_handler_logger.warning(f"[GameTora] Failed to download {full_img_url}: {dl_err}")
                                    continue
                            
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
    
    # Step 1: Scrape JP banners (IDs, types, characters, support cards)
    jp_result = await scrape_gametora_jp_banners(force_full_scan)
    
    # Step 2: Scrape Global banner images
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