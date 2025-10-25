# Reminder Configuration Guide

## Quick Reference

### View Current Settings
```
!reminder_config status
```
Shows:
- Current interval (minutes/seconds)
- Current duration (minutes/seconds)
- Follow-up status (ENABLED/DISABLED)
- Max reminders per cycle
- Random spam chance info

---

## Configuration Commands

### 1. Change Reminder Interval
**Command**: `!reminder_config interval <minutes>`

Controls how often follow-up messages are sent.

**Examples**:
```
!reminder_config interval 5    # Every 5 minutes (default)
!reminder_config interval 2    # Every 2 minutes (more aggressive)
!reminder_config interval 10   # Every 10 minutes (less frequent)
!reminder_config interval 1    # Every 1 minute (testing)
```

---

### 2. Change Reminder Duration
**Command**: `!reminder_config duration <minutes>`

Controls total time the reminder loop runs.

**Examples**:
```
!reminder_config duration 30   # 30 minutes total (default)
!reminder_config duration 60   # 1 hour total
!reminder_config duration 15   # 15 minutes total
!reminder_config duration 5    # 5 minutes total (testing)
```

**Note**: Max reminders = duration ÷ interval
- 30min duration, 5min interval = 6 reminders
- 30min duration, 2min interval = 15 reminders
- 60min duration, 10min interval = 6 reminders

---

### 3. Toggle Follow-up Messages
**Command**: `!reminder_config followup <on/off>`

**Enable** (Normal Mode):
```
!reminder_config followup on
!reminder_config followup enabled
!reminder_config followup yes
```
- Sends initial message
- Sends follow-ups at configured interval
- Stops when user responds or duration expires

**Disable** (Silent Mode with Random Spam):
```
!reminder_config followup off
!reminder_config followup disabled
!reminder_config followup no
```
- Sends ONLY initial message
- **5% chance** to activate "random spam mode"
- Spam mode: 6 messages every 5 seconds for 30 seconds
- Owner gets notified when spam activates

---

## Manual Trigger Command

### Trigger Reminder Immediately
**Command**: `!remind_naito`

- Starts reminder process right now (ignores schedule)
- Uses current configuration settings
- Doesn't affect 7 PM EST daily schedule
- Owner only
- Shows "(MANUALLY TRIGGERED)" in notifications

**Use Cases**:
- Testing new settings
- Manual reminder during the day
- Force reminder outside schedule

---

## Preset Configurations

### Testing Configuration
Quick test with short intervals:
```
!reminder_config interval 1
!reminder_config duration 5
!remind_naito
```
Result: 5 reminders over 5 minutes (1 every minute)

### Gentle Configuration
Less aggressive reminders:
```
!reminder_config interval 10
!reminder_config duration 30
```
Result: 3 reminders over 30 minutes (1 every 10 minutes)

### Aggressive Configuration
Maximum nagging:
```
!reminder_config interval 2
!reminder_config duration 60
```
Result: 30 reminders over 60 minutes (1 every 2 minutes)

### Default Configuration
Reset to original settings:
```
!reminder_config interval 5
!reminder_config duration 30
!reminder_config followup on
```
Result: 6 reminders over 30 minutes (1 every 5 minutes)

### Silent Mode (Surprise Spam)
Only initial message + 5% spam chance:
```
!reminder_config followup off
```
Result: 1 initial message, then:
- 95% chance: Nothing else
- 5% chance: 6 messages in 30 seconds

---

## How It Works

### Normal Flow (Follow-up ENABLED)
1. Check user status at 7 PM EST
2. If online/idle:
   - Send initial message
   - Wait for interval (e.g., 5 minutes)
   - Check if user went offline (stop if yes)
   - Check if user responded (stop if yes)
   - Send random follow-up message
   - Repeat until duration expires or user responds
3. If DND: Send 1 message only
4. If offline: Skip entirely

### Silent Flow (Follow-up DISABLED)
1. Check user status at 7 PM EST
2. If online/idle:
   - Send initial message
   - Roll 5% dice
   - If spam activated:
     - Send 6 messages every 5 seconds
     - Notify owner
   - If spam not activated:
     - Done (only initial message)
3. If DND: Send 1 message only
4. If offline: Skip entirely

### Manual Trigger (!remind_naito)
- Ignores time of day
- Uses current settings
- Follows same status logic
- Shows "(MANUALLY TRIGGERED)" tag

---

## Status Behavior

| User Status | Behavior |
|-------------|----------|
| Online | Full reminder loop |
| Idle/Away | Full reminder loop |
| DND | Single message only |
| Offline | Skip completely |
| Goes offline mid-loop | Stop immediately |

---

## Examples with Output

### Example 1: Check Status
```
> !reminder_config status

**Current Reminder Settings:**
📊 Interval: `5 minutes` (300 seconds)
⏱️ Duration: `30 minutes` (1800 seconds)
📨 Follow-up Messages: `ENABLED`
🔢 Max Reminders per cycle: `6`
🎲 Random spam chance (when off): `5%` (every 5s for 30s)
```

### Example 2: Change Settings
```
> !reminder_config interval 3
✅ Reminder interval changed from `5 minutes` to `3 minutes`

> !reminder_config duration 15
✅ Reminder duration changed from `30 minutes` to `15 minutes` (max 5 reminders)

> !reminder_config status
**Current Reminder Settings:**
📊 Interval: `3 minutes` (180 seconds)
⏱️ Duration: `15 minutes` (900 seconds)
📨 Follow-up Messages: `ENABLED`
🔢 Max Reminders per cycle: `5`
🎲 Random spam chance (when off): `5%` (every 5s for 30s)
```

### Example 3: Disable Follow-ups
```
> !reminder_config followup off
✅ Follow-up messages **DISABLED**. Only initial message will be sent (with 5% chance of random spam mode).

> !remind_naito
Starting manual reminder process for Naito... <:KanamiAnger:1406653154111524924>

[Owner receives either:]
- "Reminder sent (follow-ups disabled, no spam triggered)"
OR (5% chance)
- "🎲 Random spam mode activated for this reminder! (5% chance)"
- [6 messages sent rapidly]
- "Random spam mode completed - sent 6 messages in 30 seconds!"
```

---

## Notes

- All commands are owner-only
- Settings persist until bot restart
- Settings apply to both scheduled and manual reminders
- Random spam mode only triggers when follow-ups are disabled
- Manual trigger doesn't affect 7 PM EST schedule
- Settings show in both minutes and seconds for clarity
