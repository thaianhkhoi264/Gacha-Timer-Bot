from modules import *
from bot import bot
from datetime import datetime, timedelta, timezone
import dateparser.search

import asyncio
import inspect
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


def normalize_twitter_link(link: str) -> str:
    """
    Converts embed/third-party Twitter links (fixupx, fxtwitter, vxtwitter, etc.)
    to a standard https://twitter.com/ or https://x.com/ link.
    """
    # Match URLs like https://fxtwitter.com/username/status/123456789
    match = re.match(r"https?://(?:fx|vx|fixupx|twitfix|tweet|pbs|pt|xtwitter)\.twitter\.com/([^/]+)/status/(\d+)", link)
    if match:
        username, status_id = match.groups()
        return f"https://twitter.com/{username}/status/{status_id}"
    # Generic: replace known domains with twitter.com or x.com
    link = re.sub(r"https?://(fx|vx|fixupx|fxtwitter|vxtwitter|twitfix|tweet|pbs|pt|xtwitter)\.com", "https://twitter.com", link)
    link = re.sub(r"https?://(fx|vx|fixupx|fxtwitter|vxtwitter|twitfix|tweet|pbs|pt|xtwitter)\.net", "https://twitter.com", link)
    link = re.sub(r"https?://x\.com", "https://twitter.com", link)
    return link

def normalize_profile(profile):
    if not profile:
        return "ALL"
    return PROFILE_NORMALIZATION.get(profile.lower(), profile.upper())

async def get_version_start_dynamic(profile, version_str, default_base_version, default_base_date):
    """
    Looks up the latest known version and start date for the profile.
    If the requested version is newer, calculates its start date as 6 weeks after the last known.
    If not found, uses the default base.
    """
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT version, start_date FROM version_tracker WHERE profile=?", (profile,)) as cursor:
            row = await cursor.fetchone()

    # Parse version numbers
    def parse_version(v):
        major, minor = map(int, v.split('.'))
        return major, minor

    req_major, req_minor = parse_version(version_str)

    if row:
        base_version, base_date_str = row
        base_major, base_minor = parse_version(base_version)
        base_date = datetime.fromisoformat(base_date_str)
    else:
        base_major, base_minor = parse_version(default_base_version)
        base_date = default_base_date

    # If requested version is before base, just return base
    if (req_major, req_minor) <= (base_major, base_minor):
        return base_date

    # Calculate weeks difference
    delta_versions = (req_major - base_major) * 10 + (req_minor - base_minor)
    start_date = base_date + timedelta(weeks=6 * delta_versions)
    return start_date

async def update_version_tracker(profile, version_str, start_date):
    """
    Updates the version tracker table with the given profile, version, and start date.
    """
    async with aiosqlite.connect('kanami_data.db') as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO version_tracker (profile, version, start_date) VALUES (?, ?, ?)",
            (profile, version_str, start_date.isoformat())
        )
        await conn.commit()

# General date parsing function
async def parse_dates(text):
    # Find all date-like substrings (very broad)
    date_patterns = [
        r'\d{4}/\d{2}/\d{2} \d{2}:\d{2}(?:\s*\([^)]+\))?',  # 2025/06/18 04:00 (UTC+8)
        r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?:\s*\([^)]+\))?',  # 2025-06-18 04:00 (UTC+8)
        r'[A-Za-z]+\s+\d{1,2},?\s*\d{4},?\s*\d{1,2}:\d{2}(?:\s*[APMapm\.]*)?(?:\s*\([^)]+\))?',  # June 18, 2025, 04:00 AM (UTC+8)
        r'[A-Za-z]+\s+\d{1,2},?\s*\d{1,2}:\d{2}(?:\s*[APMapm\.]*)?(?:\s*\([^)]+\))?',  # June 18, 04:00 AM (UTC+8)
        r'\d{1,2}/\d{1,2}/\d{4} \d{2}:\d{2}(?:\s*\([^)]+\))?',  # 06/18/2025 04:00
        r'\d{1,2}-\d{1,2}-\d{4} \d{2}:\d{2}(?:\s*\([^)]+\))?',  # 06-18-2025 04:00
    ]
    matches = []
    for pat in date_patterns:
        matches += re.findall(pat, text)
    # Remove duplicates, preserve order
    seen = set()
    dates = []
    for d in matches:
        if d not in seen:
            seen.add(d)
            dates.append(d)
    # Try to parse and keep timezone info
    parsed = []
    for d in dates:
        dt = dateparser.parse(d, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        if dt:
            parsed.append((d, dt))
    # If less than 2, try to find more with dateparser search (with timeout)
    if len(parsed) < 2:
        async def search_dates_thread():
            return dateparser.search.search_dates(text, settings={'RETURN_AS_TIMEZONE_AWARE': True}) or []
        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(dateparser.search.search_dates, text, settings={'RETURN_AS_TIMEZONE_AWARE': True}),
                timeout=5
            )
            for result in results:
                d, dt = result
                if dt and (d, dt) not in parsed:
                    parsed.append((d, dt))
        except asyncio.TimeoutError:
            print("[DEBUG] parse_dates: dateparser.search.search_dates timed out!")
    # Missing Year
    if len(parsed) >= 2:
        dt1, dt2 = parsed[0][1], parsed[1][1]
        # If either date is missing a year, assume current year
        now = datetime.now(dt1.tzinfo)
        if dt1.year == 1900:
            dt1 = dt1.replace(year=now.year)
        if dt2.year == 1900:
            dt2 = dt2.replace(year=now.year)
        # If start is December and end is January, increment end year
        if dt1.month == 12 and dt2.month == 1 and dt2.year == dt1.year:
            dt2 = dt2.replace(year=dt1.year + 1)
        return int(dt1.timestamp()), int(dt2.timestamp())
    elif len(parsed) == 1:
        dt1 = parsed[0][1]
        now = datetime.now(dt1.tzinfo)
        if dt1.year == 1900:
            dt1 = dt1.replace(year=now.year)
        return int(dt1.timestamp()), None
    else:
        return None, None

