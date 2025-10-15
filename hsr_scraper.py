"""
HSR Scraper - Scrapes https://www.prydwen.gg/star-rail/ for event information
This module can be called from hsr_module.py to fetch and save the HTML content.
Uses Playwright for JavaScript-rendered content.
"""

from playwright.sync_api import sync_playwright
import os
from datetime import datetime
import logging
import aiosqlite
import asyncio

# Setup logging
logger = logging.getLogger("hsr_scraper")
logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

# File handler
log_file_path = os.path.join("logs", "hsr_scraper.log")
os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))

# Add handlers if not already present
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    logger.addHandler(console_handler)
if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
    logger.addHandler(file_handler)

logger.propagate = True

# Configuration
PRYDWEN_URL = "https://www.prydwen.gg/star-rail/"
SAVE_DIR = os.path.join("data", "hsr_scraper")
DB_PATH = os.path.join("data", "hsr_prydwen_data.db")

# Event type to category mapping (for bot logic)
EVENT_TYPE_TO_CATEGORY = {
    "character_banner": "Banner",
    "light_cone_banner": "Banner",
    "standard_banner": "Banner",
    "memory_of_chaos": "Event",
    "pure_fiction": "Event",
    "apocalyptic_shadow": "Event",
    "planar_fissure": "Event",
    "relic_event": "Event",
    "battle_pass": "Event",
    "login_event": "Event",
    "other_event": "Event",
    "maintenance": "Maintenance",
}

async def init_prydwen_db():
    """Initialize the HSR Prydwen database with the events table."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT,
                na_start_date TEXT,
                na_end_date TEXT,
                eu_start_date TEXT,
                eu_end_date TEXT,
                asia_start_date TEXT,
                asia_end_date TEXT,
                time_remaining TEXT,
                description TEXT,
                image TEXT,
                css_class TEXT,
                featured_5star TEXT,
                featured_4star TEXT,
                scraped_at TEXT NOT NULL,
                UNIQUE(title, type)
            )
        ''')
        await conn.commit()
    logger.info(f"Prydwen database initialized at {DB_PATH}")

async def save_events_to_db(events):
    """
    Save scraped events to the database with regional time support.
    
    Args:
        events (list): List of event dictionaries with regional fields:
            - name/title: Event name
            - type: Event type
            - status: "ongoing" or "upcoming"
            - na_start_date, na_end_date: NA region times
            - eu_start_date, eu_end_date: EU region times
            - asia_start_date, asia_end_date: Asia region times
            - time_remaining: Time until end (optional)
            - description: Event description (optional)
            - image: Image URL (optional)
            - css_class: CSS classes (optional)
    
    Returns:
        dict: Statistics about saved events (added, updated, errors)
    """
    await init_prydwen_db()
    
    stats = {"added": 0, "updated": 0, "errors": 0}
    scraped_at = datetime.now().isoformat()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        for event in events:
            try:
                # Map type to category
                event_type = event.get('type', 'other_event')
                category = EVENT_TYPE_TO_CATEGORY.get(event_type, 'Event')
                title = event.get('name', event.get('title', ''))
                
                # Check if event exists (by title and type only)
                async with conn.execute(
                    "SELECT id FROM events WHERE title=? AND type=?",
                    (title, event_type)
                ) as cursor:
                    existing = await cursor.fetchone()
                
                if existing:
                    # Update existing event with new regional times
                    await conn.execute('''
                        UPDATE events SET
                            category=?, status=?,
                            na_start_date=?, na_end_date=?,
                            eu_start_date=?, eu_end_date=?,
                            asia_start_date=?, asia_end_date=?,
                            time_remaining=?, description=?,
                            image=?, css_class=?, 
                            featured_5star=?, featured_4star=?,
                            scraped_at=?
                        WHERE id=?
                    ''', (
                        category,
                        event.get('status', 'unknown'),
                        event.get('na_start_date', ''),
                        event.get('na_end_date', ''),
                        event.get('eu_start_date', ''),
                        event.get('eu_end_date', ''),
                        event.get('asia_start_date', ''),
                        event.get('asia_end_date', ''),
                        event.get('time_remaining', ''),
                        event.get('description', ''),
                        event.get('image', ''),
                        event.get('css_class', ''),
                        event.get('featured_5star', ''),
                        event.get('featured_4star', ''),
                        scraped_at,
                        existing[0]
                    ))
                    stats["updated"] += 1
                    logger.info(f"Updated event: {title} ({event.get('status', 'unknown')})")
                else:
                    # Insert new event with regional times
                    await conn.execute('''
                        INSERT INTO events (
                            title, category, type, status,
                            na_start_date, na_end_date,
                            eu_start_date, eu_end_date,
                            asia_start_date, asia_end_date,
                            time_remaining, description, image, css_class,
                            featured_5star, featured_4star,
                            scraped_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        title,
                        category,
                        event_type,
                        event.get('status', 'unknown'),
                        event.get('na_start_date', ''),
                        event.get('na_end_date', ''),
                        event.get('eu_start_date', ''),
                        event.get('eu_end_date', ''),
                        event.get('asia_start_date', ''),
                        event.get('asia_end_date', ''),
                        event.get('time_remaining', ''),
                        event.get('description', ''),
                        event.get('image', ''),
                        event.get('css_class', ''),
                        event.get('featured_5star', ''),
                        event.get('featured_4star', ''),
                        event.get('css_class', ''),
                        scraped_at
                    ))
                    stats["added"] += 1
                    logger.info(f"Added new event: {title} ({event.get('status', 'unknown')})")
            
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error saving event {event.get('name', event.get('title', 'Unknown'))}: {e}")
        
        await conn.commit()
    
    logger.info(f"Database save complete: {stats['added']} added, {stats['updated']} updated, {stats['errors']} errors")
    return stats

async def get_all_events_from_db():
    """
    Retrieve all events from the database with regional time support.
    
    Returns:
        list: List of event dictionaries with regional fields
    """
    await init_prydwen_db()
    
    events = []
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute('''
            SELECT id, title, category, type, status,
                   na_start_date, na_end_date,
                   eu_start_date, eu_end_date,
                   asia_start_date, asia_end_date,
                   time_remaining, description, image, css_class, scraped_at
            FROM events
            ORDER BY na_start_date DESC
        ''') as cursor:
            async for row in cursor:
                events.append({
                    'id': row[0],
                    'title': row[1],
                    'category': row[2],
                    'type': row[3],
                    'status': row[4],
                    'na_start_date': row[5],
                    'na_end_date': row[6],
                    'eu_start_date': row[7],
                    'eu_end_date': row[8],
                    'asia_start_date': row[9],
                    'asia_end_date': row[10],
                    'time_remaining': row[11],
                    'description': row[12],
                    'image': row[13],
                    'css_class': row[14],
                    'scraped_at': row[15]
                })
    
    return events

def ensure_save_directory():
    """Creates the save directory if it doesn't exist."""
    os.makedirs(SAVE_DIR, exist_ok=True)
    logger.info(f"Save directory ensured: {SAVE_DIR}")

