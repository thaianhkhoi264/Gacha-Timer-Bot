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

def get_image_hash(urls):
    """
    Generate a consistent hash from image URLs to ensure same images always get same filename.
    This prevents image mismatches after database resets.
    """
    import hashlib
    combined = "|".join(sorted(urls))  # Sort to ensure consistent order
    return hashlib.md5(combined.encode()).hexdigest()[:12]

def combine_images_vertically(img_url1, img_url2):
    """
    Downloads two images and combines them vertically.
    Returns the path to the saved combined image.
    Uses content-based filename to ensure consistency after DB resets.
    """
    if not PIL_AVAILABLE:
        uma_logger.warning("[Image] PIL not available, cannot combine images")
        return img_url1  # Return first image URL as fallback
    
    try:
        # Generate consistent filename based on input URLs
        img_hash = get_image_hash([img_url1, img_url2])
        os.makedirs(os.path.join("data", "combined_images"), exist_ok=True)
        filename = f"combined_v_{img_hash}.png"
        filepath = os.path.join("data", "combined_images", filename)
        
        # If already exists, return existing file
        if os.path.exists(filepath):
            uma_logger.info(f"[Image] Using cached combined image: {filepath}")
            return filepath
        
        # Download images
        response1 = requests.get(img_url1)
        response2 = requests.get(img_url2)
        
        img1 = Image.open(BytesIO(response1.content)).convert('RGBA')
        img2 = Image.open(BytesIO(response2.content)).convert('RGBA')
        
        # Get dimensions
        width = max(img1.width, img2.width)
        height = img1.height + img2.height
        
        # Create new image with transparency
        combined = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        combined.paste(img1, (0, 0), img1 if img1.mode == 'RGBA' else None)
        combined.paste(img2, (0, img1.height), img2 if img2.mode == 'RGBA' else None)
        
        # Save combined image
        combined.save(filepath, 'PNG')
        uma_logger.info(f"[Image] Combined images vertically saved to: {filepath}")
        
        return filepath
    except Exception as e:
        uma_logger.error(f"Failed to combine images vertically: {e}")
        return None

def combine_images_horizontally(img_urls):
    """
    Downloads multiple images and combines them horizontally.
    Used for Legend Race character images.
    Returns the path to the saved combined image.
    """
    if not PIL_AVAILABLE:
        uma_logger.warning("[Image] PIL not available, cannot combine images")
        return img_urls[0] if img_urls else None
    
    if not img_urls:
        return None
    
    if len(img_urls) == 1:
        return img_urls[0]  # Single image, just return URL
    
    try:
        # Generate consistent filename based on input URLs
        img_hash = get_image_hash(img_urls)
        os.makedirs(os.path.join("data", "combined_images"), exist_ok=True)
        filename = f"combined_h_{img_hash}.png"
        filepath = os.path.join("data", "combined_images", filename)
        
        # If already exists, return existing file
        if os.path.exists(filepath):
            uma_logger.info(f"[Image] Using cached horizontal combined image: {filepath}")
            return filepath
        
        # Download all images
        images = []
        for url in img_urls:
            try:
                response = requests.get(url)
                img = Image.open(BytesIO(response.content)).convert('RGBA')
                images.append(img)
            except Exception as e:
                uma_logger.warning(f"[Image] Failed to download {url}: {e}")
        
        if not images:
            return img_urls[0]  # Fallback to first URL
        
        if len(images) == 1:
            return img_urls[0]  # Only one image downloaded successfully
        
        # Calculate total dimensions
        total_width = sum(img.width for img in images)
        max_height = max(img.height for img in images)
        
        # Create new image with transparency
        combined = Image.new('RGBA', (total_width, max_height), (0, 0, 0, 0))
        
        # Paste images side by side
        x_offset = 0
        for img in images:
            # Center vertically if heights differ
            y_offset = (max_height - img.height) // 2
            combined.paste(img, (x_offset, y_offset), img if img.mode == 'RGBA' else None)
            x_offset += img.width
        
        # Save combined image
        combined.save(filepath, 'PNG')
        uma_logger.info(f"[Image] Combined {len(images)} images horizontally saved to: {filepath}")
        
        return filepath
    except Exception as e:
        uma_logger.error(f"Failed to combine images horizontally: {e}")
        return img_urls[0] if img_urls else None

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
    """Edits the event message if it exists and changed, otherwise sends a new one."""
    async with aiosqlite.connect(UMA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT message_id FROM event_messages WHERE event_id=? AND channel_id=?",
            (event_id, str(channel.id))
        ) as cursor:
            row = await cursor.fetchone()
        
        # Determine color based on event type
        color = get_event_color(event)
        
        # Debug: Log event details for troubleshooting
        uma_logger.debug(f"[Upsert] Event: {event['title']} | Category: {event.get('category', 'N/A')} | Color: {color}")
        
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
                
                # Check if embed actually changed to avoid unnecessary edits
                needs_update = False
                if msg.embeds:
                    old_embed = msg.embeds[0]
                    if (old_embed.title != embed.title or 
                        old_embed.description != embed.description or
                        old_embed.color != embed.color or
                        (old_embed.image.url if old_embed.image else None) != (event.get("image") if event.get("image", "").startswith("http") else None)):
                        needs_update = True
                else:
                    needs_update = True
                
                if not needs_update:
                    # Message unchanged, skip edit
                    return
                
                # Update message
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
            except Exception as e:
                print(f"[UMA] Failed to edit message: {e}")
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

