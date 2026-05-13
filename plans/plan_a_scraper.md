# Plan A: External Scraper App (uma_scraper.py)

> **Prerequisite:** **Plan C (Web Control Panel)** is complete (Backend).
> `control_panel.py` logic has been moved to `event_manager.py`, clearing the way for this plan.

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
- [x] **Move Image Logic**: Moved `get_image_hash`, `is_url`, `combine_images_vertically`, `combine_images_horizontally` from `uma_module.py` to `uma_handler.py`. Removed PIL/aiohttp/BytesIO imports from `uma_module.py`. Also moved `parse_champions_meeting_phases` and `parse_legend_race_characters` (pure math, no discord) to `uma_handler.py` — needed by `schedule_notifications_db_only`.
- [x] **Move DB Logic**: Moved `add_uma_event` to `uma_handler.py`. Signature is now `add_uma_event(event_data, user_id="0")`. DummyCtx removed from `uma_handler.py`. Updated `notification_handler.py` parse imports to point to `uma_handler`.
- [x] **Remove Circular Import**: All `from uma_module import ...` calls removed from `uma_handler.py`. `uma_handler.py` is now discord-free.
- [x] **Split Notification Scheduling**: Added `schedule_notifications_db_only(event)` to `notification_handler.py`. Calls the existing specialized scheduling functions (which are already pure DB) and does generic scheduling without `bot.get_guild()` or embed refresh. `add_uma_event` in `uma_handler.py` calls this instead of `schedule_notifications_for_event`.
- [x] **Split Update Logic**: Renamed `update_uma_events` → `scrape_and_save_events`. Removed `uma_update_timers()` from inside it. All callers in `uma_module.py` now call `scrape_and_save_events()` + `uma_update_timers()` explicitly.

### Phase 2: Create Scraper Script
- [x] **Create `uma_scraper.py`**: Imports `uma_handler`, calls `scrape_and_save_events()`, writes UTC timestamp to `data/scraper_last_run.txt`, logs to `logs/scraper.log`.

### Phase 3: Bot Integration
- [x] **File Watcher**: Added `scraper_file_watcher()` coroutine to `uma_module.py`. Started as a background task from `start_uma_background_tasks()`.
- [x] **Auto-Refresh**: When `data/scraper_last_run.txt` timestamp changes, the watcher calls `uma_update_timers()` to refresh Discord embeds.

### Phase 4: Deployment
- [x] **Setup Cron**: Add the cron job on the Raspberry Pi.
  ```
  0 */4 * * * cd /path/to/bot && /path/to/venv/bin/python uma_scraper.py
  ```
