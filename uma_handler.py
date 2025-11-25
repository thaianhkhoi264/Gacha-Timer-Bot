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
                # Character names appear as text after "CHARACTERS:" or "SUPPORT CARDS:" headings
                tags = []
                full_text = await item.inner_text()
                
                # Look for CHARACTERS: section
                if "CHARACTERS:" in full_text:
                    # Find the line after CHARACTERS:
                    lines = full_text.split('\n')
                    char_idx = None
                    for i, line in enumerate(lines):
                        if "CHARACTERS:" in line:
                            char_idx = i
                            break
                    
                    if char_idx is not None and char_idx + 1 < len(lines):
                        # Get the next line which contains character names
                        char_line = lines[char_idx + 1].strip()
                        # Split by double spaces (how character names are separated)
                        char_names = [name.strip() for name in re.split(r'\s{2,}', char_line) if name.strip()]
                        tags = char_names
                
                # Look for SUPPORT CARDS: section
                elif "SUPPORT" in full_text and "CARDS:" in full_text:
                    lines = full_text.split('\n')
                    support_idx = None
                    for i, line in enumerate(lines):
                        if "SUPPORT" in line and "CARDS:" in line:
                            support_idx = i
                            break
                    
                    if support_idx is not None and support_idx + 1 < len(lines):
                        support_line = lines[support_idx + 1].strip()
                        support_names = [name.strip() for name in re.split(r'\s{2,}', support_line) if name.strip()]
                        tags = support_names
                
                # Debug: Show what we extracted
                print(f"[UMA HANDLER DEBUG] Title: {full_title[:60]}... | Tags: {tags}")
                
                # Extract event description/subtitle
                description = ""
                desc_tag = await item.query_selector('.event-description')
                if desc_tag:
                    description = (await desc_tag.inner_text()).strip()
                
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
                
                # Store ALL events - don't skip any here
                raw_events.append({
                    "full_title": full_title,
                    "tags": tags,
                    "description": description,
                    "image_url": img_url,
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
        
        # Parse title components
        title_lower = full_title.lower()
        
        # === SUPPORT BANNER (standalone or for combination) ===
        if "support" in title_lower and ("support card" in title_lower or title_lower.startswith("support")):
            # Use tags for support card names - tags are the actual character names
            support_names = " & ".join(tags) if tags else ""
            if not support_names:
                # Fallback: try to parse from title text
                support_match = re.search(r"SUPPORT CARDS?:\s*(.+)", full_title, re.IGNORECASE)
                support_names = support_match.group(1).strip() if support_match else "Support Cards"
            
            print(f"[UMA HANDLER] Support banner found - Tags: {tags}, Names: {support_names}")
            
            # Check if there's a matching Character banner (look backward and forward)
            char_banner_idx = None
            for j in range(max(0, i-5), min(i+5, len(raw_events))):
                if j == i or j in skip_indices:
                    continue
                check_event = raw_events[j]
                check_title = check_event["full_title"].lower()
                if "character" in check_title and "banner" in check_title and "support" not in check_title:
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
        if "character banner" in title_lower and "support" not in title_lower:
            # Use tags for character names (more accurate than truncated title)
            print(f"[UMA HANDLER] Character banner found - Tags: {tags}, Title: {full_title[:80]}")
            char_names = " & ".join(tags) if tags else ""
            if not char_names:
                # Fallback to parsing title
                char_match = re.search(r"Character banner featuring:\s*(.+)", full_title, re.IGNORECASE)
                char_names = char_match.group(1).strip() if char_match else "Character Banner"
                print(f"[UMA HANDLER] No tags found, using parsed name: {char_names}")
            
            # Look for matching Support banner (search backward and forward)
            support_names = ""
            support_img = None
            support_tags = []
            for j in range(max(0, i-5), min(i+5, len(raw_events))):
                if j == i or j in skip_indices:
                    continue
                next_event = raw_events[j]
                if "support" in next_event["full_title"].lower() and "support card" in next_event["full_title"].lower():
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
        if "legend race" in title_lower:
            # Extract race details from title (e.g., "2400m - Medium - Turf")
            details = ""
            details_match = re.search(r"Legend Race\s+(.+)", full_title)
            if details_match:
                details = details_match.group(1).strip()
            elif description:
                details = description
            
            # Try to extract race name from details (e.g., "Kikkasho" from description if available)
            race_name = "Legend Race"
            # For now, just use "Legend Race" - we can enhance this later if race names are in HTML
            
            # Collect multiple images for Legend Race (they typically have 3-4 character images)
            legend_images = [img_url] if img_url else []
            # Look ahead for additional Legend Race images (same event, multiple image elements)
            for j in range(i+1, min(i+10, len(raw_events))):
                next_event = raw_events[j]
                # If next event has same title and date, it's another image for same Legend Race
                if ("legend race" in next_event["full_title"].lower() and 
                    next_event["start_date"] and abs((next_event["start_date"] - start_date).total_seconds()) < 3600 and
                    next_event["end_date"] and abs((next_event["end_date"] - end_date).total_seconds()) < 3600):
                    if next_event["image_url"]:
                        legend_images.append(next_event["image_url"])
                        skip_indices.add(j)
                else:
                    break
            
            print(f"[UMA HANDLER] Legend Race found with {len(legend_images)} images")
            
            # For now, use first image (combining horizontally would require PIL changes)
            # TODO: Implement horizontal image combination
            combined_img = legend_images[0] if legend_images else img_url
            
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
        if "champions meeting" in title_lower:
            # Extract location/cup details from title (e.g., "Tokyo - Turf2400m - Medium - Counterclockwise...")
            details = ""
            cup_name = "Champions Meeting"
            
            details_match = re.search(r"Champions Meeting\s+(.+)", full_title)
            if details_match:
                details = details_match.group(1).strip()
                # Extract location as cup name (first word before dash)
                location_match = re.search(r"^([A-Za-z]+)", details)
                if location_match:
                    cup_name = f"Champions Meeting: {location_match.group(1)} Cup"
            elif description:
                details = description
            
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

if __name__ == "__main__":
    asyncio.run(update_uma_events())