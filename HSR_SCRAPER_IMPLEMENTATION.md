# HSR Prydwen Regional Scraping Implementation

## Overview
Implemented comprehensive web scraping solution for Star Rail event data from Prydwen website with support for regional times (NA/EU/Asia), event status tracking, and automated 24-hour periodic updates.

## Features Implemented

### 1. Regional Time Support
- **Multi-Region Scraping**: Automated clicking through NA, EU, and Asia region buttons on Prydwen website
- **Database Schema**: Six regional date fields (na_start_date, na_end_date, eu_start_date, eu_end_date, asia_start_date, asia_end_date)
- **Unified Times**: Currently all regions show identical "server time" (game's universal time), but infrastructure supports region-specific times if website changes

### 2. Event Status Tracking
- **Ongoing Events**: Currently active events extracted from "Current" section
- **Upcoming Events**: Future events extracted from "Upcoming" section  
- **Status Field**: Database stores "ongoing" or "upcoming" status for each event

### 3. Event Type Detection
Automatically categorizes events by analyzing CSS classes and event names:
- **Character Banners**: `character_banner`
- **Weapon/Light Cone Banners**: `weapon_banner`
- **Memory of Chaos**: `memory_of_chaos`
- **Pure Fiction**: `pure_fiction`
- **Apocalyptic Shadow**: `apocalyptic_shadow`
- **Planar Fissure**: `planar_fissure`
- **Battle Pass (Nameless Honor)**: `battle_pass`
- **Login Events (Gift of Odyssey)**: `login_event`
- **Other Events**: `other_event`

### 4. Background Automation
- **Initial Scrape**: Runs 5 seconds after bot startup
- **Periodic Updates**: Automatically scrapes every 24 hours
- **Async Integration**: Uses executor to run sync Playwright code in async bot context

### 5. Discord Commands

#### `!hsr_scrape_and_save` (Admin only)
Manually triggers scraping with regional time extraction:
- Scrapes NA, EU, and Asia regions
- Extracts events with status and dates
- Saves to database
- Shows statistics embed with:
  - Total events
  - Added/Updated/Errors
  - Ongoing vs Upcoming counts

#### `!dump_hsr_prydwen_db` (Admin only)
Dumps database contents for verification:
- Embed showing ongoing and upcoming events
- Text file with detailed regional times for all events
- Displays all six regional date fields

## Technical Implementation

### Database Schema
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,       -- Banner/Event/Maintenance
    type TEXT NOT NULL,            -- character_banner, etc.
    status TEXT,                   -- ongoing/upcoming
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
    scraped_at TEXT NOT NULL,
    UNIQUE(title, type)            -- Prevents duplicates
)
```

### Key Functions

**`scrape_prydwen_with_regions(save_html, headless)`**
- Launches Playwright browser
- Clicks NA/EU/Asia buttons sequentially
- Captures HTML content for each region
- Saves separate HTML files with timestamps
- Returns dict: `{"NA": html, "EU": html, "Asia": html}`

**`extract_events_from_regional_html(regional_html)`**
- Parses HTML to find "Current" and "Upcoming" sections
- Extracts accordion items containing events
- Parses event names, dates, and types
- Merges regional data into unified event dicts
- Returns list of events with all six regional date fields

**`extract_events_from_section(section_html, status, region)`**
- Finds accordion-item divs
- Extracts event-name, time countdown, duration text
- Parses dates using regex patterns
- Determines event type from CSS classes
- Returns list of events for that section/region

**`save_events_to_db(events)`**
- Checks for existing events by (title, type)
- Updates existing events with new regional times
- Inserts new events with all fields
- Returns statistics (added, updated, errors)

**`periodic_hsr_scraping_task()`**
- Background async task
- Runs immediately on startup (after 5s delay)
- Repeats every 24 hours
- Uses executor for sync Playwright code
- Logs all operations and errors

## Testing Results

### Test Scrape Output (2025-10-14)
```
✅ Scraped successfully!
  NA: 3,496,046 bytes
  EU: 3,452,028 bytes
  Asia: 3,457,768 bytes

✅ Extracted 14 events
  - 10 ongoing events
  - 4 upcoming events

✅ Save complete!
  Added: 14
  Updated: 0
  Errors: 0