def extract_featured_characters(accordion_body_html):
    """
    Extract featured 5-star and 4-star characters from expanded banner accordion body.
    
    Args:
        accordion_body_html (str): HTML content of the expanded accordion body
    
    Returns:
        tuple: (featured_5star, featured_4star) as comma-separated strings
    """
    import re
    
    five_star_chars = []
    four_star_chars = []
    
    # Find 5-star characters section
    five_pattern = r'<p class="featured">Featured\s+<span[^>]*rar-5[^>]*>5★</span>\s+character[s]?:</p>\s*<div class="featured-characters">(.*?)</div>'
    five_match = re.search(five_pattern, accordion_body_html, re.DOTALL | re.IGNORECASE)
    
    if five_match:
        five_section = five_match.group(1)
        # Extract character links
        char_links = re.findall(r'href="(/star-rail/characters/[^"]+)"', five_section)
        for link in char_links:
            char_name = link.split('/')[-1].replace('-', ' ').title()
            five_star_chars.append(char_name)
    
    # Find 4-star characters section
    four_pattern = r'<p class="featured">Featured\s+<span[^>]*rar-4[^>]*>4★</span>\s+character[s]?:</p>\s*<div class="featured-characters">(.*?)</div>'
    four_match = re.search(four_pattern, accordion_body_html, re.DOTALL | re.IGNORECASE)
    
    if four_match:
        four_section = four_match.group(1)
        # Extract character links
        char_links = re.findall(r'href="(/star-rail/characters/[^"]+)"', four_section)
        for link in char_links:
            char_name = link.split('/')[-1].replace('-', ' ').title()
            four_star_chars.append(char_name)
    
    return ', '.join(five_star_chars), ', '.join(four_star_chars)

def extract_events_from_html(html_content, region="NA"):
    """
    Extract events from a single region's HTML.
    
    Args:
        html_content (str): HTML content for a specific region
        region (str): Region name ("NA", "EU", or "Asia")
    
    Returns:
        tuple: (ongoing_events, upcoming_events) - two lists of event dicts
    """
    import re
    logger.info(f"Extracting events from {region} HTML...")
    
    # Find the Current and Upcoming sections
    # Pattern: <h5>Current</h5> ... content ... <h5>Upcoming</h5> ... content
    current_section = ""
    upcoming_section = ""
    
    # Split by h5 headers
    h5_pattern = r'<h5[^>]*>(.*?)</h5>(.*?)(?=<h5|$)'
    sections = re.findall(h5_pattern, html_content, re.DOTALL | re.IGNORECASE)
    
    for header, content in sections:
        clean_header = re.sub(r'<.*?>', '', header).strip()
        if clean_header.lower() == 'current':
            current_section = content
        elif clean_header.lower() == 'upcoming':
            upcoming_section = content
    
    # Extract events from each section
    ongoing_events = extract_events_from_section(current_section, "ongoing", region)
    upcoming_events = extract_events_from_section(upcoming_section, "upcoming", region)
    
    logger.info(f"{region}: Found {len(ongoing_events)} ongoing, {len(upcoming_events)} upcoming events")
    return ongoing_events, upcoming_events