# Strip server time from date strings
def strip_server_time(dt_str):
    return re.sub(r"\s*\(server time\)", "", dt_str, flags=re.IGNORECASE).strip()
# Honkai: Star Rail specific parsing functions
def get_version_start_hsr(version_str):
    # Default base: 3.3, 2025/05/21 11:00 (UTC+8)
    default_base_version = "3.3"
    default_base_date = datetime(2025, 5, 21, 11, 0, tzinfo=timezone(timedelta(hours=8)))
    return get_version_start_dynamic("HSR", version_str, default_base_version, default_base_date)

def parse_title_hsr(text):
    """
    Attempts to extract the event title from a Honkai: Star Rail tweet.
    Skips lines that are just the game name or @username.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    # Skip lines that are just the game name or @username
    skip_patterns = [
        r"^Honkai: Star Rail$",
        r"^@honkaistarrail$",
        r"^#HonkaiStarRail$"
    ]
    event_lines = []
    for line in lines:
        if any(re.match(pat, line, re.IGNORECASE) for pat in skip_patterns):
            continue
        event_lines.append(line)
    if not event_lines:
        return lines[0]  # fallback

    first_line = event_lines[0]

    # If the first line contains "Event Warp", "Event", or "Version", keep the whole line
    if any(kw in first_line for kw in ["Event Warp", "Event", "Version"]):
        return first_line

    # If the first line contains a colon, take the part before the colon
    if ":" in first_line:
        before_colon = first_line.split(":", 1)[0].strip()
        # Avoid picking up "Event Period" or similar
        if not re.search(r"(period|details|duration|time|start|end)", before_colon, re.IGNORECASE):
            return before_colon

    # If the first line contains a dash, take the part before the dash (if not a date)
    if "-" in first_line and not re.search(r"\d{4}/\d{2}/\d{2}", first_line):
        before_dash = first_line.split("-", 1)[0].strip()
        return before_dash

    # Fallback: look for a line before "Event Period"
    for line in event_lines:
        if "Event Period" in line or "▌Event Period" in line:
            idx = event_lines.index(line)
            if idx > 0:
                return event_lines[idx - 1]

    # Fallback: first hashtag
    for line in event_lines:
        if line.startswith("#"):
            return line

    # Fallback: first event line
    return first_line

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
    # Edge case: "After the Version X.X update – <end time>"
    match = re.search(
        r"After the Version (\d+\.\d+) update\s*[–-]\s*([\d/\- :]+(?:\([^)]+\))?)",
        text, re.IGNORECASE)
    if match:
        version = match.group(1)
        end_str = match.group(2).strip()
        start_dt = get_version_start_hsr(version)
        if start_dt:
            update_version_tracker("HSR", version, start_dt)
            start_str = start_dt.strftime("%Y/%m/%d %H:%M (UTC+8)")
        else:
            start_str = None
        return start_str, end_str
    
    # Maintenance case: "maintenance on <datetime> (timezone)"
    match = re.search(
        r'maintenance on ([0-9/\- :]+)\s*\((UTC[+-]\d+)\)', text, re.IGNORECASE)
    if match:
        start_str = f"{match.group(1).strip()} {match.group(2).strip()}"
        import dateparser
        dt = dateparser.parse(start_str)
        if dt:
            end_dt = dt + timedelta(hours=5)
            # Format end time in the same style as start
            end_str = end_dt.strftime("%Y/%m/%d %H:%M:%S") + f" ({match.group(2).strip()})"
            return start_str, end_str
        else:
            return start_str, None
        
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

# Zenless Zone Zero specific parsing functions
def get_version_start_zzz(version_str):
    # Default base: 2.0, 2025/06/06 11:00 (UTC+8)
    default_base_version = "2.0"
    default_base_date = datetime(2025, 6, 6, 11, 0, tzinfo=timezone(timedelta(hours=8)))
    return get_version_start_dynamic("ZZZ", version_str, default_base_version, default_base_date)

def parse_title_zzz(text):
    """
    Extracts the event title from a Zenless Zone Zero tweet.
    Skips the first 2 non-empty lines (account name and version header),
    then applies the original fallback/title logic.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # Skip the first 2 non-empty lines
    event_lines = lines[2:] if len(lines) > 2 else lines

    if not event_lines:
        return lines[0] if lines else None

    first_line = event_lines[0]

    # Remove trailing "Event Details" or similar
    import re
    first_line = re.sub(r'\s*(Event Details|Signal Search Details)$', '', first_line, flags=re.IGNORECASE)
    return first_line.strip()

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
    import dateparser
    import re

    # Maintenance case: [Update Start Time] <datetime> (timezone), "It will take about five hours to complete."
    match = re.search(
        r'\[Update Start Time\][^\d]*(\d{4}/\d{2}/\d{2} \d{2}:\d{2})\s*\((UTC[+-]\d+)\)[^\n]*\n.*five hours',
        text, re.IGNORECASE)
    if match:
        start_str = f"{match.group(1).strip()} {match.group(2).strip()}"
        dt = dateparser.parse(start_str)
        if dt:
            end_dt = dt + timedelta(hours=5)
            end_str = end_dt.strftime("%Y/%m/%d %H:%M") + f" ({match.group(2).strip()})"
            return start_str, end_str
        else:
            return start_str, None
        
    # Edge case: "After the Version X.X update – <end time>"
    match = re.search(
        r"After the Version (\d+\.\d+) update\s*[-–—~]\s*([\d/ :]+(?:\([^)]+\))?)",
        text, re.IGNORECASE)
    if match:
        version = match.group(1)
        end_str = match.group(2).strip()
        start_dt = get_version_start_zzz(version)
        if start_dt:
            update_version_tracker("ZZZ", version, start_dt)
            start_str = start_dt.strftime("%Y/%m/%d %H:%M (UTC+8)")
        else:
            start_str = None
        if end_str:
            end_str = strip_server_time(end_str)
        return start_str, end_str
    
    # 0. Look for a date range anywhere in the text (YYYY/MM/DD HH:MM – YYYY/MM/DD HH:MM)
    match = re.search(
        r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2})(?:\s*\([^)]+\))?\s*[–-]\s*(\d{4}/\d{2}/\d{2} \d{2}:\d{2})(?:\s*\([^)]+\))?',
        text
    )
    if match:
        start = match.group(1).strip()
        end = match.group(2).strip()
        return start, end

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
        r'After the Version [\d\.]+ Update\s*[-–—~]\s*(\d{4}/\d{2}/\d{2} \d{2}:\d{2}(?:\s*\([^)]+\))?)',
        text, re.IGNORECASE)
    if match:
        end = match.group(1).strip()
        return None, end

    # 3.5. In case there isn't the [Event Duration] or [Update Start Time] text
    match = re.search(
        r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2})\s*[–-]\s*(\d{4}/\d{2}/\d{2} \d{2}:\d{2})',
        text
    )
    if match:
        start = match.group(1).strip()
        end = match.group(2).strip()
        return start, end

    # 4. Fallback: find any date-like substrings
    date_candidates = re.findall(
        r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}(?:\s*\([^)]+\))?)', text)
    if len(date_candidates) >= 2:
        return date_candidates[0], date_candidates[1]
    elif len(date_candidates) == 1:
        return date_candidates[0], None
    else:
        return None, None

