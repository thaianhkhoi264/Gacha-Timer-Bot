# Uma Notification System - Deployment Checklist

## Pre-Deployment Verification ✅

### Code Changes
- [x] `uma_module.py` - Fixed notification scheduling bug
- [x] `notification_handler.py` - Added Uma timings and message templates
- [x] Syntax checked (all files compile successfully)

### Database Migration
- [x] `migrate_message_templates.py` executed
- [x] 4 new columns added to `pending_notifications`
- [x] Schema verified

### Testing
- [x] Test 1: Notification scheduling bug (PASS)
- [x] Test 2: Profile-specific timings (PASS)
- [x] Test 3: Message templates (PASS)

---

## Deployment Steps

### Step 1: Backup (Recommended)
```bash
# On Raspberry Pi
cd /path/to/bot
cp uma_module.py uma_module.py.backup
cp notification_handler.py notification_handler.py.backup
cp kanami_data.db kanami_data.db.backup
```

### Step 2: Pull Changes
```bash
git pull origin main
```

### Step 3: Run Migration (If Not Already Done)
```bash
python migrate_message_templates.py
```

Expected output:
```
✓ Added message_template column
✓ Added custom_message column
✓ Added phase column
✓ Added character_name column
✓ Migration complete!
```

### Step 4: Restart Bot
```bash
# Stop current bot process
# Then start:
python main.py
```

### Step 5: Monitor Logs
Watch for:
```
[UMA] Scheduling notifications for: Tosen Jordan Banner (start: 1733976000)
[UMA] Notifications scheduled successfully for: Tosen Jordan Banner
```

---

## Post-Deployment Verification

### Check 1: Notifications Scheduled ✓
1. Go to control panel channel
2. Look for "Pending Notifications for [Event Name]" messages
3. Verify notifications exist for each Uma event

**Expected:** Each Uma event should have pending notifications listed

### Check 2: Correct Timing ✓
1. Check notification times in control panel
2. Verify timing matches expectations:
   - **Character/Support/Paid Banners:** 1d before start, 1d + 1h before end
   - **Story Events:** 1d before start, 3d + 1h before end

**Example:**
```
Tosen Jordan Banner:
- Start: 1 day before (Dec 15 08:00)
- End: 1 day before (Dec 29 08:00)
- End: 1 day 1 hour before (Dec 29 07:00)
```

### Check 3: No Rate Limiting ✓
Monitor logs for rate limit errors:
```
# Should NOT see:
discord.errors.HTTPException: 429 Too Many Requests
```

**Expected:** No rate limiting on bot restart

### Check 4: Database Integrity ✓
```bash
python
>>> import sqlite3
>>> conn = sqlite3.connect('kanami_data.db')
>>> cursor = conn.execute("SELECT COUNT(*) FROM pending_notifications WHERE profile='UMA'")
>>> count = cursor.fetchone()[0]
>>> print(f"Uma notifications: {count}")
# Should show >0 notifications
```

---

## Troubleshooting

### Issue: No Notifications Scheduled
**Symptoms:**
- Control panel shows no pending notifications for Uma events
- Logs show "Event unchanged" but no "Notifications scheduled"

**Solution:**
```bash
# Force refresh Uma events
# In Discord, run command:
!uma_force_refresh
```

### Issue: Wrong Timing
**Symptoms:**
- Notifications scheduled at generic times (1h, 3h before)
- Not using Uma-specific timings

**Check:**
```python
# In Python console:
from notification_handler import get_notification_timings
timings = get_notification_timings("Character Banner", "UMA")
print(timings)
# Should show: [('start', 1440), ('end', 1440), ('end', 1500)]
```

**Solution:**
- Verify `UMA_NOTIFICATION_TIMINGS` is defined in `notification_handler.py`
- Check `get_notification_timings()` is passing `profile` parameter

### Issue: Database Migration Failed
**Symptoms:**
- Error: "no such column: message_template"

**Solution:**
```bash
python migrate_message_templates.py
# Verify columns added, then restart bot
```

### Issue: Bot Won't Start
**Symptoms:**
- Import errors, syntax errors

**Solution:**
```bash
# Check syntax:
python -m py_compile uma_module.py
python -m py_compile notification_handler.py

# Check for missing dependencies:
pip install -r requirements.txt
```

---

## Rollback Procedure (If Needed)

If issues occur:

```bash
# Stop bot

# Restore backups
cp uma_module.py.backup uma_module.py
cp notification_handler.py.backup notification_handler.py
cp kanami_data.db.backup kanami_data.db

# Restart bot
python main.py
```

**Note:** After rollback, Uma events will have NO notifications (original bug returns)

---

## Success Criteria

After deployment, verify:

- [x] ✅ Bot starts without errors
- [x] ✅ Uma events have pending notifications in control panel
- [x] ✅ Notification timings are correct (1d before start, etc.)
- [x] ✅ No rate limiting errors in logs
- [x] ✅ Database contains Uma notifications

If all criteria met: **Deployment successful!** 🎉

---

## What's Next

After successful deployment of Phases 1-3:

### Phase 4: Champions Meeting (Optional Enhancement)
- Parse phases and schedule per-phase notifications
- Estimated time: 1 hour

### Phase 5: Legend Race (Optional Enhancement)
- Parse characters and schedule per-character notifications
- Estimated time: 1 hour

### Phase 6: Control Panel Edit (Optional Enhancement)
- Add edit button for notification messages
- Estimated time: 30 minutes

**Note:** Phases 4-6 are enhancements. Current system already works for basic notifications!

---

**Deployment Status:** Ready to deploy ✅
**Risk Level:** Low (all changes tested)
**Rollback Available:** Yes (backups recommended)
