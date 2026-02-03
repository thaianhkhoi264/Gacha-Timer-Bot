"""
Embed builders for Discord messages.

Provides factory functions for creating consistent Discord embeds.
"""

import discord
from typing import List, Optional, Dict, Any

from ...core.models import Event, Notification
from .colors import get_event_color, get_profile_color, get_notification_color
from .emojis import get_profile_emoji, get_region_emoji, get_category_emoji
from .timestamps import (
    format_timestamp_full,
    format_timestamp_relative,
    format_timestamp_dual,
    format_event_times,
    format_hyv_regional_times,
    format_notification_time,
)


class EmbedBuilder:
    """
    Builder class for creating Discord embeds with consistent styling.

    Usage:
        embed = EmbedBuilder() \
            .set_title("Event Name") \
            .set_color_for_event("Banner", "HSR") \
            .add_time_field("Start", start_unix) \
            .build()
    """

    def __init__(self):
        """Initialize a new embed builder."""
        self._title: Optional[str] = None
        self._description: Optional[str] = None
        self._color: discord.Color = discord.Color.blurple()
        self._fields: List[Dict[str, Any]] = []
        self._image_url: Optional[str] = None
        self._thumbnail_url: Optional[str] = None
        self._footer_text: Optional[str] = None
        self._footer_icon: Optional[str] = None
        self._author_name: Optional[str] = None
        self._author_icon: Optional[str] = None

    def set_title(self, title: str) -> 'EmbedBuilder':
        """Set the embed title."""
        self._title = title
        return self

    def set_description(self, description: str) -> 'EmbedBuilder':
        """Set the embed description."""
        self._description = description
        return self

    def set_color(self, color: discord.Color) -> 'EmbedBuilder':
        """Set the embed color directly."""
        self._color = color
        return self

    def set_color_for_event(
        self,
        category: str,
        profile: Optional[str] = None,
        title: Optional[str] = None
    ) -> 'EmbedBuilder':
        """Set color based on event category/profile."""
        self._color = get_event_color(category, profile, title)
        return self

    def set_color_for_profile(self, profile: str) -> 'EmbedBuilder':
        """Set color based on game profile."""
        self._color = get_profile_color(profile)
        return self

    def add_field(
        self,
        name: str,
        value: str,
        inline: bool = False
    ) -> 'EmbedBuilder':
        """Add a field to the embed."""
        self._fields.append({
            "name": name,
            "value": value,
            "inline": inline
        })
        return self

    def add_time_field(
        self,
        label: str,
        unix_time: int,
        include_relative: bool = True,
        inline: bool = False
    ) -> 'EmbedBuilder':
        """Add a formatted timestamp field."""
        if include_relative:
            value = format_timestamp_dual(unix_time)
        else:
            value = format_timestamp_full(unix_time)

        return self.add_field(label, value, inline)

    def set_image(self, url: str) -> 'EmbedBuilder':
        """Set the embed image."""
        if url and url.startswith("http"):
            self._image_url = url
        return self

    def set_thumbnail(self, url: str) -> 'EmbedBuilder':
        """Set the embed thumbnail."""
        if url and url.startswith("http"):
            self._thumbnail_url = url
        return self

    def set_footer(
        self,
        text: str,
        icon_url: Optional[str] = None
    ) -> 'EmbedBuilder':
        """Set the embed footer."""
        self._footer_text = text
        self._footer_icon = icon_url
        return self

    def set_author(
        self,
        name: str,
        icon_url: Optional[str] = None
    ) -> 'EmbedBuilder':
        """Set the embed author."""
        self._author_name = name
        self._author_icon = icon_url
        return self

    def build(self) -> discord.Embed:
        """Build and return the Discord embed."""
        embed = discord.Embed(
            title=self._title,
            description=self._description,
            color=self._color
        )

        for field in self._fields:
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field["inline"]
            )

        if self._image_url:
            embed.set_image(url=self._image_url)

        if self._thumbnail_url:
            embed.set_thumbnail(url=self._thumbnail_url)

        if self._footer_text:
            embed.set_footer(text=self._footer_text, icon_url=self._footer_icon)

        if self._author_name:
            embed.set_author(name=self._author_name, icon_url=self._author_icon)

        return embed


# =============================================================================
# Factory Functions for Common Embed Types
# =============================================================================

def create_event_embed(
    event: Event,
    include_image: bool = True
) -> discord.Embed:
    """
    Create an embed for displaying an event.

    Args:
        event: Event model
        include_image: Whether to include the event image

    Returns:
        Discord embed
    """
    builder = EmbedBuilder() \
        .set_title(event.title) \
        .set_color_for_event(event.category, event.profile, event.title)

    # Check if this is an HYV game with regional times
    is_hyv = event.profile.upper() in ("HSR", "ZZZ", "WUWA")
    has_regional = all([
        event.asia_start, event.asia_end,
        event.america_start, event.america_end,
        event.europe_start, event.europe_end
    ])

    if is_hyv and has_regional:
        description = format_hyv_regional_times(
            event.asia_start, event.asia_end,
            event.america_start, event.america_end,
            event.europe_start, event.europe_end
        )
    else:
        description = format_event_times(event.start_date, event.end_date)

    builder.set_description(description)

    if include_image and event.image:
        builder.set_image(event.image)

    return builder.build()


