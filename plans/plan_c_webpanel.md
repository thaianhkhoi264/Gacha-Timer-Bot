# Plan C: Web Control Panel

> **Execution Order: This is the FIRST plan to execute.**
> By retiring the complex Discord-based control panel first, we simplify the dependencies
> for Plan A (Scraper) and Plan B (Notifier).

**Implementation rule**: As each step is completed, check it off (`- [x]`) and add a brief note
describing what was done or any deviations from the plan. Do not mark a step complete if it
was only partially done.

---

## Context

The Discord-based control panel (`control_panel.py`) — modals, dropdowns, and buttons posted
inside a Discord channel — is annoying to use and ties bot management to Discord being online.

The bot already runs an aiohttp REST API (`api_server.py`) accessible via the Cloudflare domain.
The fix is to extend that API with event management routes and build a static web frontend
deployed to Cloudflare Pages.

---

## What gets retired

| Item | Where |
|---|---|
| All Discord UI views/modals in `control_panel.py` | Delete the file |
| `control_panel_messages` DB table | Stop creating/using it |
| `control_panel` imports in `uma_module.py` & `arknights_module.py` | Remove calls to `update_control_panel_messages` |
| All `control_panel.*` calls in `main.py` | Lines 18, 414–456 |

---

## Architecture

```
[Cloudflare Pages — static HTML + JS]
    │  fetch(X-API-Key: ...)
    ▼
[Pi — api_server.py (aiohttp)]
    ├── /api/events/{profile}         (CRUD)
    ├── /api/events/{profile}/{id}/notifications
    ├── /api/notifications/{id}
    └── /api/dashboard/{profile}/refresh
         │
         ▼
    [event_manager.py — business logic]
         │
         ├── uma_module.py (add_uma_event, uma_update_timers)
         ├── arknights_module.py (add_ak_event, arknights_update_timers)
         └── notification_handler.py (schedule/delete notifications)
```

---

## Key files

| File | Change |
|---|---|
| `event_manager.py` | **Create** — extract utility functions from `control_panel.py` |
| `api_server.py` | Add new routes + CORS middleware |
| `requirements.txt` | Add `aiohttp-cors` |
| `main.py` | Remove all `control_panel` references |
| `web/index.html` + `web/app.js` | **Create** — Cloudflare Pages frontend |
| `control_panel.py` | **Delete** after Phase 4 |

---

## Implementation steps

### Phase 1 — Extract business logic to `event_manager.py`

- [x] **Create `event_manager.py`**

  Move these functions verbatim from `control_panel.py` (they have no Discord UI dependency):

  | Function | Notes |
  |---|---|
  | `get_events(profile)` | Pure DB read |
  | `get_event_by_id(profile, event_id)` | Pure DB read |
  | `remove_event_by_id(profile, event_id)` | Calls `bot.get_guild()` via bot_instance |
  | `update_event(profile, event_id, ...)` | DB write + notification reschedule |
  | `get_pending_notifications_for_event(profile, event_id)` | Pure DB read |
  | `remove_pending_notification(notif_id)` | Pure DB write |
  | `refresh_pending_notifications_for_event(profile, event_id)` | Calls schedule/delete |

  Also copy the `PROFILE_CONFIG` dict from `control_panel.py` into `event_manager.py` —
  it maps profile keys to their DB paths and module functions:
  ```python
  from arknights_module import AK_DB_PATH, add_ak_event, delete_event_message, arknights_update_timers, AK_TIMEZONE
  from uma_module import UMA_DB_PATH, add_uma_event, delete_event_message as uma_delete_event_message, uma_update_timers
  from notification_handler import NOTIF_DB_PATH, delete_notifications_for_event, schedule_notifications_for_event

  PROFILE_CONFIG = {
      "AK":  {"DB_PATH": AK_DB_PATH,  "add_event": add_ak_event,  "delete_event_message": delete_event_message,      "update_timers": arknights_update_timers, "TIMEZONE": AK_TIMEZONE},
      "UMA": {"DB_PATH": UMA_DB_PATH, "add_event": add_uma_event, "delete_event_message": uma_delete_event_message, "update_timers": uma_update_timers,        "TIMEZONE": "UTC"},
  }
  ```

  `remove_event_by_id` needs the bot — pass it in as a parameter or import `bot_instance`
  from `api_server` (use a setter function to avoid circular import):
  ```python
  _bot = None
  def set_bot(bot): global _bot; _bot = bot
  ```

- [x] **Update `control_panel.py`** to import from `event_manager` instead of defining those
  functions inline. This keeps the Discord panel working while the new API is being built.
  Confirm bot still starts cleanly.
  *Done: control_panel.py imports from event_manager.*

---

### Phase 2 — Add API routes to `api_server.py`

- [x] **Add `aiohttp-cors` to `requirements.txt`**
  *Done: `aiohttp-cors` is in requirements.txt.*