# Arknights specific parsing functions
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

# Strinova specific parsing functions
def parse_title_stri(text):
    import re

    # Skip lines that are just the game name or @username
    skip_patterns = [
        r"^Strinova$",
        r"^@Strinova_EN$",
        r"^Strinova \(@Strinova_EN\)$"
    ]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    event_lines = []
    for line in lines:
        if any(re.match(pat, line, re.IGNORECASE) for pat in skip_patterns):
            continue
        event_lines.append(line)
    if not event_lines:
        return lines[0] if lines else "Unknown Title"

    # 1. Maintenance
    maint_match = re.search(r"maintenance (?:is scheduled )?for ([A-Za-z]+\s*\d{1,2})", text, re.IGNORECASE)
    if maint_match:
        return f"Maintenance on {maint_match.group(1)}"

    # 2. Try to find "Get ready for ... - Title!" or "<Title> is coming soon!"
    ready_match = re.search(r"Get ready for [^\n-]+-\s*([^\n!]+)", text, re.IGNORECASE)
    if ready_match:
        return ready_match.group(1).strip("! ").title()
    coming_match = re.search(r"([A-Za-z0-9\s\-]+)\s+is coming soon!", text, re.IGNORECASE)
    if coming_match:
        return coming_match.group(1).strip("! ").title()

    # 3. Event Previews and Offers
    if event_lines:
        first_line = event_lines[0]
        first_line = re.sub(
            r"^(Event Preview\s*\|\s*|Limited Time Offer Preview\s*\|\s*|Availability:|[✨]*[A-Za-z]+ Legendary Outfit and Weapon Skin \| Preview[✨🔥]*|Event Preview\s*\|)",
            "", first_line, flags=re.IGNORECASE
        ).strip(" |")
        if first_line:
            return first_line

    # 4. Legendary Outfit/Weapon Skin Previews (longest non-generic hashtag)
    hashtags = re.findall(r"#([A-Za-z0-9]+)", text)
    generic_tags = {"strinova", "strinovaconquest", "boomfest"}
    non_generic_hashtags = [tag for tag in hashtags if tag.lower() not in generic_tags and not tag.lower().startswith("strinova")]
    if non_generic_hashtags:
        legend_tag = max(non_generic_hashtags, key=len)
        # Robustly split and capitalize
        title = legend_tag.replace("_", " ")
        if title.islower() or title.isupper():
            title = title.title()
        else:
            title = re.sub(r'([A-Z])', r' \1', title).strip()
            title = " ".join(word.capitalize() for word in title.split())
        return title

    # 5. Fallback: Use first non-empty event line
    for line in event_lines:
        if line:
            return line

    return "Unknown Title"

