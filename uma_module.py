"""Uma Musume Event Tracking Module"""
print("[INIT] Loading uma_module.py...")

import os
import aiosqlite
import asyncio
import discord
from discord.ext import commands
from bot import bot
from datetime import datetime, timezone, timedelta
from global_config import ONGOING_EVENTS_CHANNELS, UPCOMING_EVENTS_CHANNELS, OWNER_USER_ID, MAIN_SERVER_ID
import logging

# Test PIL import early to catch errors
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError as e:
    print(f"[WARNING] PIL (Pillow) not available: {e}")
    PIL_AVAILABLE = False

import requests
from io import BytesIO

# Create logger for Uma Musume
uma_logger = logging.getLogger("uma_musume")
uma_logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

# File handler
log_file_path = os.path.join("logs", "uma_musume.log")
os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))

if not any(isinstance(h, logging.StreamHandler) for h in uma_logger.handlers):
    uma_logger.addHandler(console_handler)
if not any(isinstance(h, logging.FileHandler) for h in uma_logger.handlers):
    uma_logger.addHandler(file_handler)

uma_logger.propagate = True

# Test log to verify module loaded
print("[INIT] Logger configured successfully")
uma_logger.info("[Module Load] uma_module.py imported successfully")
print("[INIT] Test log written successfully")

# Diagnostic: Write directly to file to verify file I/O works
try:
    with open("uma_debug.txt", "a") as f:
        from datetime import datetime as dt
        f.write(f"[{dt.now()}] uma_module.py module-level code executing\n")
    print("[INIT] Direct file write successful")
except Exception as e:
    print(f"[ERROR] Direct file write failed: {e}")

# Path to Uma Musume database
UMA_DB_PATH = os.path.join("data", "uma_musume_data.db")
print(f"[INIT] Database path set to: {UMA_DB_PATH}")

# Background task for periodic updates
UMA_UPDATE_TASK = None
print("[INIT] Global variables initialized")
print("[INIT] Defining async functions...")

def get_event_color(event):
    """Determine embed color based on event type.
    
    Blue - Character Banner
    Green - Support Banner
    Yellow - Story Event
    Purple - Champions Meeting
    Pink/Magenta - Legend Race
    Orange - Paid Banner
    """
    category = event.get("category", "").lower()
    title = event.get("title", "").lower()
    
    # Paid Banner - Orange
    if category == "offer" or "paid banner" in title:
        return discord.Color.orange()
    
    # Character/Support Banner
    if category == "banner":
        # Support Banner - Green
        if "support" in title:
            return discord.Color.green()
        # Character Banner - Blue
        else:
            return discord.Color.blue()
    
    # Champions Meeting - Purple
    if "champions meeting" in title:
        return discord.Color.purple()
    
    # Legend Race - Pink/Magenta
    if "legend race" in title:
        return discord.Color.magenta()
    
    # Story Event or generic Event - Yellow/Gold
    if category == "event" or "story" in title:
        return discord.Color.gold()
    
    # Default - Gray
    return discord.Color.default()

