"""
HSR-specific Discord commands.

This module registers HSR-specific commands with the bot.
"""

import discord
from discord.ext import commands
from typing import Optional

from src.discord_bot.commands.base import OWNER_ID, prompt_for_input
from .module import HSRModule


def setup_hsr_commands(bot: commands.Bot, hsr_module: HSRModule):
    """
    Register HSR commands with the bot.

    Args:
        bot: Discord bot instance
        hsr_module: Initialized HSR module instance
    """

    @bot.command(name="hsr_add")
    @commands.has_permissions(manage_guild=True)
    async def hsr_add(ctx: commands.Context, category: str, *, title: str):
        """
        Manually adds an HSR event.
        Usage: Kanami hsr_add <category> <title>
        Category: Banner, Event, or Maintenance
        """
        category = category.capitalize()
        if category not in ["Banner", "Event", "Maintenance"]:
            await ctx.send("Category must be: Banner, Event, or Maintenance")
            return

        await ctx.send(f"Adding HSR {category}: `{title}`")
        await ctx.send("Enter start time (e.g. `2025/06/18 04:00 (UTC+8)`):")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", timeout=120.0, check=check)
            start_str = msg.content.strip()
        except Exception:
            await ctx.send("Timeout. Cancelled.")
            return

        await ctx.send("Enter end time:")
        try:
            msg = await bot.wait_for("message", timeout=120.0, check=check)
            end_str = msg.content.strip()
        except Exception:
            await ctx.send("Timeout. Cancelled.")
            return

        await ctx.send("Enter image URL (or 'none'):")
        try:
            msg = await bot.wait_for("message", timeout=120.0, check=check)
            image = msg.content.strip() if msg.content.strip().lower() != "none" else None
        except Exception:
            image = None

        # Convert times to all regions
        start_times = await hsr_module.convert_to_all_timezones(start_str)
        end_times = await hsr_module.convert_to_all_timezones(end_str)

        if not start_times or not end_times:
            await ctx.send("Failed to parse times. Cancelled.")
            return

        event_data = {
            "title": title,
            "category": category,
            "image": image,
            "asia_start": start_times["Asia"][1],
            "asia_end": end_times["Asia"][1],
            "america_start": start_times["America"][1],
            "america_end": end_times["America"][1],
            "europe_start": start_times["Europe"][1],
            "europe_end": end_times["Europe"][1],
        }

        await hsr_module.add_event(ctx, event_data)

        # Update dashboards
        guild = ctx.guild or bot.get_guild(hsr_module.main_server_id)
        if guild:
            await hsr_module.update_dashboard(guild)

    @bot.command(name="hsr_remove")
    @commands.has_permissions(manage_guild=True)
    async def hsr_remove(ctx: commands.Context, *, title: str):
        """
        Removes an HSR event by title (case-insensitive).
        Usage: Kanami hsr_remove <title>
        """
        success = await hsr_module.remove_event(ctx, title)
        if success:
            guild = ctx.guild or bot.get_guild(hsr_module.main_server_id)
            if guild:
                await hsr_module.update_dashboard(guild)

    @bot.command(name="hsr_refresh")
    @commands.has_permissions(manage_guild=True)
    async def hsr_refresh(ctx: commands.Context):
        """
        Refreshes all HSR event dashboards.
        Usage: Kanami hsr_refresh
        """
        guild = ctx.guild or bot.get_guild(hsr_module.main_server_id)
        if guild:
            await hsr_module.update_dashboard(guild)
            await ctx.send("HSR event dashboards have been refreshed.")
        else:
            await ctx.send("Could not find guild to refresh.")

    @bot.command(name="hsr_list")
    async def hsr_list(ctx: commands.Context):
        """
        Lists all HSR events.
        Usage: Kanami hsr_list
        """
        events = await hsr_module.repository.get_all_events()

        if not events:
            await ctx.send("No HSR events found.")
            return

        embed = discord.Embed(
            title="HSR Events",
            color=discord.Color.purple()
        )

        for event in events[:25]:  # Discord embed limit
            embed.add_field(
                name=f"{event['title']} ({event['category']})",
                value=(
                    f"Asia: <t:{event['asia_start']}:R> - <t:{event['asia_end']}:R>\n"
                    f"NA: <t:{event['america_start']}:R> - <t:{event['america_end']}:R>\n"
                    f"EU: <t:{event['europe_start']}:R> - <t:{event['europe_end']}:R>"
                ),
                inline=False
            )

        await ctx.send(embed=embed)

    @bot.command(name="hsr_dump_db")
    async def hsr_dump_db(ctx: commands.Context):
        """
        Sends the HSR database contents to the owner's DM.
        Usage: Kanami hsr_dump_db
        """
        if ctx.author.id != OWNER_ID:
            await ctx.send("You do not have permission to use this command.")
            return

        import os
        import aiosqlite

        db_path = hsr_module.config.db_path
        if not os.path.exists(db_path):
            await ctx.author.send("No HSR database file found.")
            return

        dump_lines = []
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
                tables = [row[0] async for row in cursor]

            for table in tables:
                dump_lines.append(f"--- {table} ---")
                async with db.execute(f"SELECT * FROM {table}") as cursor:
                    columns = [desc[0] for desc in cursor.description]
                    dump_lines.append(", ".join(columns))
                    async for row in cursor:
                        dump_lines.append(", ".join(str(x) for x in row))
                dump_lines.append("")

        text = "\n".join(dump_lines)
        chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]

        owner = bot.get_user(OWNER_ID)
        if not owner:
            owner = await bot.fetch_user(OWNER_ID)

        for chunk in chunks:
            await owner.send(f"HSR DB Dump:\n```{chunk}```")

        await ctx.send("Database dump sent to your DM.")

    return {
        'hsr_add': hsr_add,
        'hsr_remove': hsr_remove,
        'hsr_refresh': hsr_refresh,
        'hsr_list': hsr_list,
        'hsr_dump_db': hsr_dump_db,
    }
