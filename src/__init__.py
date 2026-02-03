"""
Gacha Timer Bot - Refactored Source Package

This package contains the refactored, modular implementation of the Gacha Timer Bot.

Package structure:
- core/: Core business logic (models, interfaces, repositories, services)
- discord_bot/: Discord-specific code (commands, formatters, UI components, handlers)
- games/: Game-specific modules (HSR, Arknights, ZZZ, STRI, WUWA, Uma Musume, Shadowverse)
- integrations/: External service integrations (Twitter, ML, Web scrapers)
- api/: REST API routes and middleware
- utils/: Shared utilities (logging, database helpers, constants)

Usage:
    from src.core.models import Event, Notification
    from src.core.repositories import SQLiteEventRepository
    from src.core.services import EventService, NotificationService
    from src.discord_bot.commands import setup_all_commands
    from src.discord_bot.handlers import setup_handlers
    from src.games import HSRModule, ArknightsModule, create_zzz_module
    from src.api import create_api_server
    from src.utils import setup_logging, get_db_connection
"""

__version__ = "3.0.0"
__author__ = "Bloosh"

# Convenience imports for common use cases
from src.core.models import Event, Notification, GameProfile, EventCategory
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
    TimezoneService,
    ValidationService,
)
from src.discord_bot.commands import setup_all_commands
from src.discord_bot.handlers import setup_handlers, register_handlers
from src.games import (
    GameConfig,
    GameModule,
    HSRModule,
    ArknightsModule,
    GenericGameModule,
    GenericHoyoverseModule,
    create_zzz_module,
    create_stri_module,
    create_wuwa_module,
)
from src.api import create_api_server, APIServer
from src.utils import (
    setup_logging,
    get_logger,
    get_db_connection,
    VALID_PROFILES,
    HYV_PROFILES,
    BOT_VERSION,
)

__all__ = [
    # Version
    '__version__',
    '__author__',
    # Models
    'Event',
    'Notification',
    'GameProfile',
    'EventCategory',
    # Repositories
    'SQLiteEventRepository',
    'SQLiteNotificationRepository',
    'SQLiteConfigRepository',
    'ChannelRepository',
    # Services
    'EventService',
    'NotificationService',
    'NotificationScheduler',
    'TimezoneService',
    'ValidationService',
    # Discord
    'setup_all_commands',
    'setup_handlers',
    'register_handlers',
    # Games
    'GameConfig',
    'GameModule',
    'HSRModule',
    'ArknightsModule',
    'GenericGameModule',
    'GenericHoyoverseModule',
    'create_zzz_module',
    'create_stri_module',
    'create_wuwa_module',
    # API
    'create_api_server',
    'APIServer',
    # Utils
    'setup_logging',
    'get_logger',
    'get_db_connection',
    'VALID_PROFILES',
    'HYV_PROFILES',
    'BOT_VERSION',
]
