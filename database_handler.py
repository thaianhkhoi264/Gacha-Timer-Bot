import discord
from discord import app_commands
from discord.ext import commands
from modules import *
from bot import bot
import asyncio

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
        sent INTEGER DEFAULT 0
    )''')
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
async def add(ctx, title: str, start: str, end: str, image: str = None, profile: str = None, category: str = None, timezone_str: str = "UTC"):
    """
    Adds a new entry to the database.
    For HSR/ZZZ, prompts for all three region times in server time.
    """
    import sqlite3
    import asyncio
    from notification_handler import schedule_notifications_for_event

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

    valid_profiles = ["HSR", "ZZZ", "AK", "STRI", "WUWA", "ALL"]
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
    else:
        profile = profile.upper()
        if profile not in valid_profiles:
            await ctx.send(f"Invalid profile `{profile}`. Must be one of: {', '.join(valid_profiles)}.")
            return

    # Prompt for category if not provided
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

    # For HYV games, prompt for all three region times
    if profile in ("HSR", "ZZZ"):
        await ctx.send("Enter **Asia server** start date/time (YYYY-MM-DD HH:MM, server time):")
        def check(m): return m.author == ctx.author and m.channel == ctx.channel
        try:
            asia_start_msg = await bot.wait_for("message", timeout=60.0, check=check)
            asia_start = parse_time(asia_start_msg.content, "Asia/Shanghai")
        except Exception:
            await ctx.send("No valid Asia start time provided. Event not added.")
            return

        await ctx.send("Enter **Asia server** end date/time (YYYY-MM-DD HH:MM, server time):")
        try:
            asia_end_msg = await bot.wait_for("message", timeout=60.0, check=check)
            asia_end = parse_time(asia_end_msg.content, "Asia/Shanghai")
        except Exception:
            await ctx.send("No valid Asia end time provided. Event not added.")
            return

        await ctx.send("Enter **America server** start date/time (YYYY-MM-DD HH:MM, server time):")
        try:
            america_start_msg = await bot.wait_for("message", timeout=60.0, check=check)
            america_start = parse_time(america_start_msg.content, "America/New_York")
        except Exception:
            await ctx.send("No valid America start time provided. Event not added.")
            return

        await ctx.send("Enter **America server** end date/time (YYYY-MM-DD HH:MM, server time):")
        try:
            america_end_msg = await bot.wait_for("message", timeout=60.0, check=check)
            america_end = parse_time(america_end_msg.content, "America/New_York")
        except Exception:
            await ctx.send("No valid America end time provided. Event not added.")
            return

        await ctx.send("Enter **Europe server** start date/time (YYYY-MM-DD HH:MM, server time):")
        try:
            europe_start_msg = await bot.wait_for("message", timeout=60.0, check=check)
            europe_start = parse_time(europe_start_msg.content, "Europe/Berlin")
        except Exception:
            await ctx.send("No valid Europe start time provided. Event not added.")
            return

        await ctx.send("Enter **Europe server** end date/time (YYYY-MM-DD HH:MM, server time):")
        try:
            europe_end_msg = await bot.wait_for("message", timeout=60.0, check=check)
            europe_end = parse_time(europe_end_msg.content, "Europe/Berlin")
        except Exception:
            await ctx.send("No valid Europe end time provided. Event not added.")
            return

        # Use Asia server as the global start/end
        start_unix = asia_start
        end_unix = asia_end

        # Insert into DB
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        base_title = title
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
            "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(ctx.author.id), str(ctx.guild.id), new_title, str(start_unix), str(end_unix), image, category, 1,
             str(asia_start), str(asia_end), str(america_start), str(america_end), str(europe_start), str(europe_end), profile)
        )
        conn.commit()
        conn.close()

        await ctx.send(
            f"Added `{new_title}` as **{category}** for **{profile}** with region times to the database!"
        )

        # Update timer channels and schedule notifications for all regions
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        c.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),))
        profiles = [row[0] for row in c.fetchall()]
        conn.close()
        for prof in profiles:
            await update_timer_channel(ctx.guild, bot, profile=prof)

        # Schedule notifications for each region
        for region, region_start, region_end in [
            ("NA", america_start, america_end),
            ("EU", europe_start, europe_end),
            ("ASIA", asia_start, asia_end)
        ]:
            event = {
                'server_id': str(ctx.guild.id),
                'category': category,
                'profile': profile,
                'title': new_title,
                'start_date': str(region_start),
                'end_date': str(region_end),
                'region': region
            }
            asyncio.create_task(schedule_notifications_for_event(event))
        return

    # --- Non-HYV logic below (unchanged) ---
    try:
        start_unix = parse_time(start, timezone_str)
        end_unix = parse_time(end, timezone_str)
    except Exception as e:
        await ctx.send(f"Error parsing date/time: {e}")
        return

    # Insert into DB for non-HYV
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    base_title = title
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
        f"Added `{new_title}` as **{category}** for **{profile}** to the database!"
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
    asyncio.create_task(schedule_notifications_for_event(event))

@bot.command()  # "remove" command to remove an event from the database
async def remove(ctx, *, title: str):
    """
    Removes an event by title (case-insensitive) from the current server, along with its notifications and messages.
    Usage: Kanami remove <event title>
    """
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

# ...existing code...

@bot.command()
async def edit(ctx, title: str, item: str, value: str):
    """
    Edits an existing event in the database.
    For HSR/ZZZ, allows editing region-specific times.
    Now supports editing the event title.
    """
    import sqlite3

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
    