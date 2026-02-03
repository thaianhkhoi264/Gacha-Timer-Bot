"""
Timezone Service for Gacha Timer Bot.

Handles timezone conversions for Hoyoverse games (HSR, ZZZ, WUWA)
which have different server times for ASIA, AMERICA, and EUROPE regions.
"""

from datetime import datetime
from typing import Dict, Optional, Tuple
import pytz
from dateparser import parse as dateparse


# Hoyoverse server timezones
HYV_TIMEZONES: Dict[str, str] = {
    "ASIA": "Asia/Shanghai",        # UTC+8
    "AMERICA": "America/New_York",  # UTC-5 (handles DST)
    "EUROPE": "Europe/Berlin",      # UTC+1 (handles DST)
}

# Profiles that use regional timezones
HYV_PROFILES = {"HSR", "ZZZ", "WUWA"}


class TimezoneService:
    """
    Service for handling timezone conversions.

    Hoyoverse games have different server times for each region:
    - ASIA: UTC+8 (China Standard Time)
    - AMERICA: UTC-5 (Eastern Time, with DST)
    - EUROPE: UTC+1 (Central European Time, with DST)
    """

    def __init__(self):
        """Initialize timezone objects for each region."""
        self.timezones = {
            region: pytz.timezone(tz_name)
            for region, tz_name in HYV_TIMEZONES.items()
        }

    def is_hyv_profile(self, profile: str) -> bool:
        """
        Check if a profile uses Hoyoverse regional timezones.

        Args:
            profile: Game profile (e.g., "HSR", "ZZZ", "UMA")

        Returns:
            True if the profile has regional server times
        """
        return profile.upper() in HYV_PROFILES

    def get_timezone(self, region: str) -> pytz.timezone:
        """
        Get the pytz timezone object for a region.

        Args:
            region: Region name (ASIA, AMERICA, EUROPE)

        Returns:
            pytz timezone object

        Raises:
            ValueError: If region is not recognized
        """
        region = region.upper()
        if region not in self.timezones:
            raise ValueError(f"Unknown region: {region}. Must be one of {list(self.timezones.keys())}")
        return self.timezones[region]

    def parse_datetime(
        self,
        dt_str: str,
        region: Optional[str] = None,
        assume_utc: bool = False
    ) -> Optional[datetime]:
        """
        Parse a datetime string with optional timezone localization.

        Args:
            dt_str: Datetime string to parse
            region: If provided, localize naive datetime to this region
            assume_utc: If True and no region, assume UTC

        Returns:
            Parsed datetime object (timezone-aware if region provided), or None if parsing fails
        """
        if not dt_str:
            return None

        try:
            dt = dateparse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': True})
            if dt is None:
                return None

            # If datetime is naive and we have a region, localize it
            if dt.tzinfo is None and region:
                tz = self.get_timezone(region)
                dt = tz.localize(dt)
            elif dt.tzinfo is None and assume_utc:
                dt = pytz.UTC.localize(dt)

            return dt
        except Exception:
            return None

    def to_unix(self, dt: datetime) -> int:
        """
        Convert datetime to UNIX timestamp.

        Args:
            dt: Datetime object

        Returns:
            UNIX timestamp (seconds since epoch)
        """
        return int(dt.timestamp())

    def from_unix(self, timestamp: int, region: Optional[str] = None) -> datetime:
        """
        Convert UNIX timestamp to datetime.

        Args:
            timestamp: UNIX timestamp
            region: If provided, convert to this region's timezone

        Returns:
            Datetime object (in region's timezone if specified, else UTC)
        """
        dt = datetime.utcfromtimestamp(timestamp)
        dt = pytz.UTC.localize(dt)

        if region:
            tz = self.get_timezone(region)
            dt = dt.astimezone(tz)

        return dt

    def convert_to_all_regions(
        self,
        dt_str: str,
        is_version_time: bool = False
    ) -> Dict[str, Tuple[datetime, int]]:
        """
        Convert a datetime string to all Hoyoverse regions.

        For version/maintenance times: the absolute moment is the same globally,
        so we just convert the timezone.

        For event times: the local time is the same in each region
        (e.g., "10:00 AM" means 10:00 AM in Asia, America, AND Europe).

        Args:
            dt_str: Datetime string to parse
            is_version_time: If True, treat as absolute time (version/maintenance)
                           If False, treat as local time in each region

        Returns:
            Dict mapping region name to (datetime, unix_timestamp) tuple
        """
        results = {}

        # Parse the datetime
        dt = dateparse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        if dt is None:
            return results

        if is_version_time:
            # Version/maintenance: same absolute time, different local representations
            # Parse as ASIA time (Hoyoverse HQ), then convert to others
            if dt.tzinfo is None:
                asia_tz = self.get_timezone("ASIA")
                dt = asia_tz.localize(dt)

            for region, tz in self.timezones.items():
                regional_dt = dt.astimezone(tz)
                results[region] = (regional_dt, self.to_unix(regional_dt))
        else:
            # Event time: same local time in each region
            # e.g., "10:00 AM" is 10:00 AM local in Asia, America, and Europe
            naive_dt = dt.replace(tzinfo=None) if dt.tzinfo else dt

            for region, tz in self.timezones.items():
                regional_dt = tz.localize(naive_dt)
                results[region] = (regional_dt, self.to_unix(regional_dt))

        return results

    def get_region_offset_hours(self, region: str) -> float:
        """
        Get the UTC offset in hours for a region at the current time.

        Note: This changes with DST for America and Europe.

        Args:
            region: Region name

        Returns:
            UTC offset in hours (e.g., 8.0 for ASIA, -5.0 for AMERICA in winter)
        """
        tz = self.get_timezone(region)
        now = datetime.now(tz)
        offset = now.utcoffset()
        return offset.total_seconds() / 3600 if offset else 0

    def format_datetime(
        self,
        timestamp: int,
        region: Optional[str] = None,
        format_str: str = "%Y-%m-%d %H:%M"
    ) -> str:
        """
        Format a UNIX timestamp as a human-readable string.

        Args:
            timestamp: UNIX timestamp
            region: Region for timezone conversion (None = UTC)
            format_str: strftime format string

        Returns:
            Formatted datetime string
        """
        dt = self.from_unix(timestamp, region)
        return dt.strftime(format_str)
