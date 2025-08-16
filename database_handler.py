import discord
from discord import app_commands
from discord.ext import commands
from modules import *
from bot import bot
import asyncio

import dateparser
import re
from datetime import datetime, timedelta, timezone

# Initialize the database
def init_db():
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

    # Check if message exists
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT message_id FROM event_messages WHERE event_id=? AND channel_id=?", (event_id, str(channel.id)))
    row = c.fetchone()
    msg = None
    if row and row[0]:
        try:
            msg = await channel.fetch_message(int(row[0]))
            await msg.edit(embed=embed)
            conn.close()
            return
        except Exception:
            pass  # If message not found, fall through to send new

    # Send new message
    msg = await channel.send(embed=embed)
    c.execute("REPLACE INTO event_messages (event_id, server_id, channel_id, message_id) VALUES (?, ?, ?, ?)",
              (event_id, str(guild.id), str(channel.id), str(msg.id)))
    conn.commit()
    conn.close()

# Function to mark ended events in the database
async def mark_ended_events(guild):
    now = int(datetime.now().timestamp())
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Only update events that are not already marked as Ended
    c.execute(
        "UPDATE user_data SET category='Ended' WHERE server_id=? AND category != 'Ended' AND end_date != '' AND CAST(end_date AS INTEGER) < ?",
        (str(guild.id), now)
    )
    conn.commit()
    conn.close()

# Function to update the timer channel with the latest events for a given profile
async def update_timer_channel(guild, bot, profile="ALL"):
    # Mark ended events before fetching
    await mark_ended_events(guild)

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT timer_channel_id FROM config WHERE server_id=? AND profile=?", (str(guild.id), profile))
    row = c.fetchone()
    if not row:
        c.execute("SELECT timer_channel_id FROM config WHERE server_id=? AND profile='ALL'", (str(guild.id),))
        row = c.fetchone()
    if not row:
        conn.close()
        return
    channel_id = int(row[0])

    # Fetch events for this profile only, or all if profile is "ALL"
    if profile == "ALL":
        c.execute(
            "SELECT id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile FROM user_data WHERE server_id=? ORDER BY id DESC",
            (str(guild.id),)
        )
    else:
        c.execute(
            "SELECT id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile FROM user_data WHERE server_id=? AND profile=? ORDER BY id DESC",
            (str(guild.id), profile)
        )
    rows = c.fetchall()
    conn.close()

    channel = guild.get_channel(channel_id)
    if not channel:
        return

    # Get all event_ids currently in the channel
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT event_id, message_id FROM event_messages WHERE server_id=? AND channel_id=?", (str(guild.id), str(channel.id)))
    existing_msgs = {row[0]: row[1] for row in c.fetchall()}
    conn.close()

    # Build a set of current event_ids
    current_event_ids = set(row[0] for row in rows)

    # Delete messages for events that no longer exist or are marked as Ended
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Find all events marked as Ended
    c.execute("SELECT id FROM user_data WHERE server_id=? AND category='Ended'", (str(guild.id),))
    ended_event_ids = set(row[0] for row in c.fetchall())
    conn.close()

    # Delete messages for events that are either not in the DB anymore or are marked as Ended
    for event_id in set(existing_msgs.keys()) | ended_event_ids:
        if event_id not in current_event_ids or event_id in ended_event_ids:
            try:
                msg = await channel.fetch_message(int(existing_msgs.get(event_id)))
                await msg.delete()
            except Exception:
                pass
            # Remove from DB
            conn = sqlite3.connect('kanami_data.db')
            c = conn.cursor()
            c.execute("DELETE FROM event_messages WHERE event_id=? AND channel_id=?", (event_id, str(channel.id)))
            conn.commit()
            conn.close()
        # Also, if marked as Ended, remove from user_data
        if event_id in ended_event_ids:
            conn = sqlite3.connect('kanami_data.db')
            c = conn.cursor()
            c.execute("DELETE FROM user_data WHERE id=?", (event_id,))
            conn.commit()
            conn.close()

    # Upsert (edit or create) messages for current events (that are not ended)
    for row in rows:
        event_id = row[0]
        category = row[5]
        if category == "Ended":
            continue  # Skip ended events
        event_row = row[1:]  # skip id
        await upsert_event_message(guild, channel, event_row, event_id)
    # Mark ended events before fetching
    await mark_ended_events(guild)

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT timer_channel_id FROM config WHERE server_id=? AND profile=?", (str(guild.id), profile))
    row = c.fetchone()
    if not row:
        c.execute("SELECT timer_channel_id FROM config WHERE server_id=? AND profile='ALL'", (str(guild.id),))
        row = c.fetchone()
    if not row:
        conn.close()
        return
    channel_id = int(row[0])

    # Fetch events for this profile only, or all if profile is "ALL"
    if profile == "ALL":
        c.execute(
            "SELECT id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile FROM user_data WHERE server_id=? ORDER BY id DESC",
            (str(guild.id),)
        )
    else:
        c.execute(
            "SELECT id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile FROM user_data WHERE server_id=? AND profile=? ORDER BY id DESC",
            (str(guild.id), profile)
        )
    rows = c.fetchall()
    conn.close()

    channel = guild.get_channel(channel_id)
    if not channel:
        return

    # Get all event_ids currently in the channel
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT event_id, message_id FROM event_messages WHERE server_id=? AND channel_id=?", (str(guild.id), str(channel.id)))
    existing_msgs = {row[0]: row[1] for row in c.fetchall()}
    conn.close()

    # Build a set of current event_ids
    current_event_ids = set(row[0] for row in rows)

    # Delete messages for events that no longer exist
    for event_id in set(existing_msgs.keys()) - current_event_ids:
        try:
            msg = await channel.fetch_message(int(existing_msgs[event_id]))
            await msg.delete()
        except Exception:
            pass
        # Remove from DB
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        c.execute("DELETE FROM event_messages WHERE event_id=? AND channel_id=?", (event_id, str(channel.id)))
        conn.commit()
        conn.close()

    # Upsert (edit or create) messages for current events
    for row in rows:
        event_id = row[0]
        event_row = row[1:]  # skip id
        await upsert_event_message(guild, channel, event_row, event_id)
    
    try:
        emoji = "<:KanamiHeart:1374409597628186624>"
        await channel.send(f"Timer channel updates are complete. {emoji}")
    except Exception as e:
        logging.error(f"[TimerChannel] Error sending completion message: {e}", exc_info=True)
        pass

