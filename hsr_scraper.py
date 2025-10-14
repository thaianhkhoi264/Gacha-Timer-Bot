"""
HSR Scraper - Scrapes https://www.prydwen.gg/star-rail/ for event information
This module can be called from hsr_module.py to fetch and save the HTML content.
Uses Playwright for JavaScript-rendered content.
"""

from playwright.sync_api import sync_playwright
import os
from datetime import datetime
import logging

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

def ensure_save_directory():
    """Creates the save directory if it doesn't exist."""
    os.makedirs(SAVE_DIR, exist_ok=True)
    logger.info(f"Save directory ensured: {SAVE_DIR}")

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
