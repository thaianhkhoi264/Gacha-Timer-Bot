"""
Configuration commands for the Gacha Timer Bot.

This module contains commands for configuring channels and roles:
- assign: Assign announcement channel
- set_timer_channel: Set timer display channel
- set_notification_channel: Set notification channel
- check_channels: View configured channels
- Role assignment commands
"""

import discord
from discord.ext import commands
from typing import Optional, Dict

from .base import (
    prompt_for_profile,
    VALID_PROFILES,
)
from src.core.repositories import SQLiteConfigRepository


def setup_config_commands(
    bot: commands.Bot,
    config_repo: SQLiteConfigRepository,
):
    """
    Register configuration commands with the bot.

    Args:
        bot: The bot instance
        config_repo: Config repository instance
    """

    @bot.command(name="assign")
    async def assign(ctx: commands.Context):
        """
        Assigns this channel for bot announcements.
        Usage: Kanami assign
        """
        server_id = str(ctx.guild.id)
        channel_id = str(ctx.channel.id)

        try:
            await config_repo.set_announce_channel(server_id, channel_id)
            await ctx.send(
                f"This channel ({ctx.channel.mention}) has been assigned "
                f"as the announcement channel for this server."
            )
        except Exception as e:
            await ctx.send(f"Error assigning channel: {e}")

    @bot.command(name="set_timer_channel")
    async def set_timer_channel(
        ctx: commands.Context,
        channel: discord.TextChannel,
        profile: str = "ALL"
    ):
        """
        Sets the timer channel for a specific profile.
        Usage: Kanami set_timer_channel #channel [profile]
        """
        server_id = str(ctx.guild.id)

        if profile.upper() not in VALID_PROFILES:
            await ctx.send(
                f"Invalid profile `{profile}`. "
                f"Valid profiles: {', '.join(VALID_PROFILES)}"
            )
            return

        try:
            await config_repo.set_timer_channel(
                server_id, profile.upper(), str(channel.id)
            )
            await ctx.send(
                f"Timer channel for **{profile.upper()}** has been set to {channel.mention}."
            )
        except Exception as e:
            await ctx.send(f"Error setting timer channel: {e}")

    @bot.command(name="set_notification_channel")
    async def set_notification_channel(
        ctx: commands.Context,
        channel: discord.TextChannel,
        profile: str = None
    ):
        """
        Sets the notification channel for a profile.
        Usage: Kanami set_notification_channel #channel [profile]
        """
        server_id = str(ctx.guild.id)

        if not profile:
            profile = await prompt_for_profile(ctx, bot)
            if not profile:
                return

        if profile.upper() not in VALID_PROFILES:
            await ctx.send(
                f"Invalid profile `{profile}`. "
                f"Valid profiles: {', '.join(VALID_PROFILES)}"
            )
            return

        try:
            await config_repo.set_notification_channel(
                server_id, profile.upper(), str(channel.id)
            )
            await ctx.send(
                f"Notification channel for **{profile.upper()}** "
                f"has been set to {channel.mention}."
            )
        except Exception as e:
            await ctx.send(f"Error setting notification channel: {e}")

    @bot.command(name="check_channels")
    async def check_channels(ctx: commands.Context):
        """
        Shows all configured channels for this server.
        Usage: Kanami check_channels
        """
        server_id = str(ctx.guild.id)

        embed = discord.Embed(
            title="Channel Configuration",
            description="Current channel assignments for this server",
            color=discord.Color.blurple()
        )

        try:
            # Announcement channel
            announce_id = await config_repo.get_announce_channel(server_id)
            if announce_id:
                announce_channel = ctx.guild.get_channel(int(announce_id))
                announce_text = announce_channel.mention if announce_channel else f"ID: {announce_id} (not found)"
            else:
                announce_text = "Not set"
            embed.add_field(
                name="Announcement Channel",
                value=announce_text,
                inline=False
            )

            # Timer channels
            timer_channels = await config_repo.get_all_timer_channels(server_id)
            if timer_channels:
                timer_lines = []
                for profile, channel_id in timer_channels.items():
                    channel = ctx.guild.get_channel(int(channel_id))
                    channel_text = channel.mention if channel else f"ID: {channel_id} (not found)"
                    timer_lines.append(f"**{profile}**: {channel_text}")
                embed.add_field(
                    name="Timer Channels",
                    value="\n".join(timer_lines),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Timer Channels",
                    value="None configured",
                    inline=False
                )

            # Notification channels (check for each profile)
            notif_lines = []
            for profile in VALID_PROFILES:
                if profile == "ALL":
                    continue
                channel_id = await config_repo.get_notification_channel_for_server(
                    server_id, profile
                )
                if channel_id:
                    channel = ctx.guild.get_channel(int(channel_id))
                    channel_text = channel.mention if channel else f"ID: {channel_id}"
                    notif_lines.append(f"**{profile}**: {channel_text}")

            if notif_lines:
                embed.add_field(
                    name="Notification Channels",
                    value="\n".join(notif_lines),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Notification Channels",
                    value="None configured",
                    inline=False
                )

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"Error checking channels: {e}")

    @bot.command(name="set_listener_channel")
    async def set_listener_channel(
        ctx: commands.Context,
        channel: discord.TextChannel,
        profile: str = None
    ):
        """
        Sets the Twitter/X listener channel for a profile.
        Usage: Kanami set_listener_channel #channel [profile]
        """
        server_id = str(ctx.guild.id)

        if not profile:
            profile = await prompt_for_profile(ctx, bot)
            if not profile:
                return

        if profile.upper() not in VALID_PROFILES:
            await ctx.send(
                f"Invalid profile `{profile}`. "
                f"Valid profiles: {', '.join(VALID_PROFILES)}"
            )
            return

        try:
            await config_repo.set_listener_channel(
                server_id, profile.upper(), str(channel.id)
            )
            await ctx.send(
                f"Listener channel for **{profile.upper()}** "
                f"has been set to {channel.mention}."
            )
        except Exception as e:
            await ctx.send(f"Error setting listener channel: {e}")

    @bot.command(name="set_control_panel")
    async def set_control_panel(
        ctx: commands.Context,
        channel: discord.TextChannel,
        profile: str = None
    ):
        """
        Sets the control panel channel for a profile.
        Usage: Kanami set_control_panel #channel [profile]
        """
        server_id = str(ctx.guild.id)

        if not profile:
            profile = await prompt_for_profile(ctx, bot)
            if not profile:
                return

        if profile.upper() not in VALID_PROFILES:
            await ctx.send(
                f"Invalid profile `{profile}`. "
                f"Valid profiles: {', '.join(VALID_PROFILES)}"
            )
            return

        try:
            # Send a placeholder message for the control panel
            panel_msg = await channel.send(
                f"Control panel for **{profile.upper()}** will be initialized here."
            )

            await config_repo.set_control_panel(
                server_id, profile.upper(), str(channel.id), str(panel_msg.id)
            )
            await ctx.send(
                f"Control panel for **{profile.upper()}** "
                f"has been set up in {channel.mention}."
            )
        except Exception as e:
            await ctx.send(f"Error setting control panel: {e}")

    @bot.command(name="add_role_reaction")
    async def add_role_reaction(
        ctx: commands.Context,
        message_id: str,
        emoji: str,
        role: discord.Role
    ):
        """
        Adds a role reaction mapping.
        Usage: Kanami add_role_reaction <message_id> <emoji> @Role
        """
        server_id = str(ctx.guild.id)

        try:
            await config_repo.set_role_reaction(
                server_id, message_id, emoji, str(role.id)
            )
            await ctx.send(
                f"Role reaction added: {emoji} → {role.mention}"
            )
        except Exception as e:
            await ctx.send(f"Error adding role reaction: {e}")

    @bot.command(name="check_role_reactions")
    async def check_role_reactions(ctx: commands.Context):
        """
        Shows all configured role reactions for this server.
        Usage: Kanami check_role_reactions
        """
        server_id = str(ctx.guild.id)

        try:
            reactions = await config_repo.get_all_role_reactions(server_id)

            if not reactions:
                await ctx.send("No role reactions configured for this server.")
                return

            embed = discord.Embed(
                title="Role Reactions",
                description="Current role reaction mappings",
                color=discord.Color.blurple()
            )

            for reaction in reactions:
                role = ctx.guild.get_role(int(reaction["role_id"]))
                role_text = role.mention if role else f"ID: {reaction['role_id']}"
                embed.add_field(
                    name=f"{reaction['emoji']}",
                    value=f"Role: {role_text}\nMessage ID: {reaction['message_id']}",
                    inline=True
                )

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"Error checking role reactions: {e}")

    return {
        'assign': assign,
        'set_timer_channel': set_timer_channel,
        'set_notification_channel': set_notification_channel,
        'check_channels': check_channels,
        'set_listener_channel': set_listener_channel,
        'set_control_panel': set_control_panel,
        'add_role_reaction': add_role_reaction,
        'check_role_reactions': check_role_reactions,
    }
