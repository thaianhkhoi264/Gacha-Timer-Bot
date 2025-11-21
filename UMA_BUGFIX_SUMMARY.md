# Uma Musume Module Bug Fixes - November 21, 2025

## Issues Found

### Critical Issues
1. **Headless Browser Mode Disabled**: `headless=False` prevented Playwright from running on Raspberry Pi without a display
2. **Missing Data Folder**: Database path assumed `data/` folder existed, causing SQLite errors
3. **Combined Images in Wrong Location**: Saved to root `combined_images/` instead of `data/combined_images/`
4. **No Error Handling**: download_timeline() had no try/except, so Playwright errors crashed the bot
5. **Insufficient Logging**: Hard to debug issues without detailed logs

### Minor Issues
6. **No Channel Validation**: uma_update_timers() didn't log if channels were missing
7. **No Event Count Tracking**: Couldn't tell how many events were posted/deleted

## Fixes Applied

### 1. Enabled Headless Browser Mode
**File**: `uma_handler.py`
**Change**: Line 74
```python
# Before:
browser = await p.chromium.launch(headless=False)

# After:
browser = await p.chromium.launch(headless=True)
```
**Impact**: Bot can now run on Raspberry Pi without a display

### 2. Ensured Data Folder Exists
**File**: `uma_module.py`
**Function**: `init_uma_db()`
```python
# Added:
os.makedirs("data", exist_ok=True)
uma_logger.info(f"[DB Init] Ensuring database directory exists: data/")
```
**Impact**: Database can be created even if `data/` folder doesn't exist

### 3. Fixed Combined Images Path
**File**: `uma_module.py`
**Function**: `combine_images_vertically()`
```python
# Before:
os.makedirs("combined_images", exist_ok=True)
filepath = os.path.join("combined_images", filename)

# After:
os.makedirs(os.path.join("data", "combined_images"), exist_ok=True)
filepath = os.path.join("data", "combined_images", filename)
```
**Impact**: All event data (database + images) now in `data/` folder

### 4. Added Error Handling to Scraper
**File**: `uma_handler.py`
**Function**: `download_timeline()`
```python
# Wrapped entire function in try/except:
try:
    async with async_playwright() as p:
        # ... scraping logic ...
except Exception as e:
    uma_handler_logger.error(f"Failed to download timeline: {e}")
    import traceback
    uma_handler_logger.error(traceback.format_exc())
    return []
```
**Impact**: Playwright errors logged instead of crashing bot

### 5. Added Comprehensive Logging

#### Database Initialization
**File**: `uma_module.py`
```python
uma_logger.info(f"[DB Init] Ensuring database directory exists: data/")
uma_logger.info(f"[DB Init] Database initialized successfully at: {UMA_DB_PATH}")
```

#### Event Addition
**File**: `uma_module.py`
```python
uma_logger.info(f"[Add Event] Adding event: {event_data.get('title', 'Unknown')}")
```

#### Image Combination
**File**: `uma_module.py`
```python
uma_logger.info(f"[Image] Combined images saved to: {filepath}")
```

#### Timeline Download
**File**: `uma_handler.py`
```python
uma_handler_logger.info(f"Downloaded {len(raw_events)} raw events from timeline")
uma_handler_logger.info(f"Processed {len(processed_events)} events from {len(raw_events)} raw events!")
if len(processed_events) == 0:
    uma_handler_logger.warning("No events were processed! Check if timeline structure has changed.")
```

#### Dashboard Updates
**File**: `uma_module.py`
```python
uma_logger.info("[Update Timers] Starting dashboard update...")
uma_logger.info(f"[Update Timers] Fetched {len(events)} events from database")
uma_logger.info(f"[Update Timers] Ongoing channel: {ongoing_channel.name if ongoing_channel else 'None'}")
uma_logger.info(f"[Update Timers] Upcoming channel: {upcoming_channel.name if upcoming_channel else 'None'}")
uma_logger.info(f"[Update Timers] Posted ongoing event: {event['title']}")
uma_logger.info(f"[Update Timers] Posted upcoming event: {event['title']}")
uma_logger.info(f"[Update Timers] Deleted ended event: {event['title']}")
uma_logger.info(f"[Update Timers] Summary - Ongoing: {ongoing_count}, Upcoming: {upcoming_count}, Deleted: {deleted_count}, Skipped (>1mo): {skipped_count}")
```

### 6. Added Channel Validation
**File**: `uma_module.py`
```python
if not main_guild:
    uma_logger.error("[Update Timers] Main guild not found!")
    return

if not ongoing_channel:
    uma_logger.error(f"[Update Timers] Ongoing channel not found: {ONGOING_EVENTS_CHANNELS['UMA']}")
if not upcoming_channel:
    uma_logger.error(f"[Update Timers] Upcoming channel not found: {UPCOMING_EVENTS_CHANNELS['UMA']}")
```

