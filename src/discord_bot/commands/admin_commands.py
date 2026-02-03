"""
Admin commands for the Gacha Timer Bot.

This module contains owner-only administrative commands such as
shutdown, restart, getlog, and export functions.
"""

import discord
from discord.ext import commands
from typing import Optional
import subprocess
import aiosqlite
from collections import defaultdict

from .base import owner_only, is_owner, OWNER_ID


def setup_admin_commands(bot: commands.Bot):
    """
    Register admin commands with the bot.

    Args:
        bot: The bot instance
    """

    @bot.command(name="mmj")
    async def mmj(ctx: commands.Context):
        """Forces Kanami to shut down if you are worthy enough."""
        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't get to use this command!")
            return
        await ctx.send("Kanami is shutting down...")
        await bot.close()

    @bot.command(name="shutdown")
    async def shutdown(ctx: commands.Context):
        """Alias for mmj - shuts down the bot."""
        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't get to use this command!")
            return
        await ctx.send("Kanami is shutting down...")
        await bot.close()

    @bot.command(name="restart")
    async def restart(ctx: commands.Context):
        """Restarts the bot process via systemd (owner only, Raspberry Pi)."""
        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't get to use this command!")
            return

        await ctx.send("Kanami is restarting...")

        # Pull from github and restart the bot
        try:
            subprocess.run(
                ["git", "-C", "/home/piberry/Gacha-Timer-Bot", "pull"],
                check=True
            )
            subprocess.Popen(["sudo", "systemctl", "restart", "kanami-bot"])
        except Exception as e:
            await ctx.send(f"Failed to restart: {e}")

    @bot.command(name="getlog")
    async def getlog(ctx: commands.Context):
        """
        Owner-only: Sends the discord.log file to the owner's DMs.
        Usage: Kanami getlog
        """
        if ctx.author.id != OWNER_ID:
            await ctx.send("Only the bot owner can use this command.")
            return
        try:
            file = discord.File("discord.log")
            await ctx.author.send("Here is the latest discord.log file:", file=file)
            await ctx.send("Log file sent to your DMs.")
        except Exception as e:
            await ctx.send(f"Failed to send log file: {e}")

    @bot.command(name="export_pending_notifications")
    async def export_pending_notifications(ctx: commands.Context):
        """Exports the pending notifications table as a DM to the user (owner only)."""
        await _export_pending_notifications_impl(ctx)

    @bot.command(name="epn")
    async def epn(ctx: commands.Context):
        """Shortened command for exporting pending notifications (owner only)."""
        await _export_pending_notifications_impl(ctx)

    async def _export_pending_notifications_impl(ctx: commands.Context):
        """
        Exports the pending notifications table as a DM to the user.
        Only the owner can use this command.
        """
        if ctx.author.id != OWNER_ID:
            await ctx.send("You are not authorized to use this command.")
            return

        async with aiosqlite.connect('kanami_data.db') as conn:
            async with conn.execute("""
                SELECT id, server_id, category, profile, title, timing_type,
                       notify_unix, event_time_unix, sent, region
                FROM pending_notifications
                ORDER BY profile, server_id, notify_unix ASC
            """) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await ctx.author.send("There are no pending notifications in the database.")
            await ctx.send("Exported: No pending notifications.")
            return

        # Group notifications by profile, then by (title, category)
        grouped = defaultdict(lambda: defaultdict(list))
        for row in rows:
            (notif_id, server_id, category, profile, title,
             timing_type, notify_unix, event_time_unix, sent, region) = row
            key = (title, category)
            grouped[profile][key].append({
                "timing_type": timing_type,
                "notify_unix": notify_unix,
                "event_time_unix": event_time_unix,
                "region": region
            })

        # Sort profiles alphabetically, then events by title
        sorted_profiles = sorted(grouped.keys())
        lines = []
        lines.append(f"**Pending Notifications Export ({len(rows)} rows):**")

        for profile in sorted_profiles:
            lines.append(f"# {profile}")
            events_dict = grouped[profile]

            # Sort events by title
            for (title, category), events in sorted(events_dict.items(), key=lambda x: x[0][0].lower()):
                lines.append(f"**{title}**")
                lines.append(f"{category}")

                # Check if any event has a region
                has_region = any(e["region"] for e in events)
                if has_region:
                    # Group by region
                    region_map = defaultdict(list)
                    for e in events:
                        region = e["region"] or "Unknown"
                        region_map[region].append(e)

                    for region, region_events in region_map.items():
                        lines.append(f"Region: {region}")
                        start_times = [
                            f"<t:{e['event_time_unix']}:R>"
                            for e in region_events if e["timing_type"] == "start"
                        ]
                        end_times = [
                            f"<t:{e['event_time_unix']}:R>"
                            for e in region_events if e["timing_type"] == "end"
                        ]
                        if start_times:
                            lines.append(f"   Start: {', '.join(start_times)}")
                        if end_times:
                            lines.append(f"   End: {', '.join(end_times)}")
                else:
                    start_times = [
                        f"<t:{e['event_time_unix']}:F>"
                        for e in events if e["timing_type"] == "start"
                    ]
                    end_times = [
                        f"<t:{e['event_time_unix']}:F>"
                        for e in events if e["timing_type"] == "end"
                    ]
                    if start_times:
                        lines.append(f"Start: {', '.join(start_times)}")
                    if end_times:
                        lines.append(f"End: {', '.join(end_times)}")
                lines.append("")  # Blank line between events

        # Discord DMs have a 2000 character limit per message
        msg = ""
        for line in lines:
            if len(msg) + len(line) + 1 > 1990:
                await ctx.author.send(msg)
                msg = ""
            msg += line + "\n"
        if msg:
            await ctx.author.send(msg)

        await ctx.send("Pending notifications exported to your DMs.")

    @bot.command(name="sync")
    async def sync_commands(ctx: commands.Context):
        """Sync slash commands globally (owner only)."""
        if ctx.author.id != OWNER_ID:
            await ctx.send("Only the bot owner can use this command.")
            return

        try:
            synced = await bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} command(s) globally.")
        except Exception as e:
            await ctx.send(f"Failed to sync commands: {e}")

    @bot.command(name="sync_guild")
    async def sync_guild_commands(ctx: commands.Context):
        """Sync slash commands to this guild only (owner only)."""
        if ctx.author.id != OWNER_ID:
            await ctx.send("Only the bot owner can use this command.")
            return

        try:
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"Synced {len(synced)} command(s) to this guild.")
        except Exception as e:
            await ctx.send(f"Failed to sync commands: {e}")

    return {
        'mmj': mmj,
        'shutdown': shutdown,
        'restart': restart,
        'getlog': getlog,
        'export_pending_notifications': export_pending_notifications,
        'epn': epn,
        'sync': sync_commands,
        'sync_guild': sync_guild_commands,
    }
