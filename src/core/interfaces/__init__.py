"""
Core interfaces package for the Gacha Timer Bot.

This package contains abstract interfaces (protocols) following SOLID principles,
specifically the Dependency Inversion Principle (DIP) and Interface Segregation Principle (ISP).
"""

from .database_interface import (
    EventRepository,
    NotificationRepository,
    ConfigRepository,
)
from .scraper_interface import (
    EventScraper,
    WebScraper,
    APIScrap,
    LLMScraper,
    ScraperError,
    ScraperConnectionError,
    ScraperParseError,
)
from .notifier_interface import (
    Notifier,
    DiscordNotifier,
    WebhookNotifier,
    NotifierError,
    NotifierConnectionError,
    NotifierSendError,
)

__all__ = [
    # Database interfaces
    'EventRepository',
    'NotificationRepository',
    'ConfigRepository',
    # Scraper interfaces
    'EventScraper',
    'WebScraper',
    'APIScrap',
    'LLMScraper',
    'ScraperError',
    'ScraperConnectionError',
    'ScraperParseError',
    # Notifier interfaces
    'Notifier',
    'DiscordNotifier',
    'WebhookNotifier',
    'NotifierError',
    'NotifierConnectionError',
    'NotifierSendError',
]
