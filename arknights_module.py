import os
import aiosqlite
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
        await conn.commit()

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

    # Fallback: Poly Vision Museum or other event
    museum_match = re.search(r"Poly Vision Museum", text, re.IGNORECASE)
    if museum_match:
        return "Poly Vision Museum"

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



# --- Tweet Listening and Filtering ---

async def is_ak_event_tweet(tweet_text):
    """
    Uses the LLM to classify if a tweet is an Arknights event/announcement.
    Returns True if it's an event, False otherwise.
    """
    prompt = (
        "Classify the following tweet for the game profile 'AK' (Arknights). "
        "Reply only with 'Event' if it is an in-game event, banner, maintenance, or update announcement. "
        "The tweet is only classified as an 'Event' if it has both a starting time and an ending time, regardless of timezone. "
        "The starting and ending time can be vague, such as `After maintenance` or `It will take about five hours to complete`."
        "Reply only with 'Filler' if it is a trailer, fanart, contest, winner announcement, or any non-event content.\n"
        f"Tweet:\n{tweet_text}"
    )
    response = await run_llm_inference(prompt)
    return response.strip().lower().startswith("event")

# --- Tweet Reading and Event Extraction ---

async def extract_ak_event_from_tweet(tweet_text):
    """
    Uses the LLM to extract event details from an Arknights tweet.
    Returns a dict with title, category, start, end, image (if found).
    """
    prompt = (
        "Extract the following information from this Arknights event announcement tweet. "
        "Reply in this exact format (one line per field, no extra text, no quotes):\n"
        "The Category should be one of these single words: [Banner, Event, Maintenance] (Do not use phrases.) "
        "Anything that is a Headhunting or has the word Limited Time is considered a Banner\n"
        "If the Category is Banner, the Title should include the name of the Character in the Banner\n"
        "Title: <title>\n"
        "Category: <category>\n"
        "Profile: AK\n"
        "Start: <UNIX timestamp>\n"
        "End: <UNIX timestamp>\n"
        "Image: <image url or None>\n"
        "If any field is missing, write None for that field.\n"
        "Example:\n"
        "Title: Joint Operation Headhunting\n"
        "Category: Banner\n"
        "Profile: AK\n"
        "Start: 1746330000\n"
        "End: 1747420740\n"
        "Image: https://pbs.twimg.com/media/example.jpg\n"
        f"Tweet:\n{tweet_text}"
    )
    response = await run_llm_inference(prompt)
    # Parse the response
    import re
    def extract_field(field, text):
        match = re.search(rf"{field}:\s*(.+)", text)
        return match.group(1).strip() if match else None

    title = parse_title_ak(tweet_text)
    # Fallback to the AI if the title parsing fails
    if not title or title.lower() == "none":
        title = extract_field("Title", response)

    return {
        "title": title,
        "category": extract_field("Category", response),
        "start": extract_field("Start", response),
        "end": extract_field("End", response),
        "image": extract_field("Image", response)
    }

# --- Add Event to Database and Schedule Notification ---

async def add_ak_event(ctx, event_data):
    """
    Adds an event to the Arknights database and schedules notifications via the central handler.
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
    await ctx.send(
        f"Added `{event_data['title']}` as **{event_data['category']}** for Arknights!\n"
        f"Start: <t:{event_data['start']}:F>\nEnd: <t:{event_data['end']}:F>"
    )

# --- Command to Manually Add Event from Tweet Link ---

@bot.command()
async def ak_read_llm(ctx, link: str):
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
    event_data = await extract_ak_event_from_tweet(tweet_text)
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
    event_data = await extract_ak_event_from_tweet(tweet_text)
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
async def ak_read(ctx, link: str):
    """
    Checks if the tweet is an Arknights event and extracts event info, but does not add it to the database.
    """
    from twitter_handler import fetch_tweet_content, normalize_twitter_link
    link = normalize_twitter_link(link)
    tweet_text, tweet_image, username = await fetch_tweet_content(link)
    if not tweet_text:
        await ctx.send("Could not read the tweet. Please check the link or try again later.")
        return

    # Check if it's an event tweet
    is_event = await is_ak_event_tweet(tweet_text)
    await ctx.send(f"Classification: {'Event' if is_event else 'Filler'}")

    if not is_event:
        await ctx.send("This tweet is not classified as an event.")
        return

    # Extract event info
    event_data = await extract_ak_event_from_tweet(tweet_text)
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
# --- End of arknights_module.py ---