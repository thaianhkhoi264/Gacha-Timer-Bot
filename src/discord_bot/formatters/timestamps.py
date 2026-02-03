"""
Timestamp formatting utilities for Discord.

Uses Discord's built-in timestamp formatting for automatic timezone conversion.
"""

from datetime import datetime
from typing import Optional, Union
import time


class TimestampFormat:
    """Discord timestamp format codes."""
    SHORT_TIME = "t"        # 16:20
    LONG_TIME = "T"         # 16:20:30
    SHORT_DATE = "d"        # 20/04/2021
    LONG_DATE = "D"         # 20 April 2021
    SHORT_DATETIME = "f"    # 20 April 2021 16:20
    LONG_DATETIME = "F"     # Tuesday, 20 April 2021 16:20
    RELATIVE = "R"          # 2 months ago / in 2 months


def format_timestamp(
    unix_time: Union[int, float],
    format_code: str = TimestampFormat.LONG_DATETIME
) -> str:
    """
    Format a UNIX timestamp for Discord display.

    Discord automatically converts timestamps to the viewer's local timezone.

    Args:
        unix_time: UNIX timestamp (seconds since epoch)
        format_code: Discord format code (default: full datetime)

    Returns:
        Discord timestamp string like <t:1234567890:F>
    """
    return f"<t:{int(unix_time)}:{format_code}>"


def format_timestamp_full(unix_time: Union[int, float]) -> str:
    """
    Format timestamp as full datetime (Tuesday, 20 April 2021 16:20).

    Args:
        unix_time: UNIX timestamp

    Returns:
        Discord timestamp string
    """
    return format_timestamp(unix_time, TimestampFormat.LONG_DATETIME)


def format_timestamp_relative(unix_time: Union[int, float]) -> str:
    """
    Format timestamp as relative time (in 3 days, 2 hours ago).

    Args:
        unix_time: UNIX timestamp

    Returns:
        Discord timestamp string
    """
    return format_timestamp(unix_time, TimestampFormat.RELATIVE)


def format_timestamp_dual(unix_time: Union[int, float]) -> str:
    """
    Format timestamp with both full datetime and relative.

    This is the standard format used in the bot:
    "Tuesday, 20 April 2021 16:20 (in 3 days)"

    Args:
        unix_time: UNIX timestamp

    Returns:
        Combined format string
    """
    full = format_timestamp(unix_time, TimestampFormat.LONG_DATETIME)
    relative = format_timestamp(unix_time, TimestampFormat.RELATIVE)
    return f"{full} ({relative})"


def format_event_times(
    start_unix: int,
    end_unix: int,
    include_relative: bool = True
) -> str:
    """
    Format start and end times for an event.

    Args:
        start_unix: Event start UNIX timestamp
        end_unix: Event end UNIX timestamp
        include_relative: Include relative time

    Returns:
        Formatted string with start/end times
    """
    if include_relative:
        start_str = f"{format_timestamp_full(start_unix)} or {format_timestamp_relative(start_unix)}"
        end_str = f"{format_timestamp_full(end_unix)} or {format_timestamp_relative(end_unix)}"
    else:
        start_str = format_timestamp_full(start_unix)
        end_str = format_timestamp_full(end_unix)

    return f"**Start:** {start_str}\n**End:** {end_str}"


def format_hyv_regional_times(
    asia_start: int,
    asia_end: int,
    america_start: int,
    america_end: int,
    europe_start: int,
    europe_end: int
) -> str:
    """
    Format regional times for Hoyoverse games.

    Args:
        asia_start: Asia server start UNIX timestamp
        asia_end: Asia server end UNIX timestamp
        america_start: America server start UNIX timestamp
        america_end: America server end UNIX timestamp
        europe_start: Europe server start UNIX timestamp
        europe_end: Europe server end UNIX timestamp

    Returns:
        Formatted string with all regional times
    """
    return (
        f"**Asia Server:**\n"
        f"Start: {format_timestamp_full(asia_start)}\n"
        f"End: {format_timestamp_full(asia_end)}\n\n"
        f"**America Server:**\n"
        f"Start: {format_timestamp_full(america_start)}\n"
        f"End: {format_timestamp_full(america_end)}\n\n"
        f"**Europe Server:**\n"
        f"Start: {format_timestamp_full(europe_start)}\n"
        f"End: {format_timestamp_full(europe_end)}"
    )


def format_notification_time(
    notify_unix: int,
    event_unix: int,
    timing_type: str
) -> str:
    """
    Format notification time description.

    Args:
        notify_unix: When notification will be sent
        event_unix: When the event starts/ends
        timing_type: Type of timing (e.g., "start_60", "end_1440")

    Returns:
        Formatted description string
    """
    # Parse timing type
    parts = timing_type.split("_")
    if len(parts) >= 2:
        event_type = parts[0]  # "start" or "end"
        try:
            minutes = int(parts[1])
        except ValueError:
            minutes = 0
    else:
        event_type = timing_type
        minutes = 0

    # Format time difference
    if minutes >= 1440:
        days = minutes // 1440
        time_str = f"{days} day{'s' if days > 1 else ''}"
    elif minutes >= 60:
        hours = minutes // 60
        time_str = f"{hours} hour{'s' if hours > 1 else ''}"
    else:
        time_str = f"{minutes} minute{'s' if minutes > 1 else ''}"

    action = "starts" if event_type == "start" else "ends"

    return f"{time_str} before event {action}"


def get_time_until(unix_time: int, current_time: Optional[int] = None) -> str:
    """
    Get human-readable time until a timestamp.

    Args:
        unix_time: Target UNIX timestamp
        current_time: Current time (defaults to now)

    Returns:
        Human-readable string like "3 days, 2 hours"
    """
    if current_time is None:
        current_time = int(time.time())

    diff = unix_time - current_time

    if diff <= 0:
        return "now"

    days = diff // 86400
    hours = (diff % 86400) // 3600
    minutes = (diff % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 and days == 0:  # Only show minutes if less than a day
        parts.append(f"{minutes}m")

    return " ".join(parts) if parts else "< 1m"


def is_past(unix_time: int, current_time: Optional[int] = None) -> bool:
    """Check if a timestamp is in the past."""
    if current_time is None:
        current_time = int(time.time())
    return unix_time < current_time


def is_future(unix_time: int, current_time: Optional[int] = None) -> bool:
    """Check if a timestamp is in the future."""
    if current_time is None:
        current_time = int(time.time())
    return unix_time > current_time
