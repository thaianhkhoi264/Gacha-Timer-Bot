"""
Generic game module for games without specialized handling.

This module provides a GenericGameModule for games that follow standard
patterns and don't need specialized scraping or event handling:
- ZZZ (Zenless Zone Zero) - Hoyoverse game with regional servers
- STRI (Strinova) - Standard event tracking
- WUWA (Wuthering Waves) - Standard event tracking

These games use the same event structure and notification patterns
as the core system.
"""

import discord
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import pytz
import dateparser
import aiosqlite

from src.games.base import GameConfig, GameModule, HoyoverseGameModule


# =============================================================================
# Generic Repository
# =============================================================================

class GenericEventRepository:
    """
    Generic event repository for games without specialized database needs.

    Works with the standard events table schema.
    """

    def __init__(self, db_path: str, profile: str, has_regional: bool = False):
        """
        Initialize the repository.

        Args:
            db_path: Path to the SQLite database
            profile: Game profile name (e.g., "STRI", "WUWA")
            has_regional: Whether this game has regional servers
        """
        self.db_path = db_path
        self.profile = profile
        self.has_regional = has_regional

    async def initialize(self):
        """Create the events table if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as conn:
            if self.has_regional:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        title TEXT UNIQUE,
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
            else:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        title TEXT UNIQUE,
                        start_date TEXT,
                        end_date TEXT,
                        image TEXT,
                        category TEXT,
                        profile TEXT
                    )
                ''')
            await conn.commit()

    async def get_all_events(self) -> List[Dict[str, Any]]:
        """Get all events for this profile."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM events WHERE profile = ?",
                (self.profile,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_event_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Get an event by its title."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM events WHERE title = ? AND profile = ?",
                (title, self.profile)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def create_event(self, event_data: Dict[str, Any]) -> int:
        """
        Create a new event.

        Args:
            event_data: Dictionary with event fields

        Returns:
            The ID of the newly created event
        """
        async with aiosqlite.connect(self.db_path) as conn:
            if self.has_regional:
                cursor = await conn.execute(
                    """INSERT INTO events
                    (user_id, title, start_date, end_date, image, category, profile,
                     asia_start, asia_end, america_start, america_end, europe_start, europe_end)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_data.get('user_id', ''),
                        event_data['title'],
                        event_data.get('start_date', ''),
                        event_data.get('end_date', ''),
                        event_data.get('image', ''),
                        event_data.get('category', 'Event'),
                        self.profile,
                        event_data.get('asia_start', ''),
                        event_data.get('asia_end', ''),
                        event_data.get('america_start', ''),
                        event_data.get('america_end', ''),
                        event_data.get('europe_start', ''),
                        event_data.get('europe_end', ''),
                    )
                )
            else:
                cursor = await conn.execute(
                    """INSERT INTO events
                    (user_id, title, start_date, end_date, image, category, profile)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_data.get('user_id', ''),
                        event_data['title'],
                        event_data.get('start_date', ''),
                        event_data.get('end_date', ''),
                        event_data.get('image', ''),
                        event_data.get('category', 'Event'),
                        self.profile,
                    )
                )
            await conn.commit()
            return cursor.lastrowid

    async def delete_event(self, title: str) -> bool:
        """
        Delete an event by title.

        Returns:
            True if event was deleted, False if not found
        """
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM events WHERE title = ? AND profile = ?",
                (title, self.profile)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def update_event(self, title: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing event.

        Args:
            title: Title of the event to update
            updates: Dictionary of fields to update

        Returns:
            True if event was updated, False if not found
        """
        if not updates:
            return False

        set_clause = ", ".join(f"{key} = ?" for key in updates.keys())
        values = list(updates.values()) + [title, self.profile]

        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                f"UPDATE events SET {set_clause} WHERE title = ? AND profile = ?",
                values
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def generate_unique_title(self, base_title: str) -> str:
        """Generate a unique title by appending a number if needed."""
        async with aiosqlite.connect(self.db_path) as conn:
            new_title = base_title
            suffix = 1
            while True:
                async with conn.execute(
                    "SELECT COUNT(*) FROM events WHERE title = ? AND profile = ?",
                    (new_title, self.profile)
                ) as cursor:
                    count = (await cursor.fetchone())[0]
                if count == 0:
                    break
                suffix += 1
                new_title = f"{base_title} {suffix}"
            return new_title


# =============================================================================
# Generic Game Module
# =============================================================================

class GenericGameModule(GameModule):
    """
    Generic game module for games without specialized handling.

    Suitable for games like STRI (Strinova) that follow standard patterns.
    """

    # Default notification timings (minutes before event)
    DEFAULT_TIMINGS = {
        "Banner": {
            "start": [1440, 180, 60],      # 24h, 3h, 1h before
            "end": [1500, 1440, 180, 60],  # 25h, 24h, 3h, 1h before
        },
        "Event": {
            "start": [1440, 180, 60],
            "end": [1500, 1440, 180, 60],
        },
        "Maintenance": {
            "start": [180, 60],
            "end": [],
        },
        "Offer": {
            "start": [180, 60],
            "end": [180, 60],
        },
    }

    def __init__(
        self,
        profile: str,
        display_name: str,
        db_path: str = None,
        ongoing_channel_id: int = None,
        upcoming_channel_id: int = None,
        main_server_id: int = None,
    ):
        """
        Initialize the generic game module.

        Args:
            profile: Game profile code (e.g., "STRI", "WUWA")
            display_name: Human-readable game name
            db_path: Path to database (defaults to data/{profile.lower()}_data.db)
            ongoing_channel_id: Channel ID for ongoing events
            upcoming_channel_id: Channel ID for upcoming events
            main_server_id: Main Discord server ID
        """
        config = GameConfig(
            profile=profile,
            db_path=db_path or f"data/{profile.lower()}_data.db",
            log_name=profile.lower(),
            display_name=display_name,
            has_regional_servers=False,
            update_interval_hours=6,
        )
        super().__init__(config)

        self.repository = GenericEventRepository(config.db_path, profile)
        self.ongoing_channel_id = ongoing_channel_id
        self.upcoming_channel_id = upcoming_channel_id
        self.main_server_id = main_server_id

    async def initialize(self):
        """Initialize the module."""
        await self.repository.initialize()
        self.logger.info(f"{self.profile} module initialized")

    async def refresh_events(self):
        """Refresh events (no-op for generic module)."""
        self.logger.info(f"Refreshing {self.profile} events")

    async def update_dashboard(self, guild, region: Optional[str] = None):
        """Update the event dashboard."""
        if not guild:
            return

        now = int(datetime.now(timezone.utc).timestamp())
        ongoing_channel = guild.get_channel(self.ongoing_channel_id) if self.ongoing_channel_id else None
        upcoming_channel = guild.get_channel(self.upcoming_channel_id) if self.upcoming_channel_id else None

        events = await self.repository.get_all_events()

        ongoing_events = []
        upcoming_events = []

        for event in events:
            start_ts = int(event.get('start_date') or 0)
            end_ts = int(event.get('end_date') or 0)

            if start_ts <= now < end_ts:
                ongoing_events.append(event)
            elif start_ts > now:
                upcoming_events.append(event)

        # Sort events
        ongoing_events.sort(key=lambda e: int(e.get('end_date') or 0))
        upcoming_events.sort(key=lambda e: int(e.get('start_date') or 0))

        # Update ongoing channel
        if ongoing_channel:
            await self._update_channel_embeds(ongoing_channel, ongoing_events, "ongoing")

        # Update upcoming channel
        if upcoming_channel:
            await self._update_channel_embeds(upcoming_channel, upcoming_events, "upcoming")

    async def _update_channel_embeds(
        self,
        channel: discord.TextChannel,
        events: List[Dict[str, Any]],
        event_type: str,
    ):
        """Update embeds in a channel."""
        try:
            # Clear existing bot messages
            async for message in channel.history(limit=50):
                if message.author.bot:
                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass
                    await asyncio.sleep(0.5)

            if not events:
                embed = discord.Embed(
                    title=f"No {event_type.title()} Events",
                    description=f"There are no {event_type} events at this time.",
                    color=discord.Color.greyple(),
                )
                await channel.send(embed=embed)
                return

            # Send embeds for each event
            for event in events:
                embed = self._create_event_embed(event, event_type)
                await channel.send(embed=embed)
                await asyncio.sleep(0.5)

        except discord.HTTPException as e:
            self.logger.error(f"Failed to update {event_type} channel: {e}")

    def _create_event_embed(
        self,
        event: Dict[str, Any],
        event_type: str,
    ) -> discord.Embed:
        """Create an embed for an event."""
        category = event.get('category', 'Event')

        # Category colors
        colors = {
            "Banner": 0x5BCEFA,
            "Event": 0xF7BA0B,
            "Maintenance": 0xFF6B6B if event_type == "ongoing" else 0x57F287,
            "Offer": 0xFF00FF,
        }
        color = colors.get(category, 0x808080)

        embed = discord.Embed(
            title=event.get('title', 'Unknown Event'),
            color=color,
        )

        start_ts = int(event.get('start_date') or 0)
        end_ts = int(event.get('end_date') or 0)

        if event_type == "ongoing":
            embed.add_field(
                name="Ends",
                value=f"<t:{end_ts}:F>\n<t:{end_ts}:R>",
                inline=False,
            )
        else:
            embed.add_field(
                name="Starts",
                value=f"<t:{start_ts}:F>\n<t:{start_ts}:R>",
                inline=True,
            )
            embed.add_field(
                name="Ends",
                value=f"<t:{end_ts}:F>\n<t:{end_ts}:R>",
                inline=True,
            )

        if event.get('image'):
            embed.set_thumbnail(url=event['image'])

        embed.set_footer(text=f"{self.config.display_name} | {category}")

        return embed

    async def add_event(self, ctx, event_data: Dict[str, Any]):
        """Add a new event."""
        title = await self.repository.generate_unique_title(event_data['title'])
        event_data['title'] = title
        event_data['user_id'] = str(ctx.author.id)

        event_id = await self.repository.create_event(event_data)
        self.logger.info(f"Added event '{title}' (ID: {event_id})")

        return event_id, title

    async def remove_event(self, ctx, title: str):
        """Remove an event by title."""
        success = await self.repository.delete_event(title)
        if success:
            self.logger.info(f"Removed event '{title}'")
        return success

    def get_notification_timings(self, category: str) -> Dict[str, List[int]]:
        """Get notification timings for a category."""
        return self.DEFAULT_TIMINGS.get(category, self.DEFAULT_TIMINGS["Event"])


# =============================================================================
# Hoyoverse Generic Module (for ZZZ)
# =============================================================================

class GenericHoyoverseModule(HoyoverseGameModule):
    """
    Generic module for Hoyoverse games with regional servers.

    Suitable for ZZZ (Zenless Zone Zero) and similar games.
    """

    # Default version configurations
    DEFAULT_VERSIONS = {
        "ZZZ": {
            "version": "2.0",
            "date": datetime(2025, 6, 6, 11, 0, tzinfo=timezone(timedelta(hours=8)))
        }
    }

    # Default notification timings
    DEFAULT_TIMINGS = {
        "Banner": {
            "start": [1440, 180, 60],
            "end": [1500, 1440, 180, 60],
        },
        "Event": {
            "start": [1440, 180, 60],
            "end": [1500, 1440, 180, 60],
        },
        "Maintenance": {
            "start": [180, 60],
            "end": [],
        },
        "Offer": {
            "start": [180, 60],
            "end": [180, 60],
        },
    }

    def __init__(
        self,
        profile: str,
        display_name: str,
        db_path: str = None,
        ongoing_channel_id: int = None,
        upcoming_channel_id: int = None,
        main_server_id: int = None,
    ):
        """
        Initialize the Hoyoverse generic module.

        Args:
            profile: Game profile code (e.g., "ZZZ")
            display_name: Human-readable game name
            db_path: Path to database
            ongoing_channel_id: Channel ID for ongoing events
            upcoming_channel_id: Channel ID for upcoming events
            main_server_id: Main Discord server ID
        """
        config = GameConfig(
            profile=profile,
            db_path=db_path or f"data/{profile.lower()}_data.db",
            log_name=profile.lower(),
            display_name=display_name,
            has_regional_servers=True,
            regions=["ASIA", "NA", "EU"],
            update_interval_hours=6,
        )
        super().__init__(config)

        self.repository = GenericEventRepository(config.db_path, profile, has_regional=True)
        self.ongoing_channel_id = ongoing_channel_id
        self.upcoming_channel_id = upcoming_channel_id
        self.main_server_id = main_server_id

    async def initialize(self):
        """Initialize the module."""
        await self.repository.initialize()
        self.logger.info(f"{self.profile} module initialized")

    async def refresh_events(self):
        """Refresh events (no-op for generic module)."""
        self.logger.info(f"Refreshing {self.profile} events")

    async def update_dashboard(self, guild, region: Optional[str] = None):
        """Update the event dashboard with regional support."""
        if not guild:
            return

        now = int(datetime.now(timezone.utc).timestamp())
        ongoing_channel = guild.get_channel(self.ongoing_channel_id) if self.ongoing_channel_id else None
        upcoming_channel = guild.get_channel(self.upcoming_channel_id) if self.upcoming_channel_id else None

        events = await self.repository.get_all_events()
        regions_to_update = [region] if region else ["ASIA", "NA", "EU"]

        for reg in regions_to_update:
            reg_key = self.REGION_DISPLAY.get(reg, reg).lower()
            start_key = f"{reg_key}_start" if reg_key != "america" else "america_start"
            end_key = f"{reg_key}_end" if reg_key != "america" else "america_end"

            ongoing_events = []
            upcoming_events = []

            for event in events:
                start_ts = int(event.get(start_key) or event.get('start_date') or 0)
                end_ts = int(event.get(end_key) or event.get('end_date') or 0)

                if start_ts <= now < end_ts:
                    ongoing_events.append((event, start_ts, end_ts))
                elif start_ts > now:
                    upcoming_events.append((event, start_ts, end_ts))

            ongoing_events.sort(key=lambda x: x[2])
            upcoming_events.sort(key=lambda x: x[1])

            if ongoing_channel:
                await self._update_regional_embeds(
                    ongoing_channel,
                    [(e, s, end) for e, s, end in ongoing_events],
                    "ongoing",
                    reg
                )

            if upcoming_channel:
                await self._update_regional_embeds(
                    upcoming_channel,
                    [(e, s, end) for e, s, end in upcoming_events],
                    "upcoming",
                    reg
                )

    async def _update_regional_embeds(
        self,
        channel: discord.TextChannel,
        events: List[tuple],
        event_type: str,
        region: str,
    ):
        """Update embeds in a channel for a specific region."""
        try:
            if not events:
                return

            for event, start_ts, end_ts in events:
                embed = self._create_regional_embed(event, event_type, region, start_ts, end_ts)
                await channel.send(embed=embed)
                await asyncio.sleep(0.5)

        except discord.HTTPException as e:
            self.logger.error(f"Failed to update {event_type} channel for {region}: {e}")

    def _create_regional_embed(
        self,
        event: Dict[str, Any],
        event_type: str,
        region: str,
        start_ts: int,
        end_ts: int,
    ) -> discord.Embed:
        """Create an embed for a regional event."""
        category = event.get('category', 'Event')

        colors = {
            "Banner": 0x5BCEFA,
            "Event": 0xF7BA0B,
            "Maintenance": 0xFF6B6B if event_type == "ongoing" else 0x57F287,
            "Offer": 0xFF00FF,
        }
        color = colors.get(category, 0x808080)

        embed = discord.Embed(
            title=event.get('title', 'Unknown Event'),
            color=color,
        )

        if event_type == "ongoing":
            embed.add_field(
                name=f"Ends ({region})",
                value=f"<t:{end_ts}:F>\n<t:{end_ts}:R>",
                inline=False,
            )
        else:
            embed.add_field(
                name=f"Starts ({region})",
                value=f"<t:{start_ts}:F>\n<t:{start_ts}:R>",
                inline=True,
            )
            embed.add_field(
                name=f"Ends ({region})",
                value=f"<t:{end_ts}:F>\n<t:{end_ts}:R>",
                inline=True,
            )

        if event.get('image'):
            embed.set_thumbnail(url=event['image'])

        embed.set_footer(text=f"{self.config.display_name} | {category} | {region}")

        return embed

    async def convert_to_all_timezones(self, dt_str: str) -> Optional[Dict]:
        """Convert a date string to all regional timezones."""
        dt = dateparser.parse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        if not dt:
            dt = dateparser.parse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': False})
            if not dt:
                return None

        if dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None:
            unix = int(dt.timestamp())
            return {region: (dt, unix) for region in self.TIMEZONES}

        results = {}
        for region, tz_name in self.TIMEZONES.items():
            tz = pytz.timezone(tz_name)
            dt_tz = tz.localize(dt)
            unix = int(dt_tz.timestamp())
            results[region] = (dt_tz, unix)
        return results

    async def get_version_start(self, version_str: str):
        """Get the start date for a game version."""
        config = self.DEFAULT_VERSIONS.get(self.profile)
        if not config:
            return None

        def parse_version(v):
            parts = v.split('.')
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            return major, minor

        req_major, req_minor = parse_version(version_str)
        base_major, base_minor = parse_version(config["version"])
        base_date = config["date"]

        if (req_major, req_minor) <= (base_major, base_minor):
            return base_date

        delta_versions = (req_major - base_major) * 10 + (req_minor - base_minor)
        return base_date + timedelta(weeks=6 * delta_versions)

    async def add_event(self, ctx, event_data: Dict[str, Any]):
        """Add a new event with regional times."""
        title = await self.repository.generate_unique_title(event_data['title'])
        event_data['title'] = title
        event_data['user_id'] = str(ctx.author.id)

        event_id = await self.repository.create_event(event_data)
        self.logger.info(f"Added event '{title}' (ID: {event_id})")

        return event_id, title

    async def remove_event(self, ctx, title: str):
        """Remove an event by title."""
        success = await self.repository.delete_event(title)
        if success:
            self.logger.info(f"Removed event '{title}'")
        return success

    def get_notification_timings(self, category: str) -> Dict[str, List[int]]:
        """Get notification timings for a category."""
        return self.DEFAULT_TIMINGS.get(category, self.DEFAULT_TIMINGS["Event"])


# =============================================================================
# Pre-configured Module Factories
# =============================================================================

def create_zzz_module(
    db_path: str = None,
    ongoing_channel_id: int = None,
    upcoming_channel_id: int = None,
    main_server_id: int = None,
) -> GenericHoyoverseModule:
    """Create a ZZZ (Zenless Zone Zero) module."""
    return GenericHoyoverseModule(
        profile="ZZZ",
        display_name="Zenless Zone Zero",
        db_path=db_path,
        ongoing_channel_id=ongoing_channel_id,
        upcoming_channel_id=upcoming_channel_id,
        main_server_id=main_server_id,
    )


def create_stri_module(
    db_path: str = None,
    ongoing_channel_id: int = None,
    upcoming_channel_id: int = None,
    main_server_id: int = None,
) -> GenericGameModule:
    """Create a STRI (Strinova) module."""
    return GenericGameModule(
        profile="STRI",
        display_name="Strinova",
        db_path=db_path,
        ongoing_channel_id=ongoing_channel_id,
        upcoming_channel_id=upcoming_channel_id,
        main_server_id=main_server_id,
    )


def create_wuwa_module(
    db_path: str = None,
    ongoing_channel_id: int = None,
    upcoming_channel_id: int = None,
    main_server_id: int = None,
) -> GenericGameModule:
    """Create a WUWA (Wuthering Waves) module."""
    return GenericGameModule(
        profile="WUWA",
        display_name="Wuthering Waves",
        db_path=db_path,
        ongoing_channel_id=ongoing_channel_id,
        upcoming_channel_id=upcoming_channel_id,
        main_server_id=main_server_id,
    )


__all__ = [
    'GenericEventRepository',
    'GenericGameModule',
    'GenericHoyoverseModule',
    'create_zzz_module',
    'create_stri_module',
    'create_wuwa_module',
]
