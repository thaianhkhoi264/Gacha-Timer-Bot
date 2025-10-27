# Reminder Commands Guide

## Status & Debug Commands

### Check Naito's Status
**Command**: `!check_naito_status`

Shows detailed information about Naito's current Discord status with debug information.

**Output includes**:
- Current status (Online/Idle/Offline/DND)
- What action the reminder system would take
- Number of guilds checked
- Raw status value for debugging

**Example Output**:
```
**Naito's Discord Status:**
🟢 Status: `ONLINE`
📊 Details: User is online and available
🎯 Action: ✅ Reminder would be **SENT** with follow-ups

Raw Status Value: `Status.online`
User ID: `443416461457883136`
Guilds Checked: `1`
```

**Use Cases**:
- 🔍 Debug why reminder was skipped
- ✅ Verify bot can see Naito in guilds
- 📊 Check status before forcing reminder
- 🐛 Troubleshoot status detection issues

---

## Manual Reminder Commands

### Force Reminder (Online Only)
**Command**: `!force_remind`

**⚠️ SAFETY FIRST**: Forces a reminder, but **ONLY if Naito is ONLINE**.

**How it works**:
1. Checks Naito's current status
2. Blocks if user is NOT online
3. Proceeds only if status is `ONLINE`
4. Uses current configuration settings
5. Shows "(MANUALLY TRIGGERED)" in notifications

**Status Handling**:
- ✅ **ONLINE** → Reminder sent with follow-ups (based on config)
- ❌ **IDLE/AWAY** → Blocked (respects user being away)
- ❌ **OFFLINE** → Blocked (user not available)
- ❌ **DND** → Blocked (respects do not disturb)
- ❌ **NOT FOUND** → Blocked (user not in servers)

**Example Success**:
```
> !force_remind
Checking Naito's status before forcing reminder... 🔍
✅ Naito is ONLINE! Forcing reminder process... 😠
✅ Force reminder completed successfully! Naito has been reminded.
```

**Example Blocked (Idle)**:
```
> !force_remind
Checking Naito's status before forcing reminder... 🔍
❌ Cannot force reminder: Naito is currently **IDLE/AWAY**, not ONLINE.
Use `!check_naito_status` to see current status.
```

**Example Blocked (DND)**:
```
> !force_remind
Checking Naito's status before forcing reminder... 🔍
❌ Cannot force reminder: Naito is currently **DND**, not ONLINE.
Use `!check_naito_status` to see current status.
```

---

### Trigger Reminder (Any Status)
**Command**: `!remind_naito`

Triggers the reminder process immediately, following normal status rules.

**Behavior**:
- Checks status like scheduled reminder
- Follows same logic as 7 PM EST reminder
- ONLINE → Send with follow-ups
- IDLE/AWAY → Skip
- OFFLINE → Skip
- DND → Single message only

**Difference from `!force_remind`**:
- `!remind_naito` → Respects all status logic (may skip)
- `!force_remind` → Only proceeds if ONLINE (guaranteed send or blocked)

**Example**:
```
> !remind_naito
Starting manual reminder process for Naito... 😠
Manual reminder process completed successfully!
```

---

## Configuration Commands

### View Current Settings
**Command**: `!reminder_config status`

Shows all current configuration values.

**Output**:
```
**Current Reminder Settings:**
📊 Interval: `5 minutes` (300 seconds)
⏱️ Duration: `30 minutes` (1800 seconds)
📨 Follow-up Messages: `ENABLED`
🔢 Max Reminders per cycle: `6`
🎲 Random spam chance (when off): `5%` (every 5s for 30s)
```

---

### Change Reminder Interval
**Command**: `!reminder_config interval <minutes>`

Sets time between follow-up messages.

**Examples**:
```
!reminder_config interval 5    # Every 5 minutes (default)
!reminder_config interval 2    # Every 2 minutes (aggressive)
!reminder_config interval 10   # Every 10 minutes (gentle)
```

---

### Change Reminder Duration
**Command**: `!reminder_config duration <minutes>`

Sets total time the reminder loop runs.

**Examples**:
```
!reminder_config duration 30   # 30 minutes total (default)
!reminder_config duration 60   # 1 hour total
!reminder_config duration 15   # 15 minutes total
```

**Note**: Max reminders = duration ÷ interval

---

### Toggle Follow-up Messages
**Command**: `!reminder_config followup <on/off>`

**Enable** (Normal Mode):
```
!reminder_config followup on
```
- Sends initial message
- Sends follow-ups at configured interval
- Stops when user responds or duration expires

