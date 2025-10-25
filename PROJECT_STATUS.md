# Gacha Timer Bot - Project Status & Context

**Last Updated**: October 25, 2025  
**Current Phase**: Bug Fixes and Maintenance

## Project Overview
Kanami (the Discord bot) is a multi-game event tracking and notification system. The bot monitors gacha game events, sends reminders, and provides a control panel interface for managing timers.

## Recent Major Updates

### 1. Reminder Module Configuration System (Completed - October 25, 2025)
**New Features**: Added configurable reminder settings and random spam mode

**Configuration Commands**:
- `!reminder_config status` - Show current settings
- `!reminder_config interval <minutes>` - Set reminder interval (default: 5 minutes)
- `!reminder_config duration <minutes>` - Set total duration (default: 30 minutes)
- `!reminder_config followup <on/off>` - Toggle follow-up messages

**Manual Trigger Command**:
- `!remind_naito` - Owner can manually trigger reminder at any time (doesn't affect scheduling)

**Follow-up Message Modes**:
1. **ENABLED** (default) → Normal behavior with configurable interval/duration
2. **DISABLED** → Only initial message sent, BUT:
   - 5% chance to activate "random spam mode"
   - Spam mode: 6 messages sent every 5 seconds for 30 seconds
   - Owner notified when spam mode activates

**Configuration Variables** (now runtime-adjustable):
- `REMINDER_INTERVAL` - Time between follow-up messages (default: 300 seconds / 5 minutes)
- `REMINDER_DURATION` - Total reminder cycle length (default: 1800 seconds / 30 minutes)
- `FOLLOW_UP_ENABLED` - Toggle follow-up messages on/off (default: True)

**Use Cases**:
- Quick test: `!reminder_config interval 1 duration 5` (5 reminders in 5 minutes)
- Gentle mode: `!reminder_config interval 10 duration 30` (3 reminders in 30 minutes)
- Aggressive mode: `!reminder_config interval 2 duration 30` (15 reminders in 30 minutes)
- Silent mode: `!reminder_config followup off` (only initial message + 5% spam chance)

**Files Modified**:
- `reminder_module.py` - Added global config variables, `reminder_config` command, random spam logic

---

### 2. Reminder Module Status Check (Completed - October 24, 2025)
**Problem**: Daily reminder logic needed to be adjusted based on user's actual availability and needs.

**New Behavior**:
- ✅ **ONLINE/IDLE** → Send reminder + full 30-minute follow-up loop with randomized messages
- ✅ **DND (Do Not Disturb)** → Send ONE reminder only (no follow-ups, respecting DND status)
- ✅ **OFFLINE** → Skip reminder completely (user can't respond anyway, no point sending)
- ✅ **Offline during loop** → Stop sending follow-ups if user goes offline mid-reminder cycle
- ✅ **Randomized follow-ups** → 15 different reminder messages, randomly selected each time

**Rationale**:
- Online/Idle = User is at computer but not responding → persistent reminders appropriate
- DND = User is busy/focused → single reminder respects their status
- Offline = User away from computer → no point in sending (they can't respond)
- Mid-loop offline check = If user goes offline, they're likely going to sleep → stop nagging

**Implementation Details**:
- `get_user_status()` function returns actual Discord status enum
- Decision tree based on `discord.Status.online`, `.idle`, `.dnd`, `.offline`
- Follow-up messages use `random.choice(FOLLOW_UP_MESSAGES)` for variety
- Added status check during reminder loop to detect offline transition
- Owner gets detailed notifications about status and reminder decisions

**Follow-up Messages** (15 variations):
1. "Kanami is reminding you again! Go to sleep now!"
2. "Are you still awake?! Little boy needs his sleep!"
3. "Gweheh~ Kanami won't stop until you go to bed!"
4. "Sleep time is NOW! Don't make Kanami angrier!"
5. "Naito! Bed! NOW! Kanami is getting impatient!"
6. "Why are you still awake?! Kanami demands you sleep!"
7. "Little boy... Kanami is watching you... Go to sleep!"
8. "This is your health we're talking about! Sleep!"
9. "Kanami will keep pestering you until you rest!"
10. "GO TO SLEEP! Kanami is not joking around!"
11. "Sleep deprived Naito makes Kanami sad... and angry!"
12. "Your bed is calling! Answer it! Now!"
13. "Kanami's patience is running thin... SLEEP!"
14. "Do you want Kanami to keep nagging? Sleep already!"
15. "Little boy needs rest! Kanami insists!"

**Files Modified**:
- `reminder_module.py`: Complete rewrite of status checking logic and added randomized messages

**Status**: ✅ Completed and ready for testing

### 1.1 Git Ignore Update (Completed - October 22, 2025)
**Problem**: `data/hsr_scraper/latest.html` was causing git merge conflicts on Raspberry Pi.

**Solution**:
- Added `data/hsr_scraper/latest.html` to `.gitignore`
- Prevents bot's dynamic HTML file from being tracked

**Files Modified**:
- `.gitignore`: Added scraped HTML file to ignore list

**Status**: ✅ Completed

### 1. Arknights Listener Channel Fix (Completed - October 15, 2025)
**Problem**: Arknights listener was monitoring ALL game listener channels (HSR, ZZZ, STRI, WUWA) instead of just the AK channel.

**Root Cause**: 
- `arknights_on_message()` was checking `if message.channel.id not in LISTENER_CHANNELS.values()`
- This checked against ALL channel IDs in the dictionary, not just the AK channel

**Solution**:
- Changed to `if message.channel.id != LISTENER_CHANNELS.get("AK")`
- Now only processes messages from the specific AK listener channel

**Files Modified**:
- `arknights_module.py`: Fixed channel check in `arknights_on_message()`

**Status**: ✅ Fixed and tested

### 1.1 HSR Scraper Commands Debug Logging (In Progress - October 15, 2025)
**Problem**: Commands `!hsr_scrape_and_save` and `!dump_hsr_prydwen_db` not responding when called on Discord.

**Investigation Steps**:
1. ✅ Verified commands exist in `hsr_scraper.py`
2. ✅ Verified `hsr_scraper` is imported in `main.py` (line 7)
3. ✅ Verified all required functions exist
4. ✅ Added debug logging to track command registration

**Changes Made**:
- Added logging message when command registration begins
- Added success message when commands register successfully  
- Split exception handling to catch ImportError vs other exceptions separately
- Added `exc_info=True` to log full traceback if registration fails

**Next Steps**:
- Restart bot to see debug messages in logs
- Check if commands show up in `!help` or bot command list
- Verify administrator permissions are set correctly

**Files Modified**:
- `hsr_scraper.py`: Added debug logging for command registration

### 2. HSR Scraper Database Integration (Completed - October 14, 2025)
**Goal**: Store scraped Prydwen data in a dedicated database for later use in event creation.

**Implementation**:
- ✅ **Database Schema**: Created `hsr_prydwen_data.db` in `data/` directory
- ✅ **Event Mapping**: Maps Prydwen event types to bot categories (Banner/Event/Maintenance)
- ✅ **Save Function**: `save_events_to_db()` stores/updates scraped events
- ✅ **Database Commands**: Added `!hsr_scrape_and_save` and `!dump_hsr_prydwen_db`

**Database Structure**:
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL,          -- Banner/Event/Maintenance (for bot logic)
    type TEXT NOT NULL,               -- character_banner, memory_of_chaos, etc.
    start_date TEXT,
    end_date TEXT,
    time_remaining TEXT,
    description TEXT,
    image TEXT,                       -- Reserved for future image scraping
    css_class TEXT,
    scraped_at TEXT NOT NULL,
    UNIQUE(title, type, start_date)
)
```

**Event Type Mapping**:
| Prydwen Type | Bot Category |
|--------------|--------------|
| character_banner, light_cone_banner | Banner |
| memory_of_chaos, pure_fiction, apocalyptic_shadow | Event |
| planar_fissure, relic_event, battle_pass | Event |
| maintenance | Maintenance |

**New Commands**:
- `!hsr_scrape_and_save`: Scrapes Prydwen and saves to database
- `!dump_hsr_prydwen_db`: Shows all events in database (with detailed text file)

**Files Modified**:
- `hsr_scraper.py`: Added database functions, Discord commands

**Next Steps**:
- [ ] Integrate database with hsr_module.py for automatic event creation
- [ ] Add image scraping from Prydwen
- [ ] Implement automatic daily scraping task

### 2. Control Panel Bug Fixes (Completed - October 14, 2025)
**Problems Fixed**:
- ✅ **Message Duplication**: Control panel now cleans up old messages on restart
- ✅ **Event Names**: Remove confirmation shows event name instead of ID
- ✅ **Ghost Notifications**: Added cleanup for notifications without events
- ✅ **Missing Notifications**: Added validation to re-schedule missing notifications
- ✅ **Edit Interaction Failure**: Fixed timezone/category select causing "This interaction failed"

**Implementation**:
- `cleanup_old_control_panel_messages()`: Deletes untracked messages on startup
- `cleanup_ghost_notifications()`: Removes notifications for deleted events
- `validate_event_notifications()`: Ensures all events have proper notifications
- Fixed dropdown selects to use `edit_message()` instead of `defer()`
- Added `!cleanup_notifications` command for manual maintenance

**Files Modified**:
- `control_panel.py`: Message cleanup, event name display, interaction fixes
- `notification_handler.py`: Ghost cleanup, validation functions
- `main.py`: Integrated cleanup on bot startup

### 3. Control Panel UX Improvements (Completed)

**Solutions Implemented**:
- ✅ **Timezone in Modal**: Added timezone display in AddEventModal labels (e.g., "Start Date (YYYY-MM-DD HH:MM in UTC-7)")
- ✅ **Image URL Field**: Added `image_input` TextInput to both AddEventModal and EditEventModal
- ✅ **Message Editing**: Replaced delete/recreate pattern with edit-in-place using `CONTROL_PANEL_MESSAGE_IDS` dictionary to avoid rate limits
- ✅ **Auto-Update**: Added control panel update calls to:
  - `add_ak_event()` - after event addition
  - `arknights_update_timers()` - when events deleted
  - `ak_remove()` - after removal
  - `ak_edit()` - after edit

**Files Modified**:
- `control_panel.py`: Added timezone labels, image fields, message editing system, dropdown selects
- `arknights_module.py`: Added 4 control panel update trigger points

### 4. HSR Scraper Creation (Completed)
**Goal**: Automatically scrape Honkai Star Rail event data from https://www.prydwen.gg/star-rail/

**Implementation**:
- Created `hsr_scraper.py` using Playwright (handles JavaScript-rendered content)
- Targets the "Event Timeline" section below "Active Codes"
- Successfully extracts 14 events with full metadata

**Technical Details**:
- **Website Type**: Gatsby/React SPA with dynamic content loading
- **HTML Size**: ~3.5MB fully rendered
- **Scraping Method**: Playwright with Chromium browser
- **Event Structure**: Bootstrap accordion components with collapse functionality
- **Data Extraction**: Regex-based parsing of accordion items

**Event Data Extracted**:
```python
{
    "name": str,              # Event name
    "type": str,              # Event category (character_banner, memory_of_chaos, etc.)
    "css_class": str,         # CSS identifier from website
    "time_remaining": str,    # Time until end (e.g., "1d 6h")
    "start_date": str,        # YYYY-MM-DD HH:MM:SS or "After VX.X update"
    "end_date": str,          # YYYY-MM-DD HH:MM:SS
    "description": str        # Event description (truncated to 300 chars)
}
```

**Event Types Recognized**:
- `character_banner` - Limited character warps
- `memory_of_chaos` - Memory of Chaos cycles
- `pure_fiction` - Pure Fiction challenges
- `apocalyptic_shadow` - Apocalyptic Shadow challenges
- `planar_fissure` - Double Planar Ornament rewards
- `battle_pass` - Nameless Honor
- `login_event` - Gift of Odyssey
- `relic_event` - Realm of the Strange
- `other_event` - Miscellaneous events

**Current Live Events** (as of Oct 14, 2025):
- 4 character banners (Evil March Can't Hurt You, Re:Mahou Shoujo, Half Dan/Half Dragon, Anaxa Unchained)
- 2 Memory of Chaos cycles (3.5 and 3.6)
- 1 Pure Fiction (3.6)
- 1 Apocalyptic Shadow (3.6)
- 2 farming events (Planar Fissure, Realm of the Strange)
- Battle pass and login rewards

## Core Architecture

### Bot Structure
```
main.py                  # Entry point, initializes bot
bot.py                   # Discord bot setup, cog loading
modules.py               # Combined module with commands
database_handler.py      # SQLite database operations
notification_handler.py  # Notification scheduling and sending
control_panel.py         # Discord UI (Views, Modals, Buttons)
utilities.py             # Helper functions
global_config.py         # Configuration and constants
```

### Game-Specific Modules
```
arknights_module.py      # Arknights event tracking
hsr_module.py            # Honkai Star Rail tracking
hsr_scraper.py           # HSR web scraper (NEW)
hoyo_module.py           # General HoYo games
shadowverse_handler.py   # Shadowverse tracking
uma_handler.py           # Uma Musume tracking
```

### Data Flow
1. **Manual Entry**: Control panel → Database → Notifications
2. **Automated (Planned)**: Scraper → Parser → Database → Notifications
3. **Updates**: Database changes → Control panel refresh → User notifications

## Database Schema

### Events Table
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    channel_id INTEGER,
    event_name TEXT,
    start_time TEXT,
    end_time TEXT,
    game TEXT,
    image_url TEXT,
    event_type TEXT
)
```

### Notifications Table
```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    event_id INTEGER,
    notification_time TEXT,
    notified INTEGER DEFAULT 0,
    FOREIGN KEY(event_id) REFERENCES events(id)
)
```

## Key Features

### Control Panel System
- **Location**: `control_panel.py`
- **Components**:
  - `ControlPanel` (View): Main interface with event list and buttons
  - `AddEventModal`: Modal for adding new events (with timezone label, image URL)
  - `EditEventModal`: Modal for editing existing events (with image URL)
  - `update_control_panel_messages()`: Edits existing messages instead of recreating
  - `CONTROL_PANEL_MESSAGE_IDS`: Tracks message IDs for editing

### Notification System
- **Location**: `notification_handler.py`
- **Features**:
  - Background task checks every 60 seconds
  - Sends DM notifications at scheduled times
  - Marks notifications as sent to avoid duplicates
  - Auto-deletes past events

### HSR Scraper System
- **Location**: `hsr_scraper.py`
- **Key Functions**:
  - `scrape_prydwen(save_html, headless)`: Main scraping function
  - `scrape_and_extract_events(html)`: Extracts events from HTML
  - `get_latest_saved_html()`: Loads cached HTML
  - `analyze_html_structure(html)`: Debug/analysis helper

**Usage Example**:
```python
from hsr_scraper import scrape_prydwen, scrape_and_extract_events

# Scrape website
html = scrape_prydwen(save_html=True, headless=True)

# Extract events
events = scrape_and_extract_events(html)

# Filter for banners
banners = [e for e in events if e['type'] == 'character_banner']
```

## File Organization

### Essential Core Files (DO NOT DELETE)
```
bot.py                   # Bot initialization
main.py                  # Entry point
modules.py               # Command handlers
database_handler.py      # Database operations
notification_handler.py  # Notification system
control_panel.py         # UI components
utilities.py             # Helper functions
global_config.py         # Configuration
```

### Game Module Files (DO NOT DELETE)
```
arknights_module.py      # Arknights functionality
hsr_module.py            # HSR functionality
hsr_scraper.py           # HSR web scraper
hoyo_module.py           # HoYo games
shadowverse_handler.py   # Shadowverse
uma_handler.py           # Uma Musume
twitter_handler.py       # Twitter integration
tweet_listener.py        # Twitter listener
ml_handler.py            # Machine learning (future)
reminder_module.py       # Reminder functionality
update_database.py       # Database maintenance
```

### Data Files (Keep)
```
kanami_data.db           # Main database
data/hsr_scraper/latest.html  # Latest scraped HTML (for cache)
requirements.txt         # Python dependencies
event_image_map.json     # Event image mappings
```

### Documentation (Keep)
```
README.md                # Main project documentation
PROJECT_STATUS.md        # This file - project context
```

### Analysis/Debug Files (SAFE TO DELETE)
```
analyze_html.py          # HTML analysis script (debug)
extract_event_timeline.py # Event extraction test (debug)
extract_events.py        # Event extraction test (debug)
find_content_structure.py # Structure analysis (debug)
parse_event_timeline.py  # Parser test script (debug)
search_visible_data.py   # Data search script (debug)
event_timeline_context.html # HTML snippet (debug)
parsed_events.json       # Test output (debug)
PRYDWEN_ANALYSIS.md      # Analysis notes (debug)
HSR_SCRAPER_README.md    # Duplicate docs (debug)
HSR_SCRAPER_USAGE.md     # Duplicate docs (debug)
uma_timeline.html        # Old test file (debug)
data/hsr_scraper/prydwen_starrail_*.html # Old snapshots (keep only latest.html)
```

## Integration Guide: HSR Scraper → HSR Module

### Step 1: Import Scraper in hsr_module.py
```python
from hsr_scraper import scrape_prydwen, scrape_and_extract_events
import asyncio
```

### Step 2: Create Update Function
```python
async def update_hsr_events_from_web(guild_id, channel_id):
    """Fetch latest HSR events from Prydwen and add to database"""
    
    # Run scraper in thread pool (Playwright is sync)
    loop = asyncio.get_event_loop()
    html = await loop.run_in_executor(None, scrape_prydwen, True, True)
    
    if not html:
        logger.error("Failed to scrape Prydwen")
        return []
    
    # Extract events
    all_events = scrape_and_extract_events(html)
    
    # Filter for relevant event types
    relevant_types = ['character_banner', 'memory_of_chaos', 'pure_fiction', 'apocalyptic_shadow']
    events = [e for e in all_events if e['type'] in relevant_types]
    
    # Add to database
    added_events = []
    for event in events:
        if 'start_date' in event and 'end_date' in event:
            try:
                # Parse dates and add to database
                start = datetime.strptime(event['start_date'], '%Y-%m-%d %H:%M:%S')
                end = datetime.strptime(event['end_date'], '%Y-%m-%d %H:%M:%S')
                
                # Check if event already exists
                existing = await db.get_event_by_name(event['name'], guild_id)
                if not existing:
                    await db.add_event(
                        guild_id=guild_id,
                        channel_id=channel_id,
                        event_name=event['name'],
                        start_time=start,
                        end_time=end,
                        game='hsr',
                        event_type=event['type']
                    )
                    added_events.append(event['name'])
            except Exception as e:
                logger.error(f"Failed to add event {event['name']}: {e}")
    
    return added_events
```

### Step 3: Add Command
```python
@commands.command()
async def hsr_update(ctx):
    """Update HSR events from Prydwen website"""
    await ctx.send("🔄 Fetching latest events from Prydwen...")
    
    added = await update_hsr_events_from_web(ctx.guild.id, ctx.channel.id)
    
    if added:
        await ctx.send(f"✅ Added {len(added)} new events:\n" + "\n".join(f"- {e}" for e in added))
    else:
        await ctx.send("✅ No new events to add (all up to date)")
```

## Dependencies

### Python Packages
```
discord.py              # Discord API
aiosqlite              # Async SQLite
playwright             # Web scraping
python-dotenv          # Environment variables
tweepy                 # Twitter API (optional)
```

### Installation
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Environment Variables
```env
DISCORD_BOT_TOKEN=your_token_here
TIMEZONE=America/Los_Angeles  # Default timezone
```

## Next Steps (Planned)

1. **Integrate HSR Scraper with hsr_module.py**
   - Add `hsr_update` command to fetch events from Prydwen
   - Implement automatic daily scraping
   - Add event comparison to avoid duplicates

2. **Image URL Extraction**
   - Extract character images from Prydwen
   - Store image URLs in database
   - Display images in Discord embeds

3. **Notification Enhancements**
   - Multiple reminder times (24h, 1h before)
   - Custom reminder messages
   - Role mentions for important events

4. **Control Panel V2**
   - Pagination for large event lists
   - Bulk operations (delete multiple, edit batch)
   - Event filtering (by game, by type)

## Troubleshooting

### Scraper Issues
- **Timeout**: Increase wait time in `scrape_prydwen()` (currently 5s)
- **Empty events**: Website structure may have changed, check HTML
- **Playwright error**: Run `python -m playwright install chromium`

### Control Panel Issues
- **Not updating**: Check if update calls exist in event modification functions
- **Rate limit**: Using message editing instead of delete/recreate should prevent this
- **Missing events**: Verify `CONTROL_PANEL_MESSAGE_IDS` tracking

### Database Issues
- **Lock errors**: Check for long-running transactions
- **Missing events**: Verify database connection and table schema
- **Duplicate notifications**: Check `notified` flag in notifications table

## Development Notes

### Code Style
- Use `logger.info/error/debug` for logging
- Async/await for Discord operations
- Try/except blocks around external API calls
- Type hints where applicable

### Testing
- Test scraper: `python hsr_scraper.py`
- Test bot locally before deploying
- Use test server for control panel changes

### Git Workflow
- Commit frequently with descriptive messages
- Test before pushing to main
- Keep documentation updated with major changes

## Contact & Resources
- Discord.py docs: https://discordpy.readthedocs.io/
- Playwright docs: https://playwright.dev/python/
- Prydwen HSR: https://www.prydwen.gg/star-rail/

---

**For GitHub Copilot**: This document provides full context on the current state of the Gacha Timer Bot project, including recent control panel improvements and the newly implemented HSR scraper. The scraper successfully extracts 14 events from Prydwen's Event Timeline using Playwright. Next step is integration with hsr_module.py for automated event tracking.