async def clear_channel_messages(channel, event_ids_to_keep):
    """Clears messages in channel that don't correspond to events in the database.
    
    Args:
        channel: Discord channel to clean
        event_ids_to_keep: Set of event IDs that should have messages
    """
    try:
        deleted_count = 0
        async for message in channel.history(limit=100):
            if message.author.id != bot.user.id:
                continue
            
            should_delete = False
            event_id = None
            
            # Check if this message is in our database
            async with aiosqlite.connect(UMA_DB_PATH) as conn:
                async with conn.execute(
                    "SELECT event_id FROM event_messages WHERE message_id=?",
                    (str(message.id),)
                ) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        # Message is tracked in database
                        event_id = row[0]
                        if event_id not in event_ids_to_keep:
                            # Event no longer exists or is expired
                            should_delete = True
                    else:
                        # Message is NOT in database at all (orphaned after DB reset)
                        # Check if it looks like an event embed (has embeds)
                        if message.embeds:
                            should_delete = True
                            print(f"[UMA] Found untracked bot message with embed (ID: {message.id})")
                
                if should_delete:
                    try:
                        await message.delete()
                        deleted_count += 1
                        if event_id:
                            await conn.execute(
                                "DELETE FROM event_messages WHERE message_id=?",
                                (str(message.id),)
                            )
                            await conn.commit()
                            print(f"[UMA] Deleted orphaned message for event ID {event_id}")
                        else:
                            print(f"[UMA] Deleted untracked orphan message (ID: {message.id})")
                    except discord.NotFound:
                        print(f"[UMA] Message already deleted (ID: {message.id})")
                    except Exception as del_err:
                        print(f"[UMA] Failed to delete message {message.id}: {del_err}")
        
        if deleted_count > 0:
            print(f"[UMA] Cleared {deleted_count} orphaned messages from {channel.name}")
    except Exception as e:
        uma_logger.error(f"[Clear Channel] Failed to clear channel: {e}")
        import traceback
        traceback.print_exc()

async def uma_update_timers(_guild=None, force_update=False):
    """
    Updates Uma Musume event dashboards.
    Only shows events within 1 month from now.
    
    Args:
        _guild: Guild to update (unused, kept for compatibility)
        force_update: If True, forces update of all event embeds even if unchanged
    """
    uma_logger.info("[Update Timers] Starting dashboard update...")
    print("[UMA] Starting dashboard update...")
    
    if force_update:
        print("[UMA] ⚠️ FORCE UPDATE MODE ENABLED - Will delete and recreate all messages")
        uma_logger.info("[Update Timers] Force update mode enabled")
    
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
    one_month_earlier = now - (30 * 24 * 60 * 60)  # 30 days in the past
    
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
        # Fetch events that either:
        # 1. Haven't ended yet (ongoing or upcoming)
        # 2. Started within the past month (to catch recently started events)
        # This ensures we show events that started in the past but are still running
        async with conn.execute(
            "SELECT id, title, start_date, end_date, image, category, description FROM events WHERE end_date >= ? OR start_date >= ? ORDER BY start_date ASC",
            (now, one_month_earlier)
        ) as cursor:
            events = [dict(
                id=row[0], title=row[1], start=int(row[2]), end=int(row[3]), 
                image=row[4], category=row[5], description=row[6]
            ) async for row in cursor]
        
        uma_logger.info(f"[Update Timers] Fetched {len(events)} events from database")
        print(f"[UMA] Fetched {len(events)} events from database")
        
        # Clear orphaned messages (handles database resets)
        event_ids_to_keep = {event["id"] for event in events}
        if ongoing_channel:
            await clear_channel_messages(ongoing_channel, event_ids_to_keep)
        if upcoming_channel:
            await clear_channel_messages(upcoming_channel, event_ids_to_keep)
        
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
            
            # Skip upcoming events more than 1 month away (but keep ongoing events regardless of start date)
            if event["start"] > one_month_later and event["end"] > one_month_later:
                skipped_count += 1
                print(f"[UMA] SKIPPED (>1 month away): '{event['title']}' starts at {start_dt}")
                continue
            
            # Ongoing events (includes events that started in the past but haven't ended)
            if event["start"] <= now < event["end"]:
                print(f"[UMA] Event '{event['title']}' is ONGOING (start: {event['start']}, end: {event['end']}, now: {now})")
                await delete_event_message(main_guild, UPCOMING_EVENTS_CHANNELS["UMA"], event["id"])
                if ongoing_channel:
                    if force_update:
                        # Force message update by deleting and recreating
                        await delete_event_message(main_guild, ONGOING_EVENTS_CHANNELS["UMA"], event["id"])
                    await upsert_event_message(main_guild, ongoing_channel, event, event["id"])
                    ongoing_count += 1
                    uma_logger.info(f"[Update Timers] Posted ongoing event: {event['title']}")
                    print(f"[UMA] Posted to ongoing channel: {event['title']}")
            
            # Upcoming events (within 1 month)
            elif event["start"] > now and event["start"] <= one_month_later:
                print(f"[UMA] Event '{event['title']}' is UPCOMING (start: {event['start']}, now: {now})")
                if upcoming_channel:
                    if force_update:
                        # Force message update by deleting and recreating
                        await delete_event_message(main_guild, UPCOMING_EVENTS_CHANNELS["UMA"], event["id"])
                    await upsert_event_message(main_guild, upcoming_channel, event, event["id"])
                    upcoming_count += 1
                    uma_logger.info(f"[Update Timers] Posted upcoming event: {event['title']}")
                    print(f"[UMA] Posted to upcoming channel: {event['title']}")
                await delete_event_message(main_guild, ONGOING_EVENTS_CHANNELS["UMA"], event["id"])
        
        uma_logger.info(f"[Update Timers] Summary - Ongoing: {ongoing_count}, Upcoming: {upcoming_count}, Deleted: {deleted_count}, Skipped (>1mo): {skipped_count}")
    
    # Update control panel if events were deleted
    if deleted_count > 0:
        uma_logger.info("[uma_update_timers] Events were deleted, updating control panel...")
        try:
            from control_panel import update_control_panel_messages
            await update_control_panel_messages("UMA")
            uma_logger.info("[uma_update_timers] Control panel updated.")
        except Exception as e:
            uma_logger.error(f"[uma_update_timers] Failed to update control panel: {e}")

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
    print(f"[UMA] Scheduling notifications for: {event_data['title']} (start: {event_data['start']})")
    try:
        await schedule_notifications_for_event(event_for_notification)
        print(f"[UMA] Notifications scheduled successfully for: {event_data['title']}")
    except Exception as e:
        print(f"[UMA] ERROR scheduling notifications: {e}")
        uma_logger.error(f"Failed to schedule notifications for {event_data['title']}: {e}")
    
    # Update control panel to show new event in Remove/Edit/Notif panels
    uma_logger.info("[add_uma_event] Updating control panel with new event...")
    try:
        from control_panel import update_control_panel_messages
        await update_control_panel_messages("UMA")
        uma_logger.info("[add_uma_event] Control panel updated.")
    except Exception as e:
        uma_logger.error(f"[add_uma_event] Failed to update control panel: {e}")

