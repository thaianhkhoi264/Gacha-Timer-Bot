"""
Event entity model for the Gacha Timer Bot.

This module defines the Event dataclass that represents a game event with all its properties.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import EventCategory, GameProfile, Region


@dataclass
class Event:
    """
    Represents a game event (banner, event, maintenance, offer, etc.).

    Attributes:
        id: Database ID (None for new events)
        user_id: Discord user ID who created the event
        server_id: Discord server ID
        title: Event name/title
        start_date: Event start timestamp (UNIX)
        end_date: Event end timestamp (UNIX)
        image: URL to event image
        category: Event category (Banner/Event/Maintenance/Offer)
        profile: Game profile (HSR/ZZZ/AK/STRI/WUWA/UMA)
        is_hyv: Whether this is a Hoyoverse game event (uses regional timings)

        # Regional timings (Hoyoverse games only)
        asia_start: Asia server start timestamp (UNIX)
        asia_end: Asia server end timestamp (UNIX)
        america_start: America server start timestamp (UNIX)
        america_end: America server end timestamp (UNIX)
        europe_start: Europe server start timestamp (UNIX)
        europe_end: Europe server end timestamp (UNIX)
    """

    # Required fields
    title: str
    start_date: int  # UNIX timestamp
    end_date: int    # UNIX timestamp
    category: str    # EventCategory value
    profile: str     # GameProfile value

    # Optional fields with defaults
    id: Optional[int] = None
    user_id: Optional[str] = None
    server_id: Optional[str] = None
    image: Optional[str] = None
    is_hyv: bool = False

    # Regional timings (Hoyoverse games)
    asia_start: Optional[int] = None
    asia_end: Optional[int] = None
    america_start: Optional[int] = None
    america_end: Optional[int] = None
    europe_start: Optional[int] = None
    europe_end: Optional[int] = None

    def __post_init__(self):
        """Validate event data after initialization."""
        # Validate profile
        if self.profile not in GameProfile.all_profiles():
            raise ValueError(f"Invalid profile: {self.profile}")

        # Validate timestamps
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")

        # Check if this is a Hoyoverse game
        from .enums import HoyoverseGame
        self.is_hyv = HoyoverseGame.is_hoyoverse(self.profile)

    def is_ongoing(self, current_time: Optional[int] = None) -> bool:
        """
        Check if the event is currently ongoing.

        Args:
            current_time: UNIX timestamp to check against (defaults to now)

        Returns:
            True if event is ongoing, False otherwise
        """
        if current_time is None:
            current_time = int(datetime.now().timestamp())

        return self.start_date <= current_time < self.end_date

    def is_upcoming(self, current_time: Optional[int] = None) -> bool:
        """
        Check if the event is upcoming (hasn't started yet).

        Args:
            current_time: UNIX timestamp to check against (defaults to now)

        Returns:
            True if event is upcoming, False otherwise
        """
        if current_time is None:
            current_time = int(datetime.now().timestamp())

        return current_time < self.start_date

    def is_expired(self, current_time: Optional[int] = None) -> bool:
        """
        Check if the event has ended.

        Args:
            current_time: UNIX timestamp to check against (defaults to now)

        Returns:
            True if event has ended, False otherwise
        """
        if current_time is None:
            current_time = int(datetime.now().timestamp())

        return current_time >= self.end_date

    def get_regional_start(self, region: str) -> Optional[int]:
        """
        Get the start timestamp for a specific region.

        Args:
            region: Region name (ASIA/AMERICA/EUROPE)

        Returns:
            Regional start timestamp, or None if not a Hoyoverse game
        """
        if not self.is_hyv:
            return self.start_date

        region = region.upper()
        if region == Region.ASIA.value:
            return self.asia_start
        elif region == Region.AMERICA.value:
            return self.america_start
        elif region == Region.EUROPE.value:
            return self.europe_start
        else:
            return self.start_date

    def get_regional_end(self, region: str) -> Optional[int]:
        """
        Get the end timestamp for a specific region.

        Args:
            region: Region name (ASIA/AMERICA/EUROPE)

        Returns:
            Regional end timestamp, or None if not a Hoyoverse game
        """
        if not self.is_hyv:
            return self.end_date

        region = region.upper()
        if region == Region.ASIA.value:
            return self.asia_end
        elif region == Region.AMERICA.value:
            return self.america_end
        elif region == Region.EUROPE.value:
            return self.europe_end
        else:
            return self.end_date

    def to_dict(self) -> dict:
        """Convert event to dictionary for database storage."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'server_id': self.server_id,
            'title': self.title,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'image': self.image,
            'category': self.category,
            'profile': self.profile,
            'is_hyv': int(self.is_hyv),
            'asia_start': self.asia_start,
            'asia_end': self.asia_end,
            'america_start': self.america_start,
            'america_end': self.america_end,
            'europe_start': self.europe_start,
            'europe_end': self.europe_end,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Event':
        """Create Event instance from dictionary."""
        return cls(
            id=data.get('id'),
            user_id=data.get('user_id'),
            server_id=data.get('server_id'),
            title=data['title'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            image=data.get('image'),
            category=data['category'],
            profile=data['profile'],
            is_hyv=bool(data.get('is_hyv', 0)),
            asia_start=data.get('asia_start'),
            asia_end=data.get('asia_end'),
            america_start=data.get('america_start'),
            america_end=data.get('america_end'),
            europe_start=data.get('europe_start'),
            europe_end=data.get('europe_end'),
        )

    @classmethod
    def from_db_row(cls, row: tuple) -> 'Event':
        """
        Create Event instance from database row.

        Args:
            row: Database row tuple (id, user_id, server_id, title, ...)

        Returns:
            Event instance
        """
        # Assuming standard column order from user_data table
        return cls(
            id=row[0],
            user_id=row[1],
            server_id=row[2],
            title=row[3],
            start_date=row[4],
            end_date=row[5],
            image=row[6],
            category=row[7],
            is_hyv=bool(row[8]) if len(row) > 8 else False,
            asia_start=row[9] if len(row) > 9 else None,
            asia_end=row[10] if len(row) > 10 else None,
            america_start=row[11] if len(row) > 11 else None,
            america_end=row[12] if len(row) > 12 else None,
            europe_start=row[13] if len(row) > 13 else None,
            europe_end=row[14] if len(row) > 14 else None,
            profile=row[15] if len(row) > 15 else "Unknown",
        )
