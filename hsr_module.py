import os
import aiosqlite
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from bot import bot
from datetime import datetime, timezone, timedelta
from global_config import ONGOING_EVENTS_CHANNELS, UPCOMING_EVENTS_CHANNELS, OWNER_USER_ID, MAIN_SERVER_ID
from hoyo_module import *
import logging

# Create a custom logger for HSR
hsr_logger = logging.getLogger("hsr")
hsr_logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

# File handler
log_file_path = os.path.join("logs", "hsr.log")
os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))

if not any(isinstance(h, logging.StreamHandler) for h in hsr_logger.handlers):
    hsr_logger.addHandler(console_handler)
if not any(isinstance(h, logging.FileHandler) for h in hsr_logger.handlers):
    hsr_logger.addHandler(file_handler)

hsr_logger.propagate = True

# Path to HSR-specific database
HSR_DB_PATH = os.path.join("data", "hsr_data.db")

# Ensure the database and tables exist
async def init_hsr_db():
    async with aiosqlite.connect(HSR_DB_PATH) as conn:
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
                asia_start TEXT,
                asia_end TEXT,
                america_start TEXT,
                america_end TEXT,
                europe_start TEXT,
                europe_end TEXT
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS event_messages (
                event_id INTEGER,
                channel_id TEXT,
                message_id TEXT,
                region TEXT,
                PRIMARY KEY (event_id, channel_id, region)
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_update_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_unix INTEGER,
                region TEXT,
                status TEXT DEFAULT 'pending'
            )
        ''')
        await conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_update_time_region ON scheduled_update_tasks (update_unix, region)
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS version_tracker (
                profile TEXT PRIMARY KEY,
                version TEXT,
                start_date TEXT
            )
        ''')
        await conn.commit()

SCHEDULED_UPDATE_TASKS = {}  # { (update_unix, region): asyncio.Task }

async def schedule_update_task(update_unix, region):
    """
    Schedules hsr_update_timers at update_unix for the given region.
    Avoids scheduling if a task exists within ±15 minutes for the same region.
    """
    async with aiosqlite.connect(HSR_DB_PATH) as conn:
        min_time = update_unix - 900
        max_time = update_unix + 900
        async with conn.execute(
            "SELECT 1 FROM scheduled_update_tasks WHERE update_unix BETWEEN ? AND ? AND region=?",
            (min_time, max_time, region)
        ) as cursor:
            if await cursor.fetchone():
                return
        await conn.execute(
            "INSERT OR IGNORE INTO scheduled_update_tasks (update_unix, region) VALUES (?, ?)",
            (update_unix, region)
        )
        await conn.commit()

    delay = update_unix - int(datetime.now(timezone.utc).timestamp())
    if delay > 0:
        task_key = (update_unix, region)
        if task_key in SCHEDULED_UPDATE_TASKS:
            return
        SCHEDULED_UPDATE_TASKS[task_key] = asyncio.create_task(run_update_after_delay(update_unix, region, delay))

async def periodic_hsr_cleanup():
    while True:
        await cleanup_old_update_tasks()
        await asyncio.sleep(86400)

async def run_update_after_delay(update_unix, region, delay):
    await asyncio.sleep(delay)
    guild = bot.get_guild(MAIN_SERVER_ID)
    if guild:
        await hsr_update_timers(guild, region)
    async with aiosqlite.connect(HSR_DB_PATH) as conn:
        await conn.execute(
            "UPDATE scheduled_update_tasks SET status='done' WHERE update_unix=? AND region=?",
            (update_unix, region)
        )
        await conn.commit()