def parse_category_stri(text):
    """
    Parses Strinova tweet text to determine the event category.
    Returns one of: "Banner", "Event", "Maintenance", "Offer" or None.
    """
    text_lower = text.lower()
    if "banner" in text_lower or "legendary" in text_lower:
        return "Banner"
    elif "event preview" in text_lower:
        return "Event"
    elif "maintenance" in text_lower:
        return "Maintenance"
    elif "offer" in text_lower:
        return "Offer"
    return None

def parse_dates_stri(text):
    """
    Parses Strinova tweet text for start and end dates/times.
    - Assumes current year if missing.
    - If end < start, advances end year by 1.
    - Handles "after the update" and "offer" logic as described.
    Returns (start, end) as strings or None if not found.
    """
    import re
    from datetime import datetime, timedelta

    def clean_date(s):
        # Remove ordinal suffixes (st, nd, rd, th)
        return re.sub(r'(\d{1,2})(st|nd|rd|th)', r'\1', s, flags=re.IGNORECASE)

    def parse_date(date_str, default_time=None, default_year=None):
        # Try to parse with dateparser, fallback to adding year if missing
        import dateparser
        date_str = clean_date(date_str)
        settings = {'PREFER_DAY_OF_MONTH': 'first', 'PREFER_DATES_FROM': 'current_period', 'RETURN_AS_TIMEZONE_AWARE': False}
        dt = dateparser.parse(date_str, settings=settings)
        if not dt and default_year:
            # Try adding the year
            date_str_with_year = f"{date_str} {default_year}"
            dt = dateparser.parse(date_str_with_year, settings=settings)
        if dt and default_time:
            # If time is missing, set default time
            if dt.hour == 0 and dt.minute == 0 and ':' not in date_str:
                dt = dt.replace(hour=default_time.hour, minute=default_time.minute)
        return dt

    now = datetime.now()
    current_year = now.year

    # Offer logic
    is_offer = "offer" in text.lower()

    # Patterns to match date ranges
    patterns = [
        # e.g. "June 26, after the update - August 5, 6:59 AM (UTC+0)"
        r'([A-Za-z]+\s*\d{1,2}(?:,)?(?:\s*\d{4})?)\s*(?:,?\s*after the update)?\s*[-–to]+\s*([A-Za-z]+\s*\d{1,2}(?:,)?(?:\s*\d{4})?(?:,\s*\d{2}:\d{2}(?:\s*[APMapm\.]*)?)?)',
        # e.g. "May 22nd, after the update - June 19th, 06:59 AM (UTC+0)"
        r'([A-Za-z]+\s*\d{1,2}(?:,)?(?:\s*\d{4})?),?\s*after the update\s*[-–to]+\s*([A-Za-z]+\s*\d{1,2}(?:,)?(?:\s*\d{4})?(?:,\s*\d{2}:\d{2}(?:\s*[APMapm\.]*)?)?)',
        # e.g. "05/22 after the update - 06/19 12:59 AM (UTC+0)"
        r'(\d{1,2}[/-]\d{1,2})(?:,)?\s*after the update\s*[-–to]+\s*(\d{1,2}[/-]\d{1,2}(?:\s*\d{2}:\d{2}(?:\s*[APMapm\.]*)?)?)',
        # e.g. "April 29, 07:00 - May 27, 06:59 AM (UTC+0)"
        r'([A-Za-z]+\s*\d{1,2}(?:,)?(?:\s*\d{4})?,?\s*\d{2}:\d{2}(?:\s*[APMapm\.]*)?)\s*[-–to]+\s*([A-Za-z]+\s*\d{1,2}(?:,)?(?:\s*\d{4})?,?\s*\d{2}:\d{2}(?:\s*[APMapm\.]*)?)',
        # e.g. "May 15, 1:00 a.m. to June 12, 12:59 a.m. (UTC+0)"
        r'([A-Za-z]+\s*\d{1,2}(?:,)?(?:\s*\d{4})?,?\s*\d{1,2}:\d{2}\s*[APMapm\.]*)\s*(?:-|to|–)\s*([A-Za-z]+\s*\d{1,2}(?:,)?(?:\s*\d{4})?,?\s*\d{1,2}:\d{2}\s*[APMapm\.]*)',
        # e.g. "05/22 after the update - 06/19 12:59 AM (UTC+0)"
        r'(\d{1,2}[/-]\d{1,2})\s*after the update\s*[-–to]+\s*(\d{1,2}[/-]\d{1,2}(?:\s*\d{2}:\d{2}(?:\s*[APMapm\.]*)?)?)',
        # e.g. "June 19 - July 17 (UTC+0)"
        r'([A-Za-z]+\s*\d{1,2})\s*[-–to]+\s*([A-Za-z]+\s*\d{1,2})',
        # e.g. "05/22 - 06/19 (UTC+0)"
        r'(\d{1,2}[/-]\d{1,2})\s*[-–to]+\s*(\d{1,2}[/-]\d{1,2})',
    ]

    # Find timezone
    tz_match = re.search(r'\(UTC[+-]?\d+\)', text)
    tz_str = tz_match.group(0) if tz_match else "(UTC+0)"

    # Try all patterns
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            start_raw, end_raw = match.group(1), match.group(2)
            start_raw = clean_date(start_raw)
            end_raw = clean_date(end_raw)

            # Handle "after the update"
            if "after the update" in text.lower() and not is_offer:
                # Start time is 4:00 AM
                start_time = "04:00"
            elif is_offer:
                # Offer: 1:00 AM start, 12:59 AM end
                start_time = "01:00"
                end_time = "12:59"
            else:
                start_time = None
                end_time = None

            # Parse start date
            start_dt = parse_date(start_raw, default_time=datetime.strptime(start_time, "%H:%M") if start_time else None, default_year=current_year)
            # Parse end date
            # Try to extract time from end_raw
            end_time_match = re.search(r'(\d{1,2}:\d{2}(?:\s*[APMapm\.]*)?)', end_raw)
            if is_offer:
                end_dt = parse_date(end_raw, default_time=datetime.strptime(end_time, "%H:%M"), default_year=current_year)
            elif end_time_match:
                end_dt = parse_date(end_raw, default_year=current_year)
            else:
                # If no time, use default
                if "after the update" in text.lower() and not is_offer:
                    end_dt = parse_date(end_raw + " 06:59", default_year=current_year)
                elif is_offer:
                    end_dt = parse_date(end_raw + " 12:59", default_year=current_year)
                else:
                    end_dt = parse_date(end_raw, default_year=current_year)

            # If year is missing and end < start, increment end year
            if start_dt and end_dt and end_dt < start_dt:
                end_dt = end_dt.replace(year=end_dt.year + 1)

            # Format output
            def fmt(dt, time_override=None):
                if not dt:
                    return None
                if time_override:
                    dt = dt.replace(hour=time_override.hour, minute=time_override.minute)
                return dt.strftime("%B %d, %Y, %H:%M") + f" {tz_str}"

            # For offers, always use 01:00 for start, 12:59 for end
            if is_offer:
                start_str = fmt(start_dt, datetime.strptime("01:00", "%H:%M"))
                end_str = fmt(end_dt, datetime.strptime("12:59", "%H:%M"))
            elif "after the update" in text.lower():
                start_str = fmt(start_dt, datetime.strptime("04:00", "%H:%M"))
                # Try to preserve time for end if present, else 06:59
                if end_time_match:
                    end_str = fmt(end_dt)
                else:
                    end_str = fmt(end_dt, datetime.strptime("06:59", "%H:%M"))
            else:
                start_str = fmt(start_dt)
                end_str = fmt(end_dt)

            return start_str, end_str

    # Fallback: try to find a single date
    date_match = re.search(r'([A-Za-z]+\s*\d{1,2}(?:,)?(?:\s*\d{4})?)', text)
    if date_match:
        dt = parse_date(date_match.group(1), default_year=current_year)
        if dt:
            return dt.strftime("%B %d, %Y, %H:%M") + f" {tz_str}", None

    return None, None