def extract_events_from_section(section_html, status, region):
    """
    Extract individual events from a section (Current or Upcoming).
    
    Args:
        section_html (str): HTML content of the section
        status (str): "ongoing" or "upcoming"
        region (str): Region name ("NA", "EU", or "Asia")
    
    Returns:
        list: List of event dicts with extracted data
    """
    import re
    events = []
    
    # Find all accordion-item divs
    # Pattern: <div class="[something] accordion-item">...</div>
    accordion_pattern = r'<div class="([^"]*accordion-item[^"]*)"[^>]*>(.*?)</div>\s*</div>\s*</div>'
    items = re.findall(accordion_pattern, section_html, re.DOTALL)
    
    for item_class, item_content in items:
        # Extract event name
        name_match = re.search(r'<div class="event-name">([^<]+)</div>', item_content)
        if not name_match:
            continue  # Skip items without event name
        event_name = name_match.group(1).strip()
        
        # Extract time remaining
        time_match = re.search(r'<span class="time">([^<]+)</span>', item_content)
        time_remaining = time_match.group(1).strip() if time_match else ""
        
        # Extract duration with date range
        duration_match = re.search(r'<p class="duration">.*?:\s*([^<]+)</p>', item_content, re.DOTALL)
        duration_text = duration_match.group(1).strip() if duration_match else ""
        
        # Parse dates from duration text
        # Common formats:
        # "2025/10/08 04:00:00 – 2025/10/20 03:59:00 (server time)"
        # "After the V3.6 update – 2025/10/15 11:59 (server time)"
        # "2025/10/15 12:00 – 2025/11/04 15:00 (server time)"
        
        start_date = ""
        end_date = ""
        
        # Look for date patterns
        date_pattern = r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}(?::\d{2})?)'
        dates = re.findall(date_pattern, duration_text)
        
        if len(dates) >= 2:
            start_date = dates[0]
            end_date = dates[1]
        elif len(dates) == 1:
            # Only one date found (usually end date)
            end_date = dates[0]
            # Try to extract start from "After the V3.6 update" pattern
            if "after" in duration_text.lower() and "update" in duration_text.lower():
                start_date = "After update"
        
        # Determine event type from CSS class
        event_type = determine_event_type(item_class, event_name)
        
        events.append({
            'name': event_name,
            'type': event_type,
            'status': status,
            f'{region.lower()}_start_date': start_date,
            f'{region.lower()}_end_date': end_date,
            'time_remaining': time_remaining,
            'duration_text': duration_text,
            'css_class': item_class
        })
    
    return events

def determine_event_type(css_class, event_name):
    """Determine event type from CSS class or name."""
    css_lower = css_class.lower()
    name_lower = event_name.lower()
    
    # Character banners
    if any(x in css_lower for x in ['evernight', 'the-herta', 'saber', 'archer', 'character']):
        return 'character_banner'
    
    # Weapon/Light Cone banners
    if any(x in css_lower for x in ['weapon', 'light-cone', 'lightcone']):
        return 'weapon_banner'
    
    # Standard/Permanent banners
    if any(x in name_lower for x in ['standard', 'permanent', 'departure']):
        return 'standard_banner'
    
    # Events by specific keywords
    if 'memory of chaos' in name_lower or 'memory-of-chaos' in css_lower:
        return 'memory_of_chaos'
    if 'pure fiction' in name_lower or 'pure-fiction' in css_lower:
        return 'pure_fiction'
    if 'apocalyptic shadow' in name_lower or 'apo' in css_lower:
        return 'apocalyptic_shadow'
    if 'planar fissure' in name_lower or 'planar-fissure' in css_lower:
        return 'planar_fissure'
    if 'nameless honor' in name_lower or 'nameless-honor' in css_lower:
        return 'battle_pass'
    if 'gift of odyssey' in name_lower or 'odyssey' in css_lower:
        return 'login_event'
    
    # Default to other_event
    return 'other_event'

def extract_events_from_regional_html(regional_html, banner_characters=None):
    """
    Extract events from all three regional HTMLs (NA, EU, Asia) and merge them.
    Also merges simultaneous character banners into combined entries.
    
    Args:
        regional_html (dict): Dict with keys "NA", "EU", "Asia" containing HTML content
        banner_characters (dict): Dict mapping banner CSS class to (featured_5star, featured_4star) tuples
    
    Returns:
        list: List of event dicts with regional time fields and status
    """
    import re
    logger.info("Extracting events from regional HTML...")
    
    if banner_characters is None:
        banner_characters = {}
    
    # Extract from each region
    na_ongoing, na_upcoming = extract_events_from_html(regional_html.get("NA", ""), "NA")
    eu_ongoing, eu_upcoming = extract_events_from_html(regional_html.get("EU", ""), "EU")
    asia_ongoing, asia_upcoming = extract_events_from_html(regional_html.get("Asia", ""), "Asia")
    
    # Combine all events
    all_na_events = na_ongoing + na_upcoming
    all_eu_events = eu_ongoing + eu_upcoming
    all_asia_events = asia_ongoing + asia_upcoming
    
    # Merge events by name
    merged_events = {}
    
    # Process NA events as base
    for event in all_na_events:
        key = (event['name'], event['type'])
        merged_events[key] = event.copy()
        
        # Add featured characters if available
        css_class = event.get('css_class', '').split()[0] if event.get('css_class') else ''
        if css_class in banner_characters:
            five_star, four_star = banner_characters[css_class]
            merged_events[key]['featured_5star'] = five_star
            merged_events[key]['featured_4star'] = four_star
    
    # Merge EU times
    for event in all_eu_events:
        key = (event['name'], event['type'])
        if key in merged_events:
            merged_events[key]['eu_start_date'] = event['eu_start_date']
            merged_events[key]['eu_end_date'] = event['eu_end_date']
        else:
            # Event only in EU (shouldn't happen, but handle it)
            merged_events[key] = event.copy()
            merged_events[key]['na_start_date'] = ""
            merged_events[key]['na_end_date'] = ""
    
    # Merge Asia times
    for event in all_asia_events:
        key = (event['name'], event['type'])
        if key in merged_events:
            merged_events[key]['asia_start_date'] = event['asia_start_date']
            merged_events[key]['asia_end_date'] = event['asia_end_date']
        else:
            # Event only in Asia (shouldn't happen, but handle it)
            merged_events[key] = event.copy()
            merged_events[key]['na_start_date'] = ""
            merged_events[key]['na_end_date'] = ""
            merged_events[key]['eu_start_date'] = ""
            merged_events[key]['eu_end_date'] = ""
    
    # Convert to list
    result = []
    for event in merged_events.values():
        # Ensure all regional fields exist
        for region in ['na', 'eu', 'asia']:
            if f'{region}_start_date' not in event:
                event[f'{region}_start_date'] = ""
            if f'{region}_end_date' not in event:
                event[f'{region}_end_date'] = ""
        
        # Remove temporary fields
        event.pop('duration_text', None)
        
        result.append(event)
    
    # Merge simultaneous character banners
    result = merge_simultaneous_character_banners(result)
    
    logger.info(f"Processed {len(result)} events (after merging simultaneous banners)")
    return result

