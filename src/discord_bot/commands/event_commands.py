"""
Event management commands for the Gacha Timer Bot.

This module contains commands for managing events:
- add: Add a new event
- remove: Remove an event
- edit: Edit an existing event
- add_custom_category: Add a custom category
"""

import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List
import re
import dateparser

from .base import (
    prompt_for_input,
    prompt_for_profile,
    prompt_for_category,
    is_hyv_profile,
    VALID_PROFILES,
    ValidationError,
    NotFoundError,
)
from src.core.models import Event, GameProfile
from src.core.repositories import (
    SQLiteEventRepository,
    SQLiteNotificationRepository,
    SQLiteConfigRepository,
)
from src.core.services import EventService, NotificationScheduler
from src.discord_bot.formatters import (
    format_timestamp,
    format_timestamp_dual,
    create_success_embed,
    create_error_embed,
)


def setup_event_commands(
    bot: commands.Bot,
    event_repo: SQLiteEventRepository,
    notification_repo: SQLiteNotificationRepository,
    config_repo: SQLiteConfigRepository,
    update_timer_channel_func=None,
):
    """
    Register event commands with the bot.

    Args:
        bot: The bot instance
        event_repo: Event repository instance
        notification_repo: Notification repository instance
        config_repo: Config repository instance
        update_timer_channel_func: Optional function to update timer channels
    """

    # Create service instances
    scheduler = NotificationScheduler()
    event_service = EventService(event_repo, notification_repo, scheduler)

    @bot.command(name="add")
    async def add(ctx: commands.Context, *, args: str):
        """
        Adds a new event using fuzzy date/time parsing.
        Usage: Kanami add <title> <start> <end> [image] [profile] [category] [timezone]
        Example: Kanami add "Shadowverse Battle Fest" 2025-08-14 13:00 2025-08-17 13:00 https://image.url AK Event Asia/Tokyo
        """
        try:
            # Parse the arguments
            parsed = await _parse_add_args(ctx, bot, args)
            if not parsed:
                return

            title, start_unix, end_unix, image, profile, category, timezone_str = parsed

            # Check for duplicate title and generate unique one if needed
            server_id = str(ctx.guild.id)
            base_title = title
            suffix = 1
            new_title = base_title

            while True:
                existing = await event_repo.get_by_title(server_id, new_title)
                if not existing:
                    break
                suffix += 1
                new_title = f"{base_title} {suffix}"

            # Create the event
            event = Event(
                user_id=str(ctx.author.id),
                server_id=server_id,
                title=new_title,
                start_date=start_unix,
                end_date=end_unix,
                image=image,
                category=category,
                profile=profile,
                is_hyv=is_hyv_profile(profile),
            )

            # Save event and schedule notifications
            event_id, notification_ids = await event_service.create_event(
                event, schedule_notifications=True
            )

            # Send confirmation
            await ctx.send(
                f"Added `{new_title}` as **{category}** for **{profile}** to the database!\n"
                f"Start: <t:{start_unix}:F>\nEnd: <t:{end_unix}:F>\nTimezone: {timezone_str}\n"
                f"Scheduled {len(notification_ids)} notification(s)."
            )

            # Update timer channels if function provided
            if update_timer_channel_func:
                profiles = await config_repo.get_all_timer_channels(server_id)
                for prof in profiles.keys():
                    await update_timer_channel_func(ctx.guild, bot, profile=prof)

        except ValidationError as e:
            await ctx.send(f"Validation error: {e.message}")
        except Exception as e:
            await ctx.send(f"Error adding event: {e}")

    @bot.command(name="remove")
    async def remove(ctx: commands.Context, *, title: str):
        """
        Removes an event by title.
        Usage: Kanami remove <title>
        """
        server_id = str(ctx.guild.id)

        try:
            # Find the event (case-insensitive)
            event = await event_repo.get_by_title(server_id, title)
            if not event:
                await ctx.send(f"No event found with the title `{title}`.")
                return

            # Get event details for confirmation message
            event_title = event.title
            start = event.start_date
            end = event.end_date
            profile = event.profile

            # Delete the event (cascades to notifications and messages)
            success = await event_service.delete_event(
                event_id=event.id,
                profile=profile,
                title=event_title,
                category=event.category,
            )

            if success:
                await ctx.send(
                    f"Removed event `{event_title}` "
                    f"(Start: <t:{start}:F>, End: <t:{end}:F>) "
                    f"from the database and cleared its notifications."
                )

                # Update timer channels
                if update_timer_channel_func:
                    profiles = await config_repo.get_all_timer_channels(server_id)
                    for prof in profiles.keys():
                        await update_timer_channel_func(ctx.guild, bot, profile=prof)
            else:
                await ctx.send(f"Failed to remove event `{title}`.")

        except Exception as e:
            await ctx.send(f"Error removing event: {e}")

    @bot.command(name="edit")
    async def edit(ctx: commands.Context, title: str, item: str, *, value: str):
        """
        Edits an existing event in the database.
        Usage: Kanami edit <title> <item> <value>
        Items: start, end, category, profile, image, title
        """
        server_id = str(ctx.guild.id)
        allowed_items = ["start", "end", "category", "profile", "image", "title"]

        if item.lower() not in allowed_items:
            await ctx.send(
                f"Cannot edit `{item}`. Only {', '.join(allowed_items)} can be edited."
            )
            return

        try:
            # Find the event
            event = await event_repo.get_by_title(server_id, title)
            if not event:
                await ctx.send(f"No event found with the title `{title}`.")
                return

            # Handle different edit types
            if item.lower() == "title":
                # Check if new title already exists
                existing = await event_repo.get_by_title(server_id, value)
                if existing and existing.id != event.id:
                    await ctx.send(f"An event with title `{value}` already exists.")
                    return
                event.title = value

            elif item.lower() == "category":
                valid_categories = await config_repo.get_valid_categories(
                    server_id, event.profile
                )
                if value not in valid_categories:
                    await ctx.send(
                        f"Invalid category. Valid categories: {', '.join(valid_categories)}"
                    )
                    return
                event.category = value

            elif item.lower() == "profile":
                if value.upper() not in VALID_PROFILES:
                    await ctx.send(
                        f"Invalid profile. Valid profiles: {', '.join(VALID_PROFILES)}"
                    )
                    return
                event.profile = value.upper()
                event.is_hyv = is_hyv_profile(value)

            elif item.lower() == "image":
                if value.lower() == "none":
                    event.image = None
                elif value.startswith("http://") or value.startswith("https://"):
                    event.image = value
                else:
                    await ctx.send("Image must be a valid URL or 'none' to remove.")
                    return

            elif item.lower() in ("start", "end"):
                # Parse the time value
                unix_time = await _parse_time_value(ctx, bot, value)
                if unix_time is None:
                    return

                if item.lower() == "start":
                    event.start_date = unix_time
                    if event.is_hyv:
                        # For HYV games, update regional times
                        event.asia_start = unix_time
                        event.america_start = unix_time
                        event.europe_start = unix_time
                else:
                    event.end_date = unix_time
                    if event.is_hyv:
                        event.asia_end = unix_time
                        event.america_end = unix_time
                        event.europe_end = unix_time

            # Update the event
            await event_service.update_event(event, reschedule_notifications=True)

            await ctx.send(f"Updated `{item}` for event `{title}` to `{value}`.")

            # Update timer channels
            if update_timer_channel_func:
                profiles = await config_repo.get_all_timer_channels(server_id)
                for prof in profiles.keys():
                    await update_timer_channel_func(ctx.guild, bot, profile=prof)

        except Exception as e:
            await ctx.send(f"Error editing event: {e}")

    @bot.command(name="add_custom_category")
    async def add_custom_category(ctx: commands.Context, *, category: str):
        """
        Adds a custom event category for this server.
        Usage: Kanami add_custom_category <category>
        """
        server_id = str(ctx.guild.id)

        # Prompt for profile
        profile = await prompt_for_profile(ctx, bot)
        if not profile:
            return

        try:
            await config_repo.add_custom_category(server_id, profile, category)
            await ctx.send(
                f"Added custom category `{category}` for profile `{profile}`."
            )
        except Exception as e:
            await ctx.send(f"Error adding custom category: {e}")

    async def _parse_add_args(
        ctx: commands.Context, bot: commands.Bot, args: str
    ) -> Optional[Tuple[str, int, int, Optional[str], str, str, str]]:
        """
        Parse arguments for the add command.

        Returns:
            Tuple of (title, start_unix, end_unix, image, profile, category, timezone)
            or None if parsing failed
        """
        # Extract quoted title
        quoted = re.findall(r'"([^"]+)"', args)
        title = quoted[0] if quoted else None
        rest = args
        if title:
            rest = rest.replace(f'"{title}"', '').strip()

        # Find all date-like patterns
        date_patterns = re.findall(
            r'(\d{4}[-/]\d{2}[-/]\d{2} \d{1,2}:\d{2}(?:\s*\([^)]+\))?|'
            r'\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})? \d{1,2}:\d{2}(?:\s*\([^)]+\))?|'
            r'\d{1,2}:\d{2}(?:\s*\([^)]+\))?)',
            rest
        )

        # Remove duplicates, preserve order
        seen = set()
        dates = []
        for d in date_patterns:
            if d not in seen:
                seen.add(d)
                dates.append(d)

        # Try to parse with dateparser
        parsed = []
        for d in dates:
            dt = dateparser.parse(d, settings={'RETURN_AS_TIMEZONE_AWARE': True})
            if dt:
                parsed.append((d, dt))

        # If less than 2, try to find more with dateparser.search
        if len(parsed) < 2:
            try:
                results = dateparser.search.search_dates(
                    rest, settings={'RETURN_AS_TIMEZONE_AWARE': True}
                ) or []
                for result in results:
                    d, dt = result
                    if dt and (d, dt) not in parsed:
                        parsed.append((d, dt))
            except Exception:
                pass

        # Find timezone
        tz_match = re.search(
            r'([A-Za-z_]+/[A-Za-z_]+|UTC[+-]?\d{0,2}|GMT[+-]?\d{0,2})',
            rest
        )
        timezone_str = tz_match.group(1) if tz_match else None

        if not timezone_str:
            timezone_str = await prompt_for_input(
                ctx, bot,
                "No timezone detected. Please enter the timezone for this event "
                "(e.g. `Asia/Tokyo`, `UTC+8`, etc.):"
            )
            if not timezone_str:
                return None

        # Extract image, profile, category from remaining args
        after_tz = rest.split(timezone_str, 1)[-1].strip() if timezone_str in rest else rest
        image = None
        profile = None
        category = None
        extras = after_tz.split()

        for extra in extras:
            if extra.startswith("http://") or extra.startswith("https://"):
                image = extra
            elif extra.upper() in VALID_PROFILES:
                profile = extra.upper()
            elif not category:
                category = extra

        # Prompt for missing profile/category
        if not profile:
            profile = await prompt_for_profile(ctx, bot)
            if not profile:
                return None

        if not category:
            category = await prompt_for_category(ctx, bot)
            if not category:
                return None

        # Parse start/end times
        try:
            if len(parsed) >= 2:
                start_dt = parsed[0][1]
                end_dt = parsed[1][1]
            elif len(parsed) == 1:
                start_dt = parsed[0][1]
                days_str = await prompt_for_input(
                    ctx, bot,
                    "Only one date found. How many days does this event last? "
                    "(Enter a number, e.g. `14`)"
                )
                if not days_str:
                    return None
                try:
                    days = int(days_str.strip())
                except ValueError:
                    await ctx.send("Invalid number. Cancelling.")
                    return None
                end_dt = start_dt + timedelta(days=days)
            else:
                await ctx.send(
                    "Could not find valid date/time in your message. "
                    "Please provide start and end times."
                )
                return None
        except Exception as e:
            await ctx.send(f"Error parsing times: {e}")
            return None

        # Convert to UTC unix timestamps
        try:
            import pytz

            if start_dt.tzinfo is None:
                tz = pytz.timezone(timezone_str)
                start_dt = tz.localize(start_dt)
            start_unix = int(start_dt.astimezone(timezone.utc).timestamp())

            if end_dt.tzinfo is None:
                tz = pytz.timezone(timezone_str)
                end_dt = tz.localize(end_dt)
            end_unix = int(end_dt.astimezone(timezone.utc).timestamp())
        except Exception as e:
            await ctx.send(f"Error converting times to UTC: {e}")
            return None

        # Default title if not provided
        if not title:
            title = "Untitled Event"

        return (title, start_unix, end_unix, image, profile, category, timezone_str)

    async def _parse_time_value(
        ctx: commands.Context, bot: commands.Bot, value: str
    ) -> Optional[int]:
        """
        Parse a time value to unix timestamp.

        Args:
            ctx: Command context
            bot: Bot instance
            value: Time string (unix timestamp or date/time string)

        Returns:
            Unix timestamp or None if parsing failed
        """
        # Try to parse as unix timestamp first
        try:
            return int(value)
        except ValueError:
            pass

        # Try to extract timezone from value
        tz_match = re.search(
            r'(UTC[+-]\d+|GMT[+-]\d+|[A-Za-z]+/[A-Za-z_]+)',
            value
        )

        if tz_match:
            timezone_str = tz_match.group(1)
        else:
            timezone_str = await prompt_for_input(
                ctx, bot,
                "No timezone detected. Please enter the timezone "
                "(e.g. `Asia/Tokyo`, `UTC+8`, etc.):"
            )
            if not timezone_str:
                return None

        # Parse with dateparser
        try:
            dt = dateparser.parse(
                value,
                settings={
                    'TIMEZONE': timezone_str,
                    'RETURN_AS_TIMEZONE_AWARE': True
                }
            )
            if dt:
                return int(dt.astimezone(timezone.utc).timestamp())
            else:
                await ctx.send(f"Could not parse time: `{value}`")
                return None
        except Exception as e:
            await ctx.send(f"Error parsing time: {e}")
            return None

    return {
        'add': add,
        'remove': remove,
        'edit': edit,
        'add_custom_category': add_custom_category,
    }
