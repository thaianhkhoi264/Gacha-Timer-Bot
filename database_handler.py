import discord
from discord import app_commands
from discord.ext import commands
from modules import *
from bot import bot
import asyncio
import logging
import dateparser
import re
from datetime import datetime, timedelta, timezone

logging.getLogger("aiosqlite").setLevel(logging.WARNING)

# Initialize the database
def init_db():
    import sqlite3
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Event data
    c.execute('''CREATE TABLE IF NOT EXISTS user_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    server_id TEXT,
                    title TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    image TEXT,
                    category TEXT,
                    is_hyv INTEGER DEFAULT 0,
                    asia_start TEXT,
                    asia_end TEXT,
                    america_start TEXT,
                    america_end TEXT,
                    europe_start TEXT,
                    europe_end TEXT,
                    profile TEXT
                )''')
    # Event messages IDs
    c.execute('''CREATE TABLE IF NOT EXISTS event_messages (
                    event_id INTEGER,
                    server_id TEXT,
                    channel_id TEXT,
                    message_id TEXT,
                    PRIMARY KEY (event_id, channel_id)
                )''')
    # Timer channel config
    c.execute('''CREATE TABLE IF NOT EXISTS config (
                    server_id TEXT,
                    profile TEXT,
                    timer_channel_id TEXT,
                    PRIMARY KEY (server_id, profile)
                )''')
    # Announcement channel config
    c.execute('''CREATE TABLE IF NOT EXISTS announce_config (
                    server_id TEXT PRIMARY KEY,
                    announce_channel_id TEXT
                )''')
    # Notification timings per category and type (start/end)
    c.execute('''CREATE TABLE IF NOT EXISTS notification_timings (
                    server_id TEXT,
                    category TEXT,
                    timing_type TEXT,
                    timing_minutes INTEGER,
                    PRIMARY KEY (server_id, category, timing_type)
                )''')
    # Notification timing status channel/message
    c.execute('''CREATE TABLE IF NOT EXISTS notification_timing_channel (
                    server_id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    message_id TEXT
                )''')
    # Notification channel
    c.execute('''CREATE TABLE IF NOT EXISTS notification_channel (
                    server_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )''')
    # ...existing table creation code...
    # Pending notifications (persistent scheduling)
    c.execute('''CREATE TABLE IF NOT EXISTS pending_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id TEXT,
        category TEXT,
        profile TEXT,
        title TEXT,
        timing_type TEXT,
        notify_unix INTEGER,
        event_time_unix INTEGER,
        sent INTEGER DEFAULT 0,
        region TEXT
    )''')
    # UNIQUE index to prevent duplicates (including region for HYV)
    c.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_pending_notif
        ON pending_notifications (server_id, category, profile, title, timing_type, notify_unix, region)
    ''')
    # Role reaction emoji-role mapping
    c.execute('''CREATE TABLE IF NOT EXISTS role_reactions (
                    server_id TEXT,
                    message_id TEXT,
                    emoji TEXT,
                    role_id TEXT,
                    PRIMARY KEY (server_id, emoji)
                )''')
    conn.commit()
    conn.close()

init_db()

# Create a custom logger for timer channel updates
timer_logger = logging.getLogger("timer_channel")
timer_logger.setLevel(logging.INFO)

# Console handler for timer channel logs only
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
timer_logger.addHandler(console_handler)

async def mark_ended_events(guild):
    now = int(datetime.now().timestamp())
    async with aiosqlite.connect('kanami_data.db') as conn:
        await conn.execute(
            "UPDATE user_data SET category='Ended' WHERE server_id=? AND category != 'Ended' AND end_date != '' AND CAST(end_date AS INTEGER) < ?",
            (str(guild.id), now)
        )
        await conn.commit()

async def upsert_event_message(guild, channel, event_row, event_id):
    """
    Edits the event message in the channel if it exists, otherwise sends a new one.
    event_row: (title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile)
    event_id: the id of the event in user_data
    """
    title, start_unix, end_unix, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile = event_row

    # Color logic
    color = discord.Color.blue()
    if category == "Banner":
        color = discord.Color.blue()
    elif category == "Event":
        color = discord.Color.gold()
    elif category == "Maintenance":
        color = discord.Color.green()
    elif category == "Offer":
        color = discord.Color.fuchsia()
    elif category == "Ended":
        color = discord.Color.red()
    else:
        color = discord.Color.blurple()

    embed = discord.Embed(title=title, color=color)
    if int(is_hyv):
        embed.description = (
            f"**Asia Server:**\n"
            f"Start: <t:{asia_start}:F>\nEnd: <t:{asia_end}:F>\n\n"
            f"**America Server:**\n"
            f"Start: <t:{america_start}:F>\nEnd: <t:{america_end}:F>\n\n"
            f"**Europe Server:**\n"
            f"Start: <t:{europe_start}:F>\nEnd: <t:{europe_end}:F>"
        )
    else:
        embed.description = f"**Start:** <t:{start_unix}:F> or <t:{start_unix}:R>\n**End:** <t:{end_unix}:F> or <t:{end_unix}:R>"
    if image and (image.startswith("http://") or image.startswith("https://")):
        embed.set_image(url=image)

    # Check if message exists and edit if possible
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT message_id FROM event_messages WHERE event_id=? AND channel_id=?", (event_id, str(channel.id))) as cursor:
            row = await cursor.fetchone()
        msg = None
        if row and row[0]:
            try:
                msg = await channel.fetch_message(int(row[0]))
                await msg.edit(embed=embed)
                return
            except Exception:
                pass  # If message not found, fall through to send new

        # Send new message and update DB
        msg = await channel.send(embed=embed)
        await conn.execute(
            "REPLACE INTO event_messages (event_id, server_id, channel_id, message_id) VALUES (?, ?, ?, ?)",
            (event_id, str(guild.id), str(channel.id), str(msg.id))
        )
        await conn.commit()

# Function to update the timer channel with the latest events for a given profile
async def update_timer_channel(guild, bot, profile="ALL"):
    timer_logger.info(f"[update_timer_channel] Updating timer channel for guild {guild.id}, profile {profile}")

    await mark_ended_events(guild)

    # Start the SQLite connection
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT timer_channel_id FROM config WHERE server_id=? AND profile=?", (str(guild.id), profile)) as cursor:
            row = await cursor.fetchone()
        if not row:
            async with conn.execute("SELECT timer_channel_id FROM config WHERE server_id=? AND profile='ALL'", (str(guild.id),)) as cursor:
                row = await cursor.fetchone()
        if not row:
            timer_logger.warning(f"[update_timer_channel] No timer channel found for guild {guild.id}, profile {profile}")
            return
        channel_id = int(row[0])

        # Fetch events for this profile
        if profile == "ALL":
            async with conn.execute(
                "SELECT id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile FROM user_data WHERE server_id=? ORDER BY id DESC",
                (str(guild.id),)
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with conn.execute(
                "SELECT id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile FROM user_data WHERE server_id=? AND profile=? ORDER BY id DESC",
                (str(guild.id), profile)
            ) as cursor:
                rows = await cursor.fetchall()

        channel = guild.get_channel(channel_id)
        if not channel:
            timer_logger.warning(f"[update_timer_channel] Channel {channel_id} not found in guild {guild.id}")
            return

        # Get all event_ids currently in the channel
        async with conn.execute("SELECT event_id, message_id FROM event_messages WHERE server_id=? AND channel_id=?", (str(guild.id), str(channel.id))) as cursor:
            existing_msgs = {row[0]: row[1] async for row in cursor}

        # Build a set of current event_ids
        current_event_ids = set(row[0] for row in rows)

        # Find all events marked as Ended
        async with conn.execute("SELECT id FROM user_data WHERE server_id=? AND category='Ended'", (str(guild.id),)) as cursor:
            ended_event_ids = set()
            async for row in cursor:
                ended_event_ids.add(row[0])

        # Delete messages for events that are either not in the DB anymore or are marked as Ended
        for event_id in set(existing_msgs.keys()) | ended_event_ids:
            if event_id not in current_event_ids or event_id in ended_event_ids:
                try:
                    msg = await channel.fetch_message(int(existing_msgs.get(event_id)))
                    await msg.delete()
                    timer_logger.info(f"[update_timer_channel] Deleted message for event_id {event_id} (profile {profile})")
                except Exception as e:
                    timer_logger.warning(f"[update_timer_channel] Failed to delete message for event_id {event_id} (profile {profile}): {e}")
                await conn.execute("DELETE FROM event_messages WHERE event_id=? AND channel_id=?", (event_id, str(channel.id)))
                await conn.commit()
            if event_id in ended_event_ids:
                await conn.execute("DELETE FROM user_data WHERE id=?", (event_id,))
                await conn.commit()
                timer_logger.info(f"[update_timer_channel] Deleted ended event_id {event_id} from user_data (profile {profile})")

        # Upsert (edit or create) messages for current events
        for row in rows:
            event_id = row[0]
            title = row[1]
            start_date = row[2]
            end_date = row[3]
            image = row[4]
            category = row[5]
            is_hyv = int(row[6])
            asia_start = row[7]
            asia_end = row[8]
            america_start = row[9]
            america_end = row[10]
            europe_start = row[11]
            europe_end = row[12]
            event_profile = row[13]

            if category == "Ended":
                continue  # Skip ended events

            # Compare with previous message data
            msg_id = existing_msgs.get(event_id)
            needs_update = True

            if msg_id:
                # Fetch previous event data from DB for comparison
                async with conn.execute(
                    "SELECT title, start_date, end_date, asia_start, asia_end, america_start, america_end, europe_start, europe_end FROM user_data WHERE id=?",
                    (event_id,)
                ) as cursor:
                    prev = await cursor.fetchone()
                if prev:
                    prev_title, prev_start, prev_end, prev_asia_start, prev_asia_end, prev_america_start, prev_america_end, prev_europe_start, prev_europe_end = prev
                    # For HYV events, compare all region times
                    if is_hyv:
                        if (
                            title == prev_title and
                            asia_start == prev_asia_start and
                            asia_end == prev_asia_end and
                            america_start == prev_america_start and
                            america_end == prev_america_end and
                            europe_start == prev_europe_start and
                            europe_end == prev_europe_end
                        ):
                            needs_update = False
                    else:
                        if (
                            title == prev_title and
                            start_date == prev_start and
                            end_date == prev_end
                        ):
                            needs_update = False

            if not needs_update:
                timer_logger.info(f"[update_timer_channel] No update needed for event_id {event_id} (profile {profile})")
                continue

            event_row = row[1:]  # skip id
            try:
                await upsert_event_message(guild, channel, event_row, event_id)
                timer_logger.info(f"[update_timer_channel] Upserted event_id {event_id} (profile {profile})")
            except Exception as e:
                timer_logger.warning(f"[update_timer_channel] Failed to upsert event_id {event_id} (profile {profile}): {e}")
            await asyncio.sleep(1)  # Avoid rate limits

        # Orphaned message cleanup: remove messages in the channel not tracked in the DB
        try:
            messages = [msg async for msg in channel.history(limit=500)]
        except Exception as e:
            timer_logger.warning(f"[update_timer_channel] Failed to fetch history for channel {channel_id}: {e}")
            messages = []

        async with aiosqlite.connect('kanami_data.db') as conn:
            async with conn.execute("SELECT message_id FROM event_messages WHERE server_id=? AND channel_id=?", (str(guild.id), str(channel.id))) as cursor:
                db_msg_ids = {str(row[0]) async for row in cursor}

        for msg in messages:
            if str(msg.id) not in db_msg_ids and msg.author == guild.me:
                for attempt in range(3):
                    try:
                        await msg.delete()
                        timer_logger.info(f"[update_timer_channel] Deleted orphaned message {msg.id} in channel {channel_id} (profile {profile})")
                        break
                    except Exception as e:
                        timer_logger.warning(f"[update_timer_channel] Attempt {attempt+1}: Failed to delete orphaned message {msg.id} in channel {channel_id}: {e}")
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff

    timer_logger.info(f"[update_timer_channel] Finished updating for guild {guild.id}, profile {profile}")
    

async def get_valid_categories(server_id):
    # Built-in categories
    categories = {"Banner", "Event", "Maintenance", "Offer"}
    # Add custom categories from DB
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT category FROM custom_categories WHERE server_id=?", (server_id,)) as cursor:
            custom = {row[0] async for row in cursor}
    categories.update(custom)
    return categories

# Function to convert date and time to Unix timestamp
def convert_to_unix(date: str, time: str):
    """
    Converts a given date and time into a Unix timestamp.
    Date format: YYYY-MM-DD
    Time format: HH:MM (24-hour format)
    Returns the Unix timestamp or raises a ValueError if the input is invalid.
    """
    dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    return int(dt.timestamp())

# Function to convert date and time to Unix timestamp with timezone
def convert_to_unix_tz(date: str, time: str, timezone_str: str = "UTC"):
    """
    Converts a given date and time in a specified timezone or offset into a Unix timestamp.
    Supports IANA tz names (e.g., 'Asia/Tokyo') and offsets like 'UTC-8', 'GMT+5', etc.
    Returns the Unix timestamp or raises a ValueError if the input is invalid.
    """
    dt_naive = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")

    # Try to parse as offset (e.g., UTC-8, GMT+5)
    tz = None
    if timezone_str.upper().startswith("UTC") or timezone_str.upper().startswith("GMT"):
        import re
        match = re.match(r"^(UTC|GMT)([+-]\d{1,2})$", timezone_str.upper())
        if match:
            offset_hours = int(match.group(2))
            tz = timezone(timedelta(hours=offset_hours))
    # If not offset, try as IANA name
    if tz is None:
        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            raise ValueError(f"Unknown timezone: {timezone_str}")

    # Attach timezone and convert to UTC
    dt_local = dt_naive.replace(tzinfo=tz)
    dt_utc = dt_local.astimezone(timezone.utc)
    return int(dt_utc.timestamp())


@bot.command()
async def add(ctx, *, args: str):
    """
    Adds a new event using fuzzy date/time parsing.
    Usage: Kanami add <title> <start> <end> [image] [profile] [category] [timezone]
    Example: Kanami add "Shadowverse Battle Fest Vol. 1" 2025-08-14 13:00 2025-08-17 13:00 https://image.url AK Event PT Asia/Tokyo
    """
    def extract_quoted(text):
        return re.findall(r'"([^"]+)"', text)

    # Extract quoted title
    quoted = extract_quoted(args)
    title = quoted[0] if quoted else None
    rest = args
    if title:
        rest = rest.replace(f'"{title}"', '').strip()

    # Find all date-like patterns
    date_patterns = re.findall(
        r'(\d{4}[-/]\d{2}[-/]\d{2} \d{1,2}:\d{2}(?:\s*\([^)]+\))?|'
        r'\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})? \d{1,2}:\d{2}(?:\s*\([^)]+\))?|'
        r'\d{1,2}:\d{2}(?:\s*\([^)]+\))?)',
        rest
    )
    # Remove duplicates, preserve order
    seen = set()
    dates = []
    for d in date_patterns:
        if d not in seen:
            seen.add(d)
            dates.append(d)
    # Try to parse with dateparser
    parsed = []
    for d in dates:
        dt = dateparser.parse(d, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        if dt:
            parsed.append((d, dt))
    # If less than 2, try to find more with dateparser.search
    if len(parsed) < 2:
        try:
            results = dateparser.search.search_dates(rest, settings={'RETURN_AS_TIMEZONE_AWARE': True}) or []
            for result in results:
                d, dt = result
                if dt and (d, dt) not in parsed:
                    parsed.append((d, dt))
        except Exception:
            pass

    # Find timezone (must be present or prompt)
    tz_match = re.search(r'([A-Za-z_]+/[A-Za-z_]+|UTC[+-]?\d{0,2}|GMT[+-]?\d{0,2})', rest)
    timezone_str = tz_match.group(1) if tz_match else None
    if not timezone_str:
        await ctx.send("No timezone detected. Please enter the timezone for this event (e.g. `Asia/Tokyo`, `UTC+8`, etc.):")
        def check(m): return m.author == ctx.author and m.channel == ctx.channel
        try:
            msg = await bot.wait_for("message", timeout=60.0, check=check)
            timezone_str = msg.content.strip()
        except Exception:
            await ctx.send("No timezone provided. Cancelling.")
            return

    # Try to extract image, profile, category (optional, after timezone)
    after_tz = rest.split(timezone_str, 1)[-1].strip() if timezone_str in rest else rest
    image = None
    profile = None
    category = None
    extras = after_tz.split()
    valid_profiles = ["HSR", "ZZZ", "AK", "STRI", "WUWA", "ALL"]
    for extra in extras:
        if extra.startswith("http://") or extra.startswith("https://"):
            image = extra
        elif extra.upper() in valid_profiles:
            profile = extra.upper()
        else:
            category = extra

    # Prompt for missing profile/category if needed
    if not profile:
        await ctx.send(f"Which profile is this event for? (Type one of: {', '.join(valid_profiles)})")
        def profile_check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() in valid_profiles
        try:
            msg = await bot.wait_for("message", timeout=60.0, check=profile_check)
            profile = msg.content.upper()
        except Exception:
            await ctx.send("No valid profile provided. Event not added.")
            return

    if not category:
        await ctx.send("What category is this event? (e.g. Banner, Event, EX, etc.)")
        def cat_check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        try:
            msg = await bot.wait_for("message", timeout=60.0, check=cat_check)
            category = msg.content
        except Exception:
            await ctx.send("No category provided. Event not added.")
            return

    # Parse start/end times
    now = datetime.now()
    year = now.year
    try:
        if len(parsed) >= 2:
            start_dt = parsed[0][1]
            end_dt = parsed[1][1]
        elif len(parsed) == 1:
            start_dt = parsed[0][1]
            await ctx.send("Only one date found. How many days does this event last? (Enter a number, e.g. `14`)")
            def dur_check(m): return m.author == ctx.author and m.channel == ctx.channel
            try:
                msg = await bot.wait_for("message", timeout=60.0, check=dur_check)
                days = int(msg.content.strip())
            except Exception:
                await ctx.send("No valid duration provided. Cancelling.")
                return
            end_dt = start_dt + timedelta(days=days)
        else:
            await ctx.send("Could not find valid date/time in your message. Please provide start and end times.")
            return
    except Exception as e:
        await ctx.send(f"Error parsing times: {e}")
        return

    # Convert to UTC unix timestamps
    try:
        if start_dt.tzinfo is None:
            import pytz
            tz = pytz.timezone(timezone_str)
            start_dt = tz.localize(start_dt)
        start_unix = int(start_dt.astimezone(datetime.timezone.utc).timestamp())
        if end_dt.tzinfo is None:
            import pytz
            tz = pytz.timezone(timezone_str)
            end_dt = tz.localize(end_dt)
        end_unix = int(end_dt.astimezone(datetime.timezone.utc).timestamp())
    except Exception as e:
        await ctx.send(f"Error converting times to UTC: {e}")
        return

    # Insert into DB
    async with aiosqlite.connect('kanami_data.db') as conn:
        base_title = title if title else "Untitled Event"
        suffix = 1
        new_title = base_title
        while True:
            async with conn.execute(
                "SELECT COUNT(*) FROM user_data WHERE server_id=? AND title=?",
                (str(ctx.guild.id), new_title)
            ) as cursor:
                count = (await cursor.fetchone())[0]
            if count == 0:
                break
            suffix += 1
            new_title = f"{base_title} {suffix}"

        await conn.execute(
            "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category, is_hyv, profile) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(ctx.author.id), str(ctx.guild.id), new_title, str(start_unix), str(end_unix), image, category, 0, profile)
        )
        await conn.commit()

    await ctx.send(
        f"Added `{new_title}` as **{category}** for **{profile}** to the database!\n"
        f"Start: <t:{start_unix}:F>\nEnd: <t:{end_unix}:F>\nTimezone: {timezone_str}"
    )

    # Update timer channels and schedule notifications
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),)) as cursor:
            profiles = [row[0] async for row in cursor]
    for prof in profiles:
        await update_timer_channel(ctx.guild, bot, profile=prof)

    event = {
        'server_id': str(ctx.guild.id),
        'category': category,
        'profile': profile,
        'title': new_title,
        'start_date': str(start_unix),
        'end_date': str(end_unix)
    }
    from notification_handler import schedule_notifications_for_event, remove_duplicate_pending_notifications
    import asyncio
    asyncio.create_task(schedule_notifications_for_event(event))
    remove_duplicate_pending_notifications()

@bot.command()
async def remove(ctx, *, title: str):
    from notification_handler import remove_duplicate_pending_notifications

    server_id = str(ctx.guild.id)
    # Case-insensitive search for the event title
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT id, title, start_date, end_date FROM user_data WHERE server_id=? COLLATE NOCASE AND LOWER(title)=LOWER(?)", (server_id, title)) as cursor:
            row = await cursor.fetchone()
        if not row:
            await ctx.send(f"No event found with the title `{title}`.")
            return
        event_id, found_title, start, end = row

        # Remove the event
        await conn.execute("DELETE FROM user_data WHERE id=?", (event_id,))
        # Remove all pending notifications for this event (case-insensitive)
        await conn.execute("DELETE FROM pending_notifications WHERE server_id=? AND LOWER(title)=LOWER(?)", (server_id, found_title))
        await conn.commit()

        # Delete all event messages for this event
        async with conn.execute("SELECT channel_id, message_id FROM event_messages WHERE event_id=?", (event_id,)) as cursor:
            msg_rows = await cursor.fetchall()
        for channel_id, message_id in msg_rows:
            channel = ctx.guild.get_channel(int(channel_id))
            if channel:
                try:
                    msg = await channel.fetch_message(int(message_id))
                    await msg.delete()
                except Exception:
                    pass
        # Remove from DB
        await conn.execute("DELETE FROM event_messages WHERE event_id=?", (event_id,))
        await conn.commit()

    await ctx.send(f"Removed event `{found_title}` (Start: <t:{start}:F>, End: <t:{end}:F>) from the database and cleared its notifications.")

    # Update all timer channels for all profiles in this server
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT profile FROM config WHERE server_id=?", (server_id,)) as cursor:
            profiles = [row[0] async for row in cursor]
    for profile in profiles:
        await update_timer_channel(ctx.guild, bot, profile=profile)
    remove_duplicate_pending_notifications()


@bot.command()
async def edit(ctx, title: str, item: str, value: str):
    """
    Edits an existing event in the database.
    For HSR/ZZZ, allows editing region-specific times.
    Now supports editing the event title.
    """
    from twitter_handler import convert_to_all_timezones
    from notification_handler import remove_duplicate_pending_notifications

    allowed_items = ["start", "end", "category", "profile", "image", "title"]

    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT id, profile, is_hyv FROM user_data WHERE server_id=? AND LOWER(title)=?", (str(ctx.guild.id), title.lower())) as cursor:
            row = await cursor.fetchone()
        if not row:
            await ctx.send(f"No event found with the title `{title}`.")
            return
        event_id, profile, is_hyv = row
        profile = profile.upper()

        # For HYV games (HSR/ZZZ), allow editing region-specific times
        if profile in ("HSR", "ZZZ") and item.lower() in ("start", "end"):
            # Value should be in "server time" format (e.g. "2025-08-20 13:00")
            try:
                region_times = convert_to_all_timezones(value)
            except Exception as e:
                await ctx.send(f"Error converting server time to all regions: {e}")
                return

            # Update all three region times
            if item.lower() == "start":
                await conn.execute("UPDATE user_data SET asia_start=?, america_start=?, europe_start=? WHERE id=?",
                    (str(region_times["Asia"][1]), str(region_times["America"][1]), str(region_times["Europe"][1]), event_id))
            elif item.lower() == "end":
                await conn.execute("UPDATE user_data SET asia_end=?, america_end=?, europe_end=? WHERE id=?",
                    (str(region_times["Asia"][1]), str(region_times["America"][1]), str(region_times["Europe"][1]), event_id))
            await conn.commit()
            await ctx.send(f"Updated `{item}` time for `{title}` to `{value}` (all regions updated).")
            remove_duplicate_pending_notifications()
            return

        # --- Non-HYV logic below ---
        if item.lower() not in allowed_items:
            await ctx.send(f"Cannot edit `{item}`. Only {', '.join(allowed_items)} can be edited.")
            return

        # Edit start/end times (non-HYV)
        if item.lower() in ("start", "end"):
            # Try to parse as unix timestamp, else as date string
            try:
                unix_time = int(value)
            except ValueError:
                from database_handler import convert_to_unix_tz
                # Prompt for timezone if not present
                import re
                tz_match = re.search(r'(UTC[+-]\d+|GMT[+-]\d+|[A-Za-z]+/[A-Za-z_]+)', value)
                if tz_match:
                    timezone_str = tz_match.group(1)
                else:
                    await ctx.send("No timezone detected. Please enter the timezone for this event (e.g. `Asia/Tokyo`, `UTC+8`, etc.):")
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
                unix_time = convert_to_unix_tz(date, time, timezone_str)
            # Update start or end
            if item.lower() == "start":
                await conn.execute("UPDATE user_data SET start_date=? WHERE id=?", (str(unix_time), event_id))
            else:
                await conn.execute("UPDATE user_data SET end_date=? WHERE id=?", (str(unix_time), event_id))
            await conn.commit()
            await ctx.send(f"Updated `{item}` for `{title}` to `{value}`.")
            remove_duplicate_pending_notifications()
            return

        # Edit other fields
        if item.lower() == "category":
            await conn.execute("UPDATE user_data SET category=? WHERE id=?", (value, event_id))
        elif item.lower() == "profile":
            await conn.execute("UPDATE user_data SET profile=? WHERE id=?", (value.upper(), event_id))
        elif item.lower() == "image":
            await conn.execute("UPDATE user_data SET image=? WHERE id=?", (value, event_id))
        elif item.lower() == "title":
            # Update the title in user_data
            await conn.execute("UPDATE user_data SET title=? WHERE id=?", (value, event_id))
            # Also update pending_notifications and event_messages for consistency
            await conn.execute("UPDATE pending_notifications SET title=? WHERE server_id=? AND LOWER(title)=LOWER(?)", (value, str(ctx.guild.id), title))
            await conn.execute("UPDATE event_messages SET event_id=(SELECT id FROM user_data WHERE server_id=? AND title=?) WHERE server_id=? AND event_id=?", (str(ctx.guild.id), value, str(ctx.guild.id), event_id))
        await conn.commit()
        await ctx.send(f"Updated `{item}` for `{title}` to `{value}`.")
        remove_duplicate_pending_notifications()

@bot.command()
@commands.has_permissions(manage_guild=True)
async def add_custom_category(ctx, *, category: str):
    """
    Adds a custom event category for this server.
    Usage: Kanami add_custom_category <category name>
    """
    server_id = str(ctx.guild.id)
    category = category.strip()
    if not category:
        await ctx.send("Please provide a category name.")
        return

    async with aiosqlite.connect('kanami_data.db') as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS custom_categories (
            server_id TEXT,
            category TEXT,
            PRIMARY KEY (server_id, category)
        )''')
        await conn.execute("INSERT OR IGNORE INTO custom_categories (server_id, category) VALUES (?, ?)", (server_id, category))
        await conn.commit()
    await ctx.send(f"Custom category `{category}` added for this server!")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def remove_custom_category(ctx, *, category: str):
    """
    Removes a custom event category for this server.
    Usage: Kanami remove_custom_category <category name>
    """
    server_id = str(ctx.guild.id)
    category = category.strip()
    if not category:
        await ctx.send("Please provide a category name.")
        return

    async with aiosqlite.connect('kanami_data.db') as conn:
        await conn.execute("DELETE FROM custom_categories WHERE server_id=? AND category=?", (server_id, category))
        await conn.commit()
    await ctx.send(f"Custom category `{category}` removed for this server!")