def merge_simultaneous_character_banners(events):
    """
    Merge simultaneous ongoing character banners into combined entries.
    E.g., "Evil March Can't Hurt You" + "RE: Mahou Shoujo" → "Evernight & The Herta Banner"
    
    Args:
        events (list): List of event dicts
    
    Returns:
        list: List with character banners merged
    """
    # Find ongoing character banners
    ongoing_char_banners = [
        e for e in events 
        if e.get('type') == 'character_banner' and e.get('status') == 'ongoing'
    ]
    
    # If there are exactly 2 ongoing character banners, merge them
    if len(ongoing_char_banners) == 2:
        banner1, banner2 = ongoing_char_banners
        
        # Get the 5-star character names (without "March 7Th" formatting)
        char1 = banner1.get('featured_5star', '').split(',')[0].strip() if banner1.get('featured_5star') else ''
        char2 = banner2.get('featured_5star', '').split(',')[0].strip() if banner2.get('featured_5star') else ''
        
        # Create combined banner
        if char1 and char2:
            combined = {
                'name': f"{char1} & {char2} Banner",
                'type': 'character_banner',
                'status': 'ongoing',
                'na_start_date': banner1.get('na_start_date', ''),
                'na_end_date': banner1.get('na_end_date', ''),
                'eu_start_date': banner1.get('eu_start_date', ''),
                'eu_end_date': banner1.get('eu_end_date', ''),
                'asia_start_date': banner1.get('asia_start_date', ''),
                'asia_end_date': banner1.get('asia_end_date', ''),
                'time_remaining': banner1.get('time_remaining', ''),
                'description': f"Dual character banner featuring {char1} and {char2}",
                'image': '',
                'css_class': f"{banner1.get('css_class', '').split()[0]} {banner2.get('css_class', '').split()[0]}",
                'featured_5star': f"{banner1.get('featured_5star', '')}, {banner2.get('featured_5star', '')}",
                'featured_4star': f"{banner1.get('featured_4star', '')}, {banner2.get('featured_4star', '')}",
            }
            
            # Remove original banners and add combined
            result = [e for e in events if e not in ongoing_char_banners]
            result.append(combined)
            
            logger.info(f"Merged character banners: '{banner1['name']}' + '{banner2['name']}' → '{combined['name']}'")
            return result
    
    # No merging needed
    return events

def scrape_prydwen_with_regions(save_html=True, headless=True):
    """
    Scrapes the Prydwen Star Rail homepage with regional time support.
    Clicks through NA/EU/Asia buttons to collect times for all regions.
    
    Args:
        save_html (bool): If True, saves the HTML for each region
        headless (bool): If True, runs browser in headless mode
    
    Returns:
        dict: {"NA": html_content, "EU": html_content, "Asia": html_content}, or None if scraping fails
    """
    logger.info(f"Starting multi-region scrape of {PRYDWEN_URL}")
    
    try:
        with sync_playwright() as p:
            # Launch browser
            logger.info("Launching browser...")
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            # Navigate to the page
            logger.info(f"Navigating to {PRYDWEN_URL}")
            page.goto(PRYDWEN_URL, wait_until='domcontentloaded', timeout=60000)
            
            # Wait for page to fully load
            logger.info("Waiting for page to fully load...")
            page.wait_for_timeout(5000)
            
            # Collect HTML for each region
            regional_html = {}
            regions = ["NA", "EU", "Asia"]
            
            for region in regions:
                logger.info(f"Switching to {region} region...")
                
                # Find and click the region button
                try:
                    # Try multiple selectors
                    button_selectors = [
                        f'button:text("{region}")',
                        f'button:has-text("{region}")',
                    ]
                    
                    button_clicked = False
                    for selector in button_selectors:
                        try:
                            buttons = page.query_selector_all(selector)
                            # Click all matching buttons (there might be multiple on the page)
                            for button in buttons:
                                if button.is_visible():
                                    button.click()
                                    button_clicked = True
                                    logger.info(f"  Clicked {region} button")
                        except Exception as e:
                            continue
                    
                    if not button_clicked:
                        logger.warning(f"  Could not find {region} button, using default times")
                    
                    # Wait for content to update after clicking
                    page.wait_for_timeout(1000)
                    
                    # Get the HTML content for this region
                    html_content = page.content()
                    regional_html[region] = html_content
                    logger.info(f"  Captured HTML for {region} ({len(html_content)} bytes)")
                    
                except Exception as e:
                    logger.error(f"  Error switching to {region}: {e}")
                    # Use current page content as fallback
                    regional_html[region] = page.content()
            
            # Close browser
            browser.close()
            
            # Save HTML if requested
            if save_html:
                ensure_save_directory()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                for region, html_content in regional_html.items():
                    filename = f"prydwen_starrail_{region}_{timestamp}.html"
                    filepath = os.path.join(SAVE_DIR, filename)
                    
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    logger.info(f"HTML saved to: {filepath}")
                
                # Save NA as "latest.html" for backward compatibility
                if "NA" in regional_html:
                    latest_filepath = os.path.join(SAVE_DIR, "latest.html")
                    with open(latest_filepath, "w", encoding="utf-8") as f:
                        f.write(regional_html["NA"])
                    logger.info(f"NA HTML also saved to: {latest_filepath}")
            
            return regional_html
    
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        return None

