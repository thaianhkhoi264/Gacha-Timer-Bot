# Uma Musume Event Tracker Setup Guide

## Overview
The Uma Musume event tracking system automatically scrapes events from https://uma.moe/timeline and posts them to your Discord server. Events are updated on bot startup and every 3 days.

## Raspberry Pi Setup

### 1. Install Playwright Browser
After installing Python dependencies with `pip install -r requirements.txt`, you need to install the Playwright browser:

```bash
playwright install chromium
```

If you get dependency errors on Raspberry Pi, you may need to install system dependencies:

```bash
# For Raspberry Pi OS (Debian-based)
playwright install-deps chromium
```

### 2. Verify Installation
Check if the bot can run headless:

```bash
python3 -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); browser = p.chromium.launch(headless=True); print('✓ Playwright working!'); browser.close()"
```

## File Structure

The bot will automatically create these folders:
```
data/
  uma_musume_data.db         # Event database
  combined_images/           # Combined banner images
logs/
  uma_musume.log            # Uma module logs
```

## Discord Channel Configuration

Edit `global_config.py` to set your channel IDs:

```python
ONGOING_EVENTS_CHANNELS = {
    "UMA": YOUR_ONGOING_CHANNEL_ID,
}

UPCOMING_EVENTS_CHANNELS = {
    "UMA": YOUR_UPCOMING_CHANNEL_ID,
}
```

## How It Works

### Automatic Updates
1. **On Bot Startup**: Immediately downloads all events from uma.moe/timeline
2. **Every 3 Days**: Runs automatic update to refresh event data

### Event Processing
The scraper intelligently combines related events:

- **Character + Support Banners**: Combined into single "Character Name Banner" with both images vertically stacked
- **Paid Banners**: Paired paid banners combined
- **Story Events**: Extracted name from "Story Event: [Name]"
- **Legend Races**: Race details (distance, type, surface) in description
- **Champions Meetings**: Full race specifications in description

### Display Filtering
- Only shows events within **1 month** from current date
- **Ongoing Events**: Events that have started but not ended
- **Upcoming Events**: Events starting within 1 month
- Automatically deletes ended events

## Manual Commands

### `!uma_update` (Admin Only)
Manually triggers event download from uma.moe/timeline
```
!uma_update
```

### `!uma_refresh` (Manage Guild Permission)
Refreshes the event dashboards without downloading new data
```
!uma_refresh
```

### `!uma_remove <title>` (Manage Guild Permission)
Removes a specific event by title
```
!uma_remove Paid Banner
```

## Troubleshooting

### No Events Showing Up
1. **Check logs**: Look at `logs/uma_musume.log` for errors
2. **Verify channels**: Make sure channel IDs in `global_config.py` are correct
3. **Check database**: Verify `data/uma_musume_data.db` exists
4. **Playwright issues**: Run `playwright install chromium` again

### Playwright Not Working
```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2

# Then reinstall Playwright
playwright install chromium
playwright install-deps chromium
```

### Image Combination Issues
- Images are saved to `data/combined_images/`
- Uses PIL (Pillow) to combine images vertically
- If images fail to combine, events will still be created with the first image

## Logging

All Uma Musume operations are logged to both:
- **Console**: Real-time status updates
- **File**: `logs/uma_musume.log` for debugging

Log levels:
- `[INFO]`: Normal operations (startup, downloads, event counts)
- `[WARNING]`: Non-critical issues (no events processed)
- `[ERROR]`: Critical failures (Playwright errors, database issues)

## Event Times
- All events start at **10:00 PM UTC** (22:00 UTC)
- All events end at **9:59 PM UTC** (21:59 UTC)

## Database Schema

### events table
```sql
id              INTEGER PRIMARY KEY
user_id         TEXT
title           TEXT
start_date      TEXT (timestamp)
end_date        TEXT (timestamp)
image           TEXT (URL or filepath)
category        TEXT (Banner/Event/Offer)
profile         TEXT (always "UMA")
description     TEXT (race details, etc.)
```

### event_messages table
```sql
event_id        INTEGER
channel_id      TEXT
message_id      TEXT
PRIMARY KEY (event_id, channel_id)
```

## Performance Notes
- Timeline scraping takes **2-3 minutes** (scrolls through entire timeline)
- Runs headless (no GUI) on Raspberry Pi
- Network timeout: 60 seconds
- Maximum scrolls: 60 (stops when no new dates found for 5 consecutive scrolls)