print("[INIT] Functions defined, now registering bot commands...")

@commands.has_permissions(manage_guild=True)
@bot.command(name="uma_force_refresh")
async def uma_force_refresh(ctx):
    """Forces a complete refresh: updates all events from timeline and reschedules all notifications."""
    await ctx.send("🔄 Force refreshing Uma Musume events...")
    print("[UMA] Force refresh triggered by user command")
    
    # Import and run the update
    from uma_handler import update_uma_events
    try:
        await update_uma_events()
        
        # Force refresh all embeds with new colors/titles
        print("[UMA] Force updating all event embeds...")
        await uma_update_timers(force_update=True)
        
        # Reschedule notifications for ALL events in database
        from notification_handler import schedule_notifications_for_event
        async with aiosqlite.connect(UMA_DB_PATH) as conn:
            async with conn.execute(
                "SELECT id, title, category, start_date, end_date FROM events WHERE profile='UMA'"
            ) as cursor:
                rows = await cursor.fetchall()
        
        rescheduled = 0
        for row in rows:
            event_id, title, category, start_date, end_date = row
            event_for_notification = {
                'category': category,
                'profile': "UMA",
                'title': title,
                'start_date': int(start_date),
                'end_date': int(end_date)
            }
            try:
                await schedule_notifications_for_event(event_for_notification)
                rescheduled += 1
            except Exception as e:
                print(f"[UMA] Failed to reschedule notifications for {title}: {e}")
        
        await ctx.send(f"✅ Refresh complete! Rescheduled notifications for {rescheduled} events.")
        print(f"[UMA] Force refresh complete - {rescheduled} notifications rescheduled")
    except Exception as e:
        await ctx.send(f"❌ Error during refresh: {e}")
        print(f"[UMA] Force refresh failed: {e}")
        import traceback
        traceback.print_exc()