async def load_scheduled_hsr_update_tasks():
    """
    Loads all pending scheduled update tasks from the DB and schedules them in memory.
    Executes ONE update per region on startup to refresh dashboards, then marks overdue tasks as done.
    """
    async with aiosqlite.connect(HSR_DB_PATH) as conn:
        now = int(datetime.now(timezone.utc).timestamp())
        async with conn.execute(
            "SELECT update_unix, region FROM scheduled_update_tasks WHERE status='pending'",
            ()
        ) as cursor:
            tasks = [(row[0], row[1]) async for row in cursor]
        
        # Group by region
        regions = set(region for _, region in tasks)
        
        for region in regions:
            region_tasks = [(unix, reg) for unix, reg in tasks if reg == region]
            overdue = [t for t in region_tasks if t[0] <= now]
            future = [t for t in region_tasks if t[0] > now]
            
            if overdue:
                hsr_logger.info(f"Found {len(overdue)} overdue tasks for region {region}. Executing one update...")
                main_guild = bot.get_guild(MAIN_SERVER_ID)
                if main_guild:
                    await hsr_update_timers(main_guild, region)
                
                for update_unix, reg in overdue:
                    await conn.execute(
                        "UPDATE scheduled_update_tasks SET status='done' WHERE update_unix=? AND region=?",
                        (update_unix, reg)
                    )
                await conn.commit()
                hsr_logger.info(f"Marked {len(overdue)} overdue tasks as done for region {region}.")
            
            for update_unix, reg in future:
                delay = update_unix - now
                task_key = (update_unix, reg)
                if task_key not in SCHEDULED_UPDATE_TASKS:
                    hsr_logger.info(f"Scheduling future update task for {update_unix} (<t:{update_unix}:F>) in region {reg}, delay={delay}s")
                    SCHEDULED_UPDATE_TASKS[task_key] = asyncio.create_task(run_update_after_delay(update_unix, reg, delay))

async def cleanup_old_update_tasks():
    cutoff = int(datetime.now(timezone.utc).timestamp()) - 86400
    async with aiosqlite.connect(HSR_DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM scheduled_update_tasks WHERE status='done' AND update_unix < ?",
            (cutoff,)
        )
        await conn.commit()

# --- Event Posting Helper ---
async def post_event_embed(channel, event, region):
    """Posts an embed for the event in the given channel for the specified region."""
    category = event.get("category", "").lower()
    if category == "banner":
        color = discord.Color.purple()
    elif category == "event":
        color = discord.Color.gold()
    elif category == "maintenance":
        color = discord.Color.red()
    else:
        color = discord.Color.default()
    
    # Use region-specific times
    start = event[f'{region.lower()}_start']
    end = event[f'{region.lower()}_end']
    
    embed = discord.Embed(
        title=f"{event['title']} ({region})",
        description=f"**Start:** <t:{start}:F>\n**End:** <t:{end}:F>",
        color=color
    )
    if event.get("image") and event["image"].startswith("http"):
        embed.set_image(url=event["image"])
    return await channel.send(embed=embed)

# --- Event Deletion Helper ---
async def delete_event_message(guild, channel_id, event_id, region):
    """Deletes the event message from the channel for the given region."""
    async with aiosqlite.connect(HSR_DB_PATH) as conn:
        async with conn.execute(
            "SELECT message_id FROM event_messages WHERE event_id=? AND channel_id=? AND region=?",
            (event_id, str(channel_id), region)
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
            "DELETE FROM event_messages WHERE event_id=? AND channel_id=? AND region=?",
            (event_id, str(channel_id), region)
        )
        await conn.commit()

# --- Event Upsert Helper ---
async def upsert_event_message(guild, channel, event, event_id, region):
    """Edits the event message if it exists, otherwise sends a new one."""
    async with aiosqlite.connect(HSR_DB_PATH) as conn:
        async with conn.execute(
            "SELECT message_id FROM event_messages WHERE event_id=? AND channel_id=? AND region=?",
            (event_id, str(channel.id), region)
        ) as cursor:
            row = await cursor.fetchone()
        
        category = event.get("category", "").lower()
        if category == "banner":
            color = discord.Color.purple()
        elif category == "event":
            color = discord.Color.gold()
        elif category == "maintenance":
            color = discord.Color.red()
        else:
            color = discord.Color.default()
        
        start = event[f'{region.lower()}_start']
        end = event[f'{region.lower()}_end']
        
        embed = discord.Embed(
            title=f"{event['title']} ({region})",
            description=f"**Start:** <t:{start}:F>\n**End:** <t:{end}:F>",
            color=color
        )
        if event.get("image") and event["image"].startswith("http"):
            embed.set_image(url=event["image"])
        
        msg = None
        if row and row[0]:
            try:
                msg = await channel.fetch_message(int(row[0]))
                await msg.edit(embed=embed)
                return
            except Exception:
                pass
        msg = await channel.send(embed=embed)
        await conn.execute(
            "REPLACE INTO event_messages (event_id, channel_id, message_id, region) VALUES (?, ?, ?, ?)",
            (event_id, str(channel.id), str(msg.id), region)
        )
        await conn.commit()

