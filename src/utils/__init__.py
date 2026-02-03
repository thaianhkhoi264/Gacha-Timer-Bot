"""
Shared utilities for the Gacha Timer Bot.

This module provides common utility functions used across the application:
- Database connection helpers with SQLite optimizations
- Logging configuration and setup
- Date/time parsing utilities
- Async helpers and decorators
- Constants and configuration helpers
"""

import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List, Callable, TypeVar, Union
from functools import wraps
from contextlib import asynccontextmanager

import aiosqlite
import pytz
import dateparser


# =============================================================================
# Database Utilities
# =============================================================================

async def get_db_connection(
    db_path: str,
    *,
    wal_mode: bool = True,
    foreign_keys: bool = True,
) -> aiosqlite.Connection:
    """
    Get an optimized SQLite database connection.

    Args:
        db_path: Path to the SQLite database file
        wal_mode: Enable Write-Ahead Logging for better concurrency
        foreign_keys: Enable foreign key constraints

    Returns:
        Configured aiosqlite connection
    """
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row

    if wal_mode:
        await conn.execute("PRAGMA journal_mode=WAL")

    if foreign_keys:
        await conn.execute("PRAGMA foreign_keys=ON")

    # Performance optimizations
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA cache_size=-64000")  # 64MB cache

    return conn


@asynccontextmanager
async def db_transaction(conn: aiosqlite.Connection):
    """
    Context manager for database transactions.

    Automatically commits on success, rolls back on error.

    Usage:
        async with db_transaction(conn):
            await conn.execute(...)
            await conn.execute(...)
    """
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise


async def ensure_directory(path: str) -> None:
    """Ensure a directory exists, creating it if necessary."""
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


# =============================================================================
# Logging Utilities
# =============================================================================

def setup_logging(
    name: str = 'gacha_timer_bot',
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """
    Set up logging with console and optional file handlers.

    Args:
        name: Logger name
        level: Logging level (default: INFO)
        log_file: Optional file path for log output
        format_string: Custom format string

    Returns:
        Configured logger instance
    """
    if format_string is None:
        format_string = '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'

    formatter = logging.Formatter(format_string, datefmt='%Y-%m-%d %H:%M:%S')

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module."""
    return logging.getLogger(f'gacha_timer_bot.{name}')


# =============================================================================
# Date/Time Utilities
# =============================================================================

# Common timezone definitions
TIMEZONES = {
    'UTC': pytz.UTC,
    'JST': pytz.timezone('Asia/Tokyo'),
    'PST': pytz.timezone('America/Los_Angeles'),
    'EST': pytz.timezone('America/New_York'),
    'CET': pytz.timezone('Europe/Berlin'),
    'GMT+7': pytz.timezone('Asia/Bangkok'),
    'GMT+8': pytz.timezone('Asia/Shanghai'),
    # Hoyoverse server timezones
    'ASIA': pytz.timezone('Asia/Shanghai'),
    'AMERICA': pytz.timezone('America/New_York'),
    'EUROPE': pytz.timezone('Europe/Berlin'),
}


def parse_datetime(
    datetime_string: str,
    *,
    timezone_hint: Optional[str] = None,
    prefer_dates_from: str = 'future',
) -> Optional[datetime]:
    """
    Parse a datetime string with fuzzy matching.

    Args:
        datetime_string: The datetime string to parse
        timezone_hint: Timezone to use if not specified in string
        prefer_dates_from: 'future' or 'past' for ambiguous dates

    Returns:
        Parsed datetime or None if parsing fails
    """
    settings = {
        'PREFER_DATES_FROM': prefer_dates_from,
        'RETURN_AS_TIMEZONE_AWARE': True,
    }

    if timezone_hint:
        tz = TIMEZONES.get(timezone_hint.upper())
        if tz:
            settings['TIMEZONE'] = str(tz)

    return dateparser.parse(datetime_string, settings=settings)


def to_unix_timestamp(dt: datetime) -> int:
    """Convert a datetime to Unix timestamp."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def from_unix_timestamp(
    timestamp: int,
    tz: Optional[str] = None,
) -> datetime:
    """
    Convert a Unix timestamp to datetime.

    Args:
        timestamp: Unix timestamp
        tz: Optional timezone name

    Returns:
        Datetime object
    """
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

    if tz:
        target_tz = TIMEZONES.get(tz.upper(), pytz.UTC)
        dt = dt.astimezone(target_tz)

    return dt


def format_discord_timestamp(
    timestamp: int,
    style: str = 'F',
) -> str:
    """
    Format a Unix timestamp as a Discord timestamp.

    Styles:
        't': Short time (16:20)
        'T': Long time (16:20:30)
        'd': Short date (20/04/2021)
        'D': Long date (20 April 2021)
        'f': Short datetime (20 April 2021 16:20)
        'F': Long datetime (Tuesday, 20 April 2021 16:20)
        'R': Relative time (2 months ago)

    Args:
        timestamp: Unix timestamp
        style: Discord timestamp style

    Returns:
        Formatted Discord timestamp string
    """
    return f"<t:{timestamp}:{style}>"