- [x] **Configure CORS in `api_server.py`**
  *Done: CORS configured with wildcard origin (will be narrowed to the specific Cloudflare Pages
  domain once it is known). Uses `allow_credentials=True` — fine since auth uses `X-API-Key`
  header, not cookies. Origin is echoed back by aiohttp_cors (not literal `*`).*
  *Also done: `event_manager.set_bot(bot)` is now called from `main.py` alongside
  `api_server.bot_instance = bot` so that `remove_event_by_id` can delete Discord embeds.*

- [x] **Add event routes**

  ```python
  # GET /api/events/{profile}
  async def handle_list_events(request):
      profile = request.match_info["profile"].upper()
      if profile not in PROFILE_CONFIG: return 404
      events = await event_manager.get_events(profile)
      return web.json_response({"success": True, "events": events})

  # GET /api/events/{profile}/{event_id}
  async def handle_get_event(request): ...

  # POST /api/events/{profile}
  # Body: {title, category, start_unix, end_unix, image, timezone}
  # Calls PROFILE_CONFIG[profile]["add_event"](DummyCtx, event_data)
  # Auth Logic:
  # - Check X-API-Key against VALID_API_KEYS.
  # - If valid, default user_id to OWNER_USER_ID (simplifies single-user setup).
  async def handle_add_event(request): ...

  # PUT /api/events/{profile}/{event_id}
  async def handle_update_event(request): ...

  # DELETE /api/events/{profile}/{event_id}
  async def handle_remove_event(request): ...
  ```

- [x] **Add notification routes**
  *Done: handle_list_notifications, handle_remove_notification, handle_refresh_notifications.*

- [x] **Add dashboard refresh route**
  *Done: handle_refresh_dashboard.*

- [x] **Register all routes** in `create_app()` and confirm with a test curl:
  *Done: all routes registered. Test curl pending until deployed to Pi.*

---

### Phase 3 — Build Cloudflare Pages frontend

- [x] **Create `web/` folder** in the repo with `index.html` and `app.js`
  *Done: `web/index.html` (dark-theme HTML + CSS) and `web/app.js` (vanilla JS) created.*
  *Setup screen stores both API URL and API key in localStorage. Profile tabs for UMA and AK.*
  *All CRUD operations, notification management, and dashboard refresh are implemented.*
  *Dates handled as unix timestamps (UTC); datetime-local inputs labeled "(UTC)" to avoid confusion.*

- [ ] **Connect to Cloudflare Pages** (one-time setup)
  1. Cloudflare Dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
  2. Select the `Gacha-Timer-Bot` repo → **Begin setup**
  3. Settings:
     - Build output directory: `web`
     - Build command: *(leave blank)*
     - Root directory: `/` (default)
  4. Click **Save and Deploy** → Cloudflare builds and gives you a `*.pages.dev` URL
  5. Optional: In Pages → Custom Domains → add your own subdomain (e.g. `panel.yourdomain.com`)
  6. From now on: every `git push` to `main` automatically redeploys the frontend
  - Hardcode `API_BASE_URL = "https://your-api-domain.com"` in `app.js` (or use a `<meta>` tag)

- [ ] **Test all flows** in the browser (add, edit, remove event; notifications; dashboard refresh)

---

### Phase 4 — Retire `control_panel.py`

- [ ] **`main.py`**: Remove these lines:
  - Line 18: `import control_panel`
  - Lines 414–456: all `control_panel.*` calls (init, load, add_view, ensure_control_panels)

- [ ] **`uma_module.py` & `arknights_module.py`**: Remove `control_panel` imports and calls.
  - In `add_uma_event`, `uma_edit`, `uma_remove`, etc., remove the `try/except` blocks importing `control_panel`.
  - In `add_ak_event`, `ak_edit`, `ak_remove`, etc., remove the `try/except` blocks importing `control_panel`.
  - *Note:* The Web UI updates the DB directly; we no longer need to trigger Discord UI updates when events change.

- [ ] **`notification_handler.py`**: Remove the `CREATE TABLE IF NOT EXISTS control_panel_messages`
  block from `init_control_panel_db()` (or remove the whole function if only used by control panel)

- [ ] **Delete `control_panel.py`**

- [ ] **Confirm bot starts cleanly** with no import errors

---

## Verification checklist

- [ ] `GET /api/events/UMA` returns current events as JSON (requires API key)
- [ ] `POST /api/events/UMA` creates event → appears in DB and Discord dashboard embed
- [ ] `PUT /api/events/UMA/{id}` edits event → notification rows updated
- [ ] `DELETE /api/events/UMA/{id}` removes event → Discord embed deleted
- [ ] `GET /api/events/UMA/{id}/notifications` returns pending rows
- [ ] `DELETE /api/notifications/{id}` removes one row from DB
- [ ] `POST /api/dashboard/UMA/refresh` triggers embed update in Discord
- [ ] Cloudflare Pages frontend loads, API key prompt works on first visit
- [ ] All CRUD operations work end-to-end from the web UI
- [ ] Bot starts cleanly with no `control_panel` references
- [ ] CORS: fetch from Cloudflare Pages domain returns 200 (no CORS errors in browser console)
