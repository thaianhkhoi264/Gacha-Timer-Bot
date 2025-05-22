from modules import *
from bot import *
from database_handler import update_timer_channel
import pytz

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

def parse_dates_ak(text):
    """
    Parses Arknights event/maintenance tweets for start and end times.
    Handles:
      - ...during May 6, 2025, 04:00 (UTC-7) - May 20, 2025, 03:59 (UTC-7)...
      - ...on May 8, 2025, 10:00-10:10 (UTC-7)...
      - ...between May 8, 2025, 10:00 - May 22, 2024, 03:59 (UTC-7)...
    Returns (start, end) as strings if found, otherwise None for missing.
    """
    # 1. Range with dash or en-dash and optional UTC
    match = re.search(
        r'(?:during|between)?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4},?\s*\d{2}:\d{2}(?:\s*\(UTC[+-]\d+\))?)\s*[-–]\s*([A-Za-z]+\s+\d{1,2},\s*\d{4},?\s*\d{2}:\d{2}(?:\s*\(UTC[+-]\d+\))?)',
        text, re.IGNORECASE)
    if match:
        start = match.group(1).strip()
        end = match.group(2).strip()
        return start, end

    # 2. Maintenance with single date and time range (e.g. May 8, 2025, 10:00-10:10 (UTC-7))
    match = re.search(
        r'on\s*([A-Za-z]+\s+\d{1,2},\s*\d{4}),?\s*(\d{2}:\d{2})\s*[-–]\s*(\d{2}:\d{2})\s*\((UTC[+-]\d+)\)',
        text, re.IGNORECASE)
    if match:
        date = match.group(1).strip()
        start_time = match.group(2).strip()
        end_time = match.group(3).strip()
        tz = match.group(4).strip()
        start = f"{date}, {start_time} ({tz})"
        end = f"{date}, {end_time} ({tz})"
        return start, end

    # 3. Fallback: single date/time with UTC
    match = re.search(
        r'([A-Za-z]+\s+\d{1,2},\s*\d{4},?\s*\d{2}:\d{2}(?:\s*\(UTC[+-]\d+\))?)',
        text, re.IGNORECASE)
    if match:
        date = match.group(1).strip()
        return date, None

    return None, None

POSTER_PROFILES = {
    "honkaistarrail": {
        "parse_dates": parse_dates_hsr
        # Add more custom settings if needed
    },
    "ArknightsEN": {
        "parse_dates": parse_dates_ak
    }
    # Add more profiles as needed
}

# Triple timezone mapping for Hoyoverse games
HYV_TIMEZONES = {
    "Asia": "Asia/Shanghai",        # UTC+8
    "America": "America/New_York",  # UTC-5 (handles DST)
    "Europe": "Europe/Berlin",      # UTC+1 (handles DST)
}

# Set of poster usernames that use triple timezone display
HYV_ACCOUNTS = {"honkaistarrail", "zzz_en"}

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
        ":red_square: Maintenance"
    )
    emojis = {"🟦": "Banner", "🟨": "Event", "🟥": "Maintenence"}
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
    Reads a tweet from a Twitter/X link, tries to parse start/end dates, and asks for missing info.
    For HYV accounts, stores all three server times in the DB and sets is_hyv=1.
    Usage: Kanami read <twitter_link>
    """
    await ctx.send("Reading tweet, please wait...")
    tweet_text, tweet_image, username = await fetch_tweet_content(link)
    if not tweet_text:
        await ctx.send("Could not read the tweet. Please check the link or try again later.")
        return

    # --- ArknightsEN special logic ---       
    if username and username.lower() == "arknightsen":
        text_lower = tweet_text.lower()
        if "operator" in text_lower or "operators" in text_lower:
            category = "Banner"
            title = await prompt_for_title(ctx, tweet_text)
            image = tweet_image
            if not title:
                await ctx.send("No title provided. Cancelling.")
                return
        elif "event" in text_lower:
            category = "Event"
            title = await prompt_for_title(ctx, tweet_text)
            if not title:
                await ctx.send("No title provided. Cancelling.")
                return
            image = await prompt_for_image(ctx, tweet_image)
        elif "maintenance" in text_lower:
            category = "Maintenence"
            from datetime import datetime
            title = f"Maintenance {datetime.now().strftime('%Y-%m-%d')}"
            image = tweet_image
        else:
            category = await prompt_for_category(ctx)
            if not category:
                await ctx.send("No category provided. Cancelling.")
                return
            title = await prompt_for_title(ctx, tweet_text)
            if not title:
                await ctx.send("No title provided. Cancelling.")
                return
            image = await prompt_for_image(ctx, tweet_image)
        event_profile = "ArknightsEN"
    else:
        # fallback for other profiles
        category = await prompt_for_category(ctx)
        title = await prompt_for_title(ctx, tweet_text)
        image = await prompt_for_image(ctx, tweet_image)
        # Try to match username to your valid_profiles mapping
        valid_profiles = {"honkaistarrail": "HSR", "zzz_en": "ZZZ", "arknightsen": "AK"}
        event_profile = username if username else "ALL"
        # Use the actual Twitter username as the profile for consistency with your config

    # Use profile-specific parsing if available
    profile_parser = POSTER_PROFILES.get(username)
    if profile_parser and "parse_dates" in profile_parser:
        start, end = profile_parser["parse_dates"](tweet_text)
    else:
        start, end = parse_dates_from_text(tweet_text)

    if not title:
        title = await prompt_for_title(ctx, tweet_text)
        if not title:
            return

    # --- Prompt for missing dates BEFORE HYV logic ---
    is_hyv = username in HYV_ACCOUNTS
    start, end = await prompt_for_missing_dates(ctx, start, end, is_hyv=is_hyv)
    if not (start and end):
        return

    if is_hyv:
        # All further handling assumes start/end are in server time!
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

        asia_start = str(start_times["Asia"][1])
        asia_end = str(end_times["Asia"][1])
        america_start = str(start_times["America"][1])
        america_end = str(end_times["America"][1])
        europe_start = str(start_times["Europe"][1])
        europe_end = str(end_times["Europe"][1])

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
                asia_start, asia_end, america_start, america_end, europe_start, europe_end, username
            )
        )
        conn.commit()
        conn.close()
        await ctx.send(
            f"Added `{new_title}` as **{category}** for all HYV server regions to the database!"
        )
        await update_timer_channel(ctx.guild, bot, profile=username)
        return

    # --- Non-HYV logic below ---
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

    if not category:
        category = await prompt_for_category(ctx)
        if not category:
            return

    if not image:
        image = await prompt_for_image(ctx, tweet_image)

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
    for profile in profiles:
        await update_timer_channel(ctx.guild, bot, profile=profile)