### 7. Added Event Counting
**File**: `uma_module.py`
```python
ongoing_count = 0
upcoming_count = 0
deleted_count = 0
skipped_count = 0

# Incremented in respective sections, then logged:
uma_logger.info(f"[Update Timers] Summary - Ongoing: {ongoing_count}, Upcoming: {upcoming_count}, Deleted: {deleted_count}, Skipped (>1mo): {skipped_count}")
```

## Testing Steps

### On Raspberry Pi
1. **Pull latest code**:
   ```bash
   cd /path/to/Gacha-Timer-Bot
   git pull origin main
   ```

2. **Install Playwright browsers**:
   ```bash
   playwright install chromium
   playwright install-deps chromium
   ```

3. **Restart bot**:
   ```bash
   # If using systemd:
   sudo systemctl restart kanami-bot

   # Or manually:
   python3 main.py
   ```

4. **Check logs**:
   ```bash
   # Real-time monitoring:
   tail -f logs/uma_musume.log

   # Look for:
   # [Startup] Initializing Uma Musume background tasks...
   # [DB Init] Database initialized successfully at: data/uma_musume_data.db
   # [Startup] Running initial Uma Musume event update...
   # Navigating to https://uma.moe/timeline ...
   # Downloaded X raw events from timeline
   # Processed Y events from X raw events!
   # [Update Timers] Starting dashboard update...
   # [Update Timers] Posted ongoing event: ...
   # [Update Timers] Posted upcoming event: ...
   ```

5. **Verify database**:
   ```bash
   ls -la data/
   # Should see: uma_musume_data.db

   sqlite3 data/uma_musume_data.db "SELECT COUNT(*) FROM events;"
   # Should show number of events
   ```

6. **Check Discord channels**:
   - Verify events appear in ongoing/upcoming channels
   - Check that images are displayed correctly
   - Confirm event times are correct (10pm UTC start, 9:59pm UTC end)

## Expected Log Output (Success)

```
[INFO] [Startup] Initializing Uma Musume background tasks...
[INFO] [DB Init] Ensuring database directory exists: data/
[INFO] [DB Init] Database initialized successfully at: data/uma_musume_data.db
[INFO] [Startup] Uma Musume database initialized.
[INFO] [Startup] Running initial Uma Musume event update...
[INFO] Starting Uma Musume event update...
[INFO] Navigating to https://uma.moe/timeline ...
[INFO] Scroll 1: Latest event date found: 2025-12-15 21:59:00+00:00
[INFO] Scroll 2: Latest event date found: 2025-12-22 21:59:00+00:00
...
[INFO] Downloaded 45 raw events from timeline
[INFO] Processed 23 events from 45 raw events!
[INFO] [Add Event] Adding event: Kitasan Black Banner
[INFO] [Image] Combined images saved to: data/combined_images/combined_1732195234.png
[INFO] [Add Event] Adding event: Legend Race
...
[INFO] Added 23/23 events to database.
[INFO] [Update Timers] Starting dashboard update...
[INFO] [Update Timers] Ongoing channel: uma-ongoing-events
[INFO] [Update Timers] Upcoming channel: uma-upcoming-events
[INFO] [Update Timers] Fetched 23 events from database
[INFO] [Update Timers] Posted ongoing event: Kitasan Black Banner
[INFO] [Update Timers] Posted upcoming event: Champions Meeting
[INFO] [Update Timers] Summary - Ongoing: 3, Upcoming: 18, Deleted: 0, Skipped (>1mo): 2
[INFO] Dashboard updated successfully!
[INFO] [Startup] Initial update completed successfully.
[INFO] [Startup] Periodic update task scheduled (every 3 days).
```

## Common Issues & Solutions

### Issue: "Timeline container not found!"
**Cause**: Website structure changed or Playwright timeout
**Solution**: Check if uma.moe/timeline is accessible, increase timeout

### Issue: No events in database
**Cause**: process_events() returned empty list
**Solution**: Check logs for parsing errors, verify event title patterns match

### Issue: Images not displaying in Discord
**Cause**: File path issues or PIL errors
**Solution**: Check `data/combined_images/` folder exists and has images

### Issue: Events not in correct channels
**Cause**: Wrong channel IDs in global_config.py
**Solution**: Verify ONGOING_EVENTS_CHANNELS["UMA"] and UPCOMING_EVENTS_CHANNELS["UMA"]

## Files Modified
- `uma_handler.py`: Headless mode, error handling, logging
- `uma_module.py`: Folder creation, logging, validation, event counting
- `UMA_SETUP.md`: New setup documentation (this file)

## Rollback Instructions
If issues persist:
```bash
git log --oneline -5  # Find commit before changes
git checkout <commit-hash> uma_handler.py uma_module.py
git checkout HEAD~1 uma_handler.py uma_module.py  # Or go back 1 commit
```
