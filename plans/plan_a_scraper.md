# Plan A: External Scraper App (uma_scraper.py)

> **Prerequisite:** Execute **Plan C (Web Control Panel)** first.
> This removes `control_panel.py`, simplifying the dependency graph.

## Goal
Move the heavy Playwright scraping logic out of the Discord bot process into a standalone script (`uma_scraper.py`) that runs periodically via Cron.

## The "Dependency Hell" Problem
Currently, `uma_handler.py` (scraping) and `uma_module.py` (bot commands) are circular dependencies:
1. `uma_handler` imports `uma_module` for image combining and DB insertion.
2. `uma_module` imports `bot` (Discord).
3. Therefore, importing `uma_handler` initializes the Bot, preventing standalone execution.

## Execution Strategy (Cron)
Since the scraper will be a separate Python script, we will use **Cron** (Linux Task Scheduler) on the Raspberry Pi to run it.
Example Cron entry (runs every 4 hours):
`0 */4 * * * /usr/bin/python3 /path/to/bot/uma_scraper.py`

> **Implementation rule**: As each step is completed, check it off (`- [x]`) and add a brief note
> describing what was done or any deviations from the plan. Do not mark a step complete if it
> was only partially done.

## The Full Dependency Chain

Moving `add_uma_event` to `uma_handler.py` is not enough on its own. `add_uma_event` calls
`schedule_notifications_for_event()`, which lives in `notification_handler.py` and imports `bot`
at module level. The full chain:

```
uma_scraper.py
└── uma_handler.py          (already clean — no discord)
    └── add_uma_event()     [currently uma_module.py — imports bot ❌]
        └── schedule_notifications_for_event()  [notification_handler.py — imports bot ❌]
```

Both links in that chain must be broken for the standalone scraper to work.

## Implementation Steps

### Phase 1: Untangle Files (Refactoring)
- [ ] **Move Image Logic**: Move `combine_images_vertically` and `combine_images_horizontally` from `uma_module.py` to `uma_handler.py`.
- [ ] **Move DB Logic**: Move `add_uma_event` from `uma_module.py` to `uma_handler.py`.
    - *Change*: Update `add_uma_event` signature to accept `user_id` (string) instead of `ctx` (Discord object).
    - Remove the `DummyCtx` workaround inside `update_uma_events()` in `uma_handler.py`.
    - *Update*: If `event_manager.py` (from Plan C) imports `add_uma_event`, update that import to point to `uma_handler.py`.
- [ ] **Remove Circular Import**: Remove `from uma_module import ...` inside `uma_handler.py`.
    - `uma_handler.py` should become a "pure" library (no `discord` or `bot` imports).
- [ ] **Split Notification Scheduling**: In `notification_handler.py`, create `schedule_notifications_db_only(event)`:
    - Pure DB writes to `pending_notifications` — no `bot.get_guild()` calls.
    - Use role IDs from `global_config.ROLE_IDS` directly instead of resolving via guild.
    - Update `add_uma_event()` (now in `uma_handler.py`) to call `schedule_notifications_db_only()` instead of `schedule_notifications_for_event()`.
    - Keep `schedule_notifications_for_event()` unchanged for any remaining bot-side callers.
- [ ] **Split Update Logic**:
    - Rename `update_uma_events` in `uma_handler.py` to `scrape_and_save_events`.
    - Remove the call to `uma_update_timers` (dashboard refresh) from inside it.
    - The Bot (`uma_module`) will call `scrape_and_save_events` then `uma_update_timers` manually for force refreshes.

### Phase 2: Create Scraper Script
- [ ] **Create `uma_scraper.py`**:
    - Imports `uma_handler`.
    - Calls `scrape_and_save_events()`.
    - On success, writes the current timestamp to `data/scraper_last_run.txt`.
    - Handles logging to a file (`logs/scraper.log`).

### Phase 3: Bot Integration
- [ ] **File Watcher**: Add a background task in `main.py` (or `uma_module.py`) that checks `data/scraper_last_run.txt` every 60 seconds.
- [ ] **Auto-Refresh**: When the timestamp changes, the bot runs `uma_update_timers()` to update Discord embeds.

### Phase 4: Deployment
- [ ] **Setup Cron**: Add the cron job on the Raspberry Pi.