def scrape_prydwen(save_html=True, headless=True):
    """
    Scrapes the Prydwen Star Rail homepage using Playwright.
    
    Args:
        save_html (bool): If True, saves the HTML to a file
        headless (bool): If True, runs browser in headless mode
    
    Returns:
        str: HTML content, or None if scraping fails
    """
    logger.info(f"Starting scrape of {PRYDWEN_URL}")
    
    try:
        with sync_playwright() as p:
            # Launch browser
            logger.info("Launching browser...")
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            # Navigate to the page
            logger.info(f"Navigating to {PRYDWEN_URL}")
            page.goto(PRYDWEN_URL, wait_until='domcontentloaded', timeout=60000)
            
            # Wait a bit for any dynamic content to load
            logger.info("Waiting for page to fully load...")
            page.wait_for_timeout(5000)  # Wait 5 seconds for JavaScript to render content
            
            # Get the HTML content
            html_content = page.content()
            logger.info(f"Successfully fetched HTML ({len(html_content)} bytes)")
            
            # Close browser
            browser.close()
            
            # Save HTML if requested
            if save_html:
                ensure_save_directory()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"prydwen_starrail_{timestamp}.html"
                filepath = os.path.join(SAVE_DIR, filename)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"HTML saved to: {filepath}")
                
                # Also save a "latest.html" for easy access
                latest_filepath = os.path.join(SAVE_DIR, "latest.html")
                with open(latest_filepath, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"HTML also saved to: {latest_filepath}")
            
            return html_content
    
    except Exception as e:
        logger.error(f"Error while scraping: {e}")
        return None

