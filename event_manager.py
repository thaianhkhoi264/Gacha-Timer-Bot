"""
Event Manager
Handles business logic for events (CRUD operations, notifications) independent of Discord UI.
Extracted from control_panel.py as part of Plan C.
"""

import aiosqlite
from global_config import MAIN_SERVER_ID, ONGOING_EVENTS_CHANNELS, UPCOMING_EVENTS_CHANNELS

# Profile-specific imports
from arknights_module import AK_DB_PATH, add_ak_event, delete_event_message as ak_delete_event_message, arknights_update_timers, AK_TIMEZONE
from uma_module import UMA_DB_PATH, add_uma_event, delete_event_message as uma_delete_event_message, uma_update_timers
from notification_handler import NOTIF_DB_PATH, delete_notifications_for_event, schedule_notifications_for_event

# Bot instance placeholder (injected via set_bot)
_bot = None

def set_bot(bot_instance):
    """Injects the bot instance for functions that need it (e.g. fetching guilds)."""
    global _bot
    _bot = bot_instance

# Profile configuration
PROFILE_CONFIG = {
    "AK": {
        "DB_PATH": AK_DB_PATH,
        "add_event": add_ak_event,
        "delete_event_message": ak_delete_event_message,
        "update_timers": arknights_update_timers,
        "TIMEZONE": AK_TIMEZONE,
    },
    "UMA": {
        "DB_PATH": UMA_DB_PATH,
        "add_event": add_uma_event,
        "delete_event_message": uma_delete_event_message,
        "update_timers": uma_update_timers,
        "TIMEZONE": "UTC",
    },
}

async def get_events(profile):
    db_path = PROFILE_CONFIG[profile]["DB_PATH"]
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute(
            "SELECT id, title, category, start_date, end_date, image FROM events ORDER BY start_date ASC"
        ) as cursor:
            return [dict(id=row[0], title=row[1], category=row[2], start=row[3], end=row[4], image=row[5]) async for row in cursor]

async def get_event_by_id(profile, event_id):
    db_path = PROFILE_CONFIG[profile]["DB_PATH"]
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute(
            "SELECT id, title, category, start_date, end_date, image, description FROM events WHERE id=?",
            (event_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(id=row[0], title=row[1], category=row[2], start=row[3], end=row[4], image=row[5], description=row[6] or '')
    return None

async def remove_event_by_id(profile, event_id):
    db_path = PROFILE_CONFIG[profile]["DB_PATH"]
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("SELECT title, category, profile FROM events WHERE id=?", (event_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return False
        title, category, profile_code = row
        
        # Use injected bot instance
        if _bot:
            main_guild = _bot.get_guild(MAIN_SERVER_ID)
            if main_guild:
                await PROFILE_CONFIG[profile]["delete_event_message"](main_guild, ONGOING_EVENTS_CHANNELS[profile], event_id)
                await PROFILE_CONFIG[profile]["delete_event_message"](main_guild, UPCOMING_EVENTS_CHANNELS[profile], event_id)
        
        await conn.execute("DELETE FROM events WHERE id=?", (event_id,))
        await conn.commit()
    
    await delete_notifications_for_event(title, category, profile_code)
    await PROFILE_CONFIG[profile]["update_timers"]()
    return True

async def update_event(profile, event_id, title, category, start, end, image=None):
    db_path = PROFILE_CONFIG[profile]["DB_PATH"]
    async with aiosqlite.connect(db_path) as conn:
        if image is not None:
            await conn.execute(
                "UPDATE events SET title=?, category=?, start_date=?, end_date=?, image=? WHERE id=?",
                (title, category, start, end, image, event_id)
            )
        else:
            await conn.execute(
                "UPDATE events SET title=?, category=?, start_date=?, end_date=? WHERE id=?",
                (title, category, start, end, event_id)
            )
        await conn.commit()
    
    event = await get_event_by_id(profile, event_id)
    if event:
        event_for_notification = {
            'category': event['category'],
            'profile': profile,
            'title': event['title'],
            'start_date': str(event['start']),
            'end_date': str(event['end'])
        }
        await delete_notifications_for_event(event['title'], event['category'], profile)
        await schedule_notifications_for_event(event_for_notification)
        await PROFILE_CONFIG[profile]["update_timers"]()

async def get_pending_notifications_for_event(profile, event_id):
    event = await get_event_by_id(profile, event_id)
    if not event:
        return []
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        async with conn.execute(
            "SELECT id, timing_type, notify_unix, custom_message FROM pending_notifications WHERE title=? AND profile=? ORDER BY notify_unix ASC",
            (event['title'], profile)
        ) as cursor:
            return [dict(id=row[0], timing_type=row[1], notify_unix=row[2], custom_message=row[3]) async for row in cursor]

async def remove_pending_notification(notif_id):
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        await conn.execute("DELETE FROM pending_notifications WHERE id=?", (notif_id,))
        await conn.commit()

async def get_all_pending_notifications(profile=None):
    """Return all unsent pending notifications, optionally filtered by profile."""
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if profile:
            async with conn.execute(
                "SELECT * FROM pending_notifications WHERE sent=0 AND profile=? ORDER BY notify_unix ASC",
                (profile.upper(),)
            ) as cursor:
                return [dict(row) async for row in cursor]
        else:
            async with conn.execute(
                "SELECT * FROM pending_notifications WHERE sent=0 ORDER BY notify_unix ASC"
            ) as cursor:
                return [dict(row) async for row in cursor]

async def update_notification_message(notif_id, custom_message):
    """Set custom_message on a pending notification row."""
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        await conn.execute(
            "UPDATE pending_notifications SET custom_message=? WHERE id=?",
            (custom_message, notif_id)
        )
        await conn.commit()

async def refresh_pending_notifications_for_event(profile, event_id):
    event = await get_event_by_id(profile, event_id)
    if not event:
        return
    await delete_notifications_for_event(event['title'], event['category'], profile)
    event_for_notification = {
        'category': event['category'],
        'profile': profile,
        'title': event['title'],
        'start_date': str(event['start']),
        'end_date': str(event['end']),
        'description': event.get('description', ''),
    }
    await schedule_notifications_for_event(event_for_notification)
