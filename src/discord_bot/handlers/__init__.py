"""
Discord event handlers module.

This module provides event handler classes for Discord bot events:
- Message handling (auto-event detection, command preprocessing)
- Reaction handling (role reactions, confirmation reactions)
- Error handling (command errors, connection errors)
- Ready handling (bot initialization, status updates)

These handlers are designed to be registered with the bot instance
and delegate business logic to the appropriate services.
"""

from typing import Optional, Callable, Any, Dict, List
from abc import ABC, abstractmethod
import asyncio
import traceback
import discord
from discord.ext import commands


class BaseHandler(ABC):
    """Abstract base class for Discord event handlers."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @abstractmethod
    async def setup(self) -> None:
        """Register this handler with the bot."""
        pass


class ErrorHandler(BaseHandler):
    """
    Handles command and bot errors gracefully.

    Provides user-friendly error messages and logs errors for debugging.
    """

    def __init__(self, bot: commands.Bot, owner_id: Optional[int] = None):
        super().__init__(bot)
        self.owner_id = owner_id

    async def setup(self) -> None:
        """Register error handlers with the bot."""
        self.bot.add_listener(self.on_command_error, 'on_command_error')

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        """Handle command errors."""
        # Ignore commands that have their own error handlers
        if hasattr(ctx.command, 'on_error'):
            return

        # Get the original error if wrapped
        error = getattr(error, 'original', error)

        if isinstance(error, commands.CommandNotFound):
            # Silently ignore unknown commands
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                f"Missing required argument: `{error.param.name}`\n"
                f"Usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`"
            )
            return

        if isinstance(error, commands.BadArgument):
            await ctx.send(f"Invalid argument: {error}")
            return

        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to use this command.")
            return

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"Command on cooldown. Try again in {error.retry_after:.1f}s"
            )
            return

        if isinstance(error, discord.Forbidden):
            await ctx.send("I don't have permission to do that.")
            return

        if isinstance(error, discord.HTTPException):
            await ctx.send(f"Discord API error: {error}")
            return

        # Log unexpected errors
        print(f"[ERROR] Unexpected error in command {ctx.command}: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)

        await ctx.send(
            "An unexpected error occurred. The error has been logged."
        )


class ReactionHandler(BaseHandler):
    """
    Handles reaction events for role assignment and confirmations.

    Supports:
    - Role reactions (add/remove roles based on emoji reactions)
    - Confirmation reactions (yes/no prompts)
    - Re-read reactions (for tweet listener re-processing)
    """

    def __init__(
        self,
        bot: commands.Bot,
        role_config_repo=None,
        combined_role_config: Optional[Dict[str, Dict[str, int]]] = None,
    ):
        super().__init__(bot)
        self.role_config_repo = role_config_repo
        self.combined_role_config = combined_role_config or {}

    async def setup(self) -> None:
        """Register reaction handlers with the bot."""
        self.bot.add_listener(self.on_raw_reaction_add, 'on_raw_reaction_add')
        self.bot.add_listener(self.on_raw_reaction_remove, 'on_raw_reaction_remove')

    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> None:
        """Handle reaction additions."""
        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return

        # Check if this is a role reaction message
        if self.role_config_repo:
            await self._handle_role_reaction_add(payload)

    async def on_raw_reaction_remove(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> None:
        """Handle reaction removals."""
        if payload.user_id == self.bot.user.id:
            return

        if self.role_config_repo:
            await self._handle_role_reaction_remove(payload)

    async def _handle_role_reaction_add(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> None:
        """Handle role reaction additions."""
        role_config = await self.role_config_repo.get_role_reaction(
            payload.message_id,
            str(payload.emoji),
        )
        if not role_config:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member:
            return

        role = guild.get_role(role_config['role_id'])
        if role:
            try:
                await member.add_roles(role)
                # Update combined roles if applicable
                await self._update_combined_roles(member, guild)
            except discord.Forbidden:
                pass

    async def _handle_role_reaction_remove(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> None:
        """Handle role reaction removals."""
        role_config = await self.role_config_repo.get_role_reaction(
            payload.message_id,
            str(payload.emoji),
        )
        if not role_config:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member:
            return

        role = guild.get_role(role_config['role_id'])
        if role:
            try:
                await member.remove_roles(role)
                # Update combined roles if applicable
                await self._update_combined_roles(member, guild)
            except discord.Forbidden:
                pass

    async def _update_combined_roles(
        self,
        member: discord.Member,
        guild: discord.Guild,
    ) -> None:
        """Update combined roles (e.g., HSR + ASIA -> HSR_ASIA)."""
        if not self.combined_role_config:
            return

        member_role_ids = {role.id for role in member.roles}

        for combined_name, config in self.combined_role_config.items():
            game_role_id = config.get('game_role')
            region_role_id = config.get('region_role')
            combined_role_id = config.get('combined_role')

            if not all([game_role_id, region_role_id, combined_role_id]):
                continue

            combined_role = guild.get_role(combined_role_id)
            if not combined_role:
                continue

            has_game = game_role_id in member_role_ids
            has_region = region_role_id in member_role_ids
            has_combined = combined_role_id in member_role_ids

            try:
                if has_game and has_region and not has_combined:
                    await member.add_roles(combined_role)
                elif (not has_game or not has_region) and has_combined:
                    await member.remove_roles(combined_role)
            except discord.Forbidden:
                pass


class MessageHandler(BaseHandler):
    """
    Handles message events for auto-detection and preprocessing.

    Supports:
    - Twitter/X link detection for auto-event extraction
    - Listener channel monitoring
    - Message preprocessing before commands
    """

    def __init__(
        self,
        bot: commands.Bot,
        listener_channels: Optional[Dict[str, int]] = None,
        twitter_callback: Optional[Callable] = None,
    ):
        super().__init__(bot)
        self.listener_channels = listener_channels or {}
        self.twitter_callback = twitter_callback

    async def setup(self) -> None:
        """Register message handlers with the bot."""
        self.bot.add_listener(self.on_message, 'on_message')

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages."""
        # Ignore bot messages
        if message.author.bot:
            return

        # Check for Twitter/X links in listener channels
        if self.twitter_callback and message.channel.id in self.listener_channels.values():
            await self._check_twitter_links(message)

    async def _check_twitter_links(self, message: discord.Message) -> None:
        """Check message for Twitter/X links and process them."""
        twitter_patterns = [
            'twitter.com/',
            'x.com/',
            'fixupx.com/',
            'fxtwitter.com/',
            'vxtwitter.com/',
        ]

        content_lower = message.content.lower()
        for pattern in twitter_patterns:
            if pattern in content_lower:
                if self.twitter_callback:
                    await self.twitter_callback(message)
                break


