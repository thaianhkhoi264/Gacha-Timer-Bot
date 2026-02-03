"""
Utility commands for the Gacha Timer Bot.

This module contains general utility commands that don't fit into
other categories, such as purge, convert, help, version, etc.
"""

import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from typing import Optional
import re

from .base import (
    owner_only,
    is_owner,
    confirm_action,
    OWNER_ID,
)
from src.discord_bot.formatters import create_help_embed


def setup_utility_commands(bot: commands.Bot, bot_version: str = "2.7.0"):
    """
    Register utility commands with the bot.

    Args:
        bot: The bot instance
        bot_version: Current bot version string
    """

    @bot.command(name="hello")
    async def hello(ctx: commands.Context):
        """Responds with a hello along with a truth."""
        await ctx.send("Hello! Kanami here! Alfa is into wearing maid cosplays!")

    @bot.command(name="version")
    async def version(ctx: commands.Context):
        """Returns the current version of the bot."""
        await ctx.send(f"Current version is {bot_version}!")

    @bot.command(name="help")
    async def help_command(ctx: commands.Context):
        """Shows help for Kanami bot commands, organized by category."""
        embed = discord.Embed(
            title="Kanami Bot Help",
            description="Here are all the available commands that Kanami can do!",
            color=discord.Color.blurple()
        )

        # General
        embed.add_field(
            name="General",
            value=(
                "`Kanami help` — Show this help message\n"
                "`Kanami hello` — Say hello to Kanami\n"
                "`Kanami version` — Show bot version\n"
                "`Kanami timer` — Show all events for this server\n"
                "`Kanami check_channels` — Show assigned channels\n"
            ),
            inline=False
        )

        # Event Management
        embed.add_field(
            name="Event Management",
            value=(
                "`Kanami add <title> <start> <end> [image] [profile] [category] [timezone]` — Add a new event\n"
                "`Kanami remove <title>` — Remove an event by title\n"
                "`Kanami edit <title> <item> <value>` — Edit an event (start, end, category, profile, image)\n"
                "`Kanami add_custom_category <category>` — Add a custom event category\n"
            ),
            inline=False
        )

        # Notification Management
        embed.add_field(
            name="Notification Management",
            value=(
                "`Kanami set_notification_channel #channel` — Set the notification channel\n"
                "`Kanami set_pending_notifications_channel #channel` — Set the pending notifications channel\n"
                "`Kanami set_notification_timing_channel #channel` — Set the notification timing channel\n"
                "`Kanami add_notification_timing <category> <start|end> <minutes>` — Add notification timing\n"
                "`Kanami clear_notification_timing <category> <start|end>` — Clear notification timing\n"
                "`Kanami refresh_pending_notifications` — Clear and recreate all pending notifications\n"
                "`Kanami clear_pending_notifications` — Clear all pending notifications\n"
            ),
            inline=False
        )

        # Role & Channel Management
        embed.add_field(
            name="Role & Channel Management",
            value=(
                "`Kanami assign` — Assign this channel for bot announcements\n"
                "`Kanami set_timer_channel #channel [profile]` — Set timer channel for a profile\n"
                "`Kanami assign_profile_role <profile> @Role` — Assign a role to a profile\n"
                "`Kanami assign_region_role <region> @Role` — Assign a role to a region\n"
                "`Kanami create_role_reaction` — Create role reaction messages\n"
                "`Kanami update_role_reaction` — Update role reaction messages\n"
                "`Kanami create_combined_roles` — Create combined region+game roles\n"
                "`Kanami update_all_combined_roles` — Update all members' combined roles\n"
                "`Kanami delete_role <role name>` — Delete a role\n"
            ),
            inline=False
        )

        # Utility
        embed.add_field(
            name="Utility",
            value=(
                "`Kanami purge [amount]` — Delete the last X messages (default 50, requires Manage Messages)\n"
                "`Kanami convert <time> [date]` — Convert date/time to Unix timestamp\n"
                "`Kanami converttz <time> [date] [timezone]` — Convert date/time with timezone\n"
                "`Kanami update` — Manually update all timer channels\n"
            ),
            inline=False
        )

        # Admin/Owner
        embed.add_field(
            name="Bloosh only",
            value=(
                "`Kanami mmj` — Tells Kanami to More More Jump off a cliff... <:KanamiScream:1374712543704256594>\n"
            ),
            inline=False
        )

        await ctx.send(embed=embed)

    @bot.command(name="purge")
    @commands.has_permissions(manage_messages=True)
    async def purge(ctx: commands.Context, amount: int = 50):
        """
        Deletes the past X messages in the channel. Default is 50.
        Usage: Kanami purge [amount]
        """
        if amount < 1 or amount > 100:
            await ctx.send("Please specify an amount between 1 and 100.")
            return

        confirmed = await confirm_action(
            ctx, bot,
            f"Are you absolutely sure about that? Kanami won't take responsibility if she deletes anything wrong... React with ✅ to confirm or ❌ to cancel."
        )

        if confirmed:
            deleted = await ctx.channel.purge(limit=amount)
            result_msg = await ctx.send(f"Deleted {len(deleted)} messages.", delete_after=5)
            try:
                await ctx.message.delete()
            except Exception:
                pass

    @bot.command(name="convert")
    async def convert(ctx: commands.Context, *, args: str):
        """
        Convert date/time to Unix timestamp.
        Usage: Kanami convert <date> <time>
        Example: Kanami convert 2025-08-14 13:00
        """
        import dateparser

        dt = dateparser.parse(args, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        if not dt:
            await ctx.send(f"Could not parse date/time: `{args}`")
            return

        unix = int(dt.timestamp())
        await ctx.send(
            f"**Input:** `{args}`\n"
            f"**Unix Timestamp:** `{unix}`\n"
            f"**Discord Format:** <t:{unix}:F> (<t:{unix}:R>)"
        )

    @bot.command(name="converttz")
    async def converttz(ctx: commands.Context, *, args: str):
        """
        Convert date/time with timezone to Unix timestamp.
        Usage: Kanami converttz <date> <time> <timezone>
        Example: Kanami converttz 2025-08-14 13:00 Asia/Tokyo
        """
        from src.core.services import TimezoneService

        # Try to extract timezone from args
        tz_match = re.search(
            r'([A-Za-z_]+/[A-Za-z_]+|UTC[+-]?\d{0,2}|GMT[+-]?\d{0,2})',
            args
        )

        if not tz_match:
            await ctx.send(
                "No timezone detected. Please include a timezone like:\n"
                "- `Asia/Tokyo`\n"
                "- `America/New_York`\n"
                "- `UTC+8`, `UTC-5`\n"
                "- `GMT+9`"
            )
            return

        timezone_str = tz_match.group(1)
        date_time_str = args.replace(timezone_str, "").strip()

        try:
            tz_service = TimezoneService()
            unix = tz_service.parse_to_unix(date_time_str, timezone_str)

            await ctx.send(
                f"**Input:** `{date_time_str}` in `{timezone_str}`\n"
                f"**Unix Timestamp:** `{unix}`\n"
                f"**Discord Format:** <t:{unix}:F> (<t:{unix}:R>)"
            )
        except Exception as e:
            await ctx.send(f"Error converting time: {e}")

    return {
        'hello': hello,
        'version': version,
        'help': help_command,
        'purge': purge,
        'convert': convert,
        'converttz': converttz,
    }
