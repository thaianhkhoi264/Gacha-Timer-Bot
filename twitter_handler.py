from modules import *
from bot import *
from database_handler import update_timer_channel

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