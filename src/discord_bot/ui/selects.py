"""
Discord Select Menu components for the bot.

Provides reusable select menus for categories, timezones, etc.
"""

import discord
from typing import Callable, Optional, List, Any


class CategorySelect(discord.ui.Select):
    """
    Select menu for choosing event categories.

    Standard categories: Banner, Event, Maintenance, Offer
    """

    STANDARD_CATEGORIES = [
        ("Banner", "Limited-time character or item banner"),
        ("Event", "In-game event with rewards or story"),
        ("Maintenance", "Scheduled server maintenance"),
        ("Offer", "Limited-time shop offer or pack"),
    ]

    UMA_CATEGORIES = [
        ("Character Banner", "Character gacha banner"),
        ("Support Banner", "Support card gacha banner"),
        ("Paid Banner", "Paid-only gacha banner"),
        ("Story Event", "Story event with rewards"),
        ("Champions Meeting", "Competitive PvP event"),
        ("Legend Race", "Special character rotation event"),
        ("Selection Gacha", "Select ticket gacha"),
    ]

    def __init__(
        self,
        profile: str = "HSR",
        current_category: Optional[str] = None,
        callback: Optional[Callable] = None
    ):
        """
        Initialize the category select menu.

        Args:
            profile: Game profile (affects available categories)
            current_category: Currently selected category (for defaults)
            callback: Optional callback to override default
        """
        self.profile = profile.upper()
        self._custom_callback = callback

        # Choose categories based on profile
        if self.profile == "UMA":
            categories = self.UMA_CATEGORIES
        else:
            categories = self.STANDARD_CATEGORIES

        options = [
            discord.SelectOption(
                label=cat_name,
                value=cat_name,
                description=cat_desc,
                default=(current_category == cat_name)
            )
            for cat_name, cat_desc in categories
        ]

        super().__init__(
            placeholder="Select category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        if self._custom_callback:
            await self._custom_callback(interaction, self.values[0])
        else:
            await interaction.response.defer()


class TimezoneSelect(discord.ui.Select):
    """
    Select menu for choosing timezones.
    """

    TIMEZONES = [
        ("UTC", "UTC (GMT+0)", "Coordinated Universal Time"),
        ("UTC-7", "UTC-7 (PDT)", "Pacific Daylight Time"),
        ("America/New_York", "America/New_York (EDT)", "Eastern Time"),
        ("Europe/London", "Europe/London (BST)", "British Summer Time"),
        ("Europe/Berlin", "Europe/Berlin (CEST)", "Central European Time"),
        ("Asia/Tokyo", "Asia/Tokyo (JST)", "Japan Standard Time"),
        ("Asia/Shanghai", "Asia/Shanghai (CST)", "China Standard Time"),
        ("Asia/Seoul", "Asia/Seoul (KST)", "Korea Standard Time"),
    ]

    def __init__(
        self,
        current_timezone: Optional[str] = None,
        callback: Optional[Callable] = None
    ):
        """
        Initialize the timezone select menu.

        Args:
            current_timezone: Currently selected timezone
            callback: Optional callback to override default
        """
        self._custom_callback = callback

        options = [
            discord.SelectOption(
                label=tz_label,
                value=tz_value,
                description=tz_desc,
                default=(current_timezone == tz_value)
            )
            for tz_value, tz_label, tz_desc in self.TIMEZONES
        ]

        super().__init__(
            placeholder="Select timezone...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="timezone_select"
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        if self._custom_callback:
            await self._custom_callback(interaction, self.values[0])
        else:
            await interaction.response.defer()


class ProfileSelect(discord.ui.Select):
    """
    Select menu for choosing game profiles.
    """

    PROFILES = [
        ("HSR", "Honkai: Star Rail", "Hoyoverse turn-based RPG"),
        ("ZZZ", "Zenless Zone Zero", "Hoyoverse action game"),
        ("WUWA", "Wuthering Waves", "Kuro Games action RPG"),
        ("AK", "Arknights", "Tower defense gacha game"),
        ("STRI", "Strinova", "Anime-style shooter"),
        ("UMA", "Uma Musume", "Horse girl training game"),
    ]

    def __init__(
        self,
        current_profile: Optional[str] = None,
        callback: Optional[Callable] = None,
        exclude: Optional[List[str]] = None
    ):
        """
        Initialize the profile select menu.

        Args:
            current_profile: Currently selected profile
            callback: Optional callback to override default
            exclude: List of profiles to exclude from options
        """
        self._custom_callback = callback
        exclude = exclude or []

        options = [
            discord.SelectOption(
                label=profile_code,
                value=profile_code,
                description=f"{profile_name} - {profile_desc}",
                default=(current_profile == profile_code)
            )
            for profile_code, profile_name, profile_desc in self.PROFILES
            if profile_code not in exclude
        ]

        super().__init__(
            placeholder="Select game...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="profile_select"
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        if self._custom_callback:
            await self._custom_callback(interaction, self.values[0])
        else:
            await interaction.response.defer()


class RegionSelect(discord.ui.Select):
    """
    Select menu for choosing server regions (HYV games).
    """

    REGIONS = [
        ("ASIA", "Asia Server", "UTC+8 (China Standard Time)"),
        ("AMERICA", "America Server", "UTC-5 (Eastern Time)"),
        ("EUROPE", "Europe Server", "UTC+1 (Central European Time)"),
    ]

    def __init__(
        self,
        current_region: Optional[str] = None,
        callback: Optional[Callable] = None
    ):
        """
        Initialize the region select menu.

        Args:
            current_region: Currently selected region
            callback: Optional callback to override default
        """
        self._custom_callback = callback

        options = [
            discord.SelectOption(
                label=region_label,
                value=region_code,
                description=region_desc,
                default=(current_region == region_code)
            )
            for region_code, region_label, region_desc in self.REGIONS
        ]

        super().__init__(
            placeholder="Select region...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="region_select"
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        if self._custom_callback:
            await self._custom_callback(interaction, self.values[0])
        else:
            await interaction.response.defer()


class EventSelect(discord.ui.Select):
    """
    Dynamic select menu for choosing from a list of events.
    """

    def __init__(
        self,
        events: List[dict],
        placeholder: str = "Select event...",
        callback: Optional[Callable] = None
    ):
        """
        Initialize the event select menu.

        Args:
            events: List of event dicts with 'id', 'title', 'category' keys
            placeholder: Placeholder text
            callback: Optional callback to override default
        """
        self._custom_callback = callback

        options = []
        for event in events[:25]:  # Discord limit
            options.append(discord.SelectOption(
                label=event.get("title", "Unknown")[:100],
                value=str(event.get("id", "")),
                description=event.get("category", "")[:100]
            ))

        if not options:
            options.append(discord.SelectOption(
                label="No events available",
                value="none",
                description="No events to select"
            ))

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            custom_id="event_select"
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        if self._custom_callback:
            await self._custom_callback(interaction, self.values[0])
        else:
            await interaction.response.defer()