**Disable** (Silent Mode with 5% Spam Chance):
```
!reminder_config followup off
```
- Sends ONLY initial message (if online)
- **5% chance** to activate "random spam mode"
- Spam mode: 6 messages every 5 seconds for 30 seconds
- Owner gets notified when spam activates

---

## Workflow Examples

### Debugging Why Reminder Was Skipped

1. **Check the status**:
```
!check_naito_status
```

2. **If status shows OFFLINE but user is online**:
   - Bot might not be in the right server
   - User might have "Show as offline" enabled
   - Bot lacks proper intents (unlikely if it worked before)

3. **If status shows IDLE**:
   - This is correct behavior - idle means away
   - Reminder is skipped to respect user being away

4. **If status shows ONLINE**:
   - Reminder should have been sent
   - Check bot logs for errors
   - Try `!force_remind` to manually trigger

---

### Testing New Configuration

1. **Set test intervals**:
```
!reminder_config interval 1
!reminder_config duration 3
```

2. **Check status first**:
```
!check_naito_status
```

3. **Force if online, or use remind_naito**:
```
!force_remind        # Only if ONLINE
# OR
!remind_naito        # Follows all status rules
```

4. **Reset to default after testing**:
```
!reminder_config interval 5
!reminder_config duration 30
```

---

### Emergency Reminder (When User Is Online)

If you need to send a reminder RIGHT NOW and user is confirmed online:

```
!check_naito_status   # Verify status first
!force_remind         # Force send if online
```

This ensures:
- ✅ User is actually online
- ✅ Reminder will definitely be sent
- ❌ Won't spam if user is idle/away/offline

---

## Status Behavior Matrix

| User Status | `!remind_naito` | `!force_remind` | Scheduled (7PM) |
|-------------|-----------------|-----------------|-----------------|
| 🟢 **Online** | ✅ Send with follow-ups | ✅ Send with follow-ups | ✅ Send with follow-ups |
| 🟡 **Idle/Away** | ❌ Skip (user away) | ❌ Blocked | ❌ Skip (user away) |
| ⚫ **Offline** | ❌ Skip (not available) | ❌ Blocked | ❌ Skip (not available) |
| 🔴 **DND** | ⚠️ Single message only | ❌ Blocked | ⚠️ Single message only |
| ❓ **Not Found** | ❌ Skip (error) | ❌ Blocked | ❌ Skip (error) |

**Key Difference**:
- `!remind_naito` follows normal logic (respects DND with single message)
- `!force_remind` ONLY proceeds if ONLINE (blocks all other statuses)

---

## Troubleshooting

### "Naito is ONLINE but reminder was skipped"

**Possible causes**:

1. **Bot can't see user**:
```
!check_naito_status   # Shows "NOT FOUND"
```
   - Solution: Make sure bot and user share at least one server
   - Check bot has proper member intents enabled

2. **Status detected as IDLE instead of ONLINE**:
```
!check_naito_status   # Shows "IDLE/AWAY"
```
   - This is correct Discord behavior
   - User has been inactive for a while
   - Solution: User needs to interact with Discord to show as ONLINE

3. **Race condition at 7 PM**:
   - Status changed between check and send
   - Solution: Use `!force_remind` to retry

4. **Configuration issue**:
```
!reminder_config status   # Check settings
```
   - Follow-up might be disabled
   - Check logs for errors

### "Force remind says user not ONLINE"

If `!check_naito_status` shows ONLINE but `!force_remind` says not online:
- There's a timing issue
- Status changed between commands
- Run `!check_naito_status` again to confirm

Solution: Run status check immediately before force remind

### "Bot says user not found in servers"

Debug steps:
1. Check bot is in server with user
2. Check bot has "Server Members Intent" enabled
3. Check user hasn't blocked the bot
4. Restart bot to refresh guild cache

---

## Command Summary

| Command | Purpose | Owner Only |
|---------|---------|------------|
| `!check_naito_status` | Check current status with debug info | ✅ |
| `!force_remind` | Force reminder (ONLINE only) | ✅ |
| `!remind_naito` | Manual trigger (follows status rules) | ✅ |
| `!reminder_config status` | View configuration | ✅ |
| `!reminder_config interval <min>` | Set interval | ✅ |
| `!reminder_config duration <min>` | Set duration | ✅ |
| `!reminder_config followup <on/off>` | Toggle follow-ups | ✅ |

All commands are owner-only for security.
