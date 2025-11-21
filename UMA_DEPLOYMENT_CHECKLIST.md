# Uma Musume Event Tracker - Deployment Checklist

## Pre-Deployment Checklist

### ✓ Code Changes Completed
- [x] Enabled headless browser mode for Raspberry Pi
- [x] Added data folder creation in init_uma_db()
- [x] Fixed combined images path to data/combined_images/
- [x] Added comprehensive error handling
- [x] Added detailed logging throughout
- [x] Added channel validation
- [x] Added event counting and summaries

### ✓ Files Modified
- [x] `uma_handler.py` - Scraper with headless mode and error handling
- [x] `uma_module.py` - Discord integration with logging
- [x] `main.py` - Bot startup integration
- [x] Created `UMA_SETUP.md` - Setup documentation
- [x] Created `UMA_BUGFIX_SUMMARY.md` - Bug fix summary

## Raspberry Pi Deployment Steps

### 1. Push Code to GitHub
```bash
# On development machine:
git add uma_handler.py uma_module.py UMA_SETUP.md UMA_BUGFIX_SUMMARY.md
git commit -m "Fix Uma Musume module: headless mode, folders, logging"
git push origin main
```

### 2. Pull on Raspberry Pi
```bash
# SSH into Raspberry Pi
ssh pi@your-raspberry-pi-ip

# Navigate to bot directory
cd /path/to/Gacha-Timer-Bot

# Pull latest changes
git pull origin main
```

### 3. Install Playwright Browser
```bash
# Install Playwright Chromium browser
playwright install chromium

# If you get errors, also run:
playwright install-deps chromium

# Verify installation:
python3 -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); browser = p.chromium.launch(headless=True); print('✓ Playwright working!'); browser.close()"
```

### 4. Verify Channel Configuration
```bash
# Edit global_config.py if needed
nano global_config.py

# Verify these lines are correct:
# ONGOING_EVENTS_CHANNELS = {
#     "UMA": 1417203942353272882,  # ← Your ongoing events channel ID
# }
# UPCOMING_EVENTS_CHANNELS = {
#     "UMA": 1417203965308964966,  # ← Your upcoming events channel ID
# }
```

### 5. Restart Bot
```bash
# If using systemd:
sudo systemctl restart kanami-bot
sudo systemctl status kanami-bot

# Or if running manually:
# Stop current bot (Ctrl+C)
python3 main.py
```

### 6. Monitor Logs
```bash
# Watch Uma Musume logs in real-time:
tail -f logs/uma_musume.log

# Expected output:
# [INFO] [Startup] Initializing Uma Musume background tasks...
# [INFO] [DB Init] Database initialized successfully at: data/uma_musume_data.db
# [INFO] Navigating to https://uma.moe/timeline ...
# [INFO] Downloaded X raw events from timeline
# [INFO] Processed Y events from X raw events!
# [INFO] [Update Timers] Starting dashboard update...
# [INFO] [Update Timers] Posted ongoing event: ...
```

## Verification Steps

### Step 1: Check Database Created
```bash
# Verify database exists:
ls -la data/uma_musume_data.db

# Check table contents:
sqlite3 data/uma_musume_data.db "SELECT COUNT(*) FROM events;"
sqlite3 data/uma_musume_data.db "SELECT title, category FROM events LIMIT 5;"
```

**Expected**: Database exists with events table containing Uma events

### Step 2: Check Combined Images
```bash
# Verify images folder exists:
ls -la data/combined_images/

# Should contain PNG files like: combined_1732195234.png
```

**Expected**: Folder exists with combined banner images

### Step 3: Check Discord Channels
1. **Ongoing Events Channel** (ID: 1417203942353272882)
   - Should show events that have started but not ended
   - Check: Event embeds are teal (banners), gold (events), or fuchsia (offers)
   - Verify: Images display correctly (combined banners shown vertically)

2. **Upcoming Events Channel** (ID: 1417203965308964966)
   - Should show events within 1 month that haven't started
   - Same embed checks as ongoing

**Expected**: Events posted in correct channels with proper formatting