def create_event_embed_simple(
    title: str,
    start_unix: int,
    end_unix: int,
    category: str,
    profile: str,
    image_url: Optional[str] = None
) -> discord.Embed:
    """
    Create a simple event embed from raw values.

    Args:
        title: Event title
        start_unix: Start UNIX timestamp
        end_unix: End UNIX timestamp
        category: Event category
        profile: Game profile
        image_url: Optional image URL

    Returns:
        Discord embed
    """
    builder = EmbedBuilder() \
        .set_title(title) \
        .set_color_for_event(category, profile, title) \
        .set_description(format_event_times(start_unix, end_unix))

    if image_url:
        builder.set_image(image_url)

    return builder.build()


def create_hyv_event_embed(
    title: str,
    category: str,
    profile: str,
    asia_start: int,
    asia_end: int,
    america_start: int,
    america_end: int,
    europe_start: int,
    europe_end: int,
    image_url: Optional[str] = None
) -> discord.Embed:
    """
    Create an embed for Hoyoverse game events with regional times.

    Args:
        title: Event title
        category: Event category
        profile: Game profile (HSR, ZZZ, WUWA)
        asia_start/end: Asia server times
        america_start/end: America server times
        europe_start/end: Europe server times
        image_url: Optional image URL

    Returns:
        Discord embed
    """
    builder = EmbedBuilder() \
        .set_title(title) \
        .set_color_for_event(category, profile, title) \
        .set_description(format_hyv_regional_times(
            asia_start, asia_end,
            america_start, america_end,
            europe_start, europe_end
        ))

    if image_url:
        builder.set_image(image_url)

    return builder.build()


def create_notification_embed(
    notification: Notification,
    event_title: Optional[str] = None
) -> discord.Embed:
    """
    Create an embed for a notification.

    Args:
        notification: Notification model
        event_title: Override title (uses notification.title if not provided)

    Returns:
        Discord embed
    """
    title = event_title or notification.title
    is_ending = "end" in notification.timing_type.lower()

    builder = EmbedBuilder() \
        .set_title(title) \
        .set_color(get_notification_color(
            notification.profile,
            notification.category,
            is_ending
        ))

    # Build description
    timing_desc = format_notification_time(
        notification.notify_unix,
        notification.event_time_unix,
        notification.timing_type
    )

    parts = [f"**{notification.category}** notification"]

    if notification.region:
        region_emoji = get_region_emoji(notification.region)
        parts.append(f"Region: {region_emoji} {notification.region}")

    parts.append(f"Event time: {format_timestamp_full(notification.event_time_unix)}")
    parts.append(f"({timing_desc})")

    if notification.phase:
        parts.append(f"Phase: **{notification.phase}**")

    if notification.character_name:
        parts.append(f"Character: **{notification.character_name}**")

    builder.set_description("\n".join(parts))

    return builder.build()


def create_pending_notifications_embed(
    profile: str,
    notifications: List[Dict[str, str]],
    page: int = 1,
    total_pages: int = 1
) -> discord.Embed:
    """
    Create an embed showing pending notifications.

    Args:
        profile: Game profile
        notifications: List of notification field dicts with 'name' and 'value'
        page: Current page number
        total_pages: Total number of pages

    Returns:
        Discord embed
    """
    title = f"Pending Notifications: {profile}"
    if total_pages > 1:
        title += f" (Page {page}/{total_pages})"

    builder = EmbedBuilder() \
        .set_title(title) \
        .set_color_for_profile(profile)

    if not notifications:
        builder.set_description("No pending notifications.")
    else:
        builder.set_description(f"All upcoming scheduled notifications for {profile}.")
        for field in notifications:
            builder.add_field(field["name"], field["value"], inline=False)

    return builder.build()


def create_help_embed(
    title: str = "Bot Help",
    description: str = "Here are all available commands:"
) -> discord.Embed:
    """
    Create a help embed.

    Args:
        title: Help embed title
        description: Help embed description

    Returns:
        Discord embed (add fields separately)
    """
    return EmbedBuilder() \
        .set_title(title) \
        .set_description(description) \
        .set_color(discord.Color.blurple()) \
        .build()


def create_error_embed(
    title: str = "Error",
    description: str = "An error occurred."
) -> discord.Embed:
    """
    Create an error embed.

    Args:
        title: Error title
        description: Error description

    Returns:
        Discord embed
    """
    return EmbedBuilder() \
        .set_title(title) \
        .set_description(description) \
        .set_color(discord.Color.red()) \
        .build()


def create_success_embed(
    title: str = "Success",
    description: str = "Operation completed successfully."
) -> discord.Embed:
    """
    Create a success embed.

    Args:
        title: Success title
        description: Success description

    Returns:
        Discord embed
    """
    return EmbedBuilder() \
        .set_title(title) \
        .set_description(description) \
        .set_color(discord.Color.green()) \
        .build()