async def hsr_update_timers(_guild=None, region=None):
    """
    Updates HSR event dashboards for the specified region (or all regions if None).
    Groups regions with identical times into single embeds.
    Always operates on the main server's event channels.
    """
    main_guild = bot.get_guild(MAIN_SERVER_ID)
    if not main_guild:
        return
    
    now = int(datetime.now(timezone.utc).timestamp())
    ongoing_channel = main_guild.get_channel(ONGOING_EVENTS_CHANNELS.get("HSR"))
    upcoming_channel = main_guild.get_channel(UPCOMING_EVENTS_CHANNELS.get("HSR"))
    
    regions_to_update = [region] if region else ["ASIA", "NA", "EU"]

    async with aiosqlite.connect(HSR_DB_PATH) as conn:
        async with conn.execute(
            "SELECT id, title, image, category, asia_start, asia_end, america_start, america_end, europe_start, europe_end FROM events ORDER BY asia_start ASC"
        ) as cursor:
            events = [dict(
                id=row[0], title=row[1], image=row[2], category=row[3],
                asia_start=int(row[4]), asia_end=int(row[5]),
                america_start=int(row[6]), america_end=int(row[7]),
                europe_start=int(row[8]), europe_end=int(row[9])
            ) async for row in cursor]

        # Process each event
        for event in events:
            # Group regions by their start/end times
            time_groups = {}  # {(start, end): [regions]}
            for reg in ["ASIA", "NA", "EU"]:
                start = event[f'{reg.lower()}_start']
                end = event[f'{reg.lower()}_end']
                time_key = (start, end)
                if time_key not in time_groups:
                    time_groups[time_key] = []
                time_groups[time_key].append(reg)
            
            # For each unique time group, handle as one embed
            for (start, end), grouped_regions in time_groups.items():
                # Only process if this group contains a region we're updating
                if not any(r in regions_to_update for r in grouped_regions):
                    continue
                
                # Determine if event is ongoing or upcoming
                event_status = None
                if end < now:
                    # Delete ended events for all regions in this group
                    for reg in grouped_regions:
                        await delete_event_message(main_guild, ONGOING_EVENTS_CHANNELS.get("HSR"), event["id"], reg)
                        await delete_event_message(main_guild, UPCOMING_EVENTS_CHANNELS.get("HSR"), event["id"], reg)
                    
                    # Only delete from DB if ended in ALL regions
                    all_ended = all(
                        event[f'{r.lower()}_end'] < now 
                        for r in ["ASIA", "NA", "EU"]
                    )
                    if all_ended:
                        await conn.execute("DELETE FROM events WHERE id=?", (event["id"],))
                        await conn.commit()
                    continue
                elif start <= now < end:
                    event_status = "ongoing"
                else:
                    event_status = "upcoming"
                
                # Create embed with region labels
                category = event.get("category", "").lower()
                if category == "banner":
                    color = discord.Color.purple()
                elif category == "event":
                    color = discord.Color.gold()
                elif category == "maintenance":
                    color = discord.Color.red()
                else:
                    color = discord.Color.default()
                
                # Format region string
                if len(grouped_regions) == 3:
                    region_str = "All Regions"
                else:
                    region_str = ", ".join(grouped_regions)
                
                embed = discord.Embed(
                    title=f"{event['title']} ({region_str})",
                    description=f"**Start:** <t:{start}:F>\n**End:** <t:{end}:F>",
                    color=color
                )
                if event.get("image") and event["image"].startswith("http"):
                    embed.set_image(url=event["image"])
                
                # Post or update the embed
                target_channel = ongoing_channel if event_status == "ongoing" else upcoming_channel
                other_channel_id = UPCOMING_EVENTS_CHANNELS.get("HSR") if event_status == "ongoing" else ONGOING_EVENTS_CHANNELS.get("HSR")
                
                if target_channel:
                    # Use the first region in the group as the "primary" for message tracking
                    primary_region = grouped_regions[0]
                    await upsert_event_message(main_guild, target_channel, event, event["id"], primary_region)
                    
                    # Delete from the other channel for all regions in group
                    for reg in grouped_regions:
                        await delete_event_message(main_guild, other_channel_id, event["id"], reg)
