"""
Base command utilities and shared functionality.

This module provides common utilities for Discord commands including
permission checks, validation helpers, and shared patterns.
"""

import discord
from discord.ext import commands
from typing import Optional, Callable, Awaitable
import functools

# Bot owner ID
OWNER_ID = 680653908259110914

# Valid game profiles
VALID_PROFILES = ["HSR", "ZZZ", "AK", "STRI", "WUWA", "UMA", "ALL"]

# HYV (Hoyoverse) games that have regional servers
HYV_PROFILES = {"HSR", "ZZZ", "WUWA"}


def owner_only():
    """Decorator to restrict commands to bot owner only."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id != OWNER_ID:
            await ctx.send("You don't get to use this command!")
            return False
        return True
    return commands.check(predicate)


def is_owner(user_id: int) -> bool:
    """Check if a user is the bot owner."""
    return user_id == OWNER_ID


async def confirm_action(
    ctx: commands.Context,
    bot: commands.Bot,
    message: str,
    timeout: float = 30.0
) -> bool:
    """
    Ask for confirmation with reaction-based response.

    Args:
        ctx: Command context
        bot: Bot instance
        message: Confirmation message to display
        timeout: Seconds to wait for response

    Returns:
        True if confirmed, False otherwise
    """
    confirm_msg = await ctx.send(message)
    await confirm_msg.add_reaction("✅")
    await confirm_msg.add_reaction("❌")

    def check(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == confirm_msg.id
            and str(reaction.emoji) in ["✅", "❌"]
        )

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=timeout, check=check)
        confirmed = str(reaction.emoji) == "✅"
    except Exception:
        await confirm_msg.edit(content=f"{message}\n\n*Cancelled (no response)*")
        await confirm_msg.delete(delay=3)
        return False

    if not confirmed:
        await confirm_msg.edit(content=f"{message}\n\n*Cancelled*")
        await confirm_msg.delete(delay=2)
    else:
        await confirm_msg.delete()

    return confirmed


async def prompt_for_input(
    ctx: commands.Context,
    bot: commands.Bot,
    prompt: str,
    timeout: float = 60.0,
    validator: Optional[Callable[[str], bool]] = None,
    error_message: str = "Invalid input."
) -> Optional[str]:
    """
    Prompt user for text input.

    Args:
        ctx: Command context
        bot: Bot instance
        prompt: Message to display
        timeout: Seconds to wait for response
        validator: Optional function to validate input
        error_message: Message to show if validation fails

    Returns:
        User's response or None if cancelled/timed out
    """
    await ctx.send(prompt)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", timeout=timeout, check=check)
        value = msg.content.strip()

        if validator and not validator(value):
            await ctx.send(error_message)
            return None

        return value
    except Exception:
        await ctx.send("Timed out waiting for response. Cancelling.")
        return None


async def prompt_for_profile(
    ctx: commands.Context,
    bot: commands.Bot,
    timeout: float = 60.0
) -> Optional[str]:
    """
    Prompt user to select a game profile.

    Args:
        ctx: Command context
        bot: Bot instance
        timeout: Seconds to wait for response

    Returns:
        Selected profile or None if cancelled
    """
    profiles_str = ", ".join(VALID_PROFILES)
    prompt = f"Which profile is this event for? (Type one of: {profiles_str})"

    def validator(value: str) -> bool:
        return value.upper() in VALID_PROFILES

    result = await prompt_for_input(
        ctx, bot, prompt, timeout,
        validator=validator,
        error_message=f"Invalid profile. Please choose from: {profiles_str}"
    )

    return result.upper() if result else None


async def prompt_for_category(
    ctx: commands.Context,
    bot: commands.Bot,
    valid_categories: Optional[list] = None,
    timeout: float = 60.0
) -> Optional[str]:
    """
    Prompt user for event category.

    Args:
        ctx: Command context
        bot: Bot instance
        valid_categories: Optional list of valid categories
        timeout: Seconds to wait for response

    Returns:
        Category name or None if cancelled
    """
    if valid_categories:
        categories_str = ", ".join(valid_categories)
        prompt = f"What category is this event? ({categories_str})"
    else:
        prompt = "What category is this event? (e.g. Banner, Event, Maintenance, etc.)"

    return await prompt_for_input(ctx, bot, prompt, timeout)


def is_hyv_profile(profile: str) -> bool:
    """Check if a profile is a Hoyoverse game with regional servers."""
    return profile.upper() in HYV_PROFILES


class CommandError(Exception):
    """Base exception for command errors."""

    def __init__(self, message: str, should_send: bool = True):
        self.message = message
        self.should_send = should_send
        super().__init__(message)


class ValidationError(CommandError):
    """Raised when validation fails."""
    pass


class NotFoundError(CommandError):
    """Raised when a resource is not found."""
    pass


class PermissionError(CommandError):
    """Raised when user lacks permission."""
    pass
