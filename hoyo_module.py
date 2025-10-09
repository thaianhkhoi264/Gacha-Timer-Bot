"""
Hoyoverse utilities for HSR and ZZZ modules.
Handles version tracking, server time conversions, and region-specific event management.
Each profile (HSR/ZZZ) will pass its own DB path to these functions.
"""

import aiosqlite
from datetime import datetime, timedelta, timezone
import pytz
import dateparser

# Triple timezone mapping for Hoyoverse games
HYV_TIMEZONES = {
    "Asia": "Asia/Shanghai",        # UTC+8
    "America": "America/New_York",  # UTC-5 (handles DST)
    "Europe": "Europe/Berlin",      # UTC+1 (handles DST)
}

# Default base versions and dates for each game
DEFAULT_VERSIONS = {
    "HSR": {
        "version": "3.3",
        "date": datetime(2025, 5, 21, 11, 0, tzinfo=timezone(timedelta(hours=8)))
    },
    "ZZZ": {
        "version": "2.0",
        "date": datetime(2025, 6, 6, 11, 0, tzinfo=timezone(timedelta(hours=8)))
    }
}

async def get_version_start_dynamic(db_path, profile, version_str, default_base_version, default_base_date):
    """
    Looks up the latest known version and start date for the profile from the given database.
    If the requested version is newer, calculates its start date as 6 weeks after the last known.
    If not found, uses the default base.
    
    Args:
        db_path: Path to the profile's database
        profile: "HSR" or "ZZZ"
        version_str: e.g. "3.5" or "2.1"
        default_base_version: e.g. "3.3"
        default_base_date: datetime object with timezone
    
    Returns:
        datetime object for the version start time
    """
    async with aiosqlite.connect(db_path) as conn:
        # Ensure version_tracker table exists
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS version_tracker (
                profile TEXT PRIMARY KEY,
                version TEXT,
                start_date TEXT
            )
        ''')
        await conn.commit()
        
        async with conn.execute(
            "SELECT version, start_date FROM version_tracker WHERE profile=?",
            (profile,)
        ) as cursor:
            row = await cursor.fetchone()

    # Parse version numbers (major.minor format)
    def parse_version(v):
        parts = v.split('.')
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        return major, minor

    req_major, req_minor = parse_version(version_str)

    if row:
        base_version, base_date_str = row
        base_major, base_minor = parse_version(base_version)
        base_date = datetime.fromisoformat(base_date_str)
    else:
        base_major, base_minor = parse_version(default_base_version)
        base_date = default_base_date

    # If requested version is before or equal to base, return base
    if (req_major, req_minor) <= (base_major, base_minor):
        return base_date

    # Calculate weeks difference (each version is 6 weeks)
    delta_versions = (req_major - base_major) * 10 + (req_minor - base_minor)
    start_date = base_date + timedelta(weeks=6 * delta_versions)
    return start_date

async def get_version_start_hsr(db_path, version_str):
    """
    Get HSR version start time.
    
    Args:
        db_path: Path to HSR database
        version_str: e.g. "3.5"
    
    Returns:
        datetime object for version start
    """
    config = DEFAULT_VERSIONS["HSR"]
    return await get_version_start_dynamic(
        db_path,
        "HSR",
        version_str,
        config["version"],
        config["date"]
    )

async def get_version_start_zzz(db_path, version_str):
    """
    Get ZZZ version start time.
    
    Args:
        db_path: Path to ZZZ database
        version_str: e.g. "2.1"
    
    Returns:
        datetime object for version start
    """
    config = DEFAULT_VERSIONS["ZZZ"]
    return await get_version_start_dynamic(
        db_path,
        "ZZZ",
        version_str,
        config["version"],
        config["date"]
    )

async def update_version_tracker(db_path, profile, version_str, start_date):
    """
    Updates the version tracker table with the given profile, version, and start date.
    
    Args:
        db_path: Path to the profile's database
        profile: "HSR" or "ZZZ"
        version_str: e.g. "3.5"
        start_date: datetime object
    """
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO version_tracker (profile, version, start_date) VALUES (?, ?, ?)",
            (profile, version_str, start_date.isoformat())
        )
        await conn.commit()

async def convert_to_all_timezones(dt_str, db_path=None, profile=None):
    """
    Converts a date string to all three Hoyoverse timezones and returns a dict of region: (datetime, unix).
    Checks version tracker for known version start dates if db_path and profile are provided.
    
    Args:
        dt_str: Date string to parse (e.g. "2025/06/18 04:00 (UTC+8)")
        db_path: Optional, path to profile's database for version start checking
        profile: Optional, "HSR" or "ZZZ" for version start checking
    
    Returns:
        dict: {
            "Asia": (datetime, unix_timestamp),
            "America": (datetime, unix_timestamp),
            "Europe": (datetime, unix_timestamp)
        }
    """
    dt = dateparser.parse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': True})
    if not dt:
        dt = dateparser.parse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': False})
        if not dt:
            return None

    # Check if dt matches any known version start
    async def is_version_start(dt):
        if not db_path or not profile:
            return False
        
        config = DEFAULT_VERSIONS.get(profile)
        if not config:
            return False
        
        base_date = config["date"]
        
        # Check base date
        if abs((dt - base_date).total_seconds()) < 60:
            return True
        
        # Check tracked versions
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute(
                "SELECT version, start_date FROM version_tracker WHERE profile=?",
                (profile,)
            ) as cursor:
                rows = await cursor.fetchall()
        
        for version, start_date in rows:
            try:
                ver_dt = datetime.fromisoformat(start_date)
                if abs((dt - ver_dt).total_seconds()) < 60:
                    return True
            except Exception:
                continue
        
        return False

    # If dt has timezone info
    if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
        # If it's a version start, use same absolute time for all regions
        if await is_version_start(dt):
            unix = int(dt.timestamp())
            return {region: (dt, unix) for region in HYV_TIMEZONES}
        # Otherwise, use the same absolute time
        unix = int(dt.timestamp())
        return {region: (dt, unix) for region in HYV_TIMEZONES}

    # Otherwise, localize naive time to each region's server time
    results = {}
    for region, tz_name in HYV_TIMEZONES.items():
        tz = pytz.timezone(tz_name)
        dt_tz = tz.localize(dt)
        unix = int(dt_tz.timestamp())
        results[region] = (dt_tz, unix)
    return results

async def prepare_hyv_event_entries(db_path, ctx, start_times, end_times, image, category, profile, title):
    """
    Prepares event entries for all HYV regions and inserts into the profile's database.
    
    Args:
        db_path: Path to the profile's database
        ctx: Discord context
        start_times: dict from convert_to_all_timezones
        end_times: dict from convert_to_all_timezones
        image: Image URL or None
        category: "Banner", "Event", or "Maintenance"
        profile: "HSR" or "ZZZ"
        title: Event title
    
    Returns:
        (event_entries, new_title) where event_entries is a list of dicts for notification scheduling
    """
    region_keys = [("NA", "America"), ("EU", "Europe"), ("ASIA", "Asia")]
    
    # Prepare DB fields (store UNIX timestamps as strings like AK module)
    asia_start = str(start_times["Asia"][1])
    asia_end = str(end_times["Asia"][1])
    america_start = str(start_times["America"][1])
    america_end = str(end_times["America"][1])
    europe_start = str(start_times["Europe"][1])
    europe_end = str(end_times["Europe"][1])

    async with aiosqlite.connect(db_path) as conn:
        # Ensure events table exists with HYV-specific columns
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                title TEXT,
                start_date TEXT,
                end_date TEXT,
                image TEXT,
                category TEXT,
                profile TEXT,
                asia_start TEXT,
                asia_end TEXT,
                america_start TEXT,
                america_end TEXT,
                europe_start TEXT,
                europe_end TEXT
            )
        ''')
        await conn.commit()
        
        # Generate unique title
        base_title = title
        suffix = 1
        new_title = base_title
        while True:
            async with conn.execute(
                "SELECT COUNT(*) FROM events WHERE title=?",
                (new_title,)
            ) as cursor:
                count = (await cursor.fetchone())[0]
            if count == 0:
                break
            suffix += 1
            new_title = f"{base_title} {suffix}"

        # Insert event with regional times
        await conn.execute(
            """INSERT INTO events 
            (user_id, title, start_date, end_date, image, category, profile,
             asia_start, asia_end, america_start, america_end, europe_start, europe_end) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(ctx.author.id), new_title, "", "", image, category, profile,
                asia_start, asia_end, america_start, america_end, europe_start, europe_end
            )
        )
        await conn.commit()

    # Prepare event dicts for notification scheduling (one per region)
    event_entries = []
    for region, tz_key in region_keys:
        event = {
            'category': category,
            'profile': profile,
            'title': new_title,
            'start_date': str(start_times[tz_key][1]),
            'end_date': str(end_times[tz_key][1]),
            'region': region
        }
        event_entries.append(event)
    return event_entries, new_title

async def is_version_start_time(db_path, dt, profile):
    """
    Check if a datetime matches a known version start time for the given profile.
    
    Args:
        db_path: Path to the profile's database
        dt: datetime object with timezone
        profile: "HSR" or "ZZZ"
    
    Returns:
        bool: True if dt matches a version start within 1 minute
    """
    config = DEFAULT_VERSIONS.get(profile)
    if not config:
        return False
    
    base_date = config["date"]
    
    # Check base date
    if abs((dt - base_date).total_seconds()) < 60:
        return True
    
    # Check tracked versions
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute(
            "SELECT version, start_date FROM version_tracker WHERE profile=?",
            (profile,)
        ) as cursor:
            rows = await cursor.fetchall()
    
    for version, start_date in rows:
        try:
            ver_dt = datetime.fromisoformat(start_date)
            if abs((dt - ver_dt).total_seconds()) < 60:
                return True
        except Exception:
            continue
    
    return False