# --- Add Event ---
async def add_hsr_event(ctx, event_data):
    """
    Adds an HSR event to the database and schedules notifications.
    event_data should have region-specific times already set.
    """
    async with aiosqlite.connect(HSR_DB_PATH) as conn:
        await conn.execute(
            '''INSERT INTO events (user_id, title, start_date, end_date, image, category, profile,
            asia_start, asia_end, america_start, america_end, europe_start, europe_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                str(ctx.author.id),
                event_data["title"],
                "",  # start_date not used for Hoyo games
                "",  # end_date not used for Hoyo games
                event_data["image"],
                event_data["category"],
                "HSR",
                event_data["asia_start"],
                event_data["asia_end"],
                event_data["america_start"],
                event_data["america_end"],
                event_data["europe_start"],
                event_data["europe_end"]
            )
        )
        await conn.commit()

    # Schedule notifications for each region
    from notification_handler import schedule_notifications_for_event
    for region, tz_key in [("NA", "america"), ("EU", "europe"), ("ASIA", "asia")]:
        event_for_notification = {
            'category': event_data['category'],
            'profile': "HSR",
            'title': event_data['title'],
            'start_date': str(event_data[f'{tz_key}_start']),
            'end_date': str(event_data[f'{tz_key}_end']),
            'region': region
        }
        await schedule_notifications_for_event(event_for_notification)

    # Schedule dashboard updates for each region
    try:
        for region, tz_key in [("NA", "america"), ("EU", "europe"), ("ASIA", "asia")]:
            start = int(event_data[f'{tz_key}_start'])
            end = int(event_data[f'{tz_key}_end'])
            await schedule_update_task(start, region.upper())
            await schedule_update_task(end, region.upper())
    except Exception as e:
        hsr_logger.error(f"Failed to schedule update tasks: {e}")

    await ctx.send(
        f"Added `{event_data['title']}` as **{event_data['category']}** for HSR!\n"
        f"Asia: <t:{event_data['asia_start']}:F> - <t:{event_data['asia_end']}:F>\n"
        f"America: <t:{event_data['america_start']}:F> - <t:{event_data['america_end']}:F>\n"
        f"Europe: <t:{event_data['europe_start']}:F> - <t:{event_data['europe_end']}:F>"
    )

# --- Manual Add Event Command ---
@commands.has_permissions(manage_guild=True)
@bot.command(name="hsr_add")
async def hsr_add(ctx, category: str, *, title: str):
    """
    Manually adds an HSR event.
    Usage: !hsr_add <category> <title>
    Category: Banner, Event, or Maintenance
    You will be prompted for start/end times and image.
    """
    category = category.capitalize()
    if category not in ["Banner", "Event", "Maintenance"]:
        await ctx.send("Category must be: Banner, Event, or Maintenance")
        return

    await ctx.send(f"Adding HSR {category}: `{title}`")
    await ctx.send("Enter start time (e.g. `2025/06/18 04:00 (UTC+8)`):")
    
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        msg = await bot.wait_for("message", timeout=120.0, check=check)
        start_str = msg.content.strip()
    except Exception:
        await ctx.send("Timeout. Cancelled.")
        return

    await ctx.send("Enter end time:")
    try:
        msg = await bot.wait_for("message", timeout=120.0, check=check)
        end_str = msg.content.strip()
    except Exception:
        await ctx.send("Timeout. Cancelled.")
        return

    await ctx.send("Enter image URL (or 'none'):")
    try:
        msg = await bot.wait_for("message", timeout=120.0, check=check)
        image = msg.content.strip() if msg.content.strip().lower() != "none" else None
    except Exception:
        image = None

    # Convert times to all regions
    start_times = await convert_to_all_timezones(start_str, db_path=HSR_DB_PATH, profile="HSR")
    end_times = await convert_to_all_timezones(end_str, db_path=HSR_DB_PATH, profile="HSR")

    if not start_times or not end_times:
        await ctx.send("Failed to parse times. Cancelled.")
        return

    event_data = {
        "title": title,
        "category": category,
        "image": image,
        "asia_start": start_times["Asia"][1],
        "asia_end": end_times["Asia"][1],
        "america_start": start_times["America"][1],
        "america_end": end_times["America"][1],
        "europe_start": start_times["Europe"][1],
        "europe_end": end_times["Europe"][1]
    }

    await add_hsr_event(ctx, event_data)
    await hsr_update_timers()

# --- Remove Event Command ---
@commands.has_permissions(manage_guild=True)
@bot.command(name="hsr_remove")
async def hsr_remove(ctx, *, title: str):
    """Removes an HSR event by title (case-insensitive)."""
    main_guild = bot.get_guild(MAIN_SERVER_ID)
    async with aiosqlite.connect(HSR_DB_PATH) as conn:
        async with conn.execute(
            "SELECT id, title, category FROM events WHERE LOWER(title)=?",
            (title.lower(),)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            await ctx.send(f"No event found with title '{title}'.")
            return
        event_id, event_title, event_category = row

        # Delete messages for all regions
        for region in ["ASIA", "NA", "EU"]:
            await delete_event_message(main_guild, ONGOING_EVENTS_CHANNELS.get("HSR"), event_id, region)
            await delete_event_message(main_guild, UPCOMING_EVENTS_CHANNELS.get("HSR"), event_id, region)

        await conn.execute("DELETE FROM events WHERE id=?", (event_id,))
        await conn.commit()

    from notification_handler import delete_notifications_for_event
    await delete_notifications_for_event(event_title, event_category, "HSR")

    await ctx.send(f"Deleted HSR event '{event_title}' and its notifications.")
    await hsr_update_timers()

# --- Manual Refresh Command ---
@commands.has_permissions(manage_guild=True)
@bot.command(name="hsr_refresh")
async def hsr_refresh(ctx):
    """Refreshes all HSR event dashboards."""
    await hsr_update_timers()
    await ctx.send("HSR event dashboards have been refreshed.")

# --- Dump DB Command ---
@bot.command(name="hsr_dump_db")
async def hsr_dump_db(ctx):
    """Sends the HSR database as text to the owner's DM."""
    if ctx.author.id != OWNER_USER_ID:
        await ctx.send("You do not have permission to use this command.")
        return

    if not os.path.exists(HSR_DB_PATH):
        await ctx.author.send("No HSR database file found.")
        return

    dump_lines = []
    async with aiosqlite.connect(HSR_DB_PATH) as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
            tables = [row[0] async for row in cursor]
        for table in tables:
            dump_lines.append(f"--- {table} ---")
            async with db.execute(f"SELECT * FROM {table}") as cursor:
                columns = [desc[0] for desc in cursor.description]
                dump_lines.append(", ".join(columns))
                async for row in cursor:
                    dump_lines.append(", ".join(str(x) for x in row))
            dump_lines.append("")

    text = "\n".join(dump_lines)
    chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
    owner = ctx.bot.get_user(OWNER_USER_ID)
    if not owner:
        owner = await ctx.bot.fetch_user(OWNER_USER_ID)
    for chunk in chunks:
        await owner.send(f"HSR DB Dump:\n```{chunk}```")

    await ctx.send("Database dump sent to your DM.")

# --- End of hsr_module.py ---