### Step 4: Check Event Details
For each event, verify:
- **Title**: Clear event name (e.g., "Kitasan Black Banner", "Legend Race")
- **Start/End Times**: Discord timestamps show correct dates
- **Description**: 
  - Banners show character names and support cards
  - Legend Races show race details (distance, type, surface)
  - Champions Meetings show full race specifications
- **Images**: 
  - Combined banners show both character and support images stacked vertically
  - Images load properly (not broken links)

### Step 5: Test Manual Commands

#### Test !uma_refresh
```discord
!uma_refresh
```
**Expected**: "Uma Musume event dashboards have been refreshed."

#### Test !uma_update (if you want to force re-download)
```discord
!uma_update
```
**Expected**: 
- "Starting Uma Musume event update from timeline... This may take a few minutes."
- Wait 2-3 minutes for scraping to complete
- Events should be updated in channels

## Troubleshooting

### Problem: No events showing in Discord
**Check**:
1. `logs/uma_musume.log` for errors
2. `data/uma_musume_data.db` exists and has events
3. Channel IDs in `global_config.py` are correct
4. Bot has permission to send messages in those channels

**Fix**:
```bash
# Verify channel permissions
# In Discord, right-click channel → Edit Channel → Permissions
# Ensure bot role has: Send Messages, Embed Links, Attach Files

# Manually run refresh:
!uma_refresh
```

### Problem: Playwright errors
**Error**: "Executable doesn't exist at /home/pi/.cache/ms-playwright/chromium-*/chrome-linux/chrome"

**Fix**:
```bash
playwright install chromium
playwright install-deps chromium

# If still fails, install system dependencies:
sudo apt-get update
sudo apt-get install -y libnss3 libatk1.0-0 libcups2 libdrm2 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2
```

### Problem: Images not displaying
**Error**: "Image not found" or broken image icon in Discord

**Check**:
```bash
# Verify images exist:
ls -la data/combined_images/

# Check file permissions:
chmod -R 755 data/combined_images/

# Verify Pillow is installed:
python3 -c "from PIL import Image; print('✓ PIL working')"
```

### Problem: "Main guild not found"
**Error**: `[Update Timers] Main guild not found!`

**Fix**:
```python
# In global_config.py, verify:
MAIN_SERVER_ID = YOUR_DISCORD_SERVER_ID  # ← Must be correct
```

### Problem: Database locked
**Error**: `database is locked`

**Fix**:
```bash
# Stop bot
sudo systemctl stop kanami-bot

# Remove lock
rm data/uma_musume_data.db-journal

# Restart bot
sudo systemctl start kanami-bot
```

## Success Criteria

✅ **All checks passed if**:
1. `data/uma_musume_data.db` exists with events
2. `data/combined_images/` contains PNG files
3. Ongoing events channel shows active events
4. Upcoming events channel shows future events (within 1 month)
5. Images display correctly (combined banners vertical)
6. Event descriptions show race details for Legend Races/Champions Meetings
7. Logs show successful initialization and updates
8. No errors in `logs/uma_musume.log`

## Periodic Update Verification

The bot will automatically update every 3 days. To verify it's working:

1. **Check logs in 3 days**:
```bash
grep "Periodic Update" logs/uma_musume.log
# Should see: [Periodic Update] Starting scheduled Uma Musume event update...
```

2. **Or manually test the periodic update** (don't wait 3 days):
   - Edit `uma_module.py` line 398: Change `259200` to `60` (1 minute)
   - Restart bot
   - Wait 1 minute
   - Check logs for periodic update
   - **Remember to change back to 259200 after testing!**

## Contact & Support

If issues persist after following this checklist:
1. Check `logs/uma_musume.log` for detailed error messages
2. Run `!uma_update` command to manually trigger update
3. Verify all dependencies installed: `pip list | grep -E "playwright|pillow|aiosqlite"`
4. Check Discord bot permissions in server settings

## Quick Reference

**Log File**: `logs/uma_musume.log`
**Database**: `data/uma_musume_data.db`
**Images**: `data/combined_images/`
**Update Frequency**: Every 3 days (259200 seconds)
**Channels**: 
- Ongoing: 1417203942353272882
- Upcoming: 1417203965308964966