async def init_uma_db():
    """Initialize Uma Musume database with tables for events and messages."""
    os.makedirs("data", exist_ok=True)
    uma_logger.info(f"[DB Init] Ensuring database directory exists: data/")
    async with aiosqlite.connect(UMA_DB_PATH) as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                title TEXT,
                start_date TEXT,
                end_date TEXT,
                image TEXT,
                category TEXT,
                profile TEXT,
                description TEXT
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS event_messages (
                event_id INTEGER,
                channel_id TEXT,
                message_id TEXT,
                PRIMARY KEY (event_id, channel_id)
            )
        ''')
        await conn.commit()
        uma_logger.info(f"[DB Init] Database initialized successfully at: {UMA_DB_PATH}")

def combine_images_vertically(img_url1, img_url2):
    """
    Downloads two images and combines them vertically.
    Returns the path to the saved combined image.
    """
    if not PIL_AVAILABLE:
        uma_logger.warning("[Image] PIL not available, cannot combine images")
        return img_url1  # Return first image URL as fallback
    
    try:
        # Download images
        response1 = requests.get(img_url1)
        response2 = requests.get(img_url2)
        
        img1 = Image.open(BytesIO(response1.content))
        img2 = Image.open(BytesIO(response2.content))
        
        # Get dimensions
        width = max(img1.width, img2.width)
        height = img1.height + img2.height
        
        # Create new image
        combined = Image.new('RGB', (width, height))
        combined.paste(img1, (0, 0))
        combined.paste(img2, (0, img1.height))
        
        # Save combined image
        os.makedirs(os.path.join("data", "combined_images"), exist_ok=True)
        filename = f"combined_{int(datetime.now().timestamp())}.png"
        filepath = os.path.join("data", "combined_images", filename)
        combined.save(filepath)
        uma_logger.info(f"[Image] Combined images saved to: {filepath}")
        
        return filepath
    except Exception as e:
        uma_logger.error(f"Failed to combine images: {e}")
        return None

async def post_event_embed(channel, event):
    """Posts an embed for the Uma Musume event."""
    # Determine color based on event type
    color = get_event_color(event)
    
    description = f"**Start:** <t:{event['start']}:F>\n**End:** <t:{event['end']}:F>"
    if event.get("description"):
        description += f"\n\n{event['description']}"
    
    embed = discord.Embed(
        title=event["title"],
        description=description,
        color=color
    )
    
    if event.get("image"):
        if event["image"].startswith("http"):
            embed.set_image(url=event["image"])
        else:
            # Local file
            file = discord.File(event["image"], filename="image.png")
            embed.set_image(url=f"attachment://image.png")
            return await channel.send(embed=embed, file=file)
    
    return await channel.send(embed=embed)

async def delete_event_message(guild, channel_id, event_id):
    """Deletes the event message from the channel."""
    async with aiosqlite.connect(UMA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT message_id FROM event_messages WHERE event_id=? AND channel_id=?",
            (event_id, str(channel_id))
        ) as cursor:
            row = await cursor.fetchone()
        if row and row[0]:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    msg = await channel.fetch_message(int(row[0]))
                    await msg.delete()
                except Exception:
                    pass
        await conn.execute(
            "DELETE FROM event_messages WHERE event_id=? AND channel_id=?",
            (event_id, str(channel_id))
        )
        await conn.commit()

async def upsert_event_message(guild, channel, event, event_id):
    """Edits the event message if it exists, otherwise sends a new one."""
    async with aiosqlite.connect(UMA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT message_id FROM event_messages WHERE event_id=? AND channel_id=?",
            (event_id, str(channel.id))
        ) as cursor:
            row = await cursor.fetchone()
        
        # Determine color based on event type
        color = get_event_color(event)
        
        description = f"**Start:** <t:{event['start']}:F>\n**End:** <t:{event['end']}:F>"
        if event.get("description"):
            description += f"\n\n{event['description']}"
        
        embed = discord.Embed(
            title=event["title"],
            description=description,
            color=color
        )
        
        msg = None
        if row and row[0]:
            try:
                msg = await channel.fetch_message(int(row[0]))
                if event.get("image"):
                    if event["image"].startswith("http"):
                        embed.set_image(url=event["image"])
                        await msg.edit(embed=embed)
                    else:
                        file = discord.File(event["image"], filename="image.png")
                        embed.set_image(url=f"attachment://image.png")
                        await msg.edit(embed=embed, attachments=[file])
                else:
                    await msg.edit(embed=embed)
                return
            except Exception:
                pass
        
        # Send new message
        if event.get("image"):
            if event["image"].startswith("http"):
                embed.set_image(url=event["image"])
                msg = await channel.send(embed=embed)
            else:
                file = discord.File(event["image"], filename="image.png")
                embed.set_image(url=f"attachment://image.png")
                msg = await channel.send(embed=embed, file=file)
        else:
            msg = await channel.send(embed=embed)
        
        await conn.execute(
            "REPLACE INTO event_messages (event_id, channel_id, message_id) VALUES (?, ?, ?)",
            (event_id, str(channel.id), str(msg.id))
        )
        await conn.commit()

async def uma_update_timers(_guild=None):
    """
    Updates Uma Musume event dashboards.
    Only shows events within 1 month from now.
    """
    uma_logger.info("[Update Timers] Starting dashboard update...")
    print("[UMA] Starting dashboard update...")
    
    # Check if bot is ready
    if not bot.is_ready():
        uma_logger.warning("[Update Timers] Bot not ready yet, skipping dashboard update")
        print("[UMA] WARNING: Bot not ready yet, skipping dashboard update")
        return
    
    main_guild = bot.get_guild(MAIN_SERVER_ID)
    if not main_guild:
        uma_logger.error("[Update Timers] Main guild not found!")
        print(f"[UMA] ERROR: Main guild not found! MAIN_SERVER_ID={MAIN_SERVER_ID}")
        return
    
    now = int(datetime.now(timezone.utc).timestamp())
    one_month_later = now + (30 * 24 * 60 * 60)  # 30 days
    
    ongoing_channel = main_guild.get_channel(ONGOING_EVENTS_CHANNELS["UMA"])
    upcoming_channel = main_guild.get_channel(UPCOMING_EVENTS_CHANNELS["UMA"])
    
    if not ongoing_channel:
        uma_logger.error(f"[Update Timers] Ongoing channel not found: {ONGOING_EVENTS_CHANNELS['UMA']}")
        print(f"[UMA] ERROR: Ongoing channel not found! ID={ONGOING_EVENTS_CHANNELS['UMA']}")
    else:
        print(f"[UMA] Ongoing channel found: #{ongoing_channel.name}")
        
    if not upcoming_channel:
        uma_logger.error(f"[Update Timers] Upcoming channel not found: {UPCOMING_EVENTS_CHANNELS['UMA']}")
        print(f"[UMA] ERROR: Upcoming channel not found! ID={UPCOMING_EVENTS_CHANNELS['UMA']}")
    else:
        print(f"[UMA] Upcoming channel found: #{upcoming_channel.name}")
    
    if not ongoing_channel and not upcoming_channel:
        uma_logger.error("[Update Timers] Both channels not found, aborting!")
        print("[UMA] ERROR: Both channels not found, cannot post events!")
        return
    
    uma_logger.info(f"[Update Timers] Ongoing channel: {ongoing_channel.name if ongoing_channel else 'None'}")
    uma_logger.info(f"[Update Timers] Upcoming channel: {upcoming_channel.name if upcoming_channel else 'None'}")
    
    async with aiosqlite.connect(UMA_DB_PATH) as conn:
        # Fetch all events
        async with conn.execute(
            "SELECT id, title, start_date, end_date, image, category, description FROM events ORDER BY start_date ASC"
        ) as cursor:
            events = [dict(
                id=row[0], title=row[1], start=int(row[2]), end=int(row[3]), 
                image=row[4], category=row[5], description=row[6]
            ) async for row in cursor]
        
        uma_logger.info(f"[Update Timers] Fetched {len(events)} events from database")
        print(f"[UMA] Fetched {len(events)} events from database")
        
        if len(events) == 0:
            print("[UMA] No events in database!")
            uma_logger.warning("[Update Timers] No events in database")
            return
        
        ongoing_count = 0
        upcoming_count = 0
        deleted_count = 0
        skipped_count = 0
        
        for event in events:
            # Debug: Show event details
            from datetime import datetime as dt
            start_dt = dt.fromtimestamp(event["start"], tz=timezone.utc)
            end_dt = dt.fromtimestamp(event["end"], tz=timezone.utc)
            print(f"[UMA] Checking event '{event['title']}': start={start_dt}, end={end_dt}")
            
            # Delete ended events
            if event["end"] < now:
                await delete_event_message(main_guild, ONGOING_EVENTS_CHANNELS["UMA"], event["id"])
                await delete_event_message(main_guild, UPCOMING_EVENTS_CHANNELS["UMA"], event["id"])
                await conn.execute("DELETE FROM events WHERE id=?", (event["id"],))
                await conn.commit()
                deleted_count += 1
                uma_logger.info(f"[Update Timers] Deleted ended event: {event['title']}")
                continue
            
            # Skip events more than 1 month away
            if event["start"] > one_month_later:
                skipped_count += 1
                print(f"[UMA] SKIPPED (>1 month): '{event['title']}' starts at {start_dt} (now: {dt.fromtimestamp(now, tz=timezone.utc)}, cutoff: {dt.fromtimestamp(one_month_later, tz=timezone.utc)})")
                continue
            
            # Ongoing events
            if event["start"] <= now < event["end"]:
                print(f"[UMA] Event '{event['title']}' is ONGOING (start: {event['start']}, end: {event['end']}, now: {now})")
                await delete_event_message(main_guild, UPCOMING_EVENTS_CHANNELS["UMA"], event["id"])
                if ongoing_channel:
                    await upsert_event_message(main_guild, ongoing_channel, event, event["id"])
                    ongoing_count += 1
                    uma_logger.info(f"[Update Timers] Posted ongoing event: {event['title']}")
                    print(f"[UMA] Posted to ongoing channel: {event['title']}")
            
            # Upcoming events (within 1 month)
            elif event["start"] > now:
                print(f"[UMA] Event '{event['title']}' is UPCOMING (start: {event['start']}, now: {now})")
                if upcoming_channel:
                    await upsert_event_message(main_guild, upcoming_channel, event, event["id"])
                    upcoming_count += 1
                    uma_logger.info(f"[Update Timers] Posted upcoming event: {event['title']}")
                    print(f"[UMA] Posted to upcoming channel: {event['title']}")
                await delete_event_message(main_guild, ONGOING_EVENTS_CHANNELS["UMA"], event["id"])
        
        uma_logger.info(f"[Update Timers] Summary - Ongoing: {ongoing_count}, Upcoming: {upcoming_count}, Deleted: {deleted_count}, Skipped (>1mo): {skipped_count}")

async def add_uma_event(ctx, event_data):
    """Adds or updates an Uma Musume event in the database (only if changed)."""
    uma_logger.info(f"[Add Event] Processing event: {event_data.get('title', 'Unknown')}")
    
    async with aiosqlite.connect(UMA_DB_PATH) as conn:
        # Check if event already exists
        async with conn.execute(
            '''SELECT id, start_date, end_date, image, description 
               FROM events 
               WHERE title = ? AND category = ? AND profile = 'UMA' ''',
            (event_data["title"], event_data["category"])
        ) as cursor:
            existing = await cursor.fetchone()
        
        if existing:
            event_id, old_start, old_end, old_image, old_desc = existing
            
            # Check if anything changed
            changed = False
            if (str(event_data["start"]) != str(old_start) or 
                str(event_data["end"]) != str(old_end) or
                event_data.get("image") != old_image or
                event_data.get("description", "") != old_desc):
                changed = True
            
            if changed:
                # Update existing event
                await conn.execute(
                    '''UPDATE events 
                       SET start_date = ?, end_date = ?, image = ?, description = ?, user_id = ?
                       WHERE id = ?''',
                    (event_data["start"], event_data["end"], event_data.get("image"),
                     event_data.get("description", ""), str(ctx.author.id) if hasattr(ctx, 'author') else "0",
                     event_id)
                )
                await conn.commit()
                uma_logger.info(f"[Add Event] Updated existing event: {event_data['title']}")
                print(f"[UMA] Updated event: {event_data['title']}")
            else:
                uma_logger.info(f"[Add Event] Event unchanged, skipping: {event_data['title']}")
                print(f"[UMA] Event unchanged: {event_data['title']}")
                return  # Don't reschedule notifications if nothing changed
        else:
            # Insert new event
            await conn.execute(
                '''INSERT INTO events (user_id, title, start_date, end_date, image, category, profile, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (str(ctx.author.id) if hasattr(ctx, 'author') else "0",
                 event_data["title"], event_data["start"], event_data["end"],
                 event_data.get("image"), event_data["category"], "UMA",
                 event_data.get("description", ""))
            )
            await conn.commit()
            uma_logger.info(f"[Add Event] Inserted new event: {event_data['title']}")
            print(f"[UMA] New event: {event_data['title']}")
    
    # Schedule notifications (for new or updated events)
    event_for_notification = {
        'category': event_data['category'],
        'profile': "UMA",
        'title': event_data['title'],
        'start_date': event_data['start'],
        'end_date': event_data['end']
    }
    from notification_handler import schedule_notifications_for_event
    await schedule_notifications_for_event(event_for_notification)

