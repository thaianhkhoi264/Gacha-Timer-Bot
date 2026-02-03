"""
Application initialization module.

This module provides functions to initialize the refactored Gacha Timer Bot
with all its components wired together properly.

Usage:
    from src.app import create_bot_app

    bot, repos, services, modules = await create_bot_app()
    bot.run(token)
"""

import os
import asyncio
from typing import Dict, Any, Tuple, Optional

from src.core.repositories import (
    SQLiteEventRepository,
    SQLiteNotificationRepository,
    SQLiteConfigRepository,
    ChannelRepository,
)
from src.core.services import (
    EventService,
    NotificationService,
    NotificationScheduler,
)
from src.discord_bot.commands import setup_all_commands
from src.discord_bot.handlers import setup_handlers, register_handlers
from src.games import HSRModule, ArknightsModule
from src.games.generic import create_zzz_module, create_stri_module, create_wuwa_module
from src.api import create_api_server


async def initialize_repositories(db_path: str = "kanami_data.db") -> Dict[str, Any]:
    """
    Initialize all repositories.

    Args:
        db_path: Path to the main database file

    Returns:
        Dictionary containing initialized repository instances
    """
    repos = {
        "event": SQLiteEventRepository(db_path),
        "notification": SQLiteNotificationRepository(db_path),
        "config": SQLiteConfigRepository(db_path),
        "channel": ChannelRepository(db_path),
    }

    # Initialize all repositories
    await repos["event"].initialize()
    await repos["notification"].initialize()
    await repos["config"].initialize()
    await repos["channel"].initialize()

    return repos


