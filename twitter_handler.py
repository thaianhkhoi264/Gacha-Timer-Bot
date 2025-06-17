from modules import *
from bot import *
from database_handler import update_timer_channel
from notification_handler import schedule_notifications_for_event
from datetime import datetime, timedelta
import asyncio
import pytz
import re

PROFILE_NORMALIZATION = {
    "arknightsen": "AK",
    "zzz_en": "ZZZ",
    "honkaistarrail": "HSR",
    "strinova_en": "STRI",
    "wuthering_waves": "WUWA",
    "ak": "AK",
    "zzz": "ZZZ",
    "hsr": "HSR",
    "stri": "STRI",
    "wuwa": "WUWA",
    "all": "ALL"
}
def normalize_profile(profile):
    if not profile:
        return "ALL"
    return PROFILE_NORMALIZATION.get(profile.lower(), profile.upper())

def parse_category_hsr(text):
    """
    Parses Honkai: Star Rail tweet text to determine the event category.
    Returns one of: "Banner", "Event", "Maintenance", or None.
    """
    text_lower = text.lower()
    if "banner" in text_lower or "warp" in text_lower:
        return "Banner"
    elif "event" in text_lower:
        return "Event"
    elif "update" in text_lower:
        return "Maintenance"
    return None

def parse_dates_hsr(text):
    """
    Custom parsing logic for Honkai: Star Rail event tweets.
    Returns (start, end) as strings if found, otherwise None for missing.
    Handles:
      - Event Period: 2025/04/30 12:00:00 - 2025/05/20 15:00:00 (server time)
      - Event Period: After the Version 3.3 update – 2025/06/11 11:59:00 (server time)
    """
    # 1. Try full range with dash or en-dash
    match = re.search(
        r'event period[:：]?\s*([0-9/\- :]+)\s*[-–]\s*([0-9/\- :]+)(?:\s*\([^)]+\))?',
        text, re.IGNORECASE)
    if match:
        start = match.group(1).strip()
        end = match.group(2).strip()
        return start, end

    # 2. Try "After the update – end" style
    match = re.search(
        r'event period[:：]?\s*after [^\n–-]+[–-]\s*([0-9/\- :]+)(?:\s*\([^)]+\))?',
        text, re.IGNORECASE)
    if match:
        end = match.group(1).strip()
        return None, end

    # 3. Try "Event Period: [date]" (single date, fallback)
    match = re.search(
        r'event period[:：]?\s*([0-9/\- :]+)(?:\s*\([^)]+\))?',
        text, re.IGNORECASE)
    if match:
        date = match.group(1).strip()
        return date, None

    return None, None

def parse_category_zzz(text):
    """
    Parses Zenless Zone Zero tweet text to determine the event category.
    Returns one of: "Banner", "Event", "Maintenance", or None.
    """
    text_lower = text.lower()
    if "channel" in text_lower or "channels" in text_lower:
        return "Banner"
    elif "event details" in text_lower:
        return "Event"
    elif "update" in text_lower or "compensation" in text_lower:
        return "Maintenance"
    return None

def parse_dates_zzz(text):
    """
    Parses ZZZ event/update tweets for start and end times.
    Handles:
      - [Event Duration] 2025/06/18 04:00 (server time) – 2025/06/23 03:59 (server time)
      - [Update Start Time] 2025/06/06 06:00 (UTC+8)
      - After the Version X.X update – 2025/06/23 03:59 (server time)
    Returns (start, end) as strings if found, otherwise None for missing.
    """
    # 1. [Event Duration] ... – ... (range)
    match = re.search(
        r'\[Event Duration\][^\d]*(\d{4}/\d{2}/\d{2} \d{2}:\d{2})[^\d–-]*[–-][^\d]*(\d{4}/\d{2}/\d{2} \d{2}:\d{2})',
        text, re.IGNORECASE)
    if match:
        start = match.group(1).strip()
        end = match.group(2).strip()
        return start, end

    # 2. [Update Start Time] ... (single date)
    match = re.search(
        r'\[Update Start Time\][^\d]*(\d{4}/\d{2}/\d{2} \d{2}:\d{2}(?:\s*\([^)]+\))?)',
        text, re.IGNORECASE)
    if match:
        start = match.group(1).strip()
        return start, None

    # 3. After the Version X.X update – ... (prompt for start, parse end)
    match = re.search(
        r'After the Version [\d\.]+ Update\s*[–-]\s*(\d{4}/\d{2}/\d{2} \d{2}:\d{2}(?:\s*\([^)]+\))?)',
        text, re.IGNORECASE)
    if match:
        end = match.group(1).strip()
        # Signal to the caller that we need to prompt for start
        return None, end

    # 4. Fallback: find any date-like substrings
    date_candidates = re.findall(
        r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}(?:\s*\([^)]+\))?)', text)
    if len(date_candidates) >= 2:
        return date_candidates[0], date_candidates[1]
    elif len(date_candidates) == 1:
        return date_candidates[0], None
    else:
        return None, None

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