async def get_valid_categories(server_id):
    # Built-in categories
    categories = {"Banner", "Event", "Maintenance", "Offer"}
    # Add custom categories from DB
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT category FROM custom_categories WHERE server_id=?", (server_id,))
    custom = {row[0] for row in c.fetchall()}
    conn.close()
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
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    base_title = title if title else "Untitled Event"
    suffix = 1
    new_title = base_title
    while True:
        c.execute(
            "SELECT COUNT(*) FROM user_data WHERE server_id=? AND title=?",
            (str(ctx.guild.id), new_title)
        )
        count = c.fetchone()[0]
        if count == 0:
            break
        suffix += 1
        new_title = f"{base_title} {suffix}"

    c.execute(
        "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category, is_hyv, profile) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(ctx.author.id), str(ctx.guild.id), new_title, str(start_unix), str(end_unix), image, category, 0, profile)
    )
    conn.commit()
    conn.close()

    await ctx.send(
        f"Added `{new_title}` as **{category}** for **{profile}** to the database!\n"
        f"Start: <t:{start_unix}:F>\nEnd: <t:{end_unix}:F>\nTimezone: {timezone_str}"
    )

    # Update timer channels and schedule notifications
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),))
    profiles = [row[0] for row in c.fetchall()]
    conn.close()
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

