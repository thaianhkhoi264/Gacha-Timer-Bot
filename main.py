import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

import sqlite3

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import re
import asyncio
from playwright.async_api import async_playwright
import dateparser

bot_version = "0.5.7"
assigned_channels = {}

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

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
                    category TEXT
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


bot = commands.Bot(command_prefix='Kanami ', intents=intents)

@bot.event
async def on_ready():
    print(f"Kanami is ready to go!")
    # Announce in all assigned announcement channels
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT server_id, announce_channel_id FROM announce_config")
    rows = c.fetchall()
    conn.close()
    for server_id, channel_id in rows:
        guild = bot.get_guild(int(server_id))
        if guild:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    await channel.send(f"Kanami is ready to go! (version {bot_version})")
                except Exception:
                    pass

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
    c.execute("SELECT title, start_date, end_date, image, category FROM user_data WHERE server_id=? ORDER BY id DESC", (str(guild.id),))
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
        for title, start_unix, end_unix, image, category in rows:
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
                description=f"**Start:** <t:{start_unix}:F>\n**End:** <t:{end_unix}:F>",
                color=color
            )
            if image and (image.startswith("http://") or image.startswith("https://")):
                embed.set_image(url=image)
            await channel.send(embed=embed)
    else:
        await channel.send("No timer data found for this server. Use `Kanami add` to add one.")