# def parse_category_stri(text):

# def parse_dates_stri(text):

# def parse_category_wuwa(text):

# def parse_dates_wuwa(text):

POSTER_PROFILES = {
    "honkaistarrail": {
        "parse_dates": parse_dates_hsr,
        "parse_category": parse_category_hsr
    },
    "zzz_en": {
        "parse_dates": parse_dates_zzz,
        "parse_category": parse_category_zzz
    },
    "arknightsen": {
        "parse_dates": parse_dates_ak,
        "parse_category": parse_category_ak
    },
    "strinova_en": {
        # "parse_dates": parse_dates_stri  # Add if you have a custom parser
    },
    "wuthering_waves": {
        # "parse_dates": parse_dates_wuwa  # Add if you have a custom parser
    }
}

# Triple timezone mapping for Hoyoverse games
HYV_TIMEZONES = {
    "Asia": "Asia/Shanghai",        # UTC+8
    "America": "America/New_York",  # UTC-5 (handles DST)
    "Europe": "Europe/Berlin",      # UTC+1 (handles DST)
}

# Set of poster usernames that use triple timezone display
HYV_ACCOUNTS = {"honkaistarrail", "zzz_en"}

def prepare_hyv_event_entries(ctx, base_event, start_times, end_times, image, category, event_profile, title):
    """
    Returns a list of event dicts, one for each HYV region, ready for notification scheduling.
    Also inserts the event into the database with all regional times.
    """
    region_keys = [("NA", "America"), ("EU", "Europe"), ("ASIA", "Asia")]
    region_fields = {
        "NA": ("america_start", "america_end"),
        "EU": ("europe_start", "europe_end"),
        "ASIA": ("asia_start", "asia_end")
    }
    # Prepare DB fields
    asia_start = str(start_times["Asia"][1])
    asia_end = str(end_times["Asia"][1])
    america_start = str(start_times["America"][1])
    america_end = str(end_times["America"][1])
    europe_start = str(start_times["Europe"][1])
    europe_end = str(end_times["Europe"][1])

    # Insert into DB (single row with all regional times)
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
         (
             str(ctx.author.id), str(ctx.guild.id), new_title, "", "", image, category, 1,
              asia_start, asia_end, america_start, america_end, europe_start, europe_end, event_profile
          )
    )
    conn.commit()
    conn.close()

    # Prepare event dicts for notification scheduling (one per region)
    event_entries = []
    for region, tz_key in region_keys:
        event = {
            'server_id': str(ctx.guild.id),
            'category': category,
            'profile': event_profile,
            'title': new_title,
            'start_date': str(start_times[tz_key][1]),
            'end_date': str(end_times[tz_key][1]),
            'region': region  # Add region for notification logic
        }
        event_entries.append(event)
    return event_entries, new_title

# Read command helper functions
async def prompt_for_title(ctx, tweet_text):
    await ctx.send(f"Tweet content:\n```{tweet_text[:1800]}```")
    await ctx.send("What is the title for this event?")
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        msg = await bot.wait_for("message", timeout=60.0, check=check)
        return msg.content
    except asyncio.TimeoutError:
        await ctx.send("No title provided. Cancelling.")
        return None

