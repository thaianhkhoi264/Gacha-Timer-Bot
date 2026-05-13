# Plan B: External Notification Sender (uma_notifier.py)

> **Implementation rule**: As each step is completed, check it off (`- [x]`) and add a brief note
> describing what was done or any deviations from the plan. Do not mark a step complete if it
> was only partially done.

---

## Context

The bot currently runs `notification_loop()` every 30 seconds — a tight asyncio loop that queries
`pending_notifications WHERE sent=0 AND notify_unix <= now()` and calls `channel.send()` with a
role mention in the message content.

Moving this to an external script removes a persistent bot task, and means the bot no longer
needs to be running for notifications to fire. The webhook approach is fully compatible:

- **"Can't edit/delete"** — NOT a problem. Notification alerts are fire-and-forget. Dashboard
  embeds (which DO need editing) stay in the bot via `uma_update_timers()`.
- **"Can't mention roles"** — NOT a problem. Webhook message content supports `<@&ROLE_ID>`
  strings directly. The bot's `role.mention` returns exactly that string. Role IDs are already
  in `global_config.py` (`ROLE_IDS`, `COMBINED_REGIONAL_ROLE_IDS`).

---

## Current flow (inside bot)

```
notification_loop() [main.py, every 30s]
└── load_and_schedule_pending_notifications(bot)
    ├── SELECT * FROM pending_notifications WHERE sent=0 AND notify_unix <= now+60
    ├── UPDATE pending_notifications SET sent=1 WHERE id=?
    └── send_notification(event, timing_type)
        ├── guild.get_role(role_id).mention  →  "<@&ROLE_ID>" string
        ├── format message via MESSAGE_TEMPLATES
        └── channel.send(message)   ← the only discord.py call
```

## Target architecture

```
[cron / systemd timer, every 1 minute]
└── python uma_notifier.py
    ├── SELECT * FROM pending_notifications WHERE sent=0 AND notify_unix <= now
    ├── For each row:
    │   ├── Build role mention: f"<@&{ROLE_IDS[profile]}>"
    │   ├── Format message via MESSAGE_TEMPLATES
    │   └── POST to NOTIFICATION_WEBHOOK_URLS[profile]
    └── UPDATE sent=1 for each sent notification
```

---

## Scope boundary

**Plan B touches only the notification *sending* loop.** The scheduling logic in
`notification_handler.py` (`schedule_notifications_for_event`, `delete_notifications_for_event`,
`schedule_notifications_db_only` added by Plan A) is **not changed here**. The bot still writes
rows to `pending_notifications`; the external notifier only reads and fires them.

## Key files

| File | Change |
|---|---|
| `global_config.py` | Add `NOTIFICATION_WEBHOOK_URLS` dict (profile → webhook URL) |
| `notification_handler.py` | **No changes** — scheduling functions stay in the bot |
| `main.py` | Remove `notification_loop()` task and its `create_task()` call |
| `uma_notifier.py` | New standalone script (create) |

---

## Pre-implementation: Create Discord webhooks

For each game's notification channel, create a webhook in Discord:
- Channel Settings → Integrations → Webhooks → New Webhook
- Copy the webhook URL
- One webhook per notification channel (uma, ak, stri, hsr, zzz, wuwa, etc.)

---

## Implementation steps

- [ ] **Step 1 — `global_config.py`: Add `NOTIFICATION_WEBHOOK_URLS`**
  ```python
  NOTIFICATION_WEBHOOK_URLS = {
      "UMA": "https://discord.com/api/webhooks/...",
      "AK":  "https://discord.com/api/webhooks/...",
      "STRI": "https://discord.com/api/webhooks/...",
      "HSR": "https://discord.com/api/webhooks/...",
      "ZZZ": "https://discord.com/api/webhooks/...",
      "WUWA": "https://discord.com/api/webhooks/...",
      # Add regional variants if HSR/ZZZ/WUWA have per-region channels
  }
  ```
  Keys must match the `profile` column values in `pending_notifications`.

- [ ] **Step 2 — Create `uma_notifier.py`** (new standalone script, no discord.py)
  - Import: `sqlite3`, `requests`, `datetime` (standard lib only + shared config)
  - Copy `MESSAGE_TEMPLATES` dict and `format_notification_message()` from
    `notification_handler.py` (or import them directly if the file is safe to import standalone)
  - Import `ROLE_IDS`, `COMBINED_REGIONAL_ROLE_IDS`, `NOTIFICATION_WEBHOOK_URLS` from
    `global_config.py`
  - Core logic:
    ```python
    def build_role_mention(profile, region=None):
        if region and (profile, region.upper()) in COMBINED_REGIONAL_ROLE_IDS:
            role_id = COMBINED_REGIONAL_ROLE_IDS[(profile, region.upper())]
        else:
            role_id = ROLE_IDS.get(profile)
        return f"<@&{role_id}>" if role_id else ""

    def run():
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        conn = sqlite3.connect(NOTIF_DB_PATH)
        rows = conn.execute(
            "SELECT id, profile, title, category, timing_type, notify_unix, "
            "event_time_unix, region, message_template, custom_message, phase, character_name "
            "FROM pending_notifications WHERE sent=0 AND notify_unix <= ?",
            (now,)
        ).fetchall()

        for row in rows:
            # unpack row, build role mention, format message, POST webhook
            # mark sent=1 only on HTTP 200/204 response
            ...

        conn.commit()
        conn.close()
    ```
  - Runs synchronously (no asyncio needed — `requests` is sync)
  - Entrypoint: `if __name__ == "__main__": run()`

- [ ] **Step 3 — `main.py`: Remove `notification_loop()`**
  - Delete the `notification_loop()` function and its `asyncio.create_task()` call in `on_ready`
  - Confirm no other code references it

- [ ] **Step 4 — Test standalone notifier**
  Insert a test row into `pending_notifications`:
  ```sql
  INSERT INTO pending_notifications
    (category, profile, title, timing_type, notify_unix, event_time_unix, sent, region, message_template)
  VALUES
    ('Banner', 'UMA', 'Test Event', 'start', strftime('%s','now') - 1, strftime('%s','now'), 0, 'JP', 'default');
  ```
  Run `python uma_notifier.py`. Confirm:
  - Message appears in the UMA notification channel with role ping
  - Row now has `sent=1` in DB
  - No discord.py import errors

- [ ] **Step 5 — Test that bot still runs without `notification_loop()`**
  Start bot normally. Confirm no errors related to removed loop.
  Dashboard embeds and scraper watcher should still work.

- [ ] **Step 6 — Add cron entry on Raspberry Pi**
  ```
  * * * * * cd /path/to/Gacha-Timer-Bot/Gacha-Timer-Bot && python uma_notifier.py >> logs/notifier.log 2>&1
  ```
  Cron minimum interval is 1 minute. The `notify_unix` window in the old bot had a +60s buffer;
  1-minute cron is equivalent.

---

## Verification checklist

- [ ] `python uma_notifier.py` exits cleanly with no discord.py dependency errors
- [ ] Role ping appears correctly in Discord notification channel
- [ ] `sent=1` is set in DB after successful webhook post (not before)
- [ ] No duplicate notifications on re-run (idempotent due to `sent=1` flag)
- [ ] Bot starts and runs without `notification_loop()` task
- [ ] Dashboard embeds still update correctly (unrelated to this plan, but confirm no regression)
