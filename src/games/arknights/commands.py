"""
Arknights-specific Discord commands.

This module registers Arknights-specific commands with the bot.
"""

import discord
from discord.ext import commands
from typing import Optional

from src.discord_bot.commands.base import OWNER_ID
from .module import ArknightsModule


def setup_arknights_commands(bot: commands.Bot, ak_module: ArknightsModule):
    """
    Register Arknights commands with the bot.

    Args:
        bot: Discord bot instance
        ak_module: Initialized Arknights module instance
    """

    @bot.command(name="ak_add")
    @commands.has_permissions(manage_guild=True)
    async def ak_add(ctx: commands.Context, category: str, *, title: str):
        """
        Manually adds an Arknights event.
        Usage: Kanami ak_add <category> <title>
        Category: Banner, Event, CC, IS, or Maintenance
        """
        valid_categories = ["Banner", "Event", "CC", "IS", "Maintenance"]
        category = category.capitalize()
        if category not in valid_categories:
            await ctx.send(f"Category must be one of: {', '.join(valid_categories)}")
            return

        await ctx.send(f"Adding Arknights {category}: `{title}`")
        await ctx.send("Enter start time (e.g. `September 16, 2025, 10:00 (UTC-7)`):")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", timeout=120.0, check=check)
            start_str = msg.content.strip()
        except Exception:
            await ctx.send("Timeout. Cancelled.")
            return

        start_unix = ak_module.parse_date_string(start_str)
        if not start_unix:
            await ctx.send("Failed to parse start time. Cancelled.")
            return

        await ctx.send("Enter end time:")
        try:
            msg = await bot.wait_for("message", timeout=120.0, check=check)
            end_str = msg.content.strip()
        except Exception:
            await ctx.send("Timeout. Cancelled.")
            return

        end_unix = ak_module.parse_date_string(end_str)
        if not end_unix:
            await ctx.send("Failed to parse end time. Cancelled.")
            return

        await ctx.send("Enter image URL (or 'none'):")
        try:
            msg = await bot.wait_for("message", timeout=120.0, check=check)
            image = msg.content.strip() if msg.content.strip().lower() != "none" else None
        except Exception:
            image = None

        event_data = {
            "title": title,
            "category": category,
            "image": image,
            "start_date": start_unix,
            "end_date": end_unix,
        }

        await ak_module.add_event(ctx, event_data)

        # Update dashboard
        guild = ctx.guild or bot.get_guild(ak_module.main_server_id)
        if guild:
            await ak_module.update_dashboard(guild)

    @bot.command(name="ak_remove")
    @commands.has_permissions(manage_guild=True)
    async def ak_remove(ctx: commands.Context, *, title: str):
        """
        Removes an Arknights event by title (case-insensitive).
        Usage: Kanami ak_remove <title>
        """
        success = await ak_module.remove_event(ctx, title)
        if success:
            guild = ctx.guild or bot.get_guild(ak_module.main_server_id)
            if guild:
                await ak_module.update_dashboard(guild)

    @bot.command(name="ak_refresh")
    @commands.has_permissions(manage_guild=True)
    async def ak_refresh(ctx: commands.Context):
        """
        Refreshes all Arknights event dashboards.
        Usage: Kanami ak_refresh
        """
        guild = ctx.guild or bot.get_guild(ak_module.main_server_id)
        if guild:
            await ak_module.update_dashboard(guild)
            await ctx.send("Arknights event dashboards have been refreshed.")
        else:
            await ctx.send("Could not find guild to refresh.")

    @bot.command(name="ak_list")
    async def ak_list(ctx: commands.Context):
        """
        Lists all Arknights events.
        Usage: Kanami ak_list
        """
        events = await ak_module.repository.get_all_events()

        if not events:
            await ctx.send("No Arknights events found.")
            return

        embed = discord.Embed(
            title="Arknights Events",
            color=discord.Color.blue()
        )

        for event in events[:25]:  # Discord embed limit
            embed.add_field(
                name=f"{event['title']} ({event['category']})",
                value=(
                    f"Start: <t:{event['start_date']}:R>\n"
                    f"End: <t:{event['end_date']}:R>"
                ),
                inline=False
            )

        await ctx.send(embed=embed)

    @bot.command(name="ak_edit")
    @commands.has_permissions(manage_guild=True)
    async def ak_edit(ctx: commands.Context, title: str, field: str, *, value: str):
        """
        Edit an Arknights event.
        Usage: Kanami ak_edit <title> <field> <value>
        Fields: title, start, end, category, image
        """
        event = await ak_module.repository.get_event_by_title(title)
        if not event:
            await ctx.send(f"No event found with title '{title}'.")
            return

        field = field.lower()
        event_data = dict(event)

        if field == "title":
            event_data["title"] = value
        elif field == "start":
            unix = ak_module.parse_date_string(value)
            if not unix:
                await ctx.send("Failed to parse start time.")
                return
            event_data["start_date"] = unix
        elif field == "end":
            unix = ak_module.parse_date_string(value)
            if not unix:
                await ctx.send("Failed to parse end time.")
                return
            event_data["end_date"] = unix
        elif field == "category":
            event_data["category"] = value.capitalize()
        elif field == "image":
            event_data["image"] = None if value.lower() == "none" else value
        else:
            await ctx.send(f"Unknown field: {field}. Use: title, start, end, category, image")
            return

        await ak_module.repository.update_event(event["id"], event_data)
        await ctx.send(f"Updated {field} for '{title}'.")

        # Update dashboard
        guild = ctx.guild or bot.get_guild(ak_module.main_server_id)
        if guild:
            await ak_module.update_dashboard(guild)

    @bot.command(name="ak_dump_db")
    async def ak_dump_db(ctx: commands.Context):
        """
        Sends the Arknights database contents to the owner's DM.
        Usage: Kanami ak_dump_db
        """
        if ctx.author.id != OWNER_ID:
            await ctx.send("You do not have permission to use this command.")
            return

        import os
        import aiosqlite

        db_path = ak_module.config.db_path
        if not os.path.exists(db_path):
            await ctx.author.send("No Arknights database file found.")
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
            await owner.send(f"Arknights DB Dump:\n```{chunk}```")

        await ctx.send("Database dump sent to your DM.")

    return {
        'ak_add': ak_add,
        'ak_remove': ak_remove,
        'ak_refresh': ak_refresh,
        'ak_list': ak_list,
        'ak_edit': ak_edit,
        'ak_dump_db': ak_dump_db,
    }