async def prompt_for_category(ctx):
    msg = await ctx.send(
        "What category should this event be?\n"
        ":blue_square: Banner\n"
        ":yellow_square: Event\n"
        ":green_square: Maintenance"
    )
    emojis = {"🟦": "Banner", "🟨": "Event", "🟩": "Maintenance"}
    for emoji in emojis: await msg.add_reaction(emoji)
    def check(reaction, user): return user == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in emojis
    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        return emojis[str(reaction.emoji)]
    except Exception:
        await ctx.send("No category selected. Event not added.")
        return None

async def prompt_for_image(ctx, tweet_image):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    image = tweet_image
    if image:
        await ctx.send(f"Found an image in the tweet. Use this image? (yes/no)\n{image}")
        try:
            img_reply = await bot.wait_for("message", timeout=60.0, check=check)
            if img_reply.content.strip().lower() not in ["yes", "y"]:
                await ctx.send("If you want to add an image URL, reply with it now or type `skip`.")
                try:
                    img_msg = await bot.wait_for("message", timeout=60.0, check=check)
                    image = img_msg.content if img_msg.content.lower() != "skip" else None
                except asyncio.TimeoutError:
                    image = None
        except asyncio.TimeoutError:
            pass
    else:
        await ctx.send("If you want to add an image URL, reply with it now or type `skip`.")
        try:
            img_msg = await bot.wait_for("message", timeout=60.0, check=check)
            image = img_msg.content if img_msg.content.lower() != "skip" else None
        except asyncio.TimeoutError:
            image = None
    return image

async def prompt_for_timezone(ctx):
    await ctx.send(
        "No timezone detected in the tweet. Please enter the timezone for this event (e.g. `UTC`, `UTC+9`, `Asia/Tokyo`, `GMT-7`, etc.):"
    )
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        tz_msg = await bot.wait_for("message", timeout=60.0, check=check)
        return tz_msg.content.strip()
    except asyncio.TimeoutError:
        await ctx.send("No timezone provided. Cancelling.")
        return None

async def prompt_for_missing_dates(ctx, start, end, is_hyv=False):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    time_hint = " in server time (e.g. `2025-06-01 15:00`)" if is_hyv else " (e.g. `2025-06-01 15:00`)"
    if not start and not end:
        await ctx.send(f"Could not find any dates. Please enter the **start** date/time{time_hint}:")
        try:
            start_msg = await bot.wait_for("message", timeout=60.0, check=check)
            start = start_msg.content
        except asyncio.TimeoutError:
            await ctx.send("No start date provided. Cancelling.")
            return None, None
        await ctx.send(f"Please enter the **end** date/time{time_hint}:")
        try:
            end_msg = await bot.wait_for("message", timeout=60.0, check=check)
            end = end_msg.content
        except asyncio.TimeoutError:
            await ctx.send("No end date provided. Cancelling.")
            return None, None
    elif (start and not end) or (end and not start):
        found_date = start if start else end
        # Try to extract timezone from found_date
        tz_match = re.search(r'(UTC[+-]\d+|GMT[+-]\d+|[A-Za-z]+/[A-Za-z_]+)', found_date)
        tz_hint = ""
        tz_str = None
        if tz_match:
            tz_str = tz_match.group(1)
            tz_hint = f" Please use the same timezone as `{tz_str}`."
        await ctx.send(
            f"Found date: `{found_date}`\n"
            f"Discord format: <t:{to_unix_timestamp(found_date)}:F> / <t:{to_unix_timestamp(found_date)}:R>\n"
            f"Is this the **start** or **end** date? (Please answer in server time as listed in the tweet.)"
        )
        try:
            type_msg = await bot.wait_for("message", timeout=60.0, check=check)
            found_type = type_msg.content.strip().lower()
        except asyncio.TimeoutError:
            await ctx.send("No response. Cancelling.")
            return None, None

        def ensure_timezone(user_input, tz_str):
            # If user_input already contains a timezone, return as is
            if not tz_str:
                return user_input
            if re.search(r'(UTC[+-]\d+|GMT[+-]\d+|[A-Za-z]+/[A-Za-z_]+)', user_input):
                return user_input
            return f"{user_input} {tz_str}"

        if found_type == "start":
            start = found_date
            await ctx.send(f"Please enter the **end** date/time{time_hint}.{tz_hint}")
            try:
                end_msg = await bot.wait_for("message", timeout=60.0, check=check)
                end = ensure_timezone(end_msg.content, tz_str)
            except asyncio.TimeoutError:
                await ctx.send("No end date provided. Cancelling.")
                return None, None
        elif found_type == "end":
            end = found_date
            await ctx.send(f"Please enter the **start** date/time{time_hint}.{tz_hint}")
            try:
                start_msg = await bot.wait_for("message", timeout=60.0, check=check)
                start = ensure_timezone(start_msg.content, tz_str)
            except asyncio.TimeoutError:
                await ctx.send("No start date provided. Cancelling.")
                return None, None
        else:
            await ctx.send("Invalid response. Cancelling.")
            return None, None
    return start, end