@bot.command(name="uma_debug")
async def uma_debug(ctx):
    """
    Debug command: Parses uma.moe/timeline and DMs the owner with detailed parsing information.
    Shows raw HTML structure, extracted events, and how they're being processed.
    """
    # Only allow owner to run this
    if ctx.author.id != OWNER_USER_ID:
        await ctx.send("❌ This command is restricted to the bot owner.")
        return
    
    await ctx.send("🔍 Running Uma debug parser... Results will be sent to your DMs.")
    
    try:
        from playwright.async_api import async_playwright
        
        owner = await bot.fetch_user(OWNER_USER_ID)
        if not owner:
            await ctx.send("❌ Could not find owner user.")
            return
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://uma.moe/timeline", timeout=60000)
            await page.wait_for_load_state("networkidle")
            
            # Scroll to load events (simplified version)
            timeline = await page.query_selector('.timeline-container')
            if timeline:
                for _ in range(5):
                    await timeline.evaluate("el => el.scrollBy(400, 0)")
                    await asyncio.sleep(0.5)
                for _ in range(5):
                    await timeline.evaluate("el => el.scrollBy(-400, 0)")
                    await asyncio.sleep(0.5)
            
            event_items = await page.query_selector_all('.timeline-item.timeline-event')
            
            # Build debug output
            debug_output = []
            debug_output.append(f"**=== UMA DEBUG REPORT ===**")
            debug_output.append(f"**Total events found on page:** {len(event_items)}\n")
            
            event_summaries = []
            
            for idx, item in enumerate(event_items):
                if idx >= 30:  # Limit to 30 events to avoid message length issues
                    debug_output.append(f"\n... and {len(event_items) - 30} more events")
                    break
                
                # Get full text content
                full_text = await item.inner_text()
                lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                
                # Get title element specifically
                title_tag = await item.query_selector('.event-title')
                title_text = (await title_tag.inner_text()).strip() if title_tag else "NO TITLE FOUND"
                
                # Get date element
                date_tag = await item.query_selector('.event-date')
                date_text = (await date_tag.inner_text()).strip() if date_tag else "NO DATE FOUND"
                
                # Get ALL images (Legend Race can have multiple)
                img_tags = await item.query_selector_all('.event-image img')
                img_srcs = []
                for img_tag in img_tags:
                    src = await img_tag.get_attribute("src")
                    if src:
                        img_srcs.append(src)
                
                # Detect event type from full text
                full_upper = full_text.upper()
                event_type = "UNKNOWN"
                if "CHARACTER BANNER" in full_upper:
                    event_type = "CHARACTER BANNER"
                elif "SUPPORT CARD BANNER" in full_upper:
                    event_type = "SUPPORT CARD BANNER"
                elif "STORY EVENT" in full_upper:
                    event_type = "STORY EVENT"
                elif "LEGEND RACE" in full_upper:
                    event_type = "LEGEND RACE"
                elif "CHAMPIONS MEETING" in full_upper:
                    event_type = "CHAMPIONS MEETING"
                elif "PAID BANNER" in full_upper:
                    event_type = "PAID BANNER"
                
                # Find names for banners
                detected_names = []
                if event_type in ["CHARACTER BANNER", "SUPPORT CARD BANNER"]:
                    # Find date line index
                    date_idx = None
                    for i, line in enumerate(lines):
                        if "–" in line and "202" in line:
                            date_idx = i
                            break
                    
                    if date_idx is not None:
                        for i in range(date_idx + 1, min(date_idx + 6, len(lines))):
                            name = lines[i]
                            if name and len(name) < 50 and name not in ["CHARACTERS:", "SUPPORT CARDS:", "CHARACTER BANNER", "SUPPORT CARD BANNER"]:
                                detected_names.append(name)
                
                # Build summary for this event
                summary = []
                summary.append(f"**Event #{idx + 1}**")
                summary.append(f"  Type: `{event_type}`")
                summary.append(f"  Title: `{title_text[:80]}{'...' if len(title_text) > 80 else ''}`")
                summary.append(f"  Date: `{date_text}`")
                if detected_names:
                    summary.append(f"  Detected Names: `{', '.join(detected_names)}`")
                # Show image count and list
                summary.append(f"  Images ({len(img_srcs)}): `{img_srcs}`" if img_srcs else "  Images: None")
                summary.append(f"  Raw Lines: `{lines}`")
                
                event_summaries.append("\n".join(summary))
            
            await browser.close()
            
            # Send results in chunks (Discord has 2000 char limit)
            header_msg = "\n".join(debug_output[:3])
            await owner.send(header_msg)
            
            current_chunk = ""
            for summary in event_summaries:
                if len(current_chunk) + len(summary) + 2 > 1900:
                    await owner.send(current_chunk)
                    current_chunk = summary
                else:
                    current_chunk += "\n\n" + summary if current_chunk else summary
            
            if current_chunk:
                await owner.send(current_chunk)
            
            await owner.send("**=== END OF DEBUG REPORT ===**")
            await ctx.send("✅ Debug report sent to your DMs!")
            
    except Exception as e:
        import traceback
        error_msg = f"❌ Debug failed: {e}\n```{traceback.format_exc()[:1500]}```"
        await ctx.send(error_msg)

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
    
    # Refresh dashboard after removing event
    uma_logger.info("[uma_remove] Refreshing dashboard after removing event...")
    await uma_update_timers()
    uma_logger.info("[uma_remove] Dashboard refresh completed.")
    
    # Update control panel to remove event from lists
    uma_logger.info("[uma_remove] Updating control panel after removing event...")
    try:
        from control_panel import update_control_panel_messages
        await update_control_panel_messages("UMA")
        uma_logger.info("[uma_remove] Control panel updated.")
    except Exception as e:
        uma_logger.error(f"[uma_remove] Failed to update control panel: {e}")
    await uma_update_timers()

print("[INIT] uma_remove command registered")
print("[INIT] Defining uma_edit command...")

