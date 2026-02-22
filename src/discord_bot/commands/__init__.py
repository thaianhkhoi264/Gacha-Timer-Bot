"""
Discord bot commands for the Gacha Timer Bot.

This package provides organized command modules following the refactoring plan:
- base: Shared utilities and decorators
- event_commands: Event management (add, remove, edit)
- config_commands: Channel and role configuration
- utility_commands: General utilities (help, purge, convert)
- admin_commands: Owner-only administrative commands
"""

from .base import (
    OWNER_ID,
    VALID_PROFILES,
    HYV_PROFILES,
    owner_only,
    is_owner,
    confirm_action,
    prompt_for_input,
    prompt_for_profile,
    prompt_for_category,
    is_hyv_profile,
    CommandError,
    ValidationError,
    NotFoundError,
    PermissionError,
)

from .event_commands import setup_event_commands
from .config_commands import setup_config_commands
from .utility_commands import setup_utility_commands
from .admin_commands import setup_admin_commands


def setup_all_commands(
    bot,
    event_repo=None,
    notification_repo=None,
    config_repo=None,
    bot_version: str = "2.7.0",
    update_timer_channel_func=None,
):
    """
    Register all commands with the bot.

    This is a convenience function to set up all command modules at once.

    Args:
        bot: The Discord bot instance
        event_repo: SQLiteEventRepository instance
        notification_repo: SQLiteNotificationRepository instance
        config_repo: SQLiteConfigRepository instance
        bot_version: Current bot version string
        update_timer_channel_func: Function to update timer channels

    Returns:
        Dictionary of all registered commands
    """
    all_commands = {}

    # Setup utility commands (no dependencies)
    all_commands.update(setup_utility_commands(bot, bot_version))

    # Setup admin commands (no dependencies)
    all_commands.update(setup_admin_commands(bot))

    # Setup config commands (requires config_repo)
    if config_repo:
        all_commands.update(setup_config_commands(bot, config_repo))

    # Setup event commands (requires all repos)
    if event_repo and notification_repo and config_repo:
        all_commands.update(setup_event_commands(
            bot,
            event_repo,
            notification_repo,
            config_repo,
            update_timer_channel_func,
        ))

    return all_commands


__all__ = [
    # Base utilities
    'OWNER_ID',
    'VALID_PROFILES',
    'HYV_PROFILES',
    'owner_only',
    'is_owner',
    'confirm_action',
    'prompt_for_input',
    'prompt_for_profile',
    'prompt_for_category',
    'is_hyv_profile',
    'CommandError',
    'ValidationError',
    'NotFoundError',
    'PermissionError',
    # Setup functions
    'setup_event_commands',
    'setup_config_commands',
    'setup_utility_commands',
    'setup_admin_commands',
    'setup_all_commands',
]