def format_relative_time(timestamp: int) -> str:
    """Format a Unix timestamp as relative time."""
    return format_discord_timestamp(timestamp, 'R')


def get_time_until(timestamp: int) -> timedelta:
    """Get the time remaining until a Unix timestamp."""
    now = datetime.now(tz=timezone.utc)
    target = from_unix_timestamp(timestamp)
    return target - now


def is_past(timestamp: int) -> bool:
    """Check if a Unix timestamp is in the past."""
    return timestamp < int(datetime.now(tz=timezone.utc).timestamp())


def is_within(timestamp: int, hours: float = 1.0) -> bool:
    """Check if a Unix timestamp is within the specified hours from now."""
    now = int(datetime.now(tz=timezone.utc).timestamp())
    return now <= timestamp <= now + (hours * 3600)


# =============================================================================
# Async Utilities
# =============================================================================

T = TypeVar('T')


def async_retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < retries:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    continue

            raise last_exception

        return wrapper
    return decorator


async def gather_with_limit(
    coros: List,
    limit: int = 5,
) -> List[Any]:
    """
    Run coroutines concurrently with a concurrency limit.

    Args:
        coros: List of coroutines to run
        limit: Maximum concurrent coroutines

    Returns:
        List of results
    """
    semaphore = asyncio.Semaphore(limit)

    async def limited_coro(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*[limited_coro(c) for c in coros])


async def run_with_timeout(
    coro,
    timeout: float,
    default: Any = None,
) -> Any:
    """
    Run a coroutine with a timeout.

    Args:
        coro: Coroutine to run
        timeout: Timeout in seconds
        default: Value to return on timeout

    Returns:
        Coroutine result or default value
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


# =============================================================================
# String Utilities
# =============================================================================

def truncate(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """Truncate text to a maximum length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def sanitize_filename(filename: str) -> str:
    """Sanitize a string for use as a filename."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename.strip()


def pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    """Return singular or plural form based on count."""
    if plural is None:
        plural = singular + 's'
    return singular if count == 1 else plural


# =============================================================================
# Validation Utilities
# =============================================================================

def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL."""
    import re
    url_pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$',
        re.IGNORECASE
    )
    return bool(url_pattern.match(url))


def is_valid_unix_timestamp(timestamp: Union[int, str]) -> bool:
    """Check if a value is a valid Unix timestamp."""
    try:
        ts = int(timestamp)
        # Reasonable range: 2000-01-01 to 2100-01-01
        return 946684800 <= ts <= 4102444800
    except (ValueError, TypeError):
        return False


# =============================================================================
# Constants
# =============================================================================

# Bot configuration
DEFAULT_COMMAND_PREFIX = "Kanami "
BOT_VERSION = "3.0.0"

# Valid game profiles
VALID_PROFILES = ["HSR", "ZZZ", "AK", "STRI", "WUWA", "UMA", "ALL"]
HYV_PROFILES = {"HSR", "ZZZ", "WUWA"}  # Hoyoverse games with regional servers

# Event categories
STANDARD_CATEGORIES = ["Banner", "Event", "Maintenance", "Offer"]

# Notification timing types
TIMING_TYPES = [
    "reminder",
    "start_24h", "start_3h", "start_1h",
    "end_25h", "end_24h", "end_3h", "end_1h",
]

# Discord embed limits
EMBED_TITLE_LIMIT = 256
EMBED_DESCRIPTION_LIMIT = 4096
EMBED_FIELD_NAME_LIMIT = 256
EMBED_FIELD_VALUE_LIMIT = 1024
EMBED_FIELD_COUNT_LIMIT = 25
EMBED_FOOTER_LIMIT = 2048
EMBED_TOTAL_LIMIT = 6000


__all__ = [
    # Database
    'get_db_connection',
    'db_transaction',
    'ensure_directory',
    # Logging
    'setup_logging',
    'get_logger',
    # Date/Time
    'TIMEZONES',
    'parse_datetime',
    'to_unix_timestamp',
    'from_unix_timestamp',
    'format_discord_timestamp',
    'format_relative_time',
    'get_time_until',
    'is_past',
    'is_within',
    # Async
    'async_retry',
    'gather_with_limit',
    'run_with_timeout',
    # String
    'truncate',
    'sanitize_filename',
    'pluralize',
    # Validation
    'is_valid_url',
    'is_valid_unix_timestamp',
    # Constants
    'DEFAULT_COMMAND_PREFIX',
    'BOT_VERSION',
    'VALID_PROFILES',
    'HYV_PROFILES',
    'STANDARD_CATEGORIES',
    'TIMING_TYPES',
    'EMBED_TITLE_LIMIT',
    'EMBED_DESCRIPTION_LIMIT',
    'EMBED_FIELD_NAME_LIMIT',
    'EMBED_FIELD_VALUE_LIMIT',
    'EMBED_FIELD_COUNT_LIMIT',
    'EMBED_FOOTER_LIMIT',
    'EMBED_TOTAL_LIMIT',
]
