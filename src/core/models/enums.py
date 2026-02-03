"""
Core enums for the Gacha Timer Bot.

This module defines enumerations for categories, profiles, regions, and other constants
used throughout the application.
"""

from enum import Enum
from typing import Optional


class GameProfile(str, Enum):
    """Supported game profiles."""
    HSR = "HSR"  # Honkai: Star Rail
    ZZZ = "ZZZ"  # Zenless Zone Zero
    AK = "AK"    # Arknights
    STRI = "STRI"  # Strinova
    WUWA = "WUWA"  # Wuthering Waves
    UMA = "UMA"   # Uma Musume

    @classmethod
    def all_profiles(cls) -> list[str]:
        """Get list of all profile codes."""
        return [profile.value for profile in cls]

    @classmethod
    def from_string(cls, value: str) -> Optional['GameProfile']:
        """Convert string to GameProfile enum (case-insensitive)."""
        try:
            return cls[value.upper()]
        except KeyError:
            return None


class EventCategory(str, Enum):
    """Event category types."""
    BANNER = "Banner"
    EVENT = "Event"
    MAINTENANCE = "Maintenance"
    OFFER = "Offer"

    # Uma Musume specific categories
    CHARACTER_BANNER = "Character Banner"
    SUPPORT_BANNER = "Support Banner"
    PAID_BANNER = "Paid Banner"
    STORY_EVENT = "Story Event"
    CHAMPIONS_MEETING = "Champions Meeting"
    LEGEND_RACE = "Legend Race"

    @classmethod
    def uma_categories(cls) -> list[str]:
        """Get Uma Musume specific categories."""
        return [
            cls.CHARACTER_BANNER.value,
            cls.SUPPORT_BANNER.value,
            cls.PAID_BANNER.value,
            cls.STORY_EVENT.value,
            cls.CHAMPIONS_MEETING.value,
            cls.LEGEND_RACE.value,
        ]

    @classmethod
    def standard_categories(cls) -> list[str]:
        """Get standard categories (non-Uma specific)."""
        return [
            cls.BANNER.value,
            cls.EVENT.value,
            cls.MAINTENANCE.value,
            cls.OFFER.value,
        ]


class Region(str, Enum):
    """Server regions for Hoyoverse games."""
    ASIA = "ASIA"
    AMERICA = "AMERICA"
    EUROPE = "EUROPE"

    @classmethod
    def all_regions(cls) -> list[str]:
        """Get list of all regions."""
        return [region.value for region in cls]


class NotificationTimingType(str, Enum):
    """Types of notification timings."""
    # Standard timings
    REMINDER = "reminder"
    START_1H = "start_1h"
    START_3H = "start_3h"
    START_24H = "start_24h"
    END_1H = "end_1h"
    END_3H = "end_3h"
    END_24H = "end_24h"
    END_25H = "end_25h"

    # Uma Musume Champions Meeting phases
    CHAMPIONS_REGISTRATION_START = "champions_registration_start"
    CHAMPIONS_ROUND1_START = "champions_round1_start"
    CHAMPIONS_ROUND2_START = "champions_round2_start"
    CHAMPIONS_FINAL_REGISTRATION_START = "champions_final_registration_start"
    CHAMPIONS_FINALS_START = "champions_finals_start"
    CHAMPIONS_END = "champions_end"
    CHAMPIONS_REMINDER = "champions_reminder"

    # Uma Musume Legend Race
    LEGEND_RACE_CHARACTER_START = "legend_race_character_start"
    LEGEND_RACE_END = "legend_race_end"
    LEGEND_RACE_REMINDER = "legend_race_reminder"


class HoyoverseGame(str, Enum):
    """Games published by Hoyoverse that use triple timezone display."""
    HSR = "HSR"
    ZZZ = "ZZZ"
    WUWA = "WUWA"

    @classmethod
    def is_hoyoverse(cls, profile: str) -> bool:
        """Check if a profile is a Hoyoverse game."""
        try:
            cls(profile)
            return True
        except ValueError:
            return False