def scrape_and_extract_banner_characters(regional_html):
    """
    Click on character banners to expand them and extract featured characters.
    
    Args:
        regional_html (dict): Dict with keys "NA", "EU", "Asia" containing HTML content
    
    Returns:
        dict: Dict mapping banner CSS class to (featured_5star, featured_4star) tuples
    """
    logger.info("Expanding character banners to extract featured characters...")
    banner_characters = {}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = context.new_page()
            
            # Navigate to page
            page.goto(PRYDWEN_URL, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(5000)
            
            # Find all character banner accordion items (those with specific CSS classes)
            # Common banner classes: evernight, the-herta, saber, archer, etc.
            banner_selectors = [
                'div.evernight.accordion-item',
                'div.the-herta.accordion-item',
                'div.saber.accordion-item',
                'div.archer.accordion-item',
            ]
            
            # Try to find any character banner (they have specific character names in CSS)
            all_accordion_items = page.query_selector_all('div.accordion-item')
            
            for item in all_accordion_items:
                # Get the class attribute
                class_attr = item.get_attribute('class')
                
                # Check if it's a character banner (not generic accordion-item only)
                if class_attr and 'accordion-item' in class_attr:
                    classes = class_attr.split()
                    # Character banners usually have a specific class before 'accordion-item'
                    if len(classes) > 1:
                        banner_class = classes[0]  # e.g., 'evernight', 'the-herta'
                        
                        # Check if it's likely a character banner (has character-specific class)
                        if banner_class not in ['planar-fissure', 'memory-of-chaos', 'pure-fiction', 
                                                'apocalyptic-shadow', 'apo', 'nameless-honor', 'odyssey', 'realm']:
                            try:
                                # Find the button within this item
                                button = item.query_selector('button.accordion-button')
                                
                                if button:
                                    # Check if collapsed
                                    is_expanded = button.get_attribute('aria-expanded')
                                    
                                    if is_expanded == 'false':
                                        # Click to expand
                                        button.click()
                                        page.wait_for_timeout(1000)  # Wait for expansion
                                    
                                    # Get the accordion body
                                    body = item.query_selector('div.accordion-body')
                                    
                                    if body:
                                        body_html = body.inner_html()
                                        
                                        # Extract featured characters
                                        five_star, four_star = extract_featured_characters(body_html)
                                        
                                        if five_star:  # Only store if we found 5-star characters
                                            banner_characters[banner_class] = (five_star, four_star)
                                            logger.info(f"  Banner '{banner_class}': 5★={five_star}, 4★={four_star}")
                            except Exception as e:
                                logger.warning(f"  Error processing banner '{banner_class}': {e}")
                                continue
            
            browser.close()
            
    except Exception as e:
        logger.error(f"Error extracting banner characters: {e}")
    
    return banner_characters

def get_latest_saved_html():
    """
    Reads the most recently saved HTML file.
    
    Returns:
        str: HTML content, or None if no file exists
    """
    latest_filepath = os.path.join(SAVE_DIR, "latest.html")
    
    if not os.path.exists(latest_filepath):
        logger.warning(f"No saved HTML found at {latest_filepath}")
        return None
    
    try:
        with open(latest_filepath, "r", encoding="utf-8") as f:
            html_content = f.read()
        logger.info(f"Loaded saved HTML from {latest_filepath} ({len(html_content)} bytes)")
        return html_content
    except Exception as e:
        logger.error(f"Error reading saved HTML: {e}")
        return None

def parse_html_to_soup(html_content):
    """
    Parses HTML content (placeholder - BeautifulSoup removed).
    You can parse the HTML content directly as a string.
    
    Args:
        html_content (str): HTML content to parse
    
    Returns:
        str: HTML content
    """
    logger.info("HTML content ready for parsing")
    return html_content

def analyze_html_structure(html_content):
    """
    Analyzes the HTML structure to help understand the page layout.
    Returns basic statistics about the HTML.
    
    Args:
        html_content (str): HTML content to analyze
    
    Returns:
        dict: Statistics about the HTML structure
    """
    stats = {
        'total_size': len(html_content),
        'div_count': html_content.count('<div'),
        'img_count': html_content.count('<img'),
        'a_count': html_content.count('<a '),
        'section_count': html_content.count('<section'),
        'article_count': html_content.count('<article'),
    }
    
    # Try to find common class names
    import re
    class_matches = re.findall(r'class="([^"]+)"', html_content)
    if class_matches:
        # Count class occurrences
        class_counts = {}
        for classes in class_matches:
            for cls in classes.split():
                class_counts[cls] = class_counts.get(cls, 0) + 1
        # Get top 20 most common classes
        stats['top_classes'] = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    
    return stats

def scrape_and_extract_events(html_content):
    """
    Extracts event information from the HTML Event Timeline section.
    
    Args:
        html_content (str): HTML content to parse
    
    Returns:
        list: List of event dictionaries with keys:
              - name: Event name
              - type: Event type (character_banner, memory_of_chaos, etc.)
              - css_class: CSS class identifier
              - time_remaining: Time until event ends (e.g., "1d 7h")
              - start_date: Start date/time (YYYY-MM-DD HH:MM:SS or "After VX.X update")
              - end_date: End date/time (YYYY-MM-DD HH:MM:SS)
              - description: Event description (truncated to 300 chars)
    """
    import re
    
    logger.info("Extracting events from Event Timeline section")
    events = []
    
    # Find all accordion-item divs (each represents an event)
    pattern = r'<div class="[^"]*accordion-item">.*?</div>\s*</div>\s*</div>'
    accordion_items = re.findall(pattern, html_content, re.DOTALL)
    
    logger.info(f"Found {len(accordion_items)} accordion items")
    
    for item_html in accordion_items:
        event = {}
        
        # Extract CSS class (event type identifier)
        class_match = re.search(r'<div class="([^"]+)\s+accordion-item">', item_html)
        if class_match:
            event['css_class'] = class_match.group(1)
        
        # Extract event name
        name_match = re.search(r'<div class="event-name">([^<]+)</div>', item_html)
        if not name_match:
            # Skip items without names (these are sub-items like Light Cones)
            continue
        event['name'] = name_match.group(1).strip()
        
        # Extract countdown time (Xd Xh format)
        countdown_match = re.search(r'<span class="time">([^<]+)</span>', item_html)
        if countdown_match:
            event['time_remaining'] = countdown_match.group(1).strip()
        
        # Extract event duration dates - Format 1: "2025/10/08 04:00:00 – 2025/10/20 03:59:00"
        date_pattern = r'(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s*[–-]\s*(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2}):(\d{2})'
        date_match = re.search(date_pattern, item_html)
        if date_match:
            start_year, start_month, start_day, start_hour, start_min, start_sec = date_match.groups()[:6]
            end_year, end_month, end_day, end_hour, end_min, end_sec = date_match.groups()[6:]
            
            event['start_date'] = f"{start_year}-{start_month}-{start_day} {start_hour}:{start_min}:{start_sec}"
            event['end_date'] = f"{end_year}-{end_month}-{end_day} {end_hour}:{end_min}:{end_sec}"
        
        # Format 2: "After the V3.6 update – 2025/10/15 11:59"
        if 'end_date' not in event:
            alt_date_pattern = r'After the V[\d.]+ update\s*[–-]\s*(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})'
            alt_date_match = re.search(alt_date_pattern, item_html)
            if alt_date_match:
                year, month, day, hour, minute = alt_date_match.groups()
                event['end_date'] = f"{year}-{month}-{day} {hour}:{minute}:00"
                event['start_date'] = "After V3.6 update"
        
        # Format 3: "2025/10/15 12:00 – 2025/11/04 15:00" (no seconds)
        if 'end_date' not in event:
            alt_date_pattern2 = r'(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})\s*[–-]\s*(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})'
            alt_date_match2 = re.search(alt_date_pattern2, item_html)
            if alt_date_match2:
                start_year, start_month, start_day, start_hour, start_min = alt_date_match2.groups()[:5]
                end_year, end_month, end_day, end_hour, end_min = alt_date_match2.groups()[5:]
                
                event['start_date'] = f"{start_year}-{start_month}-{start_day} {start_hour}:{start_min}:00"
                event['end_date'] = f"{end_year}-{end_month}-{end_day} {end_hour}:{end_min}:00"
        
        # Determine event type based on content
        if 'Featured 5★ character' in item_html:
            event['type'] = 'character_banner'
        elif 'Memory of Chaos' in event.get('name', ''):
            event['type'] = 'memory_of_chaos'
        elif 'Pure Fiction' in event.get('name', ''):
            event['type'] = 'pure_fiction'
        elif 'Apocalyptic Shadow' in event.get('name', ''):
            event['type'] = 'apocalyptic_shadow'
        elif 'Planar Fissure' in event.get('name', ''):
            event['type'] = 'planar_fissure'
        elif 'Nameless Honor' in event.get('name', ''):
            event['type'] = 'battle_pass'
        elif 'Gift of Odyssey' in event.get('name', ''):
            event['type'] = 'login_event'
        elif 'Realm of the Strange' in event.get('name', ''):
            event['type'] = 'relic_event'
        else:
            event['type'] = 'other_event'
        
        # Extract description from accordion body
        body_match = re.search(r'<div class="accordion-body">(.*?)</div>\s*</div>\s*</div>$', item_html, re.DOTALL)
        if body_match:
            body = body_match.group(1)
            # Remove HTML tags to get plain text
            plain_text = re.sub(r'<[^>]+>', ' ', body)
            # Clean up whitespace
            plain_text = re.sub(r'\s+', ' ', plain_text).strip()
            # Truncate to 300 chars for readability
            event['description'] = plain_text[:300] + '...' if len(plain_text) > 300 else plain_text
        
        events.append(event)
        logger.debug(f"Extracted event: {event['name']} ({event['type']})")
    
    logger.info(f"Successfully extracted {len(events)} events")
    return events

# --- Main execution for testing ---
if __name__ == "__main__":
    print("=== HSR Scraper Test ===")
    print(f"Target URL: {PRYDWEN_URL}")
    print()
    
    # Test scraping
    print("1. Scraping website with Playwright and saving HTML...")
    html = scrape_prydwen(save_html=True, headless=True)
    
    if html:
        print(f"✓ Successfully scraped {len(html)} bytes of HTML")
        print(f"✓ HTML saved to {SAVE_DIR}")
        
        # Analyze HTML structure
        print("\n2. Analyzing HTML structure...")
        stats = analyze_html_structure(html)
        print(f"  - Total size: {stats['total_size']:,} bytes")
        print(f"  - <div> elements: {stats['div_count']}")
        print(f"  - <a> elements: {stats['a_count']}")
        print(f"  - <img> elements: {stats['img_count']}")
        print(f"  - <section> elements: {stats['section_count']}")
        print(f"  - <article> elements: {stats['article_count']}")
        
        if 'top_classes' in stats:
            print(f"\n  Top 10 most common CSS classes:")
            for cls, count in stats['top_classes'][:10]:
                print(f"    - {cls}: {count} occurrences")
        
        # Try to find title
        import re
        title_match = re.search(r'<title>([^<]+)</title>', html)
        if title_match:
            print(f"\n  Page title: {title_match.group(1)}")
        
        # Search for potential event-related sections
        print(f"\n3. Extracting events from Event Timeline...")
        events = scrape_and_extract_events(html)
        print(f"✓ Extracted {len(events)} events")
        
        if events:
            print(f"\n  Sample events:")
            for event in events[:5]:  # Show first 5
                print(f"\n  - {event['name']}")
                print(f"    Type: {event['type']}")
                if 'start_date' in event:
                    print(f"    Start: {event['start_date']}")
                if 'end_date' in event:
                    print(f"    End: {event['end_date']}")
                if 'time_remaining' in event:
                    print(f"    Time left: {event['time_remaining']}")
    else:
        print("✗ Failed to scrape website")
    
    print("\n4. Testing saved HTML retrieval...")
    saved_html = get_latest_saved_html()
    if saved_html:
        print(f"✓ Successfully loaded saved HTML ({len(saved_html)} bytes)")
    else:
        print("✗ Failed to load saved HTML")
    
    print("\n=== Test Complete ===")
    print(f"Check {os.path.join(SAVE_DIR, 'latest.html')} to inspect the HTML structure")

# === Background Tasks ===

async def periodic_hsr_scraping_task():
    """
    Background task that scrapes Prydwen HSR website every 24 hours.
    Runs immediately on bot startup and then repeats every 24 hours.
    """
    logger.info("HSR periodic scraping task started")
    
    # Run immediately on startup (no initial delay for first scrape)
    await asyncio.sleep(5)  # Just wait 5 seconds for bot to fully initialize
    
    while True:
        try:
            logger.info("Starting periodic HSR scrape...")
            
            # Run scraper in executor (Playwright is sync)
            loop = asyncio.get_event_loop()
            
            # First, scrape regional HTML
            regional_html = await loop.run_in_executor(
                None, 
                scrape_prydwen_with_regions,
                True,  # save_html
                True   # headless
            )
            
            if not regional_html or not any(regional_html.values()):
                logger.error("Periodic scrape failed - no HTML returned")
            else:
                # Extract featured characters from character banners
                banner_characters = await loop.run_in_executor(
                    None,
                    scrape_and_extract_banner_characters,
                    regional_html
                )
                
                # Extract events with banner character info
                events = extract_events_from_regional_html(regional_html, banner_characters)
                
                if events:
                    # Save to database
                    stats = await save_events_to_db(events)
                    logger.info(
                        f"Periodic scrape complete: {len(events)} events, "
                        f"{stats['added']} added, {stats['updated']} updated, {stats['errors']} errors"
                    )
                else:
                    logger.warning("Periodic scrape: No events extracted")
                    
        except Exception as e:
            logger.error(f"Error in periodic HSR scraping task: {e}")
        
        # Wait 24 hours before next scrape
        logger.info("Next HSR scrape in 24 hours")
        await asyncio.sleep(86400)  # 24 hours in seconds

# === Discord Bot Commands ===

# Import bot only if this module is imported by the bot
try:
    from bot import bot
    from discord.ext import commands
    import discord
    
    logger.info("Registering HSR scraper Discord commands...")
    
    @bot.command(name="hsr_scrape")
    @commands.has_permissions(administrator=True)
    async def hsr_scrape_and_save_command(ctx):
        """Scrapes Prydwen HSR website with regional times and featured characters"""
        await ctx.send("🔄 Scraping Prydwen Star Rail website (NA/EU/Asia regions)...")
        
        try:
            # Run scraper in executor (Playwright is sync)
            loop = asyncio.get_event_loop()
            regional_html = await loop.run_in_executor(None, scrape_prydwen_with_regions, True, True)
            
            if not regional_html or not any(regional_html.values()):
                await ctx.send("❌ Failed to scrape website")
                return
            
            await ctx.send("🎭 Extracting featured characters from banners...")
            
            # Extract featured characters
            banner_characters = await loop.run_in_executor(None, scrape_and_extract_banner_characters, regional_html)
            
            await ctx.send("📊 Extracting events from regional data...")
            
            # Extract events with regional times and featured characters
            events = extract_events_from_regional_html(regional_html, banner_characters)
            
            if not events:
                await ctx.send("⚠️ No events found in scraped data")
                return
            
            await ctx.send(f"💾 Saving {len(events)} events to database...")
            
            # Save to database
            stats = await save_events_to_db(events)
            
            # Send results
            embed = discord.Embed(
                title="✅ HSR Prydwen Scrape Complete",
                description=f"Successfully scraped {len(events)} events from Prydwen\n(with NA, EU, Asia times + featured characters)",
                color=discord.Color.green()
            )
            embed.add_field(name="Added", value=str(stats['added']), inline=True)
            embed.add_field(name="Updated", value=str(stats['updated']), inline=True)
            embed.add_field(name="Errors", value=str(stats['errors']), inline=True)
            
            # Count ongoing vs upcoming
            ongoing = sum(1 for e in events if e.get('status') == 'ongoing')
            upcoming = sum(1 for e in events if e.get('status') == 'upcoming')
            embed.add_field(name="Ongoing", value=str(ongoing), inline=True)
            embed.add_field(name="Upcoming", value=str(upcoming), inline=True)
            
            # Show character banners with featured chars
            char_banners = [e for e in events if e.get('type') == 'character_banner' and e.get('featured_5star')]
            if char_banners:
                banner_info = "\n".join([
                    f"**{e['name']}**\n5★: {e.get('featured_5star', 'N/A')}\n4★: {e.get('featured_4star', 'N/A')}"
                    for e in char_banners[:2]  # Show first 2
                ])
                embed.add_field(name="Character Banners", value=banner_info, inline=False)
            
            embed.set_footer(text=f"Database: {DB_PATH}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in scrape command: {e}")
            await ctx.send(f"❌ Error during scraping: {str(e)}")
    
    @bot.command(name="hsr_dump_db_prydwen")
    @commands.has_permissions(administrator=True)
    async def dump_hsr_prydwen_db_command(ctx):
        """Dumps all events from the HSR Prydwen database with regional times"""
        await ctx.send("📊 Fetching events from Prydwen database...")
        
        try:
            events = await get_all_events_from_db()
            
            if not events:
                await ctx.send("⚠️ No events found in database")
                return
            
            # Create embed with event summary
            embed = discord.Embed(
                title="HSR Prydwen Database Dump",
                description=f"Total events: {len(events)}\n(with NA/EU/Asia regional times)",
                color=discord.Color.blue()
            )
            
            # Group by status
            ongoing = [e for e in events if e.get('status') == 'ongoing']
            upcoming = [e for e in events if e.get('status') == 'upcoming']
            
            # Show ongoing events
            if ongoing:
                event_list = "\n".join([
                    f"• **{e['title']}** ({e['type']})\n  NA End: `{e.get('na_end_date', 'N/A')}`"
                    for e in ongoing[:5]  # Show first 5
                ])
                if len(ongoing) > 5:
                    event_list += f"\n... and {len(ongoing) - 5} more"
                
                embed.add_field(
                    name=f"🟢 Ongoing ({len(ongoing)})",
                    value=event_list or "None",
                    inline=False
                )
            
            # Show upcoming events
            if upcoming:
                event_list = "\n".join([
                    f"• **{e['title']}** ({e['type']})\n  NA Start: `{e.get('na_start_date', 'N/A')}`"
                    for e in upcoming[:5]  # Show first 5
                ])
                if len(upcoming) > 5:
                    event_list += f"\n... and {len(upcoming) - 5} more"
                
                embed.add_field(
                    name=f"🔵 Upcoming ({len(upcoming)})",
                    value=event_list or "None",
                    inline=False
                )
            
            embed.set_footer(text=f"Database: {DB_PATH}")
            await ctx.send(embed=embed)
            
            # Send detailed text file if too many events
            if len(events) > 10:
                import io
                output = io.StringIO()
                output.write(f"HSR Prydwen Database Dump\n")
                output.write(f"Total Events: {len(events)}\n")
                output.write(f"Database: {DB_PATH}\n")
                output.write(f"Generated: {datetime.now().isoformat()}\n\n")
                
                for event in events:
                    output.write(f"{'='*80}\n")
                    output.write(f"ID: {event['id']}\n")
                    output.write(f"Title: {event['title']}\n")
                    output.write(f"Category: {event['category']}\n")
                    output.write(f"Type: {event['type']}\n")
                    output.write(f"Status: {event.get('status', 'unknown')}\n")
                    output.write(f"NA Start: {event.get('na_start_date', 'N/A')}\n")
                    output.write(f"NA End: {event.get('na_end_date', 'N/A')}\n")
                    output.write(f"EU Start: {event.get('eu_start_date', 'N/A')}\n")
                    output.write(f"EU End: {event.get('eu_end_date', 'N/A')}\n")
                    output.write(f"Asia Start: {event.get('asia_start_date', 'N/A')}\n")
                    output.write(f"Asia End: {event.get('asia_end_date', 'N/A')}\n")
                    output.write(f"Time Remaining: {event.get('time_remaining', 'N/A')}\n")
                    desc = event.get('description', '')
                    if desc and len(desc) > 100:
                        output.write(f"Description: {desc[:100]}...\n")
                    elif desc:
                        output.write(f"Description: {desc}\n")
                    output.write(f"Scraped At: {event.get('scraped_at', 'N/A')}\n")
                    output.write(f"\n")
                
                output.seek(0)
                file = discord.File(output, filename="hsr_prydwen_dump.txt")
                await ctx.send("📄 Detailed dump with regional times:", file=file)
            
        except Exception as e:
            logger.error(f"Error in dump command: {e}")
            await ctx.send(f"❌ Error dumping database: {str(e)}")
    
    logger.info("✅ HSR scraper commands registered successfully (hsr_scrape_and_save, dump_hsr_prydwen_db)")

except ImportError as e:
    # bot.py not available, skip command registration
    logger.info(f"Bot not available, skipping command registration: {e}")
except Exception as e:
    # Some other error during command registration
    logger.error(f"Error registering HSR scraper commands: {e}", exc_info=True)
