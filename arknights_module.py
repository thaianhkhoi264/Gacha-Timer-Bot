import os
import aiosqlite
import asyncio
import discord
from discord.ext import commands
from modules import *
from bot import bot
from datetime import datetime, timezone
from global_config import ONGOING_EVENTS_CHANNELS, UPCOMING_EVENTS_CHANNELS
from ml_handler import run_llm_inference  # Uses the LLM as in ml_handler.py

# Path to Arknights-specific database
AK_DB_PATH = os.path.join("data", "arknights_data.db")

# Ensure the database and tables exist
async def init_ak_db():
    async with aiosqlite.connect(AK_DB_PATH) as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                server_id TEXT,
                title TEXT,
                start_date TEXT,
                end_date TEXT,
                image TEXT,
                category TEXT,
                profile TEXT
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS event_messages (
                event_id INTEGER,
                server_id TEXT,
                channel_id TEXT,
                message_id TEXT,
                PRIMARY KEY (event_id, channel_id)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_update_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT,
                update_unix INTEGER,
                status TEXT DEFAULT 'pending'
            )
        ''')
        await conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_update_time_server ON scheduled_update_tasks (server_id, update_unix)
        ''')
        await conn.commit()

SCHEDULED_UPDATE_TASKS = {}  # { (server_id, update_unix): asyncio.Task }

async def schedule_update_task(server_id, update_unix):
    """
    Schedules arknights_update_timers for the given server at update_unix.
    Avoids scheduling if a task exists within ±15 minutes.
    """
    async with aiosqlite.connect(AK_DB_PATH) as conn:
        min_time = update_unix - 900
        max_time = update_unix + 900
        async with conn.execute(
            "SELECT 1 FROM scheduled_update_tasks WHERE server_id=? AND update_unix BETWEEN ? AND ?",
            (str(server_id), min_time, max_time)
        ) as cursor:
            if await cursor.fetchone():
                return  # Task already scheduled in this window
        await conn.execute(
            "INSERT OR IGNORE INTO scheduled_update_tasks (server_id, update_unix) VALUES (?, ?)",
            (str(server_id), update_unix)
        )
        await conn.commit()

    # Actually schedule the task in memory
    delay = update_unix - int(datetime.now(timezone.utc).timestamp())
    if delay > 0:
        key = (str(server_id), update_unix)
        if key in SCHEDULED_UPDATE_TASKS:
            return  # Already scheduled in memory
        SCHEDULED_UPDATE_TASKS[key] = asyncio.create_task(run_update_after_delay(server_id, update_unix, delay))

async def periodic_ak_cleanup():
    from arknights_module import cleanup_old_update_tasks
    while True:
        await cleanup_old_update_tasks()
        await asyncio.sleep(86400)  # Run once every 24 hours

async def run_update_after_delay(server_id, update_unix, delay):
    await asyncio.sleep(delay)
    guild = bot.get_guild(int(server_id))
    if guild:
        await arknights_update_timers(guild)
    # Mark as done in DB
    async with aiosqlite.connect(AK_DB_PATH) as conn:
        await conn.execute(
            "UPDATE scheduled_update_tasks SET status='done' WHERE server_id=? AND update_unix=?",
            (str(server_id), update_unix)
        )
        await conn.commit()

async def load_scheduled_ak_update_tasks():
    """
    Loads all pending scheduled update tasks from the DB and schedules them in memory.
    Call this once on bot startup.
    """
    async with aiosqlite.connect(AK_DB_PATH) as conn:
        now = int(datetime.now(timezone.utc).timestamp())
        async with conn.execute(
            "SELECT server_id, update_unix FROM scheduled_update_tasks WHERE update_unix > ? AND status='pending'",
            (now,)
        ) as cursor:
            async for row in cursor:
                server_id, update_unix = row
                await schedule_update_task(server_id, update_unix)

# --- Event Posting Helper ---
async def post_event_embed(channel, event):
    """Posts an embed for the event in the given channel and returns the message."""
    embed = discord.Embed(
        title=event["title"],
        description=f"**Start:** <t:{event['start']}:F>\n**End:** <t:{event['end']}:F>",
        color=discord.Color.teal()
    )
    if event.get("image") and event["image"].startswith("http"):
        embed.set_image(url=event["image"])
    return await channel.send(embed=embed)