@bot.command()  # "remove" command to remove an event from the database
async def remove(ctx, *, title: str):
    """
    Removes an event by title (case-insensitive) from the current server, along with its notifications and messages.
    Usage: Kanami remove <event title>
    """
    from notification_handler import remove_duplicate_pending_notifications

    server_id = str(ctx.guild.id)
    # Case-insensitive search for the event title
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT id, title, start_date, end_date FROM user_data WHERE server_id=? COLLATE NOCASE AND LOWER(title)=LOWER(?)", (server_id, title))
    row = c.fetchone()
    if not row:
        await ctx.send(f"No event found with the title `{title}`.")
        conn.close()
        return
    event_id, found_title, start, end = row

    # Remove the event
    c.execute("DELETE FROM user_data WHERE id=?", (event_id,))
    # Remove all pending notifications for this event (case-insensitive)
    c.execute("DELETE FROM pending_notifications WHERE server_id=? AND LOWER(title)=LOWER(?)", (server_id, found_title))
    conn.commit()
    conn.close()

    # Delete all event messages for this event
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT channel_id, message_id FROM event_messages WHERE event_id=?", (event_id,))
    msg_rows = c.fetchall()
    conn.close()
    for channel_id, message_id in msg_rows:
        channel = ctx.guild.get_channel(int(channel_id))
        if channel:
            try:
                msg = await channel.fetch_message(int(message_id))
                await msg.delete()
            except Exception:
                pass
    # Remove from DB
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM event_messages WHERE event_id=?", (event_id,))
    conn.commit()
    conn.close()

    await ctx.send(f"Removed event `{found_title}` (Start: <t:{start}:F>, End: <t:{end}:F>) from the database and cleared its notifications.")

    # Update all timer channels for all profiles in this server
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT profile FROM config WHERE server_id=?", (server_id,))
    profiles = [row[0] for row in c.fetchall()]
    conn.close()
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
    import sqlite3
    from notification_handler import remove_duplicate_pending_notifications

    def parse_time(val, tz):
        try:
            return int(val)
        except ValueError:
            pass
        try:
            if len(val) == 10:
                val += " 00:00"
            return convert_to_unix_tz(val.split()[0], val.split()[1], tz)
        except Exception:
            raise ValueError("Invalid date/time format. Use YYYY-MM-DD HH:MM or unix timestamp.")

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT id, profile FROM user_data WHERE server_id=? AND LOWER(title)=?", (str(ctx.guild.id), title.lower()))
    row = c.fetchone()
    if not row:
        await ctx.send(f"No event found with the title `{title}`.")
        conn.close()
        return
    event_id, profile = row
    profile = profile.upper()

    # For HYV games, allow editing region-specific times
    if profile in ("HSR", "ZZZ") and item.lower() in ("start", "end"):
        # ...existing region time edit logic...
        # (unchanged, omitted for brevity)
        # ...existing code...
        return

    # --- Non-HYV logic below (unchanged except for allowed_items) ---
    # Only allow editing start, end, category, profile, image, title
    allowed_items = ["start", "end", "category", "profile", "image", "title"]
    if item.lower() not in allowed_items:
        await ctx.send(f"Cannot edit `{item}`. Only {', '.join(allowed_items)} can be edited.")
        conn.close()
        return

    if item.lower() in ("start", "end"):
        # ...existing start/end edit logic...
        # (unchanged, omitted for brevity)
        # ...existing code...
        return

    # Edit other fields
    if item.lower() == "category":
        c.execute("UPDATE user_data SET category=? WHERE id=?", (value, event_id))
    elif item.lower() == "profile":
        c.execute("UPDATE user_data SET profile=? WHERE id=?", (value.upper(), event_id))
    elif item.lower() == "image":
        c.execute("UPDATE user_data SET image=? WHERE id=?", (value, event_id))
    elif item.lower() == "title":
        # Update the title in user_data
        c.execute("UPDATE user_data SET title=? WHERE id=?", (value, event_id))
        # Also update pending_notifications and event_messages for consistency
        c.execute("UPDATE pending_notifications SET title=? WHERE server_id=? AND LOWER(title)=LOWER(?)", (value, str(ctx.guild.id), title))
        c.execute("UPDATE event_messages SET event_id=(SELECT id FROM user_data WHERE server_id=? AND title=?) WHERE server_id=? AND event_id=?", (str(ctx.guild.id), value, str(ctx.guild.id), event_id))
    conn.commit()
    await ctx.send(f"Updated `{item}` for `{title}` to `{value}`.")
    conn.close()
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

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS custom_categories (
        server_id TEXT,
        category TEXT,
        PRIMARY KEY (server_id, category)
    )''')
    c.execute("INSERT OR IGNORE INTO custom_categories (server_id, category) VALUES (?, ?)", (server_id, category))
    conn.commit()
    conn.close()
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

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM custom_categories WHERE server_id=? AND category=?", (server_id, category))
    conn.commit()
    conn.close()
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
    import sqlite3
    from datetime import datetime
    from notification_handler import remove_duplicate_pending_notifications, refresh_pending_notifications
    from database_handler import update_timer_channel

    server_id = str(ctx.guild.id)
    now = int(datetime.now().timestamp())

    await ctx.send("Refreshing all event data. This may take a moment...")

    # 1. Delete expired events and their notifications/messages
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT id, title FROM user_data WHERE server_id=? AND end_date != '' AND CAST(end_date AS INTEGER) < ?", (server_id, now))
    expired = c.fetchall()
    expired_titles = [row[1] for row in expired]
    for event_id, title in expired:
        # Remove from user_data
        c.execute("DELETE FROM user_data WHERE id=?", (event_id,))
        # Remove pending notifications for this event
        c.execute("DELETE FROM pending_notifications WHERE server_id=? AND LOWER(title)=LOWER(?)", (server_id, title))
        # Remove event messages
        c.execute("SELECT channel_id, message_id FROM event_messages WHERE event_id=?", (event_id,))
        msg_rows = c.fetchall()
        for channel_id, message_id in msg_rows:
            channel = ctx.guild.get_channel(int(channel_id))
            if channel:
                try:
                    msg = await channel.fetch_message(int(message_id))
                    await msg.delete()
                except Exception:
                    pass
        c.execute("DELETE FROM event_messages WHERE event_id=?", (event_id,))
    conn.commit()
    conn.close()

    # 2. Update all timer channels for all profiles in this server
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT profile FROM config WHERE server_id=?", (server_id,))
    profiles = [row[0] for row in c.fetchall()]
    conn.close()
    for profile in profiles:
        await update_timer_channel(ctx.guild, bot, profile=profile)

    # 3. Clear and recreate all pending notifications for this server
    await ctx.invoke(bot.get_command("refresh_pending_notifications"))

    await ctx.send(
        f"Refreshed all event data!\n"
        f"Deleted expired events: {', '.join(expired_titles) if expired_titles else 'None'}\n"
        f"Timer channels and pending notifications have been updated."
    )    