```

### Sample Events Extracted
1. **Evil March Can't Hurt You** (character_banner, ongoing)
2. **Re:Mahou Shoujo** (character_banner, ongoing)
3. **Planar Fissure** (planar_fissure, ongoing)
4. **Memory of Chaos (3.5)** (memory_of_chaos, ongoing)
5. **Nameless Honor** (battle_pass, ongoing)
6. **Gift of Odyssey** (login_event, ongoing)
7. **Apocalyptic Shadow (3.6)** (apocalyptic_shadow, ongoing)
8. **Pure Fiction (3.6)** (pure_fiction, ongoing)
9. **Excalibur!** (other_event, ongoing)
10. **Bone of My Sword** (other_event, ongoing)
11. **Half Dan, Half Dragon, Full Bad-ass** (other_event, upcoming)
12. **Anaxa Unchained** (other_event, upcoming)
13. **Realm of the Strange** (other_event, upcoming)
14. **Memory of Chaos (3.6)** (memory_of_chaos, upcoming)

### Regional Time Analysis
Testing confirmed that Prydwen displays "server time" universally - all three regions show identical times. This is expected because Star Rail uses a unified server time across all regions. The infrastructure is in place to capture region-specific times if the website changes in the future.

## Files Modified

### `hsr_scraper.py` (Major Changes)
- Updated `init_prydwen_db()`: New schema with status and regional date fields
- Created `scrape_prydwen_with_regions()`: Multi-region scraping with button clicks
- Created `extract_events_from_html()`: Parse HTML for Current/Upcoming sections
- Created `extract_events_from_section()`: Extract individual events from section
- Created `determine_event_type()`: Smart event type detection
- Created `extract_events_from_regional_html()`: Merge regional data
- Updated `save_events_to_db()`: Handle new schema with regional fields
- Updated `get_all_events_from_db()`: Return regional fields
- Created `periodic_hsr_scraping_task()`: Background scraping task
- Updated `hsr_scrape_and_save_command`: Use regional scraping
- Updated `dump_hsr_prydwen_db_command`: Display regional times

### `main.py` (Minor Changes)
- Added `asyncio.create_task(hsr_scraper.periodic_hsr_scraping_task())` to on_ready()

### `requirements.txt`
- Added `playwright` dependency

## Installation Requirements

```bash
# Install Python package
pip install playwright

# Install browser binaries
python -m playwright install chromium
```

## Usage

### Manual Scraping
```
!hsr_scrape_and_save
```
Triggers immediate scrape with regional times and saves to database.

### View Database
```
!dump_hsr_prydwen_db
```
Shows current database contents with regional times.

### Automatic Scraping
Background task runs automatically:
- Starts 5 seconds after bot launch
- Repeats every 24 hours
- Logs all operations to hsr_scraper.log

## Logs

All operations logged to:
- Console (INFO level)
- `logs/hsr_scraper.log` (file logging with rotation)

Sample log output:
```
[INFO] Starting multi-region scrape of https://www.prydwen.gg/star-rail/
[INFO] Switching to NA region...
[INFO]   Captured HTML for NA (3496046 bytes)
[INFO] Switching to EU region...
[INFO]   Captured HTML for EU (3452028 bytes)
[INFO] Switching to Asia region...
[INFO]   Captured HTML for Asia (3457768 bytes)
[INFO] Extracting events from regional HTML...
[INFO] NA: Found 10 ongoing, 4 upcoming events
[INFO] EU: Found 10 ongoing, 4 upcoming events
[INFO] Asia: Found 10 ongoing, 4 upcoming events
[INFO] Merged 14 unique events with regional times
[INFO] Database save complete: 14 added, 0 updated, 0 errors
```

## Future Enhancements

### Potential Improvements
1. **Image Extraction**: Parse and save event banner images
2. **Description Parsing**: Extract full event descriptions
3. **Notification Integration**: Send Discord notifications when new events are detected
4. **Regional Timezone Conversion**: Convert server times to local times for each region
5. **Event Comparison**: Detect changes in event dates/details between scrapes
6. **Web UI**: Create web interface to view scraped data
7. **API Endpoint**: Expose scraped data via REST API

### Known Limitations
1. **Server Time Only**: Currently all regions show same "server time" (by design on Prydwen)
2. **No Image Storage**: Images not currently scraped (URLs exist but not saved)
3. **Limited Description**: Full event descriptions not extracted
4. **Single Website**: Only Prydwen supported (could expand to other sources)

## Troubleshooting

### Common Issues

**Playwright Not Installed**
```
ModuleNotFoundError: No module named 'playwright'
```
Solution: Run `pip install playwright` and `python -m playwright install chromium`

**Browser Launch Fails**
```
ERROR: Executable doesn't exist at ...
```
Solution: Run `python -m playwright install chromium`

**Scraping Fails (403/Block)**
- Website may block automated browsers
- Try adjusting user agent or browser settings
- Consider adding delays between region switches

**No Events Extracted**
- Website HTML structure may have changed
- Check logs for parsing errors
- Inspect saved HTML files to verify structure

### Debug Mode

To run scraper with visible browser for debugging:
```python
regional_html = scrape_prydwen_with_regions(save_html=True, headless=False)
```

## Testing Scripts

Several test scripts created in `temp_analysis/` folder:

1. **`test_regional_scraper.py`**: Full pipeline test (scrape → extract → save)
2. **`analyze_events.py`**: HTML structure analysis
3. **`deep_dive_events.py`**: Event container pattern discovery
4. **`extract_event_details.py`**: Detailed event extraction test
5. **`compare_regional_times.py`**: Regional time comparison verification

These can be used to:
- Test scraping without running full bot
- Debug HTML parsing issues
- Verify regional time extraction
- Analyze website structure changes

## Conclusion

Successfully implemented a comprehensive HSR event scraping system with:
- ✅ Regional time support (NA/EU/Asia)
- ✅ Event status tracking (ongoing/upcoming)
- ✅ Smart event type detection
- ✅ Background automation (24-hour intervals)
- ✅ Discord commands for manual control
- ✅ Robust error handling and logging
- ✅ Database persistence with regional fields

The system is production-ready and will automatically keep event data up-to-date every 24 hours.