# Function to fetch the visible text content of a tweet using Playwright
async def fetch_tweet_content(url: str) -> str:
    """Uses Playwright to fetch the visible text content and first image URL of a tweet."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        tweet_text = ""
        image_url = None
        try:
            await page.goto(url, timeout=20000)
            await page.wait_for_selector("article", timeout=10000)
            tweet_text = await page.locator("article").inner_text()
            # Try to get the first image in the tweet
            images = await page.locator("article img").all()
            for img in images:
                src = await img.get_attribute("src")
                # Filter out profile avatars and emoji images (usually have "profile_images" or "emoji" in URL)
                if src and "profile_images" not in src and "emoji" not in src:
                    image_url = src
                    break
        except Exception as e:
            tweet_text = ""
            image_url = None
        await browser.close()
    return tweet_text, image_url

# Function to extract dates from the tweet text
def parse_dates_from_text(text: str):
    """
    Tries to find start and end date/time in the tweet text using dateparser.
    Returns (start, end) as strings if found, otherwise None for missing.
    """
    # Try to find a date range like "... between May 9, 2025, 04:00 - May 23, 2025, 03:59 (UTC-7)"
    range_match = re.search(
        r'between\s+(.+?)\s*[-–]\s*(.+?)(?:[\.\)]|$)', text, re.IGNORECASE)
    if range_match:
        start_str = range_match.group(1).strip()
        end_str = range_match.group(2).strip()
        # Try to append timezone if present at the end
        tz_match = re.search(r'\((UTC[+-]\d+)\)', text)
        if tz_match:
            tz = tz_match.group(1)
            if tz not in start_str:
                start_str += f' {tz}'
            if tz not in end_str:
                end_str += f' {tz}'
        return start_str, end_str

    # Fallback: find all date-like substrings (less robust)
    date_candidates = re.findall(
        r'(\w{3,9}\s+\d{1,2},\s*\d{4}(?:,?\s*\d{2}:\d{2})?(?:\s*\(UTC[+-]\d+\))?)', text)
    parsed_dates = []
    for candidate in date_candidates:
        dt = dateparser.parse(candidate, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        if dt:
            parsed_dates.append(candidate)
    if len(parsed_dates) >= 2:
        return parsed_dates[0], parsed_dates[1]
    elif len(parsed_dates) == 1:
        return parsed_dates[0], None
    else:
        return None, None

# Function to convert a date string to a Unix timestamp
def to_unix_timestamp(date_str):
    dt = dateparser.parse(date_str, settings={'RETURN_AS_TIMEZONE_AWARE': True})
    if not dt:
        raise ValueError(f"Could not parse date: {date_str}")
    return int(dt.timestamp())

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
    await ctx.send(f"Current version is {bot_version}!")

@bot.command() # "assign" command to assign the bot to announce its readiness in this channel
@commands.has_permissions(manage_channels=True)
async def assign(ctx):
    """
    Assigns the bot to announce its readiness in this channel on startup.
    Usage: Kanami assign
    """
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("REPLACE INTO announce_config (server_id, announce_channel_id) VALUES (?, ?)", (str(ctx.guild.id), str(ctx.channel.id)))
    conn.commit()
    conn.close()
    await ctx.send("This channel has been assigned for bot announcements.")

@bot.command()  # "checkchannels" command to show assigned announcement and timer channels
async def checkchannels(ctx):
    """
    Shows which channels are set for announcements and timer updates in this server.
    Usage: Kanami checkchannels
    """
    guild_id = str(ctx.guild.id)
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()

    # Get announcement channel
    c.execute("SELECT announce_channel_id FROM announce_config WHERE server_id=?", (guild_id,))
    announce_row = c.fetchone()
    announce_channel = None
    if announce_row and announce_row[0]:
        announce_channel = ctx.guild.get_channel(int(announce_row[0]))

    # Get timer channel
    c.execute("SELECT timer_channel_id FROM config WHERE server_id=?", (guild_id,))
    timer_row = c.fetchone()
    timer_channel = None
    if timer_row and timer_row[0]:
        timer_channel = ctx.guild.get_channel(int(timer_row[0]))

    conn.close()

    msg = "**Assigned Channels:**\n"
    msg += f"**Announcement Channel:** {announce_channel.mention if announce_channel else 'Not set'}\n"
    msg += f"**Timer Channel:** {timer_channel.mention if timer_channel else 'Not set'}"

    await ctx.send(msg)

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

@bot.command() # read command to read a tweet from a Twitter/X link
async def read(ctx, link: str):
    """
    Reads a tweet from a Twitter/X link, tries to parse start/end dates, and asks for missing info.
    Usage: Kanami read <twitter_link>
    """
    await ctx.send("Reading tweet, please wait...")
    tweet_text, tweet_image = await fetch_tweet_content(link)
    if not tweet_text:
        await ctx.send("Could not read the tweet. Please check the link or try again later.")
        return

    start, end = parse_dates_from_text(tweet_text)
    missing = []
    if not start:
        missing.append("start date/time")
    if not end:
        missing.append("end date/time")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send(f"Tweet content:\n```{tweet_text[:1800]}```")
    await ctx.send("What is the title for this event?")
    try:
        title_msg = await bot.wait_for("message", timeout=60.0, check=check)
        title = title_msg.content
    except asyncio.TimeoutError:
        await ctx.send("No title provided. Cancelling.")
        return

    # --- Timezone detection and prompt ---
    # Check if either start or end contains a timezone (e.g. UTC+9, GMT+8, +0900, JST, etc.)
    timezone_regex = r"(UTC[+-]\d+|GMT[+-]\d+|[+-]\d{2}:?\d{2}|[A-Z]{2,5})"
    tz_in_start = bool(start and re.search(timezone_regex, start))
    tz_in_end = bool(end and re.search(timezone_regex, end))
    timezone_str = None

    if not (tz_in_start or tz_in_end):
        await ctx.send(
            "No timezone detected in the tweet. Please enter the timezone for this event (e.g. `UTC`, `UTC+9`, `Asia/Tokyo`, `GMT-7`, etc.):"
        )
        try:
            tz_msg = await bot.wait_for("message", timeout=60.0, check=check)
            timezone_str = tz_msg.content.strip()
        except asyncio.TimeoutError:
            await ctx.send("No timezone provided. Cancelling.")
            return

    # Ask for missing dates
    if not start and not end:
        await ctx.send("Could not find any dates. Please enter the **start** date/time (e.g. `2025-06-01 15:00`):")
        try:
            start_msg = await bot.wait_for("message", timeout=60.0, check=check)
            start = start_msg.content
        except asyncio.TimeoutError:
            await ctx.send("No start date provided. Cancelling.")
            return
        await ctx.send("Please enter the **end** date/time (e.g. `2025-06-01 18:00`):")
        try:
            end_msg = await bot.wait_for("message", timeout=60.0, check=check)
            end = end_msg.content
        except asyncio.TimeoutError:
            await ctx.send("No end date provided. Cancelling.")
            return
    elif (start and not end) or (end and not start):
        found_date = start if start else end
        try:
            # Use timezone if provided
            if timezone_str:
                found_unix = to_unix_timestamp(f"{found_date} {timezone_str}")
            else:
                found_unix = int(found_date) if found_date.isdigit() else to_unix_timestamp(found_date)
        except Exception as e:
            await ctx.send(f"Error parsing found date: {e}")
            return
        await ctx.send(
            f"Found date: `{found_date}`\n"
            f"Discord format: <t:{found_unix}:F> / <t:{found_unix}:R>\n"
            "Is this the **start** or **end** date? Reply with `start` or `end`."
        )
        try:
            type_msg = await bot.wait_for("message", timeout=60.0, check=check)
            found_type = type_msg.content.strip().lower()
        except asyncio.TimeoutError:
            await ctx.send("No response. Cancelling.")
            return

        if found_type == "start":
            start_unix = found_unix
            await ctx.send("Please enter the **end** date/time (e.g. `2025-06-01 18:00`):")
            try:
                end_msg = await bot.wait_for("message", timeout=60.0, check=check)
                if timezone_str:
                    end_unix = to_unix_timestamp(f"{end_msg.content} {timezone_str}")
                else:
                    end_unix = int(end_msg.content) if end_msg.content.isdigit() else to_unix_timestamp(end_msg.content)
            except asyncio.TimeoutError:
                await ctx.send("No end date provided. Cancelling.")
                return
        elif found_type == "end":
            end_unix = found_unix
            await ctx.send("Please enter the **start** date/time (e.g. `2025-06-01 15:00`):")
            try:
                start_msg = await bot.wait_for("message", timeout=60.0, check=check)
                if timezone_str:
                    start_unix = to_unix_timestamp(f"{start_msg.content} {timezone_str}")
                else:
                    start_unix = int(start_msg.content) if start_msg.content.isdigit() else to_unix_timestamp(start_msg.content)
            except asyncio.TimeoutError:
                await ctx.send("No start date provided. Cancelling.")
                return
        else:
            await ctx.send("Invalid response. Cancelling.")
            return
    else:
        try:
            if timezone_str:
                start_unix = to_unix_timestamp(f"{start} {timezone_str}")
                end_unix = to_unix_timestamp(f"{end} {timezone_str}")
            else:
                start_unix = int(start) if start and start.isdigit() else to_unix_timestamp(start)
                end_unix = int(end) if end and end.isdigit() else to_unix_timestamp(end)
        except Exception as e:
            await ctx.send(f"Error parsing date/time: {e}")
            return

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

    def reaction_check(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == msg.id
            and str(reaction.emoji) in emojis
        )

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=reaction_check)
        category = emojis[str(reaction.emoji)]
    except Exception:
        await ctx.send("No category selected. Event not added.")
        return

    # Ask for image (optional, but default to tweet image if available)
    if tweet_image:
        await ctx.send(f"Found an image in the tweet. Use this image? (yes/no)\n{tweet_image}")
        try:
            img_reply = await bot.wait_for("message", timeout=60.0, check=check)
            if img_reply.content.strip().lower() in ["yes", "y"]:
                image = tweet_image
            else:
                await ctx.send("If you want to add an image URL, reply with it now or type `skip`.")
                try:
                    img_msg = await bot.wait_for("message", timeout=60.0, check=check)
                    image = img_msg.content if img_msg.content.lower() != "skip" else None
                except asyncio.TimeoutError:
                    image = None
        except asyncio.TimeoutError:
            image = tweet_image
    else:
        await ctx.send("If you want to add an image URL, reply with it now or type `skip`.")
        try:
            img_msg = await bot.wait_for("message", timeout=60.0, check=check)
            image = img_msg.content if img_msg.content.lower() != "skip" else None
        except asyncio.TimeoutError:
            image = None

    # Add to database (reuse your add logic)
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
        "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(ctx.author.id), str(ctx.guild.id), new_title, str(start_unix), str(end_unix), image, category)
    )
    conn.commit()
    conn.close()
    await ctx.send(
        f"Added `{new_title}` as **{category}** with start `<t:{start_unix}:F>` and end `<t:{end_unix}:F>` to the database!"
    )
    await update_timer_channel(ctx.guild, bot)

bot.run(token,log_handler=handler, log_level=logging.DEBUG)