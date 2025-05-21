import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

import sqlite3

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

def init_db(): # Initialize the SQLite database
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    server_id TEXT,
                    title TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    image TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (
                    server_id TEXT PRIMARY KEY,
                    timer_channel_id TEXT
                )''')
    conn.commit()
    conn.close()

init_db()


bot = commands.Bot(command_prefix='Kanami ', intents=intents)

@bot.event
async def on_ready():
    print(f"Kanami is ready to go!")

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
    c.execute("SELECT title, start_date, end_date, image FROM user_data WHERE server_id=? ORDER BY id DESC", (str(guild.id),))
    rows = c.fetchall()
    conn.close()

    channel = guild.get_channel(channel_id)
    if not channel:
        return

    # Delete previous bot messages in the channel (optional: limit to last 50 for efficiency)
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            await msg.delete()

    # Send new embeds
    if rows:
        for title, start_unix, end_unix, image in rows:
            embed = discord.Embed(
                title=title,
                description=f"**Start:** <t:{start_unix}:F>\n**End:** <t:{end_unix}:F>",
                color=discord.Color.blue()
            )
            if image and (image.startswith("http://") or image.startswith("https://")):
                embed.set_image(url=image)
            await channel.send(embed=embed)
    else:
        await channel.send("No timer data found for this server. Use `Kanami add` to add one.")

@bot.event # Checks for "good girl" and "good boy" in messages
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore messages from the bot itself

    if "good girl" in message.content.lower():
        emoji = "<:KanamiHeart:1374409597628186624>"  # Custom emoji with the given ID
        await message.channel.send(emoji)

    if "good boy" in message.content.lower():
        await message.channel.send(f"Go more more jump off a bridge")

    await bot.process_commands(message)  # Ensure other commands still work

@bot.command() # "hello" command
async def hello(ctx):
    """ Responds with a hello along with a truth. """
    await ctx.send("Hello! Kanami here! Alfa is into wearing maid cosplays!")

@bot.command() # "version" command
async def version(ctx):
    """ Returns the current version of the bot. """
    await ctx.send("Current version is 0.3.0")


@bot.command() # "convert" command to convert date and time to Unix timestamp
async def convert(ctx, time: str, date: str = None):
    """
    Command to convert a given date and time into a Unix timestamp.
    If no date is provided, it assumes today's date.
    """
    try:
        # Use today's date if no date is provided
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        unix_timestamp = convert_to_unix(date, time)
        await ctx.send(f"The Unix timestamp for {date} {time} is: `{unix_timestamp}`")
        await ctx.send(f"Which is <t:{unix_timestamp}:F> your time or <t:{unix_timestamp}:R>")
    except ValueError:
        await ctx.send("Invalid date or time format. Please use `YYYY-MM-DD` for the date and `HH:MM` (24-hour) for the time.")

@bot.command() # "converttz" command to convert date and time to Unix timestamp with timezone
async def converttz(ctx, time: str, date: str = None, timezone_str: str = "UTC"):
    """
    Converts a given date and time in a specified timezone or offset into a Unix timestamp.
    Supports IANA tz names (e.g., 'Asia/Tokyo') and offsets like 'UTC-8', 'GMT+5', etc.
    """
    try:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        unix_timestamp = convert_to_unix_tz(date, time, timezone_str)
        await ctx.send(
            f"The Unix timestamp for {date} {time} in `{timezone_str}` is: `{unix_timestamp}`"
        )
        await ctx.send(
            f"Which is <t:{unix_timestamp}:F> your time or <t:{unix_timestamp}:R>"
        )
    except ValueError as e:
        await ctx.send(
            str(e) if "Unknown timezone" in str(e) else
            "Invalid date or time format. Please use `YYYY-MM-DD` for the date and `HH:MM` (24-hour) for the time."
        )       

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

    c.execute(
        "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image) VALUES (?, ?, ?, ?, ?, ?)",
        (str(ctx.author.id), str(ctx.guild.id), new_title, str(start_unix), str(end_unix), image)
    )
    conn.commit()
    conn.close()
    await ctx.send(f"Added `{new_title}` with start `<t:{start_unix}:F>` and end `<t:{end_unix}:F>` to the database!")
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

@bot.command() # "update" command to manually update the timer channel
async def update(ctx):
    """Manually update the timer channel with the latest events."""
    await update_timer_channel(ctx.guild, bot)
    await ctx.send("Timer channel updated with the latest events.")

@bot.command() # settimerchannel command to set the current channel as the timer display channel
@commands.has_permissions(manage_channels=True)
async def settimerchannel(ctx):
    """Set the current channel as the timer display channel."""
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("REPLACE INTO config (server_id, timer_channel_id) VALUES (?, ?)",
              (str(ctx.guild.id), str(ctx.channel.id)))
    conn.commit()
    conn.close()
    await ctx.send("This channel is now set for timer updates.")

bot.run(token,log_handler=handler, log_level=logging.DEBUG)