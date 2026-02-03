"""
HSR (Honkai: Star Rail) game module.

This module implements the GameModule interface for HSR, handling:
- Event management with regional servers (Asia, NA, EU)
- Dashboard updates for timer channels
- Notification scheduling
- Version tracking
"""

import discord
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import pytz
import dateparser

from src.games.base import GameConfig, HoyoverseGameModule
from .database import HSREventRepository


# Default version configuration
DEFAULT_VERSION = "3.3"
DEFAULT_VERSION_DATE = datetime(2025, 5, 21, 11, 0, tzinfo=timezone(timedelta(hours=8)))


class HSRModule(HoyoverseGameModule):
    """
    HSR game module implementation.

    Handles events with regional server times (Asia, America, Europe).
    """

    def __init__(
        self,
        db_path: str = None,
        ongoing_channel_id: int = None,
        upcoming_channel_id: int = None,
        main_server_id: int = None,
    ):
        """
        Initialize the HSR module.

        Args:
            db_path: Path to HSR database (defaults to data/hsr_data.db)
            ongoing_channel_id: Channel ID for ongoing events
            upcoming_channel_id: Channel ID for upcoming events
            main_server_id: Main Discord server ID
        """
        config = GameConfig(
            profile="HSR",
            db_path=db_path or "data/hsr_data.db",
            log_name="hsr",
            display_name="Honkai: Star Rail",
            has_regional_servers=True,
            regions=["ASIA", "NA", "EU"],
            update_interval_hours=6,
        )
        super().__init__(config)

        self.repository = HSREventRepository(config.db_path)
        self.ongoing_channel_id = ongoing_channel_id
        self.upcoming_channel_id = upcoming_channel_id
        self.main_server_id = main_server_id

        # In-memory task tracking
        self._scheduled_tasks: Dict[tuple, asyncio.Task] = {}

    async def initialize(self):
        """Initialize the module."""
        await self.repository.initialize()
        self.logger.info("HSR module initialized")

    async def refresh_events(self):
        """
        Refresh events from source.

        HSR events are typically scraped from external sources
        or entered manually. This method can be extended for scraping.
        """
        # For now, just update the dashboard
        self.logger.info("Refreshing HSR events")

    async def update_dashboard(self, guild, region: Optional[str] = None):
        """
        Update the HSR event dashboard.

        Args:
            guild: Discord guild object
            region: Optional specific region to update (or all if None)
        """
        if not guild:
            return

        now = int(datetime.now(timezone.utc).timestamp())
        ongoing_channel = guild.get_channel(self.ongoing_channel_id) if self.ongoing_channel_id else None
        upcoming_channel = guild.get_channel(self.upcoming_channel_id) if self.upcoming_channel_id else None

        regions_to_update = [region] if region else ["ASIA", "NA", "EU"]
        events = await self.repository.get_all_events()

        for event in events:
            # Group regions by their start/end times
            time_groups = self._group_regions_by_time(event)

            for (start, end), grouped_regions in time_groups.items():
                # Only process if this group contains a region we're updating
                if not any(r in regions_to_update for r in grouped_regions):
                    continue

                # Determine event status
                if end < now:
                    # Delete ended events
                    for reg in grouped_regions:
                        await self._delete_event_message(
                            guild, self.ongoing_channel_id, event["id"], reg
                        )
                        await self._delete_event_message(
                            guild, self.upcoming_channel_id, event["id"], reg
                        )

                    # Delete from DB if ended in ALL regions
                    if await self.repository.is_event_ended(event, now):
                        await self.repository.delete_event(event["id"])
                    continue

                elif start <= now < end:
                    event_status = "ongoing"
                else:
                    event_status = "upcoming"

                # Create embed
                embed = self._create_event_embed(event, grouped_regions, start, end)

                # Post or update the embed
                target_channel = ongoing_channel if event_status == "ongoing" else upcoming_channel
                other_channel_id = self.upcoming_channel_id if event_status == "ongoing" else self.ongoing_channel_id

                if target_channel:
                    primary_region = grouped_regions[0]
                    await self._upsert_event_message(
                        guild, target_channel, event, event["id"], primary_region, embed
                    )

                    # Delete from the other channel
                    for reg in grouped_regions:
                        await self._delete_event_message(guild, other_channel_id, event["id"], reg)

        self.logger.info(f"Dashboard updated for regions: {regions_to_update}")

    async def add_event(self, ctx, event_data: Dict[str, Any]):
        """
        Add a new HSR event.

        Args:
            ctx: Discord command context
            event_data: Event data with regional timestamps
        """
        event_data["user_id"] = str(ctx.author.id)
        event_id = await self.repository.create_event(event_data)

        # Schedule notifications for each region
        await self._schedule_event_notifications(event_data)

        # Schedule dashboard updates
        await self._schedule_dashboard_updates(event_data)

        await ctx.send(
            f"Added `{event_data['title']}` as **{event_data['category']}** for HSR!\n"
            f"Asia: <t:{event_data['asia_start']}:F> - <t:{event_data['asia_end']}:F>\n"
            f"America: <t:{event_data['america_start']}:F> - <t:{event_data['america_end']}:F>\n"
            f"Europe: <t:{event_data['europe_start']}:F> - <t:{event_data['europe_end']}:F>"
        )

        return event_id

    async def remove_event(self, ctx, title: str):
        """
        Remove an HSR event by title.

        Args:
            ctx: Discord command context
            title: Event title to remove
        """
        event = await self.repository.get_event_by_title(title)
        if not event:
            await ctx.send(f"No event found with title '{title}'.")
            return False

        # Delete messages for all regions
        guild = ctx.guild
        for region in ["ASIA", "NA", "EU"]:
            await self._delete_event_message(
                guild, self.ongoing_channel_id, event["id"], region
            )
            await self._delete_event_message(
                guild, self.upcoming_channel_id, event["id"], region
            )

        # Delete from database
        await self.repository.delete_event(event["id"])

        await ctx.send(f"Deleted HSR event '{event['title']}' and its notifications.")
        return True

    def get_notification_timings(self, category: str) -> Dict[str, List[int]]:
        """Get notification timings for HSR events."""
        # Standard timings (in minutes before event)
        base_timings = {
            "Banner": {
                "start": [60, 1440],       # 1h, 1d before start
                "end": [60, 1440],          # 1h, 1d before end
            },
            "Event": {
                "start": [60, 1440],
                "end": [60, 1440],
            },
            "Maintenance": {
                "start": [60, 180, 1440],   # 1h, 3h, 1d before
                "end": [60],
            },
        }
        return base_timings.get(category, {"start": [60], "end": [60]})

    async def convert_to_all_timezones(self, dt_str: str) -> Optional[Dict]:
        """
        Convert a date string to all regional timezones.

        Args:
            dt_str: Date string to parse

        Returns:
            Dictionary mapping region to (datetime, unix_timestamp)
        """
        dt = dateparser.parse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        if not dt:
            dt = dateparser.parse(dt_str, settings={'RETURN_AS_TIMEZONE_AWARE': False})
            if not dt:
                return None

        # If no timezone, assume UTC+8 (server time)
        if dt.tzinfo is None:
            tz_utc8 = pytz.timezone("Asia/Shanghai")
            dt = tz_utc8.localize(dt)

        result = {}
        for region_name, tz_name in self.TIMEZONES.items():
            tz = pytz.timezone(tz_name)
            local_dt = dt.astimezone(tz)
            unix = int(dt.timestamp())
            result[region_name] = (local_dt, unix)

        return result

    async def get_version_start(self, version_str: str):
        """
        Get the start date for an HSR version.

        Args:
            version_str: Version number (e.g. "3.5")

        Returns:
            datetime object for version start
        """
        version_info = await self.repository.get_version_info("HSR")

        def parse_version(v):
            parts = v.split('.')
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            return major, minor

        req_major, req_minor = parse_version(version_str)

        if version_info:
            base_version, base_date_str = version_info
            base_major, base_minor = parse_version(base_version)
            base_date = datetime.fromisoformat(base_date_str)
        else:
            base_major, base_minor = parse_version(DEFAULT_VERSION)
            base_date = DEFAULT_VERSION_DATE

        # If requested version is before or equal to base, return base
        if (req_major, req_minor) <= (base_major, base_minor):
            return base_date

        # Calculate weeks difference (each version is 6 weeks)
        delta_versions = (req_major - base_major) * 10 + (req_minor - base_minor)
        return base_date + timedelta(weeks=6 * delta_versions)

    async def on_ready(self, bot):
        """Start background tasks when bot is ready."""
        await self._load_scheduled_tasks(bot)
        asyncio.create_task(self._periodic_cleanup())

    # ==================== Private Helper Methods ====================

    def _group_regions_by_time(self, event: Dict) -> Dict[tuple, List[str]]:
        """Group regions that have identical start/end times."""
        time_groups = {}
        region_map = {
            "ASIA": ("asia_start", "asia_end"),
            "NA": ("america_start", "america_end"),
            "EU": ("europe_start", "europe_end"),
        }

        for region, (start_key, end_key) in region_map.items():
            start = event.get(start_key, 0)
            end = event.get(end_key, 0)
            time_key = (start, end)
            if time_key not in time_groups:
                time_groups[time_key] = []
            time_groups[time_key].append(region)

        return time_groups

    def _create_event_embed(
        self,
        event: Dict,
        regions: List[str],
        start: int,
        end: int
    ) -> discord.Embed:
        """Create an embed for the event."""
        category = event.get("category", "").lower()
        if category == "banner":
            color = discord.Color.purple()
        elif category == "event":
            color = discord.Color.gold()
        elif category == "maintenance":
            color = discord.Color.red()
        else:
            color = discord.Color.default()

        # Format region string
        if len(regions) == 3:
            region_str = "All Regions"
        else:
            region_str = ", ".join(regions)

        embed = discord.Embed(
            title=f"{event['title']} ({region_str})",
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
        event: Dict,
        event_id: int,
        region: str,
        embed: discord.Embed
    ):
        """Update existing message or create new one."""
        msg_id = await self.repository.get_message_id(
            event_id, str(channel.id), region
        )

        if msg_id:
            try:
                msg = await channel.fetch_message(int(msg_id))
                await msg.edit(embed=embed)
                return
            except Exception:
                pass

        # Send new message
        msg = await channel.send(embed=embed)
        await self.repository.set_message_id(
            event_id, str(channel.id), str(msg.id), region
        )

    async def _delete_event_message(
        self,
        guild,
        channel_id: int,
        event_id: int,
        region: str
    ):
        """Delete an event message from a channel."""
        if not channel_id:
            return

        msg_id = await self.repository.get_message_id(
            event_id, str(channel_id), region
        )
        if msg_id:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.delete()
                except Exception:
                    pass

        await self.repository.delete_message_record(event_id, str(channel_id), region)

    async def _schedule_event_notifications(self, event_data: Dict):
        """Schedule notifications for each region."""
        # This would integrate with the notification service
        # For now, log the intent
        self.logger.info(f"Scheduling notifications for event: {event_data['title']}")

    async def _schedule_dashboard_updates(self, event_data: Dict):
        """Schedule dashboard updates at event start/end times."""
        for region, tz_key in [("NA", "america"), ("EU", "europe"), ("ASIA", "asia")]:
            start = int(event_data[f'{tz_key}_start'])
            end = int(event_data[f'{tz_key}_end'])
            await self.repository.schedule_update_task(start, region.upper())
            await self.repository.schedule_update_task(end, region.upper())

    async def _load_scheduled_tasks(self, bot):
        """Load scheduled tasks from database on startup."""
        tasks = await self.repository.get_pending_update_tasks()
        now = int(datetime.now(timezone.utc).timestamp())

        # Group by region
        from collections import defaultdict
        region_tasks = defaultdict(list)
        for update_unix, region in tasks:
            region_tasks[region].append(update_unix)

        for region, task_times in region_tasks.items():
            overdue = [t for t in task_times if t <= now]
            future = [t for t in task_times if t > now]

            # Execute one update for overdue tasks
            if overdue:
                self.logger.info(
                    f"Found {len(overdue)} overdue tasks for region {region}. Executing update..."
                )
                main_guild = bot.get_guild(self.main_server_id)
                if main_guild:
                    await self.update_dashboard(main_guild, region)

                for update_unix in overdue:
                    await self.repository.mark_task_done(update_unix, region)

            # Schedule future tasks
            for update_unix in future:
                delay = update_unix - now
                task_key = (update_unix, region)
                if task_key not in self._scheduled_tasks:
                    self._scheduled_tasks[task_key] = asyncio.create_task(
                        self._run_scheduled_update(bot, update_unix, region, delay)
                    )

    async def _run_scheduled_update(self, bot, update_unix: int, region: str, delay: int):
        """Run a scheduled dashboard update after delay."""
        await asyncio.sleep(delay)
        guild = bot.get_guild(self.main_server_id)
        if guild:
            await self.update_dashboard(guild, region)
        await self.repository.mark_task_done(update_unix, region)

    async def _periodic_cleanup(self):
        """Periodically clean up old completed tasks."""
        while True:
            await asyncio.sleep(86400)  # Run daily
            cutoff = int(datetime.now(timezone.utc).timestamp()) - 86400
            await self.repository.cleanup_old_tasks(cutoff)
            self.logger.info("Cleaned up old scheduled tasks")
