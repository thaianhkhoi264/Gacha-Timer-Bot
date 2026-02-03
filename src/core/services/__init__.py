"""
Services package for the Gacha Timer Bot.

This package contains the business logic layer following SOLID principles:
- timezone_service: Timezone conversions for HYV games
- notification_scheduler: Calculate notification timings
- uma_scheduler: Champions Meeting and Legend Race scheduling
- event_service: High-level event operations
- notification_service: Notification processing and cleanup
- validation_service: Data validation and normalization
"""

from .timezone_service import (
    TimezoneService,
    HYV_TIMEZONES,
    HYV_PROFILES,
)

from .notification_scheduler import (
    NotificationScheduler,
    NotificationTiming,
    NOTIFICATION_TIMINGS,
    UMA_NOTIFICATION_TIMINGS,
    HYV_REGIONS,
)

from .uma_scheduler import (
    UmaScheduler,
    ChampionsMeetingPhase,
    LegendRaceCharacter,
)

from .event_service import EventService

from .notification_service import (
    NotificationService,
    NotificationBatch,
)

from .validation_service import (
    ValidationService,
    ValidationError,
    ValidationResult,
)


__all__ = [
    # Timezone
    'TimezoneService',
    'HYV_TIMEZONES',
    'HYV_PROFILES',
    # Notification scheduling
    'NotificationScheduler',
    'NotificationTiming',
    'NOTIFICATION_TIMINGS',
    'UMA_NOTIFICATION_TIMINGS',
    'HYV_REGIONS',
    # Uma scheduling
    'UmaScheduler',
    'ChampionsMeetingPhase',
    'LegendRaceCharacter',
    # Services
    'EventService',
    'NotificationService',
    'NotificationBatch',
    'ValidationService',
    'ValidationError',
    'ValidationResult',
]
