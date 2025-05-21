from modules import *
from bot import *

# Initialize the database
def init_db():
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
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
                    europe_end TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (
                    server_id TEXT PRIMARY KEY,
                    timer_channel_id TEXT
                )''')
    # Add a new table for announcement channels
    c.execute('''CREATE TABLE IF NOT EXISTS announce_config (
                    server_id TEXT PRIMARY KEY,
                    announce_channel_id TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

# Function to update the timer channel with the latest events
async def update_timer_channel(guild, bot):
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT timer_channel_id FROM config WHERE server_id=?", (str(guild.id),))
    row = c.fetchone()
    if not row:
        conn.close()
        return  # No timer channel set
    channel_id = int(row[0])
    c.execute("SELECT title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end FROM user_data WHERE server_id=? ORDER BY id DESC", (str(guild.id),))
    rows = c.fetchall()
    conn.close()

    channel = guild.get_channel(channel_id)
    if not channel:
        return

    # Delete previous bot messages in the channel (optional: limit to last 50 for efficiency)
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    # Send new embeds with color based on category
    if rows:
        for row in rows:
            title, start_unix, end_unix, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end = row
            color = discord.Color.blue()  # Default to blue
            if category == "Banner":
                color = discord.Color.blue()
            elif category == "Event":
                color = discord.Color.gold()
            elif category == "Maintenence":
                color = discord.Color.red()
            else:
                color = discord.Color.blurple()
            embed = discord.Embed(
                title=title,
                color=color
            )
            if int(is_hyv):
                # Show all three regions
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
            await channel.send(embed=embed)
    else:
        await channel.send("No timer data found for this server. Use `Kanami add` to add one.")


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
async def add(ctx, title: str, start: str, end: str, image: str = None, timezone_str: str = "UTC"):
    """
    Adds a new entry to the database.
    - title: The title for the timer/event.
    - start: Start date/time (YYYY-MM-DD HH:MM or unix timestamp).
    - end: End date/time (YYYY-MM-DD HH:MM or unix timestamp).
    - image: (Optional) Image URL.
    - timezone_str: (Optional) Timezone for date/time (default: UTC).
    If the title already exists, appends a number to make it unique (e.g., "Event", "Event 2", "Event 3", ...).
    """
    def parse_time(val, tz):
        # Try to parse as unix timestamp
        try:
            return int(val)
        except ValueError:
            pass
        # Try to parse as date/time string
        try:
            if len(val) == 10:  # Only date provided
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

    # Ask for category
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

    c.execute(
        "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(ctx.author.id), str(ctx.guild.id), new_title, str(start_unix), str(end_unix), image, category)
    )
    conn.commit()
    conn.close()
    await ctx.send(
        f"Added `{new_title}` as **{category}** with start `<t:{start_unix}:F>` and end `<t:{end_unix}:F>` to the database!"
    )
    await update_timer_channel(ctx.guild, bot)

@bot.command()  # "remove" command to remove an event from the database
async def remove(ctx, title: str):
    """
    Removes an event by title for this server.
    Usage: Kanami remove <title>
    """
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Find the event with the exact title
    c.execute(
        "SELECT id, start_date, end_date FROM user_data WHERE server_id=? AND title=?",
        (str(ctx.guild.id), title)
    )
    row = c.fetchone()

    if not row:
        await ctx.send(f"No event with the title `{title}` found for this server.")
        conn.close()
        return

    event_id, start, end = row

    # Remove the event
    c.execute("DELETE FROM user_data WHERE id=?", (event_id,))
    conn.commit()
    conn.close()
    await ctx.send(f"Removed event `{title}` (Start: <t:{start}:F>, End: <t:{end}:F>) from the database.")
    await update_timer_channel(ctx.guild, bot)

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