class ReadyHandler(BaseHandler):
    """
    Handles bot ready event for initialization tasks.

    Supports:
    - Status updates
    - Background task initialization
    - Module startup callbacks
    """

    def __init__(
        self,
        bot: commands.Bot,
        startup_callbacks: Optional[List[Callable]] = None,
        status_message: Optional[str] = None,
    ):
        super().__init__(bot)
        self.startup_callbacks = startup_callbacks or []
        self.status_message = status_message

    async def setup(self) -> None:
        """Register ready handler with the bot."""
        self.bot.add_listener(self.on_ready, 'on_ready')

    async def on_ready(self) -> None:
        """Handle bot ready event."""
        print(f"[INFO] Logged in as {self.bot.user} (ID: {self.bot.user.id})")

        # Set status
        if self.status_message:
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=self.status_message,
                )
            )

        # Run startup callbacks
        for callback in self.startup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self.bot)
                else:
                    callback(self.bot)
            except Exception as e:
                print(f"[ERROR] Startup callback failed: {e}")
                traceback.print_exc()

        print("[INFO] Bot is ready!")


def setup_handlers(
    bot: commands.Bot,
    *,
    owner_id: Optional[int] = None,
    role_config_repo=None,
    combined_role_config: Optional[Dict] = None,
    listener_channels: Optional[Dict] = None,
    twitter_callback: Optional[Callable] = None,
    startup_callbacks: Optional[List[Callable]] = None,
    status_message: Optional[str] = None,
) -> Dict[str, BaseHandler]:
    """
    Set up all handlers for the bot.

    Args:
        bot: The Discord bot instance
        owner_id: Bot owner's Discord ID for error notifications
        role_config_repo: Repository for role reaction configuration
        combined_role_config: Configuration for combined roles (game+region)
        listener_channels: Channel IDs to monitor for Twitter links
        twitter_callback: Callback function for processing Twitter links
        startup_callbacks: Functions to call when bot is ready
        status_message: Bot status message to display

    Returns:
        Dictionary of handler name -> handler instance
    """
    handlers = {}

    # Error handler
    error_handler = ErrorHandler(bot, owner_id)
    handlers['error'] = error_handler

    # Reaction handler
    reaction_handler = ReactionHandler(
        bot,
        role_config_repo,
        combined_role_config,
    )
    handlers['reaction'] = reaction_handler

    # Message handler
    message_handler = MessageHandler(
        bot,
        listener_channels,
        twitter_callback,
    )
    handlers['message'] = message_handler

    # Ready handler
    ready_handler = ReadyHandler(
        bot,
        startup_callbacks,
        status_message,
    )
    handlers['ready'] = ready_handler

    return handlers


async def register_handlers(handlers: Dict[str, BaseHandler]) -> None:
    """Register all handlers with the bot."""
    for name, handler in handlers.items():
        try:
            await handler.setup()
            print(f"[INFO] Registered {name} handler")
        except Exception as e:
            print(f"[ERROR] Failed to register {name} handler: {e}")


__all__ = [
    'BaseHandler',
    'ErrorHandler',
    'ReactionHandler',
    'MessageHandler',
    'ReadyHandler',
    'setup_handlers',
    'register_handlers',
]