# Wuthering Waves specific parsing functions
# def parse_category_wuwa(text):

# def parse_dates_wuwa(text):

POSTER_PROFILES = {
    "honkaistarrail": {
        "parse_title": parse_title_hsr,
        "parse_dates": parse_dates_hsr,
        "parse_category": parse_category_hsr
    },
    "zzz_en": {
        "parse_title": parse_title_zzz,
        "parse_dates": parse_dates_zzz,
        "parse_category": parse_category_zzz
    },
    "arknightsen": {
        "parse_title": parse_title_ak,
        "parse_dates": parse_dates_ak,
        "parse_category": parse_category_ak
    },
    "strinova_en": {
        "parse_title": parse_title_stri,
        "parse_dates": parse_dates_stri,
        "parse_category": parse_category_stri
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

async def prepare_hyv_event_entries(ctx, base_event, start_times, end_times, image, category, event_profile, title):
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
    async with aiosqlite.connect('kanami_data.db') as conn:
        base_title = title
        suffix = 1
        new_title = base_title
        while True:
            async with conn.execute(
                "SELECT COUNT(*) FROM user_data WHERE server_id=? AND title=?",
                (str(ctx.guild.id), new_title)
            ) as cursor:
                count = (await cursor.fetchone())[0]
            if count == 0:
                break
            suffix += 1
            new_title = f"{base_title} {suffix}"

        await conn.execute(
            "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category, is_hyv, asia_start, asia_end, america_start, america_end, europe_start, europe_end, profile) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(ctx.author.id), str(ctx.guild.id), new_title, "", "", image, category, 1,
                asia_start, asia_end, america_start, america_end, europe_start, europe_end, event_profile
            )
        )
        await conn.commit()

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
async def convert_to_all_timezones(dt_str):
    """
    Converts a date string to all three Hoyoverse timezones and returns a dict of region: (datetime, unix).
    Checks version tracker for known version start dates.
    """
    import dateparser
    import pytz
    import re

    dt = dateparser.parse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': True})
    if not dt:
        dt = dateparser.parse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': False})
        if not dt:
            return None

    # Check if dt matches any known version start (ZZZ or HSR)
    async def is_version_start(dt):
        # ZZZ
        zzz_base_version = "2.0"
        zzz_base_date = datetime(2025, 6, 6, 11, 0, tzinfo=timezone(timedelta(hours=8)))
        # HSR
        hsr_base_version = "3.3"
        hsr_base_date = datetime(2025, 5, 21, 11, 0, tzinfo=timezone(timedelta(hours=8)))
        async with aiosqlite.connect('kanami_data.db') as conn:
            for profile, base_version, base_date in [
                ("ZZZ", zzz_base_version, zzz_base_date),
                ("HSR", hsr_base_version, hsr_base_date)
            ]:
                async with conn.execute("SELECT version, start_date FROM version_tracker WHERE profile=?", (profile,)) as cursor:
                    rows = await cursor.fetchall()
                for version, start_date in rows:
                    try:
                        ver_dt = datetime.fromisoformat(start_date)
                        if abs((dt - ver_dt).total_seconds()) < 60:
                            return True
                    except Exception:
                        continue
                # Also check the base date
                if abs((dt - base_date).total_seconds()) < 60:
                    return True
        return False

    if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
        if await is_version_start(dt):
            unix = int(dt.timestamp())
            return {region: (dt, unix) for region in HYV_TIMEZONES}
        # Otherwise, just use the same time for all regions
        unix = int(dt.timestamp())
        return {region: (dt, unix) for region in HYV_TIMEZONES}

    # Otherwise, localize naive time to each region
    results = {}
    for region, tz_name in HYV_TIMEZONES.items():
        tz = pytz.timezone(tz_name)
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
            # Get all images, filter out emoji/profile images
            images = await page.locator("article img").all()
            for img in images:
                src = await img.get_attribute("src")
                # Filter: skip emoji, profile, SVG, and very small images
                if (
                    src
                    and "profile_images" not in src
                    and "emoji" not in src
                    and not src.endswith(".svg")
                    and not re.search(r'/emoji/', src)
                    and not re.search(r'/ext_tw_emoji/', src)
                    and not re.search(r'/hashflags/', src)
                ):
                    image_url = src
                    break
            # Get the poster's username (usually in the first <a> with href="/username")
            user_link = await page.locator("article a[href^='/']").first.get_attribute("href")
            if user_link:
                username = user_link.strip("/").lower()
        except Exception as e:
            print(f"[DEBUG] Exception in fetch_tweet_content: {e}")
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
    import traceback
    from database_handler import update_timer_channel
    from notification_handler import schedule_notifications_for_event, remove_duplicate_pending_notifications
    import aiosqlite

    assumed_end = False

    print("[DEBUG] read: Starting command")
    await ctx.send("Reading tweet, please wait...")
    try:
        link = normalize_twitter_link(link)
        print(f"[DEBUG] read: Normalized link: {link}")

        try:
            tweet_text, tweet_image, username = await asyncio.wait_for(fetch_tweet_content(link), timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("Timed out while trying to read the tweet. Twitter/X may be slow or blocking the bot.")
            print("[DEBUG] read: fetch_tweet_content timed out.")
            return
        print(f"[DEBUG] read: tweet_text={repr(tweet_text)[:200]}, tweet_image={tweet_image}, username={username}")

        if not tweet_text:
            await ctx.send("Could not read the tweet. Please check the link or try again later.")
            print("[DEBUG] read: No tweet text found, aborting.")
            return

        event_profile = normalize_profile(username) if username else "ALL"
        print(f"[DEBUG] read: event_profile={event_profile}")
        profile_parser = POSTER_PROFILES.get(username.lower() if username else "")
        print(f"[DEBUG] read: profile_parser keys={list(profile_parser.keys()) if profile_parser else None}")

        # --- Parse category and dates using poster profile logic ---
        title = None
        category = None
        start = None
        end = None

        if profile_parser:
            if "parse_title" in profile_parser:
                parse_title_fn = profile_parser["parse_title"]
                print("[DEBUG] read: Parsing title...")
                if inspect.iscoroutinefunction(parse_title_fn):
                    title = await parse_title_fn(tweet_text)
                else:
                    title = parse_title_fn(tweet_text)
                print(f"[DEBUG] read: Parsed title: {title}")
            if "parse_category" in profile_parser:
                parse_category_fn = profile_parser["parse_category"]
                print("[DEBUG] read: Parsing category...")
                if inspect.iscoroutinefunction(parse_category_fn):
                    category = await parse_category_fn(tweet_text)
                else:
                    category = parse_category_fn(tweet_text)
                print(f"[DEBUG] read: Parsed category: {category}")
            if "parse_dates" in profile_parser:
                parse_date_fn = profile_parser["parse_dates"]
                print("[DEBUG] read: Parsing dates...")
                if inspect.iscoroutinefunction(parse_date_fn):
                    start, end = await parse_date_fn(ctx, tweet_text)
                else:
                    start, end = parse_date_fn(tweet_text)
                print(f"[DEBUG] read: Parsed dates: start={start}, end={end}")
        else:
            print("[DEBUG] read: No profile_parser found for this username.")

        # --- Autofill for missing info ---
        if not title:
            title = "Unknown Title"
            print("[DEBUG] read: Autofilled title.")
        if not category:
            category = "Unknown Category"
            print("[DEBUG] read: Autofilled category.")

        image = tweet_image if tweet_image else None
        print(f"[DEBUG] read: image={image}")

        # --- Parse dates if not already parsed ---
        if not (start or end):
            print("[DEBUG] read: No dates found, using general parser.")
            start, end = await parse_dates(tweet_text)
            print(f"[DEBUG] read: General parser dates: start={start}, end={end}")
            if not (start or end):
                await ctx.send("No valid dates found in the tweet. Cancelling read: this tweet does not appear to contain an event time.")
                print("[DEBUG] read: No dates found after all parsing, cancelling.")
                return
            if start and not end:
                # Assume end is 2 weeks after start
                try:
                    dt_start = dateparser.parse(start, settings={'RETURN_AS_TIMEZONE_AWARE': True})
                    if dt_start:
                        dt_end = dt_start + timedelta(days=14)
                        # Format end in the same style as start
                        if dt_start.tzinfo:
                            end = dt_end.strftime("%Y/%m/%d %H:%M %Z")
                        else:
                            end = dt_end.strftime("%Y/%m/%d %H:%M")
                        print(f"[DEBUG] read: End date autofilled as 2 weeks after start: {end}")
                        assumed_end = True
                    else:
                        await ctx.send("Could not parse the start date to autofill end date. Cancelling.")
                        print("[DEBUG] read: Could not parse start date for autofill, cancelling.")
                        return
                except Exception as e:
                    await ctx.send(f"Error autofilling end date: {e}")
                    print(f"[DEBUG] read: Exception autofilling end date: {e}")
                    return

        is_hyv = username in HYV_ACCOUNTS
        print(f"[DEBUG] read: is_hyv={is_hyv}")

        # --- Hoyoverse logic below ---
        if is_hyv:
            print("[DEBUG] read: Converting to all timezones...")
            start_times = await convert_to_all_timezones(start)
            end_times = await convert_to_all_timezones(end)
            print(f"[DEBUG] read: start_times={start_times}, end_times={end_times}")
            if not (start_times and end_times):
                await ctx.send("Could not parse start or end time for all regions. Cancelling.")
                print("[DEBUG] read: Could not parse all regions, aborting.")
                return

            if not category:
                print("[DEBUG] read: Prompting for category...")
                category = await prompt_for_category(ctx)
                if not category:
                    print("[DEBUG] read: No category selected, aborting.")
                    return

            event_entries, new_title = await prepare_hyv_event_entries(
                ctx, {}, start_times, end_times, image, category, event_profile, title
            )
            print(f"[DEBUG] read: Prepared HYV event entries.")

            await ctx.send(
                f"Added `{new_title}` as **{category}** for all HYV server regions to the database!"
            )
            await update_timer_channel(ctx.guild, bot, profile=event_profile)
            print("[DEBUG] read: Updated timer channel for HYV.")

            # Update all timer channels for HYV profiles
            async with aiosqlite.connect('kanami_data.db') as conn:
                async with conn.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),)) as cursor:
                    profiles = [row[0] async for row in cursor]
            for profile in profiles:
                await update_timer_channel(ctx.guild, bot, profile=profile)
            print("[DEBUG] read: Updated all timer channels for HYV.")

            for event in event_entries:
                asyncio.create_task(schedule_notifications_for_event(event))
            print("[DEBUG] read: Scheduled notifications for HYV.")
            
            remove_duplicate_pending_notifications()
            return

        # --- Non-HYV logic: store as usual ---
        timezone_regex = r"(UTC[+-]\d+|GMT[+-]\d+|[+-]\d{2}:?\d{2}|[A-Z]{2,5})"
        tz_in_start = bool(start and re.search(timezone_regex, start))
        tz_in_end = bool(end and re.search(timezone_regex, end))
        timezone_str = None

        if not (tz_in_start or tz_in_end):
            print("[DEBUG] read: Prompting for timezone...")
            timezone_str = await prompt_for_timezone(ctx)
            if not timezone_str:
                print("[DEBUG] read: No timezone provided, aborting.")
                return

        try:
            if timezone_str:
                start_unix = to_unix_timestamp(f"{start} {timezone_str}")
                end_unix = to_unix_timestamp(f"{end} {timezone_str}")
            else:
                start_unix = int(start) if start and start.isdigit() else to_unix_timestamp(start)
                end_unix = int(end) if end and end.isdigit() else to_unix_timestamp(end)
            print(f"[DEBUG] read: start_unix={start_unix}, end_unix={end_unix}")
        except Exception as e:
            await ctx.send(f"Error parsing date/time: {e}")
            print(f"[DEBUG] read: Exception parsing date/time: {e}")
            return

        # Ensure unique title
        async with aiosqlite.connect('kanami_data.db') as conn:
            base_title = title
            suffix = 1
            new_title = base_title
            while True:
                async with conn.execute(
                    "SELECT COUNT(*) FROM user_data WHERE server_id=? AND title=?",
                    (str(ctx.guild.id), new_title)
                ) as cursor:
                    count = (await cursor.fetchone())[0]
                if count == 0:
                    break
                suffix += 1
                new_title = f"{base_title} {suffix}"
            print(f"[DEBUG] read: Final event title: {new_title}")

            await conn.execute(
                "INSERT INTO user_data (user_id, server_id, title, start_date, end_date, image, category, profile) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(ctx.author.id), str(ctx.guild.id), new_title, str(start_unix), str(end_unix), image, category, event_profile)
            )
            await conn.commit()
            print("[DEBUG] read: Inserted event into database.")

        if not assumed_end:
            await ctx.send(
                f"Added `{new_title}` as **{category}** with start `<t:{start_unix}:F>` and end `<t:{end_unix}:F>` to the database!"
            )
        else:
            await ctx.send(
                f"Added `{new_title}` as **{category}** with start `<t:{start_unix}:F>` and __**assumed**__ end `<t:{end_unix}:F>` to the database!"
            )

        await update_timer_channel(ctx.guild, bot, profile=event_profile)
        print("[DEBUG] read: Updated timer channel for non-HYV.")

        # Update all timer channels for non-HYV profiles
        async with aiosqlite.connect('kanami_data.db') as conn:
            async with conn.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),)) as cursor:
                profiles = [row[0] async for row in cursor]
        unique_profiles = set(profiles)
        unique_profiles.add("ALL")
        for profile in unique_profiles:
            await update_timer_channel(ctx.guild, bot, profile=profile)
        print("[DEBUG] read: Updated all timer channels for non-HYV.")

        event = {
            'server_id': str(ctx.guild.id),
            'category': category,
            'profile': event_profile,
            'title': new_title,
            'start_date': str(start_unix),
            'end_date': str(end_unix)
        }
        
        asyncio.create_task(schedule_notifications_for_event(event))
        print("[DEBUG] read: Scheduled notification for non-HYV.")
        remove_duplicate_pending_notifications()
        
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: `{e}`")
        print("[DEBUG] Exception in read command:")
        print(traceback.format_exc())


