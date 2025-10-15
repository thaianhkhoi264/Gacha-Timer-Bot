"""
HSR Scraper - Scrapes https://www.prydwen.gg/star-rail/ for event information
Uses Playwright for JavaScript-rendered content and Prydwen's server time.
"""

from playwright.sync_api import sync_playwright
import os
from datetime import datetime
import logging
import aiosqlite
import asyncio
import re

# Setup logging
logger = logging.getLogger("hsr_scraper")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

log_file_path = os.path.join("logs", "hsr_scraper.log")
os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))

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

# === Database Functions ===

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
                start_date TEXT,
                end_date TEXT,
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
        
        # Check columns and add missing ones (for migration)
        cursor = await conn.execute("PRAGMA table_info(events)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'start_date' not in column_names:
            logger.info("Adding start_date column")
            await conn.execute('ALTER TABLE events ADD COLUMN start_date TEXT')
        if 'end_date' not in column_names:
            logger.info("Adding end_date column")
            await conn.execute('ALTER TABLE events ADD COLUMN end_date TEXT')
        if 'featured_5star' not in column_names:
            logger.info("Adding featured_5star column")
            await conn.execute('ALTER TABLE events ADD COLUMN featured_5star TEXT')
        if 'featured_4star' not in column_names:
            logger.info("Adding featured_4star column")
            await conn.execute('ALTER TABLE events ADD COLUMN featured_4star TEXT')
        
        # Migrate old regional data if present
        if 'na_start_date' in column_names and 'start_date' in column_names:
            logger.info("Migrating regional time data to unified columns")
            await conn.execute('UPDATE events SET start_date = na_start_date WHERE start_date IS NULL OR start_date = ""')
            await conn.execute('UPDATE events SET end_date = na_end_date WHERE end_date IS NULL OR end_date = ""')
        
        await conn.commit()
    logger.info(f"Prydwen database initialized at {DB_PATH}")

async def save_events_to_db(events):
    """
    Save scraped events to the database.
    
    Args:
        events (list): List of event dictionaries
    
    Returns:
        dict: Statistics (added, updated, errors)
    """
    await init_prydwen_db()
    
    stats = {"added": 0, "updated": 0, "errors": 0}
    scraped_at = datetime.now().isoformat()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        for event in events:
            try:
                event_type = event.get('type', 'other_event')
                category = EVENT_TYPE_TO_CATEGORY.get(event_type, 'Event')
                title = event.get('name', event.get('title', ''))
                
                # Check if event exists
                async with conn.execute(
                    "SELECT id FROM events WHERE title=? AND type=?",
                    (title, event_type)
                ) as cursor:
                    existing = await cursor.fetchone()
                
                if existing:
                    # Update existing event
                    if event_type == 'character_banner':
                        await conn.execute('''
                            UPDATE events SET
                                category=?, status=?, start_date=?, end_date=?,
                                time_remaining=?, description=?, image=?, css_class=?, 
                                featured_5star=?, featured_4star=?, scraped_at=?
                            WHERE id=?
                        ''', (
                            category, event.get('status', 'unknown'),
                            event.get('start_date', ''), event.get('end_date', ''),
                            event.get('time_remaining', ''), event.get('description', ''),
                            event.get('image', ''), event.get('css_class', ''),
                            event.get('featured_5star', ''), event.get('featured_4star', ''),
                            scraped_at, existing[0]
                        ))
                    else:
                        await conn.execute('''
                            UPDATE events SET
                                category=?, status=?, start_date=?, end_date=?,
                                time_remaining=?, description=?, image=?, css_class=?, 
                                scraped_at=?
                            WHERE id=?
                        ''', (
                            category, event.get('status', 'unknown'),
                            event.get('start_date', ''), event.get('end_date', ''),
                            event.get('time_remaining', ''), event.get('description', ''),
                            event.get('image', ''), event.get('css_class', ''),
                            scraped_at, existing[0]
                        ))
                    stats["updated"] += 1
                    logger.info(f"Updated: {title}")
                else:
                    # Insert new event
                    if event_type == 'character_banner':
                        await conn.execute('''
                            INSERT INTO events (
                                title, category, type, status, start_date, end_date,
                                time_remaining, description, image, css_class,
                                featured_5star, featured_4star, scraped_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            title, category, event_type, event.get('status', 'unknown'),
                            event.get('start_date', ''), event.get('end_date', ''),
                            event.get('time_remaining', ''), event.get('description', ''),
                            event.get('image', ''), event.get('css_class', ''),
                            event.get('featured_5star', ''), event.get('featured_4star', ''),
                            scraped_at
                        ))
                    else:
                        await conn.execute('''
                            INSERT INTO events (
                                title, category, type, status, start_date, end_date,
                                time_remaining, description, image, css_class, scraped_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            title, category, event_type, event.get('status', 'unknown'),
                            event.get('start_date', ''), event.get('end_date', ''),
                            event.get('time_remaining', ''), event.get('description', ''),
                            event.get('image', ''), event.get('css_class', ''),
                            scraped_at
                        ))
                    stats["added"] += 1
                    logger.info(f"Added: {title}")
            
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Error saving event {event.get('name', 'Unknown')}: {e}")
        
        await conn.commit()
    
    logger.info(f"Save complete: {stats['added']} added, {stats['updated']} updated, {stats['errors']} errors")
    return stats

async def get_all_events_from_db():
    """Retrieve all events from the database."""
    await init_prydwen_db()
    
    events = []
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute('''
            SELECT id, title, category, type, status, start_date, end_date,
                   time_remaining, description, image, css_class, 
                   featured_5star, featured_4star, scraped_at
            FROM events
            ORDER BY start_date DESC
        ''') as cursor:
            async for row in cursor:
                events.append({
                    'id': row[0], 'title': row[1], 'category': row[2], 'type': row[3],
                    'status': row[4], 'start_date': row[5], 'end_date': row[6],
                    'time_remaining': row[7], 'description': row[8], 'image': row[9],
                    'css_class': row[10], 'featured_5star': row[11], 'featured_4star': row[12],
                    'scraped_at': row[13]
                })
    
    return events

# === Helper Functions ===

def ensure_save_directory():
    """Creates the save directory if it doesn't exist."""
    os.makedirs(SAVE_DIR, exist_ok=True)

def extract_featured_characters(accordion_body_html):
    """Extract featured 5-star and 4-star characters from expanded banner accordion."""
    five_star_chars = []
    four_star_chars = []
    
    # Find 5-star characters section
    five_pattern = r'<p class="featured">Featured\s+<span[^>]*rar-5[^>]*>5★</span>\s+character[s]?:</p>\s*<div class="featured-characters">(.*?)</div>'
    five_match = re.search(five_pattern, accordion_body_html, re.DOTALL | re.IGNORECASE)
    
    if five_match:
        five_section = five_match.group(1)
        char_links = re.findall(r'href="(/star-rail/characters/[^"]+)"', five_section)
        for link in char_links:
            char_name = link.split('/')[-1].replace('-', ' ').title()
            five_star_chars.append(char_name)
    
    # Find 4-star characters section
    four_pattern = r'<p class="featured">Featured\s+<span[^>]*rar-4[^>]*>4★</span>\s+character[s]?:</p>\s*<div class="featured-characters">(.*?)</div>'
    four_match = re.search(four_pattern, accordion_body_html, re.DOTALL | re.IGNORECASE)
    
    if four_match:
        four_section = four_match.group(1)
        char_links = re.findall(r'href="(/star-rail/characters/[^"]+)"', four_section)
        for link in char_links:
            char_name = link.split('/')[-1].replace('-', ' ').title()
            four_star_chars.append(char_name)
    
    return ', '.join(five_star_chars), ', '.join(four_star_chars)

def determine_event_type(css_class, event_name):
    """Determine event type from CSS class or name."""
    css_lower = css_class.lower()
    name_lower = event_name.lower()
    
    # Character banners
    if any(x in css_lower for x in ['evernight', 'the-herta', 'saber', 'archer', 'character']):
        return 'character_banner'
    
    # Weapon/Light Cone banners
    if any(x in css_lower for x in ['weapon', 'light-cone', 'lightcone']):
        return 'light_cone_banner'
    
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
    if 'realm of the strange' in name_lower or 'realm' in css_lower:
        return 'relic_event'
    
    return 'other_event'

# === Scraping Functions ===

def scrape_prydwen(save_html=True, headless=True):
    """
    Scrapes the Prydwen Star Rail homepage using Playwright.
    
    Returns:
        str: HTML content, or None if scraping fails
    """
    logger.info(f"Starting scrape of {PRYDWEN_URL}")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()
            
            page.goto(PRYDWEN_URL, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(5000)
            
            html_content = page.content()
            logger.info(f"Successfully fetched HTML ({len(html_content)} bytes)")
            
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
                
                # Also save as "latest.html"
                latest_filepath = os.path.join(SAVE_DIR, "latest.html")
                with open(latest_filepath, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logger.info(f"HTML also saved to: {latest_filepath}")
            
            return html_content
    
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        return None

def scrape_and_extract_banner_characters(html_content):
    """
    Click on character banners to expand them and extract featured characters.
    
    Returns:
        dict: Mapping banner CSS class to (featured_5star, featured_4star) tuples
    """
    logger.info("Expanding character banners to extract featured characters...")
    banner_characters = {}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = context.new_page()
            
            page.goto(PRYDWEN_URL, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(5000)
            
            all_accordion_items = page.query_selector_all('div.accordion-item')
            
            for item in all_accordion_items:
                class_attr = item.get_attribute('class')
                
                if class_attr and 'accordion-item' in class_attr:
                    classes = class_attr.split()
                    if len(classes) > 1:
                        banner_class = classes[0]
                        
                        # Skip non-banner accordion items
                        if banner_class not in ['planar-fissure', 'memory-of-chaos', 'pure-fiction', 
                                                'apocalyptic-shadow', 'apo', 'nameless-honor', 'odyssey', 'realm']:
                            try:
                                button = item.query_selector('button.accordion-button')
                                
                                if button:
                                    is_expanded = button.get_attribute('aria-expanded')
                                    
                                    if is_expanded == 'false':
                                        button.click()
                                        page.wait_for_timeout(1000)
                                    
                                    body = item.query_selector('div.accordion-body')
                                    
                                    if body:
                                        body_html = body.inner_html()
                                        five_star, four_star = extract_featured_characters(body_html)
                                        
                                        if five_star:
                                            banner_characters[banner_class] = (five_star, four_star)
                                            logger.info(f"  Banner '{banner_class}': 5★={five_star}, 4★={four_star}")
                            except Exception as e:
                                logger.warning(f"  Error processing banner '{banner_class}': {e}")
                                continue
            
            browser.close()
            
    except Exception as e:
        logger.error(f"Error extracting banner characters: {e}")
    
    return banner_characters

def extract_events_from_html(html_content, banner_characters=None):
    """
    Extract events from HTML content (server time).
    
    Returns:
        list: List of event dictionaries
    """
    logger.info("Extracting events from HTML...")
    
    if banner_characters is None:
        banner_characters = {}
    
    events = []
    
    # Find all accordion items
    accordion_pattern = r'<div class="([^"]*accordion-item[^"]*)"[^>]*>(.*?)</div>\s*</div>\s*</div>'
    items = re.findall(accordion_pattern, html_content, re.DOTALL)
    
    for item_class, item_content in items:
        # Extract event name
        name_match = re.search(r'<div class="event-name">([^<]+)</div>', item_content)
        if not name_match:
            continue
        event_name = name_match.group(1).strip()
        
        # Extract time remaining
        time_match = re.search(r'<span class="time">([^<]+)</span>', item_content)
        time_remaining = time_match.group(1).strip() if time_match else ""
        
        # Determine status (ongoing if time is counting down, upcoming otherwise)
        status = "ongoing" if time_remaining and ("d" in time_remaining or "h" in time_remaining) else "upcoming"
        
        # Extract duration with date range
        duration_match = re.search(r'<p class="duration">.*?:\s*([^<]+)</p>', item_content, re.DOTALL)
        duration_text = duration_match.group(1).strip() if duration_match else ""
        
        # Parse dates from duration text (server time)
        start_date = ""
        end_date = ""
        
        date_pattern = r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}(?::\d{2})?)'
        dates = re.findall(date_pattern, duration_text)
        
        if len(dates) >= 2:
            start_date = dates[0].replace('/', '-')
            end_date = dates[1].replace('/', '-')
        elif len(dates) == 1:
            end_date = dates[0].replace('/', '-')
            if "after" in duration_text.lower() and "update" in duration_text.lower():
                start_date = "After update"
        
        # Determine event type
        event_type = determine_event_type(item_class, event_name)
        
        # Create event dict
        event = {
            'name': event_name,
            'type': event_type,
            'status': status,
            'start_date': start_date,
            'end_date': end_date,
            'time_remaining': time_remaining,
            'css_class': item_class
        }
        
        # Add featured characters for character banners
        if event_type == 'character_banner':
            css_class = item_class.split()[0] if item_class else ''
            if css_class in banner_characters:
                five_star, four_star = banner_characters[css_class]
                event['featured_5star'] = five_star
                event['featured_4star'] = four_star
            else:
                event['featured_5star'] = ''
                event['featured_4star'] = ''
        
        events.append(event)
    
    logger.info(f"Extracted {len(events)} events")
    
    # Merge simultaneous character banners
    events = merge_simultaneous_character_banners(events)
    
    return events

def merge_simultaneous_character_banners(events):
    """
    Merge simultaneous ongoing character banners into combined entries.
    
    Returns:
        list: List with character banners merged
    """
    ongoing_char_banners = [
        e for e in events 
        if e.get('type') == 'character_banner' and e.get('status') == 'ongoing'
    ]
    
    if len(ongoing_char_banners) == 2:
        banner1, banner2 = ongoing_char_banners
        
        char1 = banner1.get('featured_5star', '').split(',')[0].strip() if banner1.get('featured_5star') else ''
        char2 = banner2.get('featured_5star', '').split(',')[0].strip() if banner2.get('featured_5star') else ''
        
        if char1 and char2:
            combined = {
                'name': f"{char1} & {char2} Banner",
                'type': 'character_banner',
                'status': 'ongoing',
                'start_date': banner1.get('start_date', ''),
                'end_date': banner1.get('end_date', ''),
                'time_remaining': banner1.get('time_remaining', ''),
                'description': f"Dual character banner featuring {char1} and {char2}",
                'image': '',
                'css_class': f"{banner1.get('css_class', '').split()[0]} {banner2.get('css_class', '').split()[0]}",
                'featured_5star': f"{banner1.get('featured_5star', '')}, {banner2.get('featured_5star', '')}",
                'featured_4star': f"{banner1.get('featured_4star', '')}, {banner2.get('featured_4star', '')}",
            }
            
            result = [e for e in events if e not in ongoing_char_banners]
            result.append(combined)
            
            logger.info(f"Merged character banners: '{banner1['name']}' + '{banner2['name']}' → '{combined['name']}'")
            return result
    
    return events

# === Background Task ===

async def periodic_hsr_scraping_task():
    """Background task that scrapes Prydwen HSR website every 24 hours."""
    try:
        logger.info("HSR periodic scraping task started")
        print("[HSR_SCRAPER] Periodic scraping task started")
        
        await asyncio.sleep(5)  # Wait for bot initialization
        
        logger.info("HSR scraper: Starting first scrape...")
        print("[HSR_SCRAPER] Starting first scrape...")
        
        while True:
            try:
                logger.info("Starting periodic HSR scrape...")
                
                loop = asyncio.get_event_loop()
                
                # Scrape HTML
                html_content = await loop.run_in_executor(None, scrape_prydwen, True, True)
                
                if not html_content:
                    logger.error("Periodic scrape failed - no HTML returned")
                else:
                    # Extract featured characters from banners
                    banner_characters = await loop.run_in_executor(
                        None,
                        scrape_and_extract_banner_characters,
                        html_content
                    )
                    
                    # Extract events
                    events = extract_events_from_html(html_content, banner_characters)
                    
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
                logger.error(f"Error in periodic HSR scraping task: {e}", exc_info=True)
            
            # Wait 24 hours
            logger.info("Next HSR scrape in 24 hours")
            await asyncio.sleep(86400)
            
    except Exception as e:
        logger.error(f"Fatal error in periodic_hsr_scraping_task: {e}", exc_info=True)
        print(f"[HSR_SCRAPER] FATAL ERROR: {e}")
        raise

# === Discord Bot Commands ===

try:
    from bot import bot
    from discord.ext import commands
    import discord
    
    logger.info("Registering HSR scraper Discord commands...")
    
    @bot.command(name="hsr_scrape")
    @commands.has_permissions(administrator=True)
    async def hsr_scrape_command(ctx):
        """Scrapes Prydwen HSR website with featured characters (server time)"""
        await ctx.send("🔄 Scraping Prydwen Star Rail website...")
        
        try:
            loop = asyncio.get_event_loop()
            html_content = await loop.run_in_executor(None, scrape_prydwen, True, True)
            
            if not html_content:
                await ctx.send("❌ Failed to scrape website")
                return
            
            await ctx.send("🎭 Extracting featured characters from banners...")
            
            banner_characters = await loop.run_in_executor(None, scrape_and_extract_banner_characters, html_content)
            
            await ctx.send("📊 Extracting events...")
            
            events = extract_events_from_html(html_content, banner_characters)
            
            if not events:
                await ctx.send("⚠️ No events found in scraped data")
                return
            
            await ctx.send(f"💾 Saving {len(events)} events to database...")
            
            stats = await save_events_to_db(events)
            
            # Send results
            embed = discord.Embed(
                title="✅ HSR Prydwen Scrape Complete",
                description=f"Successfully scraped {len(events)} events from Prydwen\n(server time with featured characters)",
                color=discord.Color.green()
            )
            embed.add_field(name="Added", value=str(stats['added']), inline=True)
            embed.add_field(name="Updated", value=str(stats['updated']), inline=True)
            embed.add_field(name="Errors", value=str(stats['errors']), inline=True)
            
            ongoing = sum(1 for e in events if e.get('status') == 'ongoing')
            upcoming = sum(1 for e in events if e.get('status') == 'upcoming')
            embed.add_field(name="Ongoing", value=str(ongoing), inline=True)
            embed.add_field(name="Upcoming", value=str(upcoming), inline=True)
            
            # Show character banners
            char_banners = [e for e in events if e.get('type') == 'character_banner' and e.get('featured_5star')]
            if char_banners:
                banner_info = "\n".join([
                    f"**{e['name']}**\n5★: {e.get('featured_5star', 'N/A')}\n4★: {e.get('featured_4star', 'N/A')}"
                    for e in char_banners[:2]
                ])
                embed.add_field(name="Character Banners", value=banner_info, inline=False)
            
            embed.set_footer(text=f"Database: {DB_PATH}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in scrape command: {e}")
            await ctx.send(f"❌ Error during scraping: {str(e)}")
    
    @bot.command(name="hsr_dump_db")
    @commands.has_permissions(administrator=True)
    async def dump_hsr_db_command(ctx):
        """Dumps all events from the HSR Prydwen database"""
        await ctx.send("📊 Fetching events from Prydwen database...")
        
        try:
            events = await get_all_events_from_db()
            
            if not events:
                await ctx.send("⚠️ No events found in database")
                return
            
            embed = discord.Embed(
                title="HSR Prydwen Database Dump",
                description=f"Total events: {len(events)}\n(server time)",
                color=discord.Color.blue()
            )
            
            ongoing = [e for e in events if e.get('status') == 'ongoing']
            upcoming = [e for e in events if e.get('status') == 'upcoming']
            
            if ongoing:
                event_list = "\n".join([
                    f"• **{e['title']}** ({e['type']})\n  End: `{e.get('end_date', 'N/A')}`"
                    for e in ongoing[:5]
                ])
                if len(ongoing) > 5:
                    event_list += f"\n... and {len(ongoing) - 5} more"
                
                embed.add_field(name=f"🟢 Ongoing ({len(ongoing)})", value=event_list or "None", inline=False)
            
            if upcoming:
                event_list = "\n".join([
                    f"• **{e['title']}** ({e['type']})\n  Start: `{e.get('start_date', 'N/A')}`"
                    for e in upcoming[:5]
                ])
                if len(upcoming) > 5:
                    event_list += f"\n... and {len(upcoming) - 5} more"
                
                embed.add_field(name=f"🔵 Upcoming ({len(upcoming)})", value=event_list or "None", inline=False)
            
            embed.set_footer(text=f"Database: {DB_PATH}")
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in dump command: {e}")
            await ctx.send(f"❌ Error dumping database: {str(e)}")
    
    logger.info("HSR scraper commands registered successfully")

except ImportError as e:
    logger.info(f"Bot not available, skipping command registration: {e}")
except Exception as e:
    logger.error(f"Error registering HSR scraper commands: {e}", exc_info=True)