async def initialize_services(repos: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initialize all services with their dependencies.

    Args:
        repos: Dictionary of initialized repositories

    Returns:
        Dictionary containing initialized service instances
    """
    scheduler = NotificationScheduler()

    services = {
        "scheduler": scheduler,
        "event": EventService(
            repos["event"],
            repos["notification"],
            scheduler,
        ),
        "notification": NotificationService(repos["notification"]),
    }

    return services


async def initialize_game_modules(
    main_server_id: int,
    channel_config: Dict[str, Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Initialize all game modules.

    Args:
        main_server_id: Main Discord server ID
        channel_config: Dictionary of channel IDs per game profile

    Returns:
        Dictionary containing initialized game module instances
    """
    if channel_config is None:
        channel_config = {}

    modules = {}

    # HSR Module
    hsr_config = channel_config.get("HSR", {})
    hsr_module = HSRModule(
        ongoing_channel_id=hsr_config.get("ongoing"),
        upcoming_channel_id=hsr_config.get("upcoming"),
        main_server_id=main_server_id,
    )
    await hsr_module.initialize()
    modules["hsr"] = hsr_module

    # Arknights Module
    ak_config = channel_config.get("AK", {})
    ak_module = ArknightsModule(
        ongoing_channel_id=ak_config.get("ongoing"),
        upcoming_channel_id=ak_config.get("upcoming"),
        main_server_id=main_server_id,
    )
    await ak_module.initialize()
    modules["arknights"] = ak_module

    # ZZZ Module (Hoyoverse, regional servers)
    zzz_config = channel_config.get("ZZZ", {})
    zzz_module = create_zzz_module(
        ongoing_channel_id=zzz_config.get("ongoing"),
        upcoming_channel_id=zzz_config.get("upcoming"),
        main_server_id=main_server_id,
    )
    await zzz_module.initialize()
    modules["zzz"] = zzz_module

    # STRI Module (Strinova)
    stri_config = channel_config.get("STRI", {})
    stri_module = create_stri_module(
        ongoing_channel_id=stri_config.get("ongoing"),
        upcoming_channel_id=stri_config.get("upcoming"),
        main_server_id=main_server_id,
    )
    await stri_module.initialize()
    modules["stri"] = stri_module

    # WUWA Module (Wuthering Waves)
    wuwa_config = channel_config.get("WUWA", {})
    wuwa_module = create_wuwa_module(
        ongoing_channel_id=wuwa_config.get("ongoing"),
        upcoming_channel_id=wuwa_config.get("upcoming"),
        main_server_id=main_server_id,
    )
    await wuwa_module.initialize()
    modules["wuwa"] = wuwa_module

    return modules


def setup_bot_commands(
    bot,
    repos: Dict[str, Any],
    services: Dict[str, Any],
    modules: Dict[str, Any],
    bot_version: str = "3.0.0",
):
    """
    Set up all bot commands.

    Args:
        bot: Discord bot instance
        repos: Dictionary of repositories
        services: Dictionary of services
        modules: Dictionary of game modules
        bot_version: Bot version string
    """
    # Import game command setup functions
    from src.games.hsr import setup_hsr_commands
    from src.games.arknights import setup_arknights_commands

    # Set up core commands
    setup_all_commands(
        bot,
        event_repo=repos["event"],
        notification_repo=repos["notification"],
        config_repo=repos["config"],
        bot_version=bot_version,
    )

    # Set up game-specific commands
    setup_hsr_commands(bot, modules["hsr"])
    setup_arknights_commands(bot, modules["arknights"])


async def create_bot_app(
    bot,
    main_server_id: int,
    channel_config: Dict[str, Dict[str, int]] = None,
    db_path: str = "kanami_data.db",
    bot_version: str = "3.0.0",
    owner_id: Optional[int] = None,
    api_port: int = 8080,
    enable_api: bool = True,
    status_message: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Create and initialize the full bot application.

    Args:
        bot: Discord bot instance
        main_server_id: Main Discord server ID
        channel_config: Dictionary of channel IDs per game profile
        db_path: Path to the main database file
        bot_version: Bot version string
        owner_id: Bot owner's Discord ID
        api_port: Port for the REST API server
        enable_api: Whether to start the API server
        status_message: Bot status message to display

    Returns:
        Tuple of (repos, services, modules)
    """
    # Initialize components in order
    repos = await initialize_repositories(db_path)
    services = await initialize_services(repos)
    modules = await initialize_game_modules(main_server_id, channel_config)

    # Set up commands
    setup_bot_commands(bot, repos, services, modules, bot_version)

    # Set up event handlers
    handlers = setup_handlers(
        bot,
        owner_id=owner_id,
        status_message=status_message or f"v{bot_version}",
    )
    await register_handlers(handlers)

    # Start API server
    if enable_api:
        try:
            app, runner = await create_api_server(
                port=api_port,
                bot_instance=bot,
            )
            services["api_runner"] = runner
        except Exception as e:
            print(f"[WARNING] Failed to start API server: {e}")

    return repos, services, modules


async def on_ready_handler(
    bot,
    modules: Dict[str, Any],
):
    """
    Handler for bot on_ready event to initialize background tasks.

    Args:
        bot: Discord bot instance
        modules: Dictionary of game modules
    """
    # Initialize module background tasks
    for name, module in modules.items():
        try:
            await module.on_ready(bot)
            print(f"[DEBUG] {name.upper()} module on_ready completed.")
        except Exception as e:
            print(f"[ERROR] {name.upper()} module on_ready failed: {e}")


# Example usage in main.py:
"""
from discord.ext import commands
from src.app import create_bot_app, on_ready_handler
from global_config import (
    MAIN_SERVER_ID,
    ONGOING_EVENTS_CHANNELS,
    UPCOMING_EVENTS_CHANNELS,
    OWNER_ID,
)

bot = commands.Bot(command_prefix="Kanami ", ...)

@bot.event
async def on_ready():
    # Initialize the refactored components
    repos, services, modules = await create_bot_app(
        bot,
        main_server_id=MAIN_SERVER_ID,
        channel_config={
            "HSR": {
                "ongoing": ONGOING_EVENTS_CHANNELS.get("HSR"),
                "upcoming": UPCOMING_EVENTS_CHANNELS.get("HSR"),
            },
            "AK": {
                "ongoing": ONGOING_EVENTS_CHANNELS.get("AK"),
                "upcoming": UPCOMING_EVENTS_CHANNELS.get("AK"),
            },
            "ZZZ": {
                "ongoing": ONGOING_EVENTS_CHANNELS.get("ZZZ"),
                "upcoming": UPCOMING_EVENTS_CHANNELS.get("ZZZ"),
            },
            "STRI": {
                "ongoing": ONGOING_EVENTS_CHANNELS.get("STRI"),
                "upcoming": UPCOMING_EVENTS_CHANNELS.get("STRI"),
            },
            "WUWA": {
                "ongoing": ONGOING_EVENTS_CHANNELS.get("WUWA"),
                "upcoming": UPCOMING_EVENTS_CHANNELS.get("WUWA"),
            },
        },
        bot_version="3.0.0",
        owner_id=OWNER_ID,
        api_port=8080,
    )

    # Run module initialization
    await on_ready_handler(bot, modules)

    print("Bot is ready!")

bot.run(token)
"""