print("[INIT] Functions defined, now registering bot commands...")

@commands.has_permissions(manage_guild=True)
@bot.command(name="uma_remove")
async def uma_remove(ctx, *, title: str):
    """Removes an Uma Musume event by title."""
    main_guild = bot.get_guild(MAIN_SERVER_ID)
    async with aiosqlite.connect(UMA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT id, title, category, profile FROM events WHERE LOWER(title)=?",
            (title.lower(),)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            await ctx.send(f"No event found with title '{title}'.")
            return
        event_id, event_title, event_category, event_profile = row
        
        await delete_event_message(main_guild, ONGOING_EVENTS_CHANNELS["UMA"], event_id)
        await delete_event_message(main_guild, UPCOMING_EVENTS_CHANNELS["UMA"], event_id)
        
        await conn.execute("DELETE FROM events WHERE id=?", (event_id,))
        await conn.commit()
    
    from notification_handler import delete_notifications_for_event
    await delete_notifications_for_event(event_title, event_category, event_profile)
    
    await ctx.send(f"Deleted event '{event_title}' and its notifications.")
    await uma_update_timers()

print("[INIT] uma_remove command registered")
print("[INIT] Defining uma_refresh command...")

@commands.has_permissions(manage_guild=True)
@bot.command(name="uma_refresh")
async def uma_refresh(ctx):
    """Refreshes Uma Musume event dashboards."""
    await uma_update_timers()
    await ctx.send("Uma Musume event dashboards have been refreshed.")

print("[INIT] uma_refresh command registered")
print("[INIT] Defining uma_update command...")

@commands.has_permissions(administrator=True)
@bot.command(name="uma_update")
async def uma_update(ctx):
    """Downloads and updates Uma Musume events from uma.moe/timeline."""
    await ctx.send("Starting Uma Musume event update from timeline... This may take a few minutes.")
    
    try:
        from uma_handler import update_uma_events
        await update_uma_events()
        await ctx.send("✅ Uma Musume events have been updated successfully!")
    except Exception as e:
        uma_logger.error(f"Failed to update Uma Musume events: {e}")
        await ctx.send(f"❌ Failed to update Uma Musume events: {e}")

async def periodic_uma_update():
    """Background task that updates Uma Musume events every 3 days."""
    global UMA_UPDATE_TASK
    uma_logger.info("[Periodic Update] Uma Musume periodic update task started.")
    
    while True:
        try:
            # Wait 3 days (259200 seconds)
            await asyncio.sleep(259200)
            
            uma_logger.info("[Periodic Update] Starting scheduled Uma Musume event update...")
            from uma_handler import update_uma_events
            await update_uma_events()
            uma_logger.info("[Periodic Update] Scheduled update completed successfully.")
            
        except asyncio.CancelledError:
            uma_logger.info("[Periodic Update] Uma Musume periodic update task cancelled.")
            break
        except Exception as e:
            uma_logger.error(f"[Periodic Update] Failed to update Uma Musume events: {e}")
            # Continue despite errors

async def start_uma_background_tasks():
    """Starts background tasks for Uma Musume (initial update + periodic updates)."""
    global UMA_UPDATE_TASK
    
    try:
        uma_logger.info("[Startup] Initializing Uma Musume background tasks...")
        print("[UMA STARTUP] Initializing Uma Musume background tasks...")
        
        # Initialize database
        await init_uma_db()
        uma_logger.info("[Startup] Uma Musume database initialized.")
        print("[UMA STARTUP] Database initialized.")
        
        # Run initial update on startup
        try:
            uma_logger.info("[Startup] Running initial Uma Musume event update...")
            print("[UMA STARTUP] Running initial event update (this may take 2-3 minutes)...")
            from uma_handler import update_uma_events
            await update_uma_events()
            uma_logger.info("[Startup] Initial update completed successfully.")
            print("[UMA STARTUP] Initial update completed successfully!")
        except Exception as e:
            uma_logger.error(f"[Startup] Initial update failed: {e}")
            print(f"[UMA ERROR] Initial update failed: {e}")
            import traceback
            uma_logger.error(traceback.format_exc())
            traceback.print_exc()
        
        # Start periodic update task (every 3 days)
        if UMA_UPDATE_TASK is None or UMA_UPDATE_TASK.done():
            UMA_UPDATE_TASK = asyncio.create_task(periodic_uma_update())
            uma_logger.info("[Startup] Periodic update task scheduled (every 3 days).")
            print("[UMA STARTUP] Periodic update task scheduled (every 3 days).")
    
    except Exception as e:
        uma_logger.error(f"[Startup] CRITICAL ERROR in start_uma_background_tasks: {e}")
        print(f"[UMA ERROR] CRITICAL ERROR in start_uma_background_tasks: {e}")
        import traceback
        uma_logger.error(traceback.format_exc())
        print(f"[ERROR] Uma Musume initialization failed: {e}")
        print(traceback.format_exc())

async def stop_uma_background_tasks():
    """Stops Uma Musume background tasks."""
    global UMA_UPDATE_TASK
    
    if UMA_UPDATE_TASK and not UMA_UPDATE_TASK.done():
        UMA_UPDATE_TASK.cancel()
        try:
            await UMA_UPDATE_TASK
        except asyncio.CancelledError:
            pass
        uma_logger.info("[Shutdown] Uma Musume background tasks stopped.")

print("[INIT] uma_module.py fully loaded - all commands registered")
print("=" * 60)
