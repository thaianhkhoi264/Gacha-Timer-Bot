# Shadowverse Season System

## Overview

The Shadowverse tracker now supports **seasons** - periods of competitive tracking that can be archived and started fresh. All data from previous seasons is preserved and accessible.

**Current Season**: 3 (default for existing servers)

---

## Commands

### 1. Start a New Season (Admin Only)
**Command**: `Kanami sv_newseason`

**Requirements**: Administrator permissions

**What it does**:
1. Archives all current winrate data to Season X
2. Clears all current winrates
3. Starts Season X+1
4. Posts announcement in Shadowverse channel

**Process**:
```
> Kanami sv_newseason

⚠️ Confirm Season Transition
This will:
• Archive all Season 3 data
• Start Season 4
• Clear all current winrate data

React with ✅ to confirm or ❌ to cancel.

[After confirmation]
✅ Season transition complete!
• Season 3: 1,247 records archived
• Current season: 4
• All winrate trackers reset
Users can view archived data with `Kanami sv_season 3`
```

**Safety Features**:
- Requires explicit confirmation (✅/❌ reaction)
- 30-second timeout for confirmation
- All data is archived before clearing
- Cannot be undone (data is preserved in archives)

---

### 2. View Season Data
**Command**: `Kanami sv_season [season_number] [@user]`

**Examples**:
```
Kanami sv_season              # View your current season data
Kanami sv_season 3            # View your Season 3 data (archived)
Kanami sv_season 4 @Naito     # View Naito's Season 4 data
```

**Features**:
- Shows winrate dashboard for specified season
- Works with both current and archived seasons
- Interactive buttons to view different crafts
- Shows season status (Current/Archived)
- Color-coded: Blue for current, Gray for archived

**Output**:
```
Naito
Swordcraft 🗡️ Win Rate (Season 3 - Archived)
Total: 45W / 23L / Win rate: 66.2% / 🧱: 8
---
Forestcraft 🌲: win: 8 / loss: 3 / Win rate: 72.7% / 🧱: 1
Swordcraft 🗡️: win: 7 / loss: 4 / Win rate: 63.6% / 🧱: 2
...
```

---

### 3. List All Seasons
**Command**: `Kanami sv_seasons`

**Shows**:
- Current season number
- All archived seasons
- How to view each season

**Example Output**:
```
📅 Shadowverse Seasons

Current Season
Season 4 🟢

Archived Seasons (2)
Season 3 - View with `Kanami sv_season 3`
Season 2 - View with `Kanami sv_season 2`

Use 'Kanami sv_newseason' (admin only) to start a new season
```

---

## How It Works

### Data Structure

**Current Data** (Active Season):
- Stored in `winrates` table
- Updated with every match recorded
- Used for live dashboards
- Automatically shows current season number

**Archived Data**:
- Stored in `archived_winrates` table
- Read-only (cannot be modified)
- Preserved forever
- Accessible via `sv_season` command

**Season Configuration**:
- Stored in `season_config` table
- Tracks current season per server
- Defaults to Season 3 for existing servers
- Increments when `sv_newseason` is run

---

## Migration from Current System

**For existing servers**:
1. Current data is treated as **Season 3**
2. No data loss - everything continues working
3. When you run `sv_newseason`, it becomes:
   - Season 3 → Archived
   - Season 4 → Current (fresh start)

**Database Tables Added**:
- `season_config` - Tracks current season per server
- `archived_winrates` - Stores all historical season data

---

## Typical Season Workflow

### End of Season
1. Admin runs `Kanami sv_newseason`
2. Bot asks for confirmation
3. Bot archives all data
4. Bot clears current winrates
5. Bot posts announcement
6. New season begins!

### During Season
- Users record matches normally
- Dashboard shows current season
- Old seasons remain viewable
- No changes to normal workflow

### Viewing History
- Anyone can view archived seasons
- Use `Kanami sv_season 3` to view Season 3
- Use `Kanami sv_seasons` to list all seasons
- Data is preserved permanently

---

## Use Cases

### Competitive Seasons
Match Discord events or game updates:
```
Season 3: Eternal Awakening expansion
Season 4: New expansion release
```

### Monthly Resets
Fresh start every month:
```
Season 3: October 2025
Season 4: November 2025
```

### Special Events
Track specific tournaments or events:
```
Season 3: Regular ranked
Season 4: Tournament prep
Season 5: Back to ranked
```

---

## Examples

### Starting Season 4
```
> Kanami sv_newseason

⚠️ Confirm Season Transition
This will:
• Archive all Season 3 data
• Start Season 4
• Clear all current winrate data

[React ✅]

Archiving current season data...

✅ Season transition complete!
• Season 3: 1,247 records archived
• Current season: 4
• All winrate trackers reset

[In Shadowverse channel]
🎉 Season 3 has ended!
📊 Archived 1,247 winrate records
🆕 Season 4 has started!
```

### Viewing Old Season
```
> Kanami sv_season 3

[Shows dashboard with Season 3 data]
Naito
Swordcraft 🗡️ Win Rate (Season 3 - Archived)
...
```

### Comparing Seasons
```
> Kanami sv_season 3        # Check Season 3 performance
> Kanami sv_season 4        # Check Season 4 performance
```

---

## Technical Details

### Database Schema

**season_config**:
- `server_id` (PRIMARY KEY)
- `current_season` (INTEGER, default 3)

**archived_winrates**:
- `season` (INTEGER)
- `user_id` (TEXT)
- `server_id` (TEXT)
- `played_craft` (TEXT)
- `opponent_craft` (TEXT)
- `wins` (INTEGER)
- `losses` (INTEGER)
- `bricks` (INTEGER)
- PRIMARY KEY: (season, user_id, server_id, played_craft, opponent_craft)

**winrates** (existing, unchanged):
- Continues to store current season data
- Cleared when new season starts
- Data copied to `archived_winrates` before clearing

### Season Archival Process

1. Get current season number
2. Copy all `winrates` records to `archived_winrates` with season tag
3. Delete all `winrates` records for this server
4. Increment season number in `season_config`
5. Announce in Shadowverse channel

### View Season Process

1. Check if season is current or archived
2. If current: Query `winrates` table
3. If archived: Query `archived_winrates` WHERE season = X
4. Generate dashboard with season indicator
5. Color code: Blue = current, Gray = archived

---

## FAQ

**Q: What happens to my current data?**
A: It's preserved as Season 3 and remains viewable forever.

**Q: Can I delete archived seasons?**
A: Not currently - all archived data is permanent. (Could add admin command if needed)

**Q: Can I go back to a previous season?**
A: No, seasons only move forward. Archived seasons are read-only.

**Q: What if I accidentally start a new season?**
A: Data is safely archived, but you can't "undo" it. Current data is lost (but preserved in archive).

**Q: Do streaks carry over seasons?**
A: No, streaks are session-based and independent of seasons.

**Q: Can different servers have different seasons?**
A: Yes! Each server tracks its own season number independently.

**Q: Does this affect the export command?**
A: Yes, exported data will now include both current and archived seasons.

---

## Future Enhancements (Potential)

- Season leaderboards (compare users within a season)
- Season statistics (most played craft, highest winrate, etc.)
- Season themes/names instead of just numbers
- Automatic season transitions on schedule
- Export individual season data
- Delete archived seasons (admin command)
- Season comparisons (your Season 3 vs Season 4 performance)

---

## Changelog

**October 29, 2025**:
- Added season system
- Default current season: 3
- Added `sv_newseason`, `sv_season`, `sv_seasons` commands
- Added `season_config` and `archived_winrates` tables
- Updated dashboard to show season information
- Updated channel instructions to show current season
