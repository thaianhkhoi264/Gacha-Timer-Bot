"""
Core package for the Gacha Timer Bot.

This package contains the core business logic following SOLID principles:
- models: Domain entities (Event, Notification, etc.)
- interfaces: Abstract base classes (repositories, scrapers, notifiers)
- repositories: Data access layer implementations
- services: Business logic layer
"""

from .models import (
    # Enums
    GameProfile,
    EventCategory,
    Region,
    NotificationTimingType,
    HoyoverseGame,
    # Models
    Event,
    Notification,
)

from .interfaces import (
    # Database interfaces
    EventRepository,
    NotificationRepository,
    ConfigRepository,
    # Scraper interfaces
    EventScraper,
    WebScraper,
    APIScrap,
    LLMScraper,
    # Notifier interfaces
    Notifier,
    DiscordNotifier,
    WebhookNotifier,
)

from .repositories import (
    # Base
    BaseRepository,
    # Concrete repositories
    SQLiteEventRepository,
    ProfileEventRepository,
    SQLiteNotificationRepository,
    SQLiteConfigRepository,
    ChannelRepository,
)

from .services import (
    # Timezone
    TimezoneService,
    # Scheduling
    NotificationScheduler,
    UmaScheduler,
    ChampionsMeetingPhase,
    LegendRaceCharacter,
    # Services
    EventService,
    NotificationService,
    ValidationService,
    ValidationError,
    ValidationResult,
)

__all__ = [
    # Models
    'GameProfile',
    'EventCategory',
    'Region',
    'NotificationTimingType',
    'HoyoverseGame',
    'Event',
    'Notification',
    # Interfaces
    'EventRepository',
    'NotificationRepository',
    'ConfigRepository',
    'EventScraper',
    'WebScraper',
    'APIScrap',
    'LLMScraper',
    'Notifier',
    'DiscordNotifier',
    'WebhookNotifier',
    # Repositories
    'BaseRepository',
    'SQLiteEventRepository',
    'ProfileEventRepository',
    'SQLiteNotificationRepository',
    'SQLiteConfigRepository',
    'ChannelRepository',
    # Services
    'TimezoneService',
    'NotificationScheduler',
    'UmaScheduler',
    'ChampionsMeetingPhase',
    'LegendRaceCharacter',
    'EventService',
    'NotificationService',
    'ValidationService',
    'ValidationError',
    'ValidationResult',
]