# Function to convert a date string to all three Hoyoverse timezones
def convert_to_all_timezones(dt_str):
    # Try to parse as naive datetime (no timezone info)
    dt = dateparser.parse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': False})
    if not dt:
        return None
    results = {}
    for region, tz_name in HYV_TIMEZONES.items():
        tz = pytz.timezone(tz_name)
        # Localize the naive datetime to the region's timezone
        dt_tz = tz.localize(dt)
        unix = int(dt_tz.timestamp())
        results[region] = (dt_tz, unix)
    return results

# Function to fetch the visible text content of a tweet using Playwright
async def fetch_tweet_content(url: str):
    """Fetch tweet text, first image, and poster username."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        tweet_text = ""
        image_url = None
        username = None
        try:
            await page.goto(url, timeout=20000)
            await page.wait_for_selector("article", timeout=10000)
            tweet_text = await page.locator("article").inner_text()
            # Get the first image
            images = await page.locator("article img").all()
            for img in images:
                src = await img.get_attribute("src")
                if src and "profile_images" not in src and "emoji" not in src:
                    image_url = src
                    break
            # Get the poster's username (usually in the first <a> with href="/username")
            user_link = await page.locator("article a[href^='/']").first.get_attribute("href")
            if user_link:
                username = user_link.strip("/").lower()
        except Exception:
            pass
        await browser.close()
    return tweet_text, image_url, username

# Function to extract dates from the tweet text
def parse_dates_from_text(text: str):
    """
    Tries to find start and end date/time in the tweet text using dateparser.
    Returns (start, end) as strings if found, otherwise None for missing.
    Ignores Twitter upload timestamps like '1:00 PM · May 19, 2025'.
    """
    # Remove all occurrences of Twitter upload timestamp lines from text
    # Pattern: time (AM/PM) · Month Day, Year
    cleaned_text = re.sub(
        r'\d{1,2}:\d{2}\s*[AP]M\s*·\s*[A-Za-z]+\s+\d{1,2},\s*\d{4}', '', text)

    # Try to find a date range like "... between May 9, 2025, 04:00 - May 23, 2025, 03:59 (UTC-7)"
    range_match = re.search(
        r'between\s+(.+?)\s*[-–]\s*(.+?)(?:[\.\)]|$)', cleaned_text, re.IGNORECASE)
    if range_match:
        start_str = range_match.group(1).strip()
        end_str = range_match.group(2).strip()
        # Try to append timezone if present at the end
        tz_match = re.search(r'\((UTC[+-]\d+)\)', cleaned_text)
        if tz_match:
            tz = tz_match.group(1)
            if tz not in start_str:
                start_str += f' {tz}'
            if tz not in end_str:
                end_str += f' {tz}'
        return start_str, end_str

    # Fallback: find all date-like substrings (strictly from tweet text)
    date_candidates = re.findall(
        r'(\w{3,9}\s+\d{1,2},\s*\d{4}(?:,?\s*\d{2}:\d{2})?(?:\s*\(UTC[+-]\d+\))?)', cleaned_text)
    parsed_dates = []
    for candidate in date_candidates:
        dt = dateparser.parse(candidate, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        if dt and candidate in cleaned_text:
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

@bot.command()
async def read(ctx, link: str):
    """
    Reads a tweet from a Twitter/X link, parses category and dates using POSTER_PROFILES,
    prompts for missing info, and stores the event in the database.
    """
    await ctx.send("Reading tweet, please wait...")
    tweet_text, tweet_image, username = await fetch_tweet_content(link)
    if not tweet_text:
        await ctx.send("Could not read the tweet. Please check the link or try again later.")
        return

    # Normalize profile and get poster logic
    event_profile = normalize_profile(username) if username else "ALL"
    profile_parser = POSTER_PROFILES.get(username.lower() if username else "")

    # --- Parse category and dates using poster profile logic ---
    category = None
    start = None
    end = None

    if profile_parser:
        if "parse_category" in profile_parser:
            category = await profile_parser["parse_category"](tweet_text)
        if "parse_dates" in profile_parser:
            start, end = profile_parser["parse_dates"](tweet_text)
        # If you add more special logic, check and use it here
        # e.g. if "parse_special" in profile_parser: ...
    else:
        # Fallback: prompt for category and use generic date parser
        pass

    # --- Prompt for missing info ---
    if not category:
        category = await prompt_for_category(ctx)
        if not category:
            return

    title = await prompt_for_title(ctx, tweet_text)
    if not title:
        return

    image = await prompt_for_image(ctx, tweet_image)

    # --- Parse dates if not already parsed ---
    if not (start and end):
        start, end = parse_dates_from_text(tweet_text)

    # --- Prompt for missing dates ---
    is_hyv = username in HYV_ACCOUNTS
    start, end = await prompt_for_missing_dates(ctx, start, end, is_hyv=is_hyv)
    if not (start and end):
        return

    # --- Hoyoverse logic below ---
    if is_hyv:
        start_times = convert_to_all_timezones(start)
        end_times = convert_to_all_timezones(end)
        if not (start_times and end_times):
            await ctx.send("Could not parse start or end time for all regions. Cancelling.")
            return

        # Optionally prompt for category/image if not set
        if not category:
            category = await prompt_for_category(ctx)
            if not category:
                return
        if not image:
            image = await prompt_for_image(ctx, tweet_image)

        # Use the new function to insert and prepare notification events
        event_entries, new_title = prepare_hyv_event_entries(
            ctx, {}, start_times, end_times, image, category, event_profile, title
        )

        await ctx.send(
            f"Added `{new_title}` as **{category}** for all HYV server regions to the database!"
        )
        await update_timer_channel(ctx.guild, bot, profile=event_profile)
        # Update all timer channels for all profiles in this server (HYV logic)
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        c.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),))
        profiles = [row[0] for row in c.fetchall()]
        conn.close()
        for profile in profiles:
            await update_timer_channel(ctx.guild, bot, profile=profile)

        # --- Schedule notifications for each region ---
        for event in event_entries:
            asyncio.create_task(schedule_notifications_for_event(event))
        return

    # --- Non-HYV logic: store as usual ---
    # Timezone detection
    timezone_regex = r"(UTC[+-]\d+|GMT[+-]\d+|[+-]\d{2}:?\d{2}|[A-Z]{2,5})"
    tz_in_start = bool(start and re.search(timezone_regex, start))
    tz_in_end = bool(end and re.search(timezone_regex, end))
    timezone_str = None

    if not (tz_in_start or tz_in_end):
        timezone_str = await prompt_for_timezone(ctx)
        if not timezone_str:
            return

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

    # Ensure unique title
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
        "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category, profile) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(ctx.author.id), str(ctx.guild.id), new_title, str(start_unix), str(end_unix), image, category, event_profile)
    )
    conn.commit()
    conn.close()

    await ctx.send(
        f"Added `{new_title}` as **{category}** with start `<t:{start_unix}:F>` and end `<t:{end_unix}:F>` to the database!"
    )
    await update_timer_channel(ctx.guild, bot, profile=event_profile)

    # After adding the event, update all timer channels for all profiles in this server
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),))
    profiles = [row[0] for row in c.fetchall()]
    conn.close()
    unique_profiles = set(profiles)
    unique_profiles.add("ALL")
    for profile in unique_profiles:
        await update_timer_channel(ctx.guild, bot, profile=profile)

    # SCHEDULE NOTIFICATION HERE
    event = {
        'server_id': str(ctx.guild.id),
        'category': category,
        'profile': event_profile,
        'title': new_title,
        'start_date': str(start_unix),
        'end_date': str(end_unix)
    }
    asyncio.create_task(schedule_notifications_for_event(event))

