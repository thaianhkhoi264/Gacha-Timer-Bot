# CRITICAL FIX: Enable Presence Intent

## Problem
Bot detects all users as "offline" even when they're online, causing reminders to always be skipped.

## Root Cause
Missing **Presence Intent** - Discord doesn't send user status updates without this privileged intent.

## Solution

### Step 1: Enable Intent in Discord Developer Portal

1. Go to https://discord.com/developers/applications
2. Select your bot application (Kanami)
3. Click on "Bot" in the left sidebar
4. Scroll down to "Privileged Gateway Intents"
5. Find "PRESENCE INTENT" 
6. **Toggle it ON** (should turn green)
7. Click "Save Changes" at the bottom

### Step 2: Restart the Bot

**On Raspberry Pi**:
```bash
sudo systemctl restart kanami-bot
```

**Or locally**:
```bash
# Stop the bot (Ctrl+C)
# Start it again
python main.py
```

### Step 3: Verify Fix

Run the diagnostic command:
```
Kanami check_naito_status
```

**Expected Output (FIXED)**:
```
Bot Intents:
Members Intent: ✅ Enabled
Presences Intent: ✅ Enabled  <-- Should now show ENABLED
Guilds Intent: ✅ Enabled

Status: 🟢 ONLINE  <-- Should show actual status
```

**Before Fix (BROKEN)**:
```
Bot Intents:
Members Intent: ✅ Enabled
Presences Intent: ⚠️ DISABLED - Status will always show offline!
Guilds Intent: ✅ Enabled

Status: ⚫ OFFLINE  <-- Always offline when intent disabled
```

## Why This Happened

Discord has three "Privileged Gateway Intents" that require explicit enabling:
1. **Server Members Intent** - See guild members (already enabled)
2. **Presence Intent** - See user online/offline/idle/dnd status (**was missing**)
3. **Message Content Intent** - Read message content (already enabled)

Without Presence Intent:
- Bot can see who is in a server
- Bot **cannot** see if they're online/offline/idle/dnd
- All users default to showing as "offline"
- Reminder system skips everyone (thinks they're offline)

## What Was Changed in Code

**bot.py** - Added one line:
```python
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True  # ← NEW: Required to see statuses
```

**reminder_module.py** - Enhanced diagnostics:
- `!check_naito_status` now shows which intents are enabled
- Warns if Presences Intent is disabled
- Shows detailed guild membership info

## Verification Checklist

After restarting the bot, verify:

- [ ] Bot starts without errors
- [ ] `Kanami check_naito_status` shows "Presences Intent: ✅ Enabled"
- [ ] Status shows actual user status (🟢 Online / 🟡 Idle / ⚫ Offline / 🔴 DND)
- [ ] Status matches what you see in Discord
- [ ] Test `Kanami force_remind` when user is online

## If Bot Fails to Start

**Error**: "Privileged intent provided is not enabled or whitelisted"

**Solution**: You forgot Step 1! Enable "PRESENCE INTENT" in Discord Developer Portal.

## Additional Notes

- This intent is **required** for the reminder system to work correctly
- Without it, reminders will always be skipped (user appears offline)
- The intent must be enabled BOTH in code AND in Discord Developer Portal
- If your bot is in 100+ servers, Discord may require verification to use this intent
- For personal/small bots, just toggle it on - no verification needed

## Testing After Fix

1. **Check status when user is online**:
   ```
   Kanami check_naito_status
   ```
   Should show: 🟢 ONLINE

2. **Check status when user is idle**:
   (User inactive for 5+ minutes)
   ```
   Kanami check_naito_status
   ```
   Should show: 🟡 IDLE/AWAY

3. **Check status when user is DND**:
   (User manually sets DND)
   ```
   Kanami check_naito_status
   ```
   Should show: 🔴 DO NOT DISTURB

4. **Try force reminder**:
   ```
   Kanami force_remind
   ```
   Should work when user is online, block otherwise

## Related Issues

If status still shows as offline after fix:
1. Verify intent is enabled in Developer Portal
2. Verify bot restarted after code change
3. Check user isn't using "Invisible" status (appears offline intentionally)
4. Check bot and user share at least one server
5. Run `Kanami check_naito_status` to see detailed diagnostics
