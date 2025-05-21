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
    conn.commit()
    conn.close()

init_db()


bot = commands.Bot(command_prefix='Kanami ', intents=intents)

@bot.event
async def on_ready():
    print(f"Kanami is ready to go, {bot.user.name}!")

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
    await ctx.send("Current version is 0.1.5")


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
    """ Sends an embed with the latest timer details for this server """
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Get the latest timer for this server
    c.execute(
        "SELECT title, start_date, end_date, image FROM user_data WHERE server_id=? ORDER BY id DESC LIMIT 1",
        (str(ctx.guild.id),)
    )
    row = c.fetchone()
    conn.close()

    if row:
        title, start_unix, end_unix, image = row
        embed = discord.Embed(
            title=title,
            description=f"**Start:** <t:{start_unix}:F>\n**End:** <t:{end_unix}:F>",
            color=discord.Color.blue()
        )
        if image:
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

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image) VALUES (?, ?, ?, ?, ?, ?)",
        (str(ctx.author.id), str(ctx.guild.id), title, str(start_unix), str(end_unix), image)
    )
    conn.commit()
    conn.close()
    await ctx.send(f"Added `{title}` with start `<t:{start_unix}:F>` and end `<t:{end_unix}:F>` to the database!")


bot.run(token,log_handler=handler, log_level=logging.DEBUG)