@commands.has_permissions(manage_guild=True)
@bot.command(name="uma_edit")
async def uma_edit(ctx, title: str, item: str, *, value: str):
    """
    Edits an Uma Musume event in the database.
    Usage: !uma_edit "<title>" <item> <value>
    Allowed items: start, end, category, profile, image, title, description
    For start/end, accepts UNIX timestamp or "YYYY-MM-DD HH:MM" (will prompt for timezone if missing).
    """
    allowed_items = ["start", "end", "category", "profile", "image", "title", "description"]
    
    async with aiosqlite.connect(UMA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT id, title, category, profile FROM events WHERE LOWER(title)=?",
            (title.lower(),)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            await ctx.send(f"No event found with the title `{title}`.")
            return
        event_id, old_title, old_category, old_profile = row
        
        # Edit start/end times
        if item.lower() in ("start", "end"):
            # Try to parse as unix timestamp, else as date string
            try:
                unix_time = int(value)
            except ValueError:
                # Prompt for timezone if not present
                import re
                tz_match = re.search(r'(UTC[+-]\d+|GMT[+-]\d+|[A-Za-z]+/[A-Za-z_]+)', value)
                if tz_match:
                    timezone_str = tz_match.group(1)
                else:
                    await ctx.send("No timezone detected. Please enter the timezone for this event (e.g. `Asia/Tokyo`, `UTC+9`, etc.):")
                    def check(m): return m.author == ctx.author and m.channel == ctx.channel
                    try:
                        msg = await bot.wait_for("message", timeout=60.0, check=check)
                        timezone_str = msg.content.strip()
                    except Exception:
                        await ctx.send("No timezone provided. Cancelling.")
                        return
                # Split date/time from value
                date_time = value.split()
                if len(date_time) == 2:
                    date, time = date_time
                else:
                    await ctx.send("Invalid date/time format. Use `YYYY-MM-DD HH:MM`.")
                    return
                from database_handler import convert_to_unix_tz
                unix_time = convert_to_unix_tz(date, time, timezone_str)
            # Update start or end
            if item.lower() == "start":
                await conn.execute("UPDATE events SET start_date=? WHERE id=?", (str(unix_time), event_id))
            else:
                await conn.execute("UPDATE events SET end_date=? WHERE id=?", (str(unix_time), event_id))
            await conn.commit()
            await ctx.send(f"Updated `{item}` for `{old_title}` to `{value}`.")
        # Edit other fields
        elif item.lower() == "category":
            await conn.execute("UPDATE events SET category=? WHERE id=?", (value, event_id))
            await conn.commit()
            await ctx.send(f"Updated `category` for `{old_title}` to `{value}`.")
        elif item.lower() == "profile":
            await conn.execute("UPDATE events SET profile=? WHERE id=?", (value.upper(), event_id))
            await conn.commit()
            await ctx.send(f"Updated `profile` for `{old_title}` to `{value.upper()}`.")
        elif item.lower() == "image":
            await conn.execute("UPDATE events SET image=? WHERE id=?", (value, event_id))
            await conn.commit()
            await ctx.send(f"Updated `image` for `{old_title}`.")
        elif item.lower() == "title":
            await conn.execute("UPDATE events SET title=? WHERE id=?", (value, event_id))
            await conn.commit()
            await ctx.send(f"Updated `title` for `{old_title}` to `{value}`.")
        elif item.lower() == "description":
            await conn.execute("UPDATE events SET description=? WHERE id=?", (value, event_id))
            await conn.commit()
            await ctx.send(f"Updated `description` for `{old_title}`.")
        else:
            await ctx.send(f"Cannot edit `{item}`. Only {', '.join(allowed_items)} can be edited.")
            return
    
    # Delete and reschedule notifications
    from notification_handler import delete_notifications_for_event, schedule_notifications_for_event
    await delete_notifications_for_event(old_title, old_category, old_profile)
    
    # Fetch updated event info for notification rescheduling
    async with aiosqlite.connect(UMA_DB_PATH) as conn:
        async with conn.execute(
            "SELECT title, start_date, end_date, category, profile FROM events WHERE id=?",
            (event_id,)
        ) as cursor:
            updated = await cursor.fetchone()
    if updated:
        new_title, new_start, new_end, new_category, new_profile = updated
        event_for_notification = {
            'category': new_category,
            'profile': new_profile,
            'title': new_title,
            'start_date': str(new_start),
            'end_date': str(new_end)
        }
        await schedule_notifications_for_event(event_for_notification)
    
    # Refresh dashboard after editing event
    uma_logger.info("[uma_edit] Refreshing dashboard after editing event...")
    await uma_update_timers()
    uma_logger.info("[uma_edit] Dashboard refresh completed.")
    
    # Update control panel to reflect edits
    uma_logger.info("[uma_edit] Updating control panel after editing event...")
    try:
        from control_panel import update_control_panel_messages
        await update_control_panel_messages("UMA")
        uma_logger.info("[uma_edit] Control panel updated.")
    except Exception as e:
        uma_logger.error(f"[uma_edit] Failed to update control panel: {e}")

print("[INIT] uma_edit command registered")
print("[INIT] Defining uma_force_refresh command...")

@commands.has_permissions(manage_guild=True)
@bot.command(name="uma_refresh")
async def uma_refresh(ctx, force: str = ""):
    """Refreshes Uma Musume event dashboards. Use 'force' to update all embeds."""
    force_update = (force.lower() == "force")
    await ctx.send("🔄 Refreshing Uma Musume dashboards...")
    await uma_update_timers(force_update=force_update)
    msg = "✅ Dashboards refreshed!"
    if force_update:
        msg += " (All embeds force-updated with new colors/titles)"
    await ctx.send(msg)

print("[INIT] uma_refresh command registered")
print("[INIT] Defining uma_update command...")

async def uma_notification_refresh(message):
    """
    Call this from main.py's on_message to auto-refresh dashboard when bot posts notifications.
    Returns True if message was in UMA notification channel and refresh was triggered.
    """
    from global_config import NOTIFICATION_CHANNELS
    
    # Only trigger for bot's own messages
    if not message.author.bot or message.author.id != bot.user.id:
        return False
    
    # Check if message is in UMA notification channel
    uma_notif_channel_id = NOTIFICATION_CHANNELS.get("UMA")
    if not uma_notif_channel_id or message.channel.id != uma_notif_channel_id:
        return False
    
    uma_logger.info("[Auto-Refresh] Bot sent notification in UMA channel, refreshing dashboard...")
    await uma_update_timers()
    uma_logger.info("[Auto-Refresh] Dashboard refreshed for UMA.")
    return True

@commands.has_permissions(administrator=True)
@bot.command(name="uma_update")
async def uma_update(ctx):
    """Downloads and updates Uma Musume events from uma.moe/timeline."""
    await ctx.send("🔄 Updating Uma Musume events from timeline... This may take a few minutes.")
    
    try:
        from uma_handler import update_uma_events
        await update_uma_events()
        await ctx.send("✅ Uma Musume events updated! Use `!uma_refresh force` to update all embeds with new colors/titles.")
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
        
        # Database already initialized in main.py before control panels
        # No need to initialize again here
        
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


# ==================== GAMETORA DEBUG COMMANDS ====================

@bot.command(name="uma_gametora_debug")
async def uma_gametora_debug(ctx):
    """
    Debug command: Scrapes GameTora and shows what the bot sees.
    Shows raw banner cards, IDs, image URLs, and any parsing issues.
    Results are sent via DM.
    """
    # Only allow owner to run this
    if ctx.author.id != OWNER_USER_ID:
        await ctx.send("❌ This command is restricted to the bot owner.")
        return
    
    await ctx.send("🔍 Running GameTora debug scraper... Results will be sent to your DMs.")
    
    try:
        from playwright.async_api import async_playwright
        import re
        
        owner = await bot.fetch_user(OWNER_USER_ID)
        if not owner:
            await ctx.send("❌ Could not find owner user.")
            return
        
        debug_messages = []
        debug_messages.append("**=== GAMETORA DEBUG REPORT ===**")
        debug_messages.append(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # ===== JP SERVER =====
            debug_messages.append("**--- JP SERVER (Banner Data) ---**")
            jp_url = "https://gametora.com/umamusume/gacha/history?server=ja&type=all&year=all"
            debug_messages.append(f"URL: `{jp_url}`")
            
            try:
                await page.goto(jp_url, timeout=90000, wait_until="domcontentloaded")
                await asyncio.sleep(5)
                
                # Get page title to verify load
                page_title = await page.title()
                debug_messages.append(f"Page Title: `{page_title}`")
                
                # Find banner containers using the actual CSS class
                banner_containers = await page.query_selector_all('.sc-37bc0b3c-0')
                debug_messages.append(f"**Banner containers (.sc-37bc0b3c-0) found:** {len(banner_containers)}")
                
                # Also check banner images
                banner_images = await page.query_selector_all('img[src*="img_bnr_gacha_"]')
                debug_messages.append(f"**Banner images found:** {len(banner_images)}")
                
                jp_banners = []
                for idx, container in enumerate(banner_containers):
                    if idx >= 15:  # Limit to first 15 for DM
                        debug_messages.append(f"... and {len(banner_containers) - 15} more banners")
                        break
                    
                    try:
                        # Get banner image src
                        img_tag = await container.query_selector('img[src*="img_bnr_gacha_"]')
                        img_src = await img_tag.get_attribute('src') if img_tag else "NO IMG TAG"
                        
                        # Extract banner ID
                        banner_id = "NO ID"
                        if img_src and "img_bnr_gacha_" in img_src:
                            match = re.search(r'img_bnr_gacha_(\d+)\.png', img_src)
                            if match:
                                banner_id = match.group(1)
                        
                        # Get character/support list
                        items_list = await container.query_selector('ul.sc-37bc0b3c-3')
                        item_names = []
                        
                        if items_list:
                            list_items = await items_list.query_selector_all('li')
                            for li in list_items:
                                name_span = await li.query_selector('.gacha_link_alt__mZW_P, span.sc-37bc0b3c-5')
                                if name_span:
                                    name_text = (await name_span.inner_text()).strip()
                                    if name_text:
                                        item_names.append(name_text)
                        
                        # Get container text for type detection
                        container_text = await container.inner_text()
                        banner_type = "Unknown"
                        if "Character" in container_text:
                            banner_type = "Character"
                        elif "Support" in container_text or item_names:
                            banner_type = "Support (assumed)"
                        
                        description = ", ".join(item_names[:3]) if item_names else "No items found"
                        
                        jp_banners.append({
                            "idx": idx + 1,
                            "id": banner_id,
                            "type": banner_type,
                            "img_src": img_src[:80] if img_src else "None",
                            "desc": description,
                            "items": item_names
                        })
                    except Exception as card_err:
                        jp_banners.append({
                            "idx": idx + 1,
                            "error": str(card_err)
                        })
                
                for b in jp_banners:
                    if "error" in b:
                        debug_messages.append(f"  #{b['idx']}: ❌ Error: `{b['error']}`")
                    else:
                        debug_messages.append(f"  **#{b['idx']}** ID:`{b['id']}` Type:`{b['type']}`")
                        debug_messages.append(f"    Img: `{b['img_src']}`")
                        debug_messages.append(f"    Items: `{b['items']}`")
                
            except Exception as jp_err:
                debug_messages.append(f"❌ JP scrape error: `{jp_err}`")
            
            # ===== GLOBAL SERVER =====
            debug_messages.append("\n**--- GLOBAL SERVER (Images) ---**")
            global_url = "https://gametora.com/umamusume/gacha/history?server=en&type=all&year=all"
            debug_messages.append(f"URL: `{global_url}`")
            
            try:
                await page.goto(global_url, timeout=90000, wait_until="domcontentloaded")
                await asyncio.sleep(5)
                
                page_title = await page.title()
                debug_messages.append(f"Page Title: `{page_title}`")
                
                banner_containers = await page.query_selector_all('.sc-37bc0b3c-0')
                debug_messages.append(f"**Banner containers found:** {len(banner_containers)}")
                
                global_banners = []
                for idx, container in enumerate(banner_containers):
                    if idx >= 10:  # Limit to first 10 for DM
                        debug_messages.append(f"... and {len(banner_containers) - 10} more banners")
                        break
                    
                    try:
                        img_tag = await container.query_selector('img[src*="img_bnr_gacha_"]')
                        img_src = await img_tag.get_attribute('src') if img_tag else "NO IMG TAG"
                        
                        banner_id = "NO ID"
                        if img_src and "img_bnr_gacha_" in img_src:
                            match = re.search(r'img_bnr_gacha_(\d+)\.png', img_src)
                            if match:
                                banner_id = match.group(1)
                        
                        global_banners.append({
                            "idx": idx + 1,
                            "id": banner_id,
                            "img_src": img_src
                        })
                    except Exception as card_err:
                        global_banners.append({
                            "idx": idx + 1,
                            "error": str(card_err)
                        })
                
                for b in global_banners:
                    if "error" in b:
                        debug_messages.append(f"  #{b['idx']}: ❌ Error: `{b['error']}`")
                    else:
                        debug_messages.append(f"  **#{b['idx']}** ID:`{b['id']}` Img:`{b['img_src'][:60] if b['img_src'] else 'None'}`")
                
            except Exception as global_err:
                debug_messages.append(f"❌ Global scrape error: `{global_err}`")
            
            await browser.close()
        
        debug_messages.append("\n**=== END OF GAMETORA DEBUG REPORT ===**")
        
        # Send results in chunks
        current_chunk = ""
        for msg in debug_messages:
            if len(current_chunk) + len(msg) + 2 > 1900:
                await owner.send(current_chunk)
                current_chunk = msg
            else:
                current_chunk += "\n" + msg if current_chunk else msg
        
        if current_chunk:
            await owner.send(current_chunk)
        
        await ctx.send("✅ GameTora debug report sent to your DMs!")
        
    except Exception as e:
        import traceback
        error_msg = f"❌ GameTora debug failed: {e}\n```{traceback.format_exc()[:1500]}```"
        await ctx.send(error_msg)


@bot.command(name="uma_gametora_status")
async def uma_gametora_status(ctx):
    """
    Shows GameTora database status: counts, recent entries, downloaded images.
    Results are sent via DM.
    """
    # Only allow owner to run this
    if ctx.author.id != OWNER_USER_ID:
        await ctx.send("❌ This command is restricted to the bot owner.")
        return
    
    await ctx.send("📊 Checking GameTora database status... Results will be sent to your DMs.")
    
    try:
        from uma_handler import GAMETORA_DB_PATH, GAMETORA_IMAGES_PATH
        
        owner = await bot.fetch_user(OWNER_USER_ID)
        if not owner:
            await ctx.send("❌ Could not find owner user.")
            return
        
        debug_messages = []
        debug_messages.append("**=== GAMETORA DATABASE STATUS ===**")
        debug_messages.append(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")
        
        # Check if database exists
        db_exists = os.path.exists(GAMETORA_DB_PATH)
        debug_messages.append(f"**Database Path:** `{GAMETORA_DB_PATH}`")
        debug_messages.append(f"**Database Exists:** {'✅ Yes' if db_exists else '❌ No'}")
        
        if db_exists:
            db_size = os.path.getsize(GAMETORA_DB_PATH)
            debug_messages.append(f"**Database Size:** {db_size / 1024:.2f} KB")
            
            async with aiosqlite.connect(GAMETORA_DB_PATH) as conn:
                # Count banners
                async with conn.execute("SELECT COUNT(*) FROM banners") as cursor:
                    banner_count = (await cursor.fetchone())[0]
                debug_messages.append(f"\n**📌 Banners:** {banner_count}")
                
                # Count characters
                async with conn.execute("SELECT COUNT(*) FROM characters") as cursor:
                    char_count = (await cursor.fetchone())[0]
                debug_messages.append(f"**👤 Characters:** {char_count}")
                
                # Count support cards
                async with conn.execute("SELECT COUNT(*) FROM support_cards") as cursor:
                    support_count = (await cursor.fetchone())[0]
                debug_messages.append(f"**🃏 Support Cards:** {support_count}")
                
                # Count global banner images
                async with conn.execute("SELECT COUNT(*) FROM global_banner_images") as cursor:
                    img_count = (await cursor.fetchone())[0]
                debug_messages.append(f"**🖼️ Global Banner Image Links:** {img_count}")
                
                # Get recent banners (last 5)
                debug_messages.append("\n**--- Recent Banners (Last 5) ---**")
                async with conn.execute(
                    "SELECT banner_id, banner_type, description FROM banners ORDER BY ROWID DESC LIMIT 5"
                ) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        debug_messages.append(f"  ID:`{row[0]}` Type:`{row[1]}` Desc:`{(row[2] or '')[:50]}`")
                
                if not rows:
                    debug_messages.append("  (No banners in database)")
                
                # Get metadata
                debug_messages.append("\n**--- Metadata ---**")
                async with conn.execute("SELECT key, value FROM metadata") as cursor:
                    meta_rows = await cursor.fetchall()
                    for row in meta_rows:
                        debug_messages.append(f"  `{row[0]}`: `{row[1]}`")
                
                if not meta_rows:
                    debug_messages.append("  (No metadata)")
        
        # Check images folder
        debug_messages.append(f"\n**--- Downloaded Images ---**")
        debug_messages.append(f"**Images Path:** `{GAMETORA_IMAGES_PATH}`")
        
        images_folder_exists = os.path.exists(GAMETORA_IMAGES_PATH)
        debug_messages.append(f"**Folder Exists:** {'✅ Yes' if images_folder_exists else '❌ No'}")
        
        if images_folder_exists:
            image_files = [f for f in os.listdir(GAMETORA_IMAGES_PATH) if f.endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            debug_messages.append(f"**Image Count:** {len(image_files)}")
            
            # List first 10 images
            if image_files:
                debug_messages.append("**Sample Images:**")
                for img in image_files[:10]:
                    img_path = os.path.join(GAMETORA_IMAGES_PATH, img)
                    img_size = os.path.getsize(img_path)
                    debug_messages.append(f"  `{img}` ({img_size / 1024:.1f} KB)")
                
                if len(image_files) > 10:
                    debug_messages.append(f"  ... and {len(image_files) - 10} more images")
            else:
                debug_messages.append("  (No images downloaded)")
        
        debug_messages.append("\n**=== END OF STATUS REPORT ===**")
        
        # Send results in chunks
        current_chunk = ""
        for msg in debug_messages:
            if len(current_chunk) + len(msg) + 2 > 1900:
                await owner.send(current_chunk)
                current_chunk = msg
            else:
                current_chunk += "\n" + msg if current_chunk else msg
        
        if current_chunk:
            await owner.send(current_chunk)
        
        await ctx.send("✅ GameTora status report sent to your DMs!")
        
    except Exception as e:
        import traceback
        error_msg = f"❌ Status check failed: {e}\n```{traceback.format_exc()[:1500]}```"
        await ctx.send(error_msg)


@bot.command(name="uma_gametora_refresh")
async def uma_gametora_refresh(ctx):
    """
    Force a full GameTora database refresh, ignoring incremental checks.
    """
    # Only allow owner to run this
    if ctx.author.id != OWNER_USER_ID:
        await ctx.send("❌ This command is restricted to the bot owner.")
        return
    
    await ctx.send("🔄 Starting forced GameTora database refresh... This may take a few minutes.")
    
    try:
        from uma_handler import update_gametora_database
        
        result = await update_gametora_database(force_full_scan=True)
        
        if result:
            jp_result = result.get("jp", {})
            global_result = result.get("global", {})
            
            msg = "✅ **GameTora Refresh Complete!**\n"
            if jp_result:
                msg += f"  JP: {jp_result.get('banners', 0)} banners, {jp_result.get('characters', 0)} chars, {jp_result.get('support_cards', 0)} supports\n"
            else:
                msg += "  JP: ❌ Failed or skipped\n"
            
            if global_result:
                msg += f"  Global: {global_result.get('images_saved', 0)} images saved"
            else:
                msg += "  Global: ❌ Failed or skipped"
            
            await ctx.send(msg)
        else:
            await ctx.send("❌ GameTora refresh returned no results.")
            
    except Exception as e:
        import traceback
        error_msg = f"❌ Refresh failed: {e}\n```{traceback.format_exc()[:1500]}```"
        await ctx.send(error_msg)


print("[INIT] uma_module.py fully loaded - all commands registered")
print("=" * 60)