@bot.command(name="refresh_all")
@commands.has_permissions(manage_guild=True)
async def refresh_all(ctx):
    """
    Completely refreshes all event data:
    - Deletes expired events (end time in the past)
    - Clears and updates all timer channels (removes ended/expired events)
    - Clears and recreates all pending notifications
    """
    from datetime import datetime
    from notification_handler import remove_duplicate_pending_notifications, refresh_pending_notifications
    from database_handler import update_timer_channel

    server_id = str(ctx.guild.id)
    now = int(datetime.now().timestamp())

    await ctx.send("Refreshing all event data. This may take a moment...")

    async with aiosqlite.connect('kanami_data.db') as conn:
        # 1. Delete expired events and their notifications/messages
        async with conn.execute("SELECT id, title FROM user_data WHERE server_id=? AND end_date != '' AND CAST(end_date AS INTEGER) < ?", (server_id, now)) as cursor:
            expired = await cursor.fetchall()
        expired_titles = [row[1] for row in expired]
        for event_id, title in expired:
            await conn.execute("DELETE FROM user_data WHERE id=?", (event_id,))
            await conn.execute("DELETE FROM pending_notifications WHERE server_id=? AND LOWER(title)=LOWER(?)", (server_id, title))
            async with conn.execute("SELECT channel_id, message_id FROM event_messages WHERE event_id=?", (event_id,)) as msg_cursor:
                msg_rows = await msg_cursor.fetchall()
            for channel_id, message_id in msg_rows:
                channel = ctx.guild.get_channel(int(channel_id))
                if channel:
                    try:
                        msg = await channel.fetch_message(int(message_id))
                        await msg.delete()
                    except Exception as e:
                        logging.warning(f"Failed to delete message {message_id} in channel {channel_id}: {e}")
            await conn.execute("DELETE FROM event_messages WHERE event_id=?", (event_id,))
        await conn.commit()

        # 2. Fetch all profiles and their timer channel IDs once
        async with conn.execute("SELECT profile, timer_channel_id FROM config WHERE server_id=?", (server_id,)) as cursor:
            profile_channel_map = {row[0]: int(row[1]) for row in await cursor.fetchall()}

        for profile, channel_id in profile_channel_map.items():
            await update_timer_channel(ctx.guild, bot, profile=profile)

            # --- Orphaned message cleanup for this timer channel ---
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                continue

            try:
                messages = [msg async for msg in channel.history(limit=500)]
            except Exception as e:
                logging.warning(f"Failed to fetch history for channel {channel_id}: {e}")
                continue

            async with conn.execute("SELECT message_id FROM event_messages WHERE server_id=? AND channel_id=?", (str(ctx.guild.id), str(channel_id))) as cursor:
                db_msg_ids = {str(row[0]) async for row in cursor}

            for msg in messages:
                if str(msg.id) not in db_msg_ids and msg.author == ctx.guild.me:
                    for attempt in range(3):
                        try:
                            await msg.delete()
                            break
                        except Exception as e:
                            logging.warning(f"Attempt {attempt+1}: Failed to delete orphaned message {msg.id} in channel {channel_id}: {e}")
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff

        # Send completion message to announcement channel
        async with conn.execute("SELECT announce_channel_id FROM announce_config WHERE server_id=?", (server_id,)) as cursor:
            row = await cursor.fetchone()
        if row and row[0]:
            announce_channel = ctx.guild.get_channel(int(row[0]))
            if announce_channel:
                emoji = "<:KanamiHeart:1374409597628186624>"
                await announce_channel.send(f"Timer channel updates are complete. {emoji}")

    # 3. Clear and recreate all pending notifications for this server
    await ctx.invoke(bot.get_command("refresh_pending_notifications"))

    await ctx.send(
        f"Refreshed all event data!\n"
        f"Deleted expired events: {', '.join(expired_titles) if expired_titles else 'None'}\n"
        f"Timer channels and pending notifications have been updated."
    )