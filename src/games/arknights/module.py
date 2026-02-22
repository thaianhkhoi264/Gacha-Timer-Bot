"""
Arknights game module.

This module implements the GameModule interface for Arknights, handling:
- Event management (single timezone - UTC-7 for Global)
- Dashboard updates for timer channels
- Notification scheduling
- LLM-based event extraction from images
"""

import discord
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import dateparser

from src.games.base import GameConfig, GameModule
from .database import ArknightsEventRepository


class ArknightsModule(GameModule):
    """
    Arknights game module implementation.

    Uses a single timezone (UTC-7 for Global server).
    Supports LLM-based event extraction from images.
    """

    # Default timezone for Arknights Global
    DEFAULT_TIMEZONE = "America/Los_Angeles"  # UTC-7/-8 depending on DST

    def __init__(
        self,
        db_path: str = None,
        ongoing_channel_id: int = None,
        upcoming_channel_id: int = None,
        main_server_id: int = None,
    ):
        """
        Initialize the Arknights module.

        Args:
            db_path: Path to Arknights database (defaults to data/arknights_data.db)
            ongoing_channel_id: Channel ID for ongoing events
            upcoming_channel_id: Channel ID for upcoming events
            main_server_id: Main Discord server ID
        """
        config = GameConfig(
            profile="AK",
            db_path=db_path or "data/arknights_data.db",
            log_name="arknights",
            display_name="Arknights",
            has_regional_servers=False,
            update_interval_hours=6,
        )
        super().__init__(config)

        self.repository = ArknightsEventRepository(config.db_path)
        self.ongoing_channel_id = ongoing_channel_id
        self.upcoming_channel_id = upcoming_channel_id
        self.main_server_id = main_server_id

        # In-memory task tracking
        self._scheduled_tasks: Dict[int, asyncio.Task] = {}

    async def initialize(self):
        """Initialize the module."""
        await self.repository.initialize()
        self.logger.info("Arknights module initialized")

    async def refresh_events(self):
        """
        Refresh events from source.

        Arknights events can be extracted from:
        - Twitter/X screenshots
        - Manual entry
        - Web scraping (if available)
        """
        self.logger.info("Refreshing Arknights events")

    async def update_dashboard(self, guild, region: Optional[str] = None):
        """
        Update the Arknights event dashboard.

        Args:
            guild: Discord guild object
            region: Ignored for Arknights (single timezone)
        """
        if not guild:
            return

        now = int(datetime.now(timezone.utc).timestamp())
        ongoing_channel = guild.get_channel(self.ongoing_channel_id) if self.ongoing_channel_id else None
        upcoming_channel = guild.get_channel(self.upcoming_channel_id) if self.upcoming_channel_id else None

        events = await self.repository.get_all_events()

        for event in events:
            start = event["start_date"]
            end = event["end_date"]

            # Determine event status
            if end < now:
                # Delete ended event messages
                if self.ongoing_channel_id:
                    await self._delete_event_message(guild, self.ongoing_channel_id, event["id"])
                if self.upcoming_channel_id:
                    await self._delete_event_message(guild, self.upcoming_channel_id, event["id"])
                # Delete from database
                await self.repository.delete_event(event["id"])
                continue

            elif start <= now < end:
                # Ongoing
                target_channel = ongoing_channel
                other_channel_id = self.upcoming_channel_id
            else:
                # Upcoming
                target_channel = upcoming_channel
                other_channel_id = self.ongoing_channel_id

            # Create embed
            embed = self._create_event_embed(event)

            # Post or update
            if target_channel:
                await self._upsert_event_message(guild, target_channel, event["id"], embed)

            # Remove from other channel
            if other_channel_id:
                await self._delete_event_message(guild, other_channel_id, event["id"])

        self.logger.info("Dashboard updated")

    async def add_event(self, ctx, event_data: Dict[str, Any]):
        """
        Add a new Arknights event.

        Args:
            ctx: Discord command context
            event_data: Event data dictionary
        """
        event_data["user_id"] = str(ctx.author.id)
        event_id = await self.repository.create_event(event_data)

        # Schedule notifications
        await self._schedule_event_notifications(event_data)

        # Schedule dashboard updates
        await self.repository.schedule_update_task(event_data["start_date"])
        await self.repository.schedule_update_task(event_data["end_date"])

        await ctx.send(
            f"Added `{event_data['title']}` as **{event_data['category']}** for Arknights!\n"
            f"Start: <t:{event_data['start_date']}:F>\n"
            f"End: <t:{event_data['end_date']}:F>"
        )

        return event_id

    async def remove_event(self, ctx, title: str):
        """
        Remove an Arknights event by title.

        Args:
            ctx: Discord command context
            title: Event title to remove
        """
        event = await self.repository.get_event_by_title(title)
        if not event:
            await ctx.send(f"No event found with title '{title}'.")
            return False

        # Delete messages
        guild = ctx.guild
        if self.ongoing_channel_id:
            await self._delete_event_message(guild, self.ongoing_channel_id, event["id"])
        if self.upcoming_channel_id:
            await self._delete_event_message(guild, self.upcoming_channel_id, event["id"])

        # Delete from database
        await self.repository.delete_event(event["id"])

        await ctx.send(f"Deleted Arknights event '{event['title']}'.")
        return True

    def get_notification_timings(self, category: str) -> Dict[str, List[int]]:
        """Get notification timings for Arknights events."""
        base_timings = {
            "Banner": {
                "start": [60, 1440],       # 1h, 1d before
                "end": [60, 1440],
            },
            "Event": {
                "start": [60, 1440],
                "end": [60, 1440, 4320],   # 1h, 1d, 3d before end
            },
            "CC": {  # Contingency Contract
                "start": [60, 1440],
                "end": [60, 1440],
            },
            "IS": {  # Integrated Strategies
                "start": [60, 1440],
                "end": [60, 1440],
            },
            "Maintenance": {
                "start": [60, 180],
                "end": [60],
            },
        }
        return base_timings.get(category, {"start": [60], "end": [60]})

    async def on_ready(self, bot):
        """Start background tasks when bot is ready."""
        await self._load_scheduled_tasks(bot)
        asyncio.create_task(self._periodic_cleanup())

    def parse_date_string(self, date_str: str) -> Optional[int]:
        """
        Parse an Arknights date string to Unix timestamp.

        Args:
            date_str: Date string like 'September 16, 2025, 10:00 (UTC-7)'

        Returns:
            Unix timestamp or None if parsing failed
        """
        date_str = date_str.strip().replace("  ", " ")
        dt = dateparser.parse(date_str)
        if not dt:
            return None
        if dt.tzinfo:
            return int(dt.timestamp())
        return int(dt.replace(tzinfo=timezone.utc).timestamp())

    # ==================== Private Helper Methods ====================

    def _create_event_embed(self, event: Dict) -> discord.Embed:
        """Create an embed for the event."""
        category = event.get("category", "").lower()
        if category == "banner":
            color = discord.Color.gold()
        elif category == "event":
            color = discord.Color.blue()
        elif category in ("cc", "contingency contract"):
            color = discord.Color.red()
        elif category in ("is", "integrated strategies"):
            color = discord.Color.purple()
        elif category == "maintenance":
            color = discord.Color.dark_gray()
        else:
            color = discord.Color.default()

        start = event["start_date"]
        end = event["end_date"]

        embed = discord.Embed(
            title=event["title"],
            description=f"**Start:** <t:{start}:F>\n**End:** <t:{end}:F>",
            color=color
        )

        if event.get("image") and event["image"].startswith("http"):
            embed.set_image(url=event["image"])

        return embed

    async def _upsert_event_message(
        self,
        guild,
        channel,
        event_id: int,
        embed: discord.Embed
    ):
        """Update existing message or create new one."""
        msg_id = await self.repository.get_message_id(event_id, str(channel.id))

        if msg_id:
            try:
                msg = await channel.fetch_message(int(msg_id))
                await msg.edit(embed=embed)
                return
            except Exception:
                pass

        # Send new message
        msg = await channel.send(embed=embed)
        await self.repository.set_message_id(event_id, str(channel.id), str(msg.id))

    async def _delete_event_message(self, guild, channel_id: int, event_id: int):
        """Delete an event message from a channel."""
        if not channel_id:
            return

        msg_id = await self.repository.get_message_id(event_id, str(channel_id))
        if msg_id:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.delete()
                except Exception:
                    pass

        await self.repository.delete_message_record(event_id, str(channel_id))

    async def _schedule_event_notifications(self, event_data: Dict):
        """Schedule notifications for the event."""
        self.logger.info(f"Scheduling notifications for event: {event_data['title']}")

    async def _load_scheduled_tasks(self, bot):
        """Load scheduled tasks from database on startup."""
        tasks = await self.repository.get_pending_update_tasks()
        now = int(datetime.now(timezone.utc).timestamp())

        overdue = [t for t in tasks if t <= now]
        future = [t for t in tasks if t > now]

        # Execute one update for overdue tasks
        if overdue:
            self.logger.info(f"Found {len(overdue)} overdue tasks. Executing update...")
            main_guild = bot.get_guild(self.main_server_id)
            if main_guild:
                await self.update_dashboard(main_guild)

            for update_unix in overdue:
                await self.repository.mark_task_done(update_unix)

        # Schedule future tasks
        for update_unix in future:
            delay = update_unix - now
            if update_unix not in self._scheduled_tasks:
                self._scheduled_tasks[update_unix] = asyncio.create_task(
                    self._run_scheduled_update(bot, update_unix, delay)
                )

    async def _run_scheduled_update(self, bot, update_unix: int, delay: int):
        """Run a scheduled dashboard update after delay."""
        await asyncio.sleep(delay)
        guild = bot.get_guild(self.main_server_id)
        if guild:
            await self.update_dashboard(guild)
        await self.repository.mark_task_done(update_unix)

    async def _periodic_cleanup(self):
        """Periodically clean up old completed tasks."""
        while True:
            await asyncio.sleep(86400)
            cutoff = int(datetime.now(timezone.utc).timestamp()) - 86400
            await self.repository.cleanup_old_tasks(cutoff)
            self.logger.info("Cleaned up old scheduled tasks")
