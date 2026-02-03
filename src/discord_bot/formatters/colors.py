"""
Color definitions for Discord embeds.

Centralizes all color mappings used throughout the bot for consistency.
"""

import discord
from typing import Optional

from ...core.models import GameProfile, EventCategory


# Profile colors (game-specific colors)
PROFILE_COLORS = {
    "AK": discord.Color.teal(),
    "HSR": discord.Color.fuchsia(),
    "ZZZ": discord.Color.yellow(),
    "STRI": discord.Color.orange(),
    "WUWA": discord.Color.green(),
    "UMA": discord.Color.purple(),
}

# Category colors (event type colors)
CATEGORY_COLORS = {
    "Banner": discord.Color.blue(),
    "Event": discord.Color.gold(),
    "Maintenance": discord.Color.green(),
    "Offer": discord.Color.fuchsia(),
    "Ended": discord.Color.red(),
    # Uma Musume specific
    "Character Banner": discord.Color.blue(),
    "Support Banner": discord.Color.green(),
    "Paid Banner": discord.Color.orange(),
    "Story Event": discord.Color.gold(),
    "Champions Meeting": discord.Color.purple(),
    "Legend Race": discord.Color.magenta(),
    "Selection Gacha": discord.Color.teal(),
}

# Default color when no match is found
DEFAULT_COLOR = discord.Color.blurple()


def get_profile_color(profile: str) -> discord.Color:
    """
    Get the color associated with a game profile.

    Args:
        profile: Game profile (e.g., "HSR", "UMA")

    Returns:
        Discord color for the profile
    """
    return PROFILE_COLORS.get(profile.upper(), DEFAULT_COLOR)


def get_category_color(category: str) -> discord.Color:
    """
    Get the color associated with an event category.

    Args:
        category: Event category (e.g., "Banner", "Event")

    Returns:
        Discord color for the category
    """
    return CATEGORY_COLORS.get(category, DEFAULT_COLOR)


def get_event_color(
    category: str,
    profile: Optional[str] = None,
    title: Optional[str] = None
) -> discord.Color:
    """
    Get the appropriate color for an event based on category, profile, and title.

    This implements the smart color logic used in the old code:
    - First checks for category-specific color
    - Falls back to profile color
    - Uses title hints for Uma Musume events

    Args:
        category: Event category
        profile: Game profile (optional)
        title: Event title for additional context (optional)

    Returns:
        Appropriate Discord color
    """
    # Special handling for Uma Musume based on title keywords
    if profile and profile.upper() == "UMA" and title:
        title_lower = title.lower()

        if "paid" in title_lower:
            return discord.Color.orange()
        elif "support" in title_lower:
            return discord.Color.green()
        elif "character" in title_lower or "banner" in title_lower:
            return discord.Color.blue()
        elif "champions meeting" in title_lower:
            return discord.Color.purple()
        elif "legend race" in title_lower:
            return discord.Color.magenta()
        elif "story" in title_lower:
            return discord.Color.gold()

    # Check category color
    if category in CATEGORY_COLORS:
        return CATEGORY_COLORS[category]

    # Fall back to profile color
    if profile:
        return get_profile_color(profile)

    return DEFAULT_COLOR


def get_notification_color(
    profile: str,
    category: str,
    is_ending: bool = False
) -> discord.Color:
    """
    Get color for notification embeds.

    Args:
        profile: Game profile
        category: Event category
        is_ending: Whether this is an "ending" notification (use warning color)

    Returns:
        Discord color
    """
    if is_ending:
        # Use orange/red tint for ending notifications
        return discord.Color.orange()

    # Use profile color for consistency
    return get_profile_color(profile)
