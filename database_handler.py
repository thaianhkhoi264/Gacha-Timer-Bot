import discord
from modules import *
from bot import *
from notification_handler import schedule_notifications_for_event

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
    elif category == "Maintenence":
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
        embed.description = f"**Start:** <t:{start_unix}:F>\n**End:** <t:{end_unix}:F>"
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

# Function to update the timer channel with the latest events for a given profile
async def update_timer_channel(guild, bot, profile="ALL"):
    profile_map = {
        "HSR": "honkaistarrail",
        "ZZZ": "zzz_en",
        "AK": "ArknightsEN",
        "ALL": "ALL"
    }
    canonical_profile = profile_map.get(profile, profile)

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
    if canonical_profile == "ALL":
        c.execute(
            "SELECT id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile FROM user_data WHERE server_id=? ORDER BY id DESC",
            (str(guild.id),)
        )
    else:
        c.execute(
            "SELECT id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile FROM user_data WHERE server_id=? AND profile=? ORDER BY id DESC",
            (str(guild.id), canonical_profile)
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
    dt_local = dt_naive.replace(tzinfo=tz)
    return int(dt_local.timestamp())


@bot.command()  # "add" command to add data into the database
async def add(ctx, title: str, start: str, end: str, image: str = None, profile: str = None, category: str = None, timezone_str: str = "UTC"):
    """
    Adds a new entry to the database.
    - title: The title for the timer/event.
    - start: Start date/time (YYYY-MM-DD HH:MM or unix timestamp).
    - end: End date/time (YYYY-MM-DD HH:MM or unix timestamp).
    - image: (Optional) Image URL.
    - profile: (Optional) Profile (e.g., HSR, ZZZ, AK, ALL).
    - category: (Optional) Category (Banner, Event, Maintenence).
    - timezone_str: (Optional) Timezone for date/time (default: UTC).
    If the title already exists, appends a number to make it unique (e.g., "Event", "Event 2", ...).
    """
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

    try:
        start_unix = parse_time(start, timezone_str)
        end_unix = parse_time(end, timezone_str)
    except Exception as e:
        await ctx.send(f"Error parsing date/time: {e}")
        return

    # Check for duplicate titles and append a number if needed
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

    # Prompt for category if not provided
    if not category:
        msg = await ctx.send(
            "What category should this event be?\n"
            ":blue_square: Banner\n"
            ":yellow_square: Event\n"
            ":red_square: Maintenance"
        )
        emojis = {
            "🟦": "Banner",
            "🟨": "Event",
            "🟥": "Maintenence"
        }
        for emoji in emojis:
            await msg.add_reaction(emoji)

        def check(reaction, user):
            return (
                user == ctx.author
                and reaction.message.id == msg.id
                and str(reaction.emoji) in emojis
            )

        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
            category = emojis[str(reaction.emoji)]
        except Exception:
            await ctx.send("No category selected. Event not added.")
            conn.close()
            return

    # Prompt for profile if not provided
    valid_profiles = ["HSR", "ZZZ", "AK", "ALL"]
    if not profile:
        await ctx.send(f"Which profile is this event for? (Type one of: {', '.join(valid_profiles)})")
        def profile_check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() in valid_profiles
        try:
            msg = await bot.wait_for("message", timeout=60.0, check=profile_check)
            profile = msg.content.upper()
        except Exception:
            await ctx.send("No valid profile provided. Event not added.")
            conn.close()
            return
    else:
        profile = profile.upper()
        if profile not in valid_profiles:
            await ctx.send(f"Invalid profile `{profile}`. Must be one of: {', '.join(valid_profiles)}.")
            conn.close()
            return

    c.execute(
        "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category, profile) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(ctx.author.id), str(ctx.guild.id), new_title, str(start_unix), str(end_unix), image, category, profile)
    )
    conn.commit()
    conn.close()

    # SCHEDULE NOTIFICATION HERE
    event = {
        'server_id': str(ctx.guild.id),
        'category': category,
        'profile': profile,
        'title': new_title,
        'start_date': str(start_unix),
        'end_date': str(end_unix)
    }
    await schedule_notifications_for_event(event)

    await ctx.send(
        f"Added `{new_title}` as **{category}** for **{profile}** with start `<t:{start_unix}:F>` and end `<t:{end_unix}:F>` to the database!"
    )
    # Update all timer channels for all profiles in this server
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),))
    profiles = [row[0] for row in c.fetchall()]
    conn.close()
    for prof in profiles:
        await update_timer_channel(ctx.guild, bot, profile=prof)

@bot.command()  # "remove" command to remove an event from the database
async def remove(ctx, title: str):
    # ...existing code to find event_id...
    event_id, start, end = row

    # Remove the event
    c.execute("DELETE FROM user_data WHERE id=?", (event_id,))
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

    await ctx.send(f"Removed event `{title}` (Start: <t:{start}:F>, End: <t:{end}:F>) from the database.")
    # Update all timer channels for all profiles in this server
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),))
    profiles = [row[0] for row in c.fetchall()]
    conn.close()
    for profile in profiles:
        await update_timer_channel(ctx.guild, bot, profile=profile)

@bot.command() # "timer" command
async def timer(ctx):
    """ Sends each event as its own embed with its image for this server """
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute(
        "SELECT title, start_date, end_date, image FROM user_data WHERE server_id=? ORDER BY id DESC",
        (str(ctx.guild.id),)
    )
    rows = c.fetchall()
    conn.close()

    if rows:
        for title, start_unix, end_unix, image in rows:
            embed = discord.Embed(
                title=title,
                description=f"**Start:** <t:{start_unix}:F>\n**End:** <t:{end_unix}:F>",
                color=discord.Color.blue()
            )
            # Only set image if it's a valid URL
            if image and (image.startswith("http://") or image.startswith("https://")):
                embed.set_image(url=image)
            await ctx.send(embed=embed)
    else:
        await ctx.send("No timer data found for this server. Use `Kanami add` to add one.")