# --- Event Deletion Helper ---
async def delete_event_message(guild, channel_id, event_id):
    """Deletes the event message from the channel and removes its record from the DB."""
    async with aiosqlite.connect(AK_DB_PATH) as conn:
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

# --- Event Upsert Helper ---
async def upsert_event_message(guild, channel, event, event_id):
    """Edits the event message if it exists, otherwise sends a new one and updates the DB."""
    async with aiosqlite.connect(AK_DB_PATH) as conn:
        async with conn.execute(
            "SELECT message_id FROM event_messages WHERE event_id=? AND channel_id=?",
            (event_id, str(channel.id))
        ) as cursor:
            row = await cursor.fetchone()
        embed = discord.Embed(
            title=event["title"],
            description=f"**Start:** <t:{event['start']}:F>\n**End:** <t:{event['end']}:F>",
            color=discord.Color.teal()
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
                pass  # If message not found, fall through to send new
        msg = await channel.send(embed=embed)
        await conn.execute(
            "REPLACE INTO event_messages (event_id, server_id, channel_id, message_id) VALUES (?, ?, ?, ?)",
            (event_id, str(guild.id), str(channel.id), str(msg.id))
        )
        await conn.commit()

async def arknights_update_timers(guild):
    """
    Updates all Arknights event dashboards:
    - Moves events between upcoming/current channels as needed.
    - Deletes ended events and their messages.
    - Ensures no overlapping events with the same name.
    """
    now = int(datetime.now(timezone.utc).timestamp())
    ongoing_channel = guild.get_channel(ONGOING_EVENTS_CHANNELS["AK"])
    upcoming_channel = guild.get_channel(UPCOMING_EVENTS_CHANNELS["AK"])

    async with aiosqlite.connect(AK_DB_PATH) as conn:
        # Fetch all events, sorted by start time
        async with conn.execute(
            "SELECT id, title, start_date, end_date, image, category FROM events WHERE server_id=? ORDER BY start_date ASC",
            (str(guild.id),)
        ) as cursor:
            events = [dict(
                id=row[0], title=row[1], start=int(row[2]), end=int(row[3]), image=row[4], category=row[5]
            ) async for row in cursor]

        # Track which titles are currently ongoing
        ongoing_titles = set()
        for event in events:
            # If event has ended, delete from DB and both channels
            if event["end"] < now:
                await delete_event_message(guild, ONGOING_EVENTS_CHANNELS["AK"], event["id"])
                await delete_event_message(guild, UPCOMING_EVENTS_CHANNELS["AK"], event["id"])
                await conn.execute("DELETE FROM events WHERE id=?", (event["id"],))
                await conn.commit()
                continue

            # If event is ongoing
            if event["start"] <= now < event["end"]:
                # Only allow one ongoing event with the same title
                if event["title"] in ongoing_titles:
                    # If another event with the same name is ongoing, skip this one (or handle as needed)
                    continue
                ongoing_titles.add(event["title"])
                # Remove from upcoming channel if exists
                await delete_event_message(guild, UPCOMING_EVENTS_CHANNELS["AK"], event["id"])
                # Upsert in ongoing channel
                await upsert_event_message(guild, ongoing_channel, event, event["id"])
            # If event is upcoming
            elif event["start"] > now:
                # Only add to upcoming if no ongoing event with the same name
                if event["title"] in ongoing_titles:
                    continue  # Wait until the current event ends
                # Upsert in upcoming channel
                await upsert_event_message(guild, upcoming_channel, event, event["id"])
                # Remove from ongoing channel if exists (shouldn't be, but for safety)
                await delete_event_message(guild, ONGOING_EVENTS_CHANNELS["AK"], event["id"])

def parse_title_ak(text):
    """
    Parses Arknights tweet text to extract the event/banner/maintenance title.
    Handles banner logic as described in the prompt.
    """
    import re
    # 1. Maintenance
    maint_match = re.search(r"maintenance on (\w+ \d{1,2}, \d{4})", text, re.IGNORECASE)
    if maint_match:
        date = maint_match.group(1)
        return f"{date} Maintenance"

    # 2. Title line (fallback for events)
    title_match = re.search(r"Title\s*:?\s*(.+)", text, re.IGNORECASE)
    if title_match:
        return title_match.group(1).strip()

    # 3. Banner logic
    # Find ★★★★★★ line
    six_star_match = re.search(r"★{6}:\s*(.+)", text)
    if six_star_match:
        six_star_line = six_star_match.group(1)
        # Split by / or comma
        six_stars = [s.strip() for s in re.split(r"/|,|\n", six_star_line) if s.strip()]
        num_six = len(six_stars)

        # Case 1: 2 6*s
        if num_six == 2:
            kernel_list = [
                "Exusiai", "Siege", "Ifrit", "Eyjafjalla", "Angelina", "Shining", "Nightingale",
                "Hoshiguma", "Saria", "SilverAsh", "Skadi", "Ch'en", "Schwarz", "Hellagur",
                "Magallan", "Mostima", "Blaze", "Aak", "Ceobe", "Bagpipe", "Phantom", "Rosa",
                "Suzuran", "Weedy", "Thorns", "Eunectes", "Surtr", "Blemishine", "Mudrock",
                "Mountain", "Archetto", "Saga", "Passenger", "Kal'tsit", "Carnelian", "Pallas"
            ]
            # If any kernel operator is present
            if any(op.lower() in (s.lower() for s in six_stars) for op in kernel_list):
                return "Kernel Banner"
            # If "Limited" or "[Limited]" in text
            if re.search(r"\[?Limited\]?", text, re.IGNORECASE):
                return "Limited Banner"
            return "Rotating Banner"

        # Case 2: 4 6*s
        elif num_six == 4:
            return "Joint Operation"

        # Case 3: 1 6*
        elif num_six == 1:
            return f"{six_stars[0]} Banner"

        # Case 4: fallback
        else:
            return "Special Banner"

    # Fallback: first non-empty line after "Dear Doctor,"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if "dear doctor" in line.lower() and i + 1 < len(lines):
            return lines[i + 1]

    # Fallback: first non-empty line
    for line in lines:
        if line:
            return line

    return "Unknown Title"

def parse_category_ak(text):
    """
    Parses Arknights tweet text to determine the event category.
    Returns one of: "Banner", "Event", "Maintenance", or None.
    """
    text_lower = text.lower()
    if "operator" in text_lower or "operators" in text_lower:
        return "Banner"
    elif "event" in text_lower:
        return "Event"
    elif "maintenance" in text_lower:
        return "Maintenance"
    return None

async def parse_dates_ak(ctx, text):
    """
    Parses Arknights event/maintenance tweets for start and end times.
    If only one date is found, prompts the user for event duration and calculates the end date.
    Returns (start, end) as strings if found, otherwise None for missing.
    """
    current_year = datetime.now().year

    def ensure_year(date_str):
        if re.search(r'\b\d{4}\b', date_str):
            return date_str
        match = re.match(r'([A-Za-z]+ \d{1,2}),?\s*(\d{2}:\d{2})(.*)', date_str)
        if match:
            month_day = match.group(1)
            time_part = match.group(2)
            rest = match.group(3)
            return f"{month_day}, {current_year}, {time_part}{rest}"
        return date_str

    # 1. Range with dash or en-dash and optional UTC
    match = re.search(
        r'(?:during|between)?\s*([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?,?\s*\d{2}:\d{2}(?:\s*\(UTC[+-]\d+\))?)\s*[-–]\s*([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?,?\s*\d{2}:\d{2}(?:\s*\(UTC[+-]\d+\))?)',
        text, re.IGNORECASE)
    if match:
        start = ensure_year(match.group(1).strip())
        end = ensure_year(match.group(2).strip())
        return start, end

    # 2. Maintenance with single date and time range (e.g. May 8, 2025, 10:00-10:10 (UTC-7))
    match = re.search(
        r'on\s*([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?),?\s*(\d{2}:\d{2})\s*[-–]\s*(\d{2}:\d{2})\s*\((UTC[+-]\d+)\)',
        text, re.IGNORECASE)
    if match:
        date = ensure_year(match.group(1).strip())
        start_time = match.group(2).strip()
        end_time = match.group(3).strip()
        tz = match.group(4).strip()
        start = f"{date}, {start_time} ({tz})"
        end = f"{date}, {end_time} ({tz})"
        return start, end
    
    # 2.5. Lax date-time range
    match = re.search(
    r'([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?,?\s*\d{1,2}:\d{2})\s*[-–]\s*([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?,?\s*\d{1,2}:\d{2})(?:\s*\((UTC[+-]\d+)\))?',
    text, re.IGNORECASE)
    if match:
        start = ensure_year(match.group(1).strip())
        end = ensure_year(match.group(2).strip())
        tz = match.group(3)
        if tz:
            start += f" ({tz})"
            end += f" ({tz})"
        return start, end

    # 3. Fallback: single date/time with UTC or missing year
    match = re.search(
        r'([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?,?\s*\d{2}:\d{2}(?:\s*\(UTC[+-]\d+\))?)',
        text, re.IGNORECASE)
    if match:
        date = ensure_year(match.group(1).strip())
        # Prompt user for duration
        await ctx.send("Kanami only found 1 date in the tweet... How many days does this event last for? (Enter a number, e.g. `14`)")
        def check(m): return m.author == ctx.author and m.channel == ctx.channel
        try:
            msg = await bot.wait_for("message", timeout=60.0, check=check)
            days = int(msg.content.strip())
        except Exception:
            await ctx.send("No valid duration provided. Cancelling.")
            return date, None

        # Parse the start date to datetime
        import dateparser
        dt = dateparser.parse(date)
        if not dt:
            await ctx.send("Could not parse the start date. Cancelling.")
            return date, None

        # Add days, set time to 03:59 of the same timezone as start
        end_dt = dt + timedelta(days=days)
        end_dt = end_dt.replace(hour=3, minute=59)
        # Try to extract timezone from the original string
        tz_match = re.search(r'\(UTC[+-]\d+\)', date)
        tz_str = tz_match.group(0) if tz_match else ""
        # Format end date in the same style as start
        end_str = end_dt.strftime("%B %d, %Y, %H:%M") + f" {tz_str}".strip()
        return date, end_str

    return None, None

# --- Tweet Listening and Filtering ---

async def is_ak_event_tweet(tweet_text):
    """
    Uses the LLM to classify if a tweet is an Arknights event/announcement.
    Returns True if it's an event, False otherwise.
    """
    prompt = (
        "Classify the following tweet for the game profile 'AK' (Arknights)."
        ""
        "Reply only with 'Event' if it is an in-game event, banner, or maintenance/update announcement that has a clear start and end time, or a clear time window for participation or availability."
        "Do NOT classify as 'Event' if the tweet is about outfits, skins, music, comics, trailers, fanart, lore, rewards, or any non-event content, even if they have a time window."
        "Outfit/skin announcements are NOT events, even if they have a start/end date."
        "The tweet is only classified as an 'Event' if it is about gameplay content (e.g., new stages, banners, maintenance, or in-game missions) with a time window."
        "If the tweet is not an event, reply only with 'Filler'."
        ""
        "Examples:"
        ""
        "Tweet:"
        "Dear Doctor,"
        "New episode: Dissociative Recombination will soon be live on September 16, 10:00 (UTC-7), and some of the contents are available for a limited time. Please refer to the following notification for the event details."
        "Classification: Event"
        ""
        "Tweet:"
        "【Ambience Synesthesia Tailor-Provided - Golden Reverie - Muelsyse】"
        "Now available at the Store until October 14, 2025, 03:59 (UTC-7)!"
        "Classification: Filler"
        ""
        "Tweet:"
        "Dear Doctor, thank you for playing New episode: Dissociative Recombination!"
        "\"Hope is never a lie. Rhodes Island still clings to that faintest sliver of possibility—to press forward.\""
        "Classification: Filler"
        ""
        "Tweet:"
        "Arknights EP - Skeletal Wings"
        "When wind swept through, bore did the tide; in dust left in endlessness, memories laid."
        "Skeletal wings carving yesterdays, measuring unfinished faraways."
        "Classification: Filler"
        ""
        "Tweet:"
        "【Ambience Synesthesia Tailor-Provided - Melodic Flutter - Ines】"
        "Now available at the Store until October 14, 2025, 03:59 (UTC-7)!"
        "Classification: Filler"
        ""
        "Tweet:"
        "【0011 Tempest Series - Candy Strike - Odda】"
        "Collect 'Courage' Badge to redeem this outfit FOR FREE in Closure's Backup before October 7, 2025, 03:59 (UTC-7)!"
        "Classification: Filler"
        ""
        "Tweet:"
        "【New Operators】"
        "Operators Mon3tr, Alanna and Windscoot will be rated up in the Limited-time Headhunting - Command: Reconstruction between September 16, 2025, 10:00 - September 30, 2025, 03:59 (UTC-7)!"
        "Classification: Event"
        ""
        "Tweet:"
        "Dear Doctor, the new episode: Dissociative Recombination will be available soon. Here is a brief introduction about the new enemies and the new mechanisms. Hope this can help you in challenging the stages of Dissociative Recombination."
        "Classification: Filler"
        ""
        "Tweet:"
        "Dear Doctor,"
        "The following Operators will appear at a higher rate between September 16, 2025, 10:00 - September 30, 2025, 03:59 (UTC-7)."
        "★★★★★★: Mon3tr"
        "★★★★★: Alanna / Cement"
        "★★★★: Windscoot"
        "Classification: Event"
        ""
        "Tweet:"
        "Dear Doctor,"
        "Please note that we plan to perform the following server maintenance on September 16, 2025, 10:00-10:10 (UTC-7). Thank you for your understanding and support."
        "Classification: Event"
        ""
        "Tweet:"
        "Dear Doctor,"
        "Limited-Time Headhunting - Orienteering Headhunting will be available between September 4, 2025, 10:00 – September 18, 2025, 03:59 (UTC-7)."
        "Classification: Event"
        ""
        "Tweet:"
        "【EPOQUE Collection - Playfellows - Vermeil】"
        "Raise Hype levels in Icebreaker Games #1 to obtain this outfit FOR FREE before September 28, 2025, 03:59 (UTC-7)!"
        "Classification: Filler"
        ""
        "Now classify this tweet:"
        "{tweet_text}"
        "Classification:"
    )
    response = await run_llm_inference(prompt)
    return response.strip().lower().startswith("event")

# --- Tweet Reading and Event Extraction ---

async def extract_ak_event_from_tweet(tweet_text, tweet_image):
    """
    Uses the LLM to extract event details from an Arknights tweet.
    Returns a dict with title, category, start, end, image (if found).
    """
    prompt = (
        "Extract the following information from this Arknights event announcement tweet."
        "Reply in this exact format (one line per field, no extra text, no quotes):"
        ""
        "Title: <title>"
        "Category: <category>"
        "Profile: AK"
        "Start: <UNIX timestamp>"
        "End: <UNIX timestamp>"
        "Image: <image url or None>"
        ""
        "Rules:"
        "- The Category should be one of these single words: [Banner, Event, Maintenance]. Do not use phrases."
        "- Only extract if the tweet is about an in-game event, banner, or maintenance/update with a clear time window."
        "- Do NOT extract for outfits, skins, music, comics, trailers, fanart, lore, or rewards, even if they have a time window. For these, reply with None for all fields except Profile."
        "- If the tweet has the word 'headhunting' or 'rate up' or 'operator', it is a banner."
        "- If the Category is Banner, the Title should include the name of the 6★ Operators in the Banner, or the banner name if multiple."
        "- If any field is missing, write None for that field."
        "- If the tweet contains a date range, always convert and extract Start and End as UNIX timestamps in UTC."
        "- For banners, Category must be Banner and Start/End must be extracted from the date range."
        ""
        "Examples:"
        ""
        "Tweet:"
        "Dear Doctor,"
        "New episode: Dissociative Recombination will soon be live on September 16, 10:00 (UTC-7), and some of the contents are available for a limited time. Please refer to the following notification for the event details."
        "Image: https://pbs.twimg.com/media/example.jpg"
        "Title: Dissociative Recombination"
        "Category: Event"
        "Profile: AK"
        "Start: 1726498800"
        "End: 1727715600"
        "Image: https://pbs.twimg.com/media/example.jpg"
        ""
        "Tweet:"
        "【New Operators】"
        "Operators Mon3tr, Alanna and Windscoot will be rated up in the Limited-time Headhunting - Command: Reconstruction between September 16, 2025, 10:00 - September 30, 2025, 03:59 (UTC-7)!"
        "Title: Mon3tr Banner"
        "Category: Banner"
        "Profile: AK"
        "Start: 1726498800"
        "End: 1727715540"
        "Image: None"
        ""
        "Tweet:"
        "Dear Doctor,"
        "Please note that we plan to perform the following server maintenance on September 16, 2025, 10:00-10:10 (UTC-7). Thank you for your understanding and support."
        "Title: Maintenance"
        "Category: Maintenance"
        "Profile: AK"
        "Start: 1726498800"
        "End: 1726499400"
        "Image: None"
        ""
        "Now extract from this tweet:"
        "{tweet_text}"
    )
    # Try to call the LLM, but handle the case where it is commented out or fails
    try:
        response = await run_llm_inference(prompt)
    except Exception:
        response = None

    # --- Robust field extraction using line-by-line parsing ---
    def extract_fields(text):
        fields = {"Title": None, "Category": None, "Profile": None, "Start": None, "End": None, "Image": None}
        if not text:
            return fields
        for line in text.splitlines():
            for key in fields:
                if line.strip().lower().startswith(f"{key.lower()}:"):
                    value = line.split(":", 1)[1].strip()
                    fields[key] = value
        return fields

    fields = extract_fields(response)

    # Fallbacks for missing or None fields
    title = fields["Title"] if fields["Title"] and fields["Title"].lower() != "none" else parse_title_ak(tweet_text)
    category = fields["Category"] if fields["Category"] and fields["Category"].lower() != "none" else parse_category_ak(tweet_text)
    start = fields["Start"] if fields["Start"] and fields["Start"].lower() != "none" else None
    end = fields["End"] if fields["End"] and fields["End"].lower() != "none" else None

    # If start or end is missing, use parse_dates_ak
    if not start or not end:
        parsed_start, parsed_end = await parse_dates_ak(None, tweet_text)
        if not start and parsed_start:
            start = parsed_start
        if not end and parsed_end:
            end = parsed_end

    # --- Image extraction ---
    image = fields["Image"] if fields["Image"] and fields["Image"].lower() != "none" else None
    # If still no image, try to extract from tweet text using twitter_handler logic
    if not image:
        import re
        images = re.findall(r'https://pbs\.twimg\.com/media/[^\s]+', tweet_text)
        if images:
            image = images[0]
        elif tweet_image:
            image = tweet_image

    return {
        "title": title,
        "category": category,
        "start": start,
        "end": end,
        "image": image
    }

# --- Add Event to Database and Schedule Notification ---

async def add_ak_event(ctx, event_data):
    """
    Adds an event to the Arknights database and schedules notifications via the central handler.
    Also schedules dashboard update tasks at event start and end.
    """
    async with aiosqlite.connect(AK_DB_PATH) as conn:
        await conn.execute(
            '''INSERT INTO events (user_id, server_id, title, start_date, end_date, image, category, profile)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                str(ctx.author.id),
                str(ctx.guild.id),
                event_data["title"],
                event_data["start"],
                event_data["end"],
                event_data["image"],
                event_data["category"],
                "AK"
            )
        )
        await conn.commit()
    # Prepare event dict for notification_handler
    event_for_notification = {
        'server_id': str(ctx.guild.id),
        'category': event_data['category'],
        'profile': "AK",
        'title': event_data['title'],
        'start_date': event_data['start'],
        'end_date': event_data['end']
    }
    # Schedule notifications using the central handler
    from notification_handler import schedule_notifications_for_event
    await schedule_notifications_for_event(event_for_notification)

    # --- Schedule dashboard updates at event start and end ---
    try:
        start_unix = int(event_data["start"])
        end_unix = int(event_data["end"])
        await schedule_update_task(ctx.guild.id, start_unix)
        await schedule_update_task(ctx.guild.id, end_unix)
    except Exception as e:
        print(f"[Arknights] Failed to schedule update tasks: {e}")

    await ctx.send(
        f"Added `{event_data['title']}` as **{event_data['category']}** for Arknights!\n"
        f"Start: <t:{event_data['start']}:F>\nEnd: <t:{event_data['end']}:F>"
    )

# --- Command to Manually Add Event from Tweet Link ---

@bot.command()
async def ak_read(ctx, link: str):
    """
    Reads an Arknights tweet, extracts event info using the LLM, and adds it to the AK database.
    """
    from twitter_handler import fetch_tweet_content, normalize_twitter_link
    link = normalize_twitter_link(link)
    tweet_text, tweet_image, username = await fetch_tweet_content(link)
    if not tweet_text:
        await ctx.send("Could not read the tweet. Please check the link or try again later.")
        return
    # Use LLM to extract event info
    event_data = await extract_ak_event_from_tweet(tweet_text, tweet_image)
    # If LLM didn't find an image, use the tweet image
    if (not event_data["image"] or event_data["image"].lower() == "none") and tweet_image:
        event_data["image"] = tweet_image
    # Validate required fields
    if not (event_data["title"] and event_data["category"] and event_data["start"] and event_data["end"]):
        await ctx.send(f"AI could not extract all required info. LLM response:\n```{event_data}```")
        return
    await add_ak_event(ctx, event_data)

async def arknights_on_message(message, force=False):
    """
    Call this from main.py's on_message to process Arknights event tweets.
    Returns True if the message was handled, False otherwise.
    If force=True, always process as an event.
    """
    from global_config import LISTENER_CHANNELS
    if message.channel.id not in LISTENER_CHANNELS.values():
        return False
    twitter_link = None
    for word in message.content.split():
        if "twitter.com" in word or "x.com" in word:
            twitter_link = word
            break
    if not twitter_link:
        return False
    from twitter_handler import fetch_tweet_content, normalize_twitter_link
    twitter_link = normalize_twitter_link(twitter_link)
    tweet_text, tweet_image, username = await fetch_tweet_content(twitter_link)
    if not tweet_text:
        return False
    # Only skip classification if not forced
    if not force and not await is_ak_event_tweet(tweet_text):
        return False
    event_data = await extract_ak_event_from_tweet(tweet_text, tweet_image)
    if (not event_data["image"] or event_data["image"].lower() == "none") and tweet_image:
        event_data["image"] = tweet_image
    if not (event_data["title"] and event_data["category"] and event_data["start"] and event_data["end"]):
        return False
    class DummyCtx:
        author = message.author
        guild = message.guild
        async def send(self, msg, **kwargs):
            await message.channel.send(msg, **kwargs)
    await add_ak_event(DummyCtx(), event_data)
    return True

# Manual Refresh command
from discord.ext import commands

@commands.has_permissions(manage_guild=True)
@bot.command(name="ak_refresh_timers")
async def ak_refresh_timers(ctx):
    """Refreshes all Arknights event dashboards (ongoing/upcoming channels)."""
    await arknights_update_timers(ctx.guild)
    await ctx.send("Arknights event dashboards have been refreshed.")

@bot.command()
async def ak_read_test(ctx, link: str):
    """
    Checks if the tweet is an Arknights event and extracts event info, but does not add it to the database.
    """
    from twitter_handler import fetch_tweet_content, normalize_twitter_link
    link = normalize_twitter_link(link)
    tweet_text, tweet_image, username = await fetch_tweet_content(link)
    if not tweet_text:
        await ctx.send("Could not read the tweet. Please check the link or try again later.")
        return
    else:
        await ctx.send(f"Found tweet, tweet text:\n```{tweet_text}```")

    # Check if it's an event tweet
    await ctx.send("Checking if the tweet is an event...")
    is_event = await is_ak_event_tweet(tweet_text)
    await ctx.send(f"Classification: {'Event' if is_event else 'Filler'}")

    if not is_event:
        await ctx.send("This tweet is not classified as an event.")
        return

    # Extract event info
    await ctx.send("This tweet is classified as an event! Extracting event info...")
    event_data = await extract_ak_event_from_tweet(tweet_text,tweet_image)
    if (not event_data["image"] or event_data["image"].lower() == "none") and tweet_image:
        event_data["image"] = tweet_image

    # Show extracted info
    await ctx.send(
        f"**Extracted Event Info:**\n"
        f"Title: {event_data['title']}\n"
        f"Category: {event_data['category']}\n"
        f"Start: {event_data['start']}\n"
        f"End: {event_data['end']}\n"
        f"Image: {event_data['image']}"
    )
    
@commands.has_permissions(manage_guild=True)
@bot.command(name="ak_remove_event")
async def ak_remove_event(ctx, *, title: str):
    """
    Removes an Arknights event by title (case-insensitive).
    """
    async with aiosqlite.connect(AK_DB_PATH) as conn:
        # Find the event
        async with conn.execute(
            "SELECT id, title, category, profile FROM events WHERE server_id=? AND LOWER(title)=?",
            (str(ctx.guild.id), title.lower())
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            await ctx.send(f"No event found with title '{title}'.")
            return
        event_id, event_title, event_category, event_profile = row

        # Delete event messages from both channels
        await delete_event_message(ctx.guild, ONGOING_EVENTS_CHANNELS["AK"], event_id)
        await delete_event_message(ctx.guild, UPCOMING_EVENTS_CHANNELS["AK"], event_id)

        # Delete from DB
        await conn.execute("DELETE FROM events WHERE id=?", (event_id,))
        await conn.commit()

    # Delete notifications for this event
    from notification_handler import delete_notifications_for_event
    await delete_notifications_for_event(
        str(ctx.guild.id), event_title, event_category, event_profile
    )

    await ctx.send(f"Deleted event '{event_title}' and its notifications.")
    
@commands.has_permissions(manage_guild=True)
@bot.command(name="ak_edit_event")
async def ak_edit_event(ctx, title: str, item: str, *, value: str):
    """
    Edits an Arknights event in the database.
    Usage: !ak_edit_event "<title>" <item> <value>
    Allowed items: start, end, category, profile, image, title
    For start/end, accepts UNIX timestamp or "YYYY-MM-DD HH:MM" (will prompt for timezone if missing).
    """
    allowed_items = ["start", "end", "category", "profile", "image", "title"]

    async with aiosqlite.connect(AK_DB_PATH) as conn:
        async with conn.execute("SELECT id, title, category, profile FROM events WHERE server_id=? AND LOWER(title)=?", (str(ctx.guild.id), title.lower())) as cursor:
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
            # Update the title in events
            await conn.execute("UPDATE events SET title=? WHERE id=?", (value, event_id))
            # Also update event_messages for consistency
            await conn.execute("UPDATE event_messages SET event_id=(SELECT id FROM events WHERE server_id=? AND title=?) WHERE server_id=? AND event_id=?", (str(ctx.guild.id), value, str(ctx.guild.id), event_id))
            await conn.commit()
            await ctx.send(f"Updated `title` for `{old_title}` to `{value}`.")
        else:
            await ctx.send(f"Cannot edit `{item}`. Only {', '.join(allowed_items)} can be edited.")
            return

    # Delete and reschedule notifications
    from notification_handler import delete_notifications_for_event, schedule_notifications_for_event
    await delete_notifications_for_event(
        str(ctx.guild.id), old_title, old_category, old_profile
    )
    # Fetch updated event info for notification rescheduling
    async with aiosqlite.connect(AK_DB_PATH) as conn:
        async with conn.execute("SELECT title, start_date, end_date, category, profile FROM events WHERE id=?", (event_id,)) as cursor:
            updated = await cursor.fetchone()
    if updated:
        new_title, new_start, new_end, new_category, new_profile = updated
        event_for_notification = {
            'server_id': str(ctx.guild.id),
            'category': new_category,
            'profile': new_profile,
            'title': new_title,
            'start_date': str(new_start),
            'end_date': str(new_end)
        }
        await schedule_notifications_for_event(event_for_notification)
        # Schedule dashboard updates at new start and end
        try:
            await schedule_update_task(ctx.guild.id, int(new_start))
            await schedule_update_task(ctx.guild.id, int(new_end))
        except Exception as e:
            print(f"[Arknights] Failed to schedule update tasks after edit: {e}")
# --- End of arknights_module.py ---