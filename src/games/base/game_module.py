"""
Abstract base class for all game modules.

This module defines the GameModule interface that all game-specific modules
must implement. It follows the Open/Closed Principle (OCP) - new games can be
added by extending this class without modifying core code.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import os
import logging


@dataclass
class GameConfig:
    """Configuration for a game module."""
    profile: str
    db_path: str
    log_name: str
    display_name: str
    has_regional_servers: bool = False
    regions: List[str] = None
    update_interval_hours: int = 6

    def __post_init__(self):
        if self.regions is None:
            self.regions = []
        if self.has_regional_servers and not self.regions:
            self.regions = ["ASIA", "NA", "EU"]


class GameModule(ABC):
    """
    Abstract base class for all game modules.

    Each game module handles:
    - Database initialization and management
    - Event CRUD operations
    - Dashboard/timer channel updates
    - Notification scheduling
    - Periodic updates/scraping

    Game modules must be stateless where possible, delegating persistence
    to repositories.
    """

    def __init__(self, config: GameConfig):
        """
        Initialize the game module.

        Args:
            config: GameConfig with profile settings
        """
        self.config = config
        self.profile = config.profile
        self.db_path = config.db_path
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Set up a logger for this game module."""
        logger = logging.getLogger(self.config.log_name)
        logger.setLevel(logging.INFO)

        # Ensure log directory exists
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{self.config.log_name}.log")

        # Console handler
        if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(
                logging.Formatter("[%(levelname)s] %(message)s")
            )
            logger.addHandler(console_handler)

        # File handler
        if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(
                logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
            )
            logger.addHandler(file_handler)

        return logger

    @abstractmethod
    async def initialize(self):
        """
        Initialize the module.

        This should:
        - Create database tables if needed
        - Load scheduled tasks
        - Start any background tasks
        """
        pass

    @abstractmethod
    async def refresh_events(self):
        """
        Refresh events from source.

        This could involve:
        - Scraping websites
        - Calling APIs
        - Processing LLM-extracted data
        """
        pass

    @abstractmethod
    async def update_dashboard(self, guild, region: Optional[str] = None):
        """
        Update the timer channel dashboard for this game.

        Args:
            guild: Discord guild object
            region: Optional region to update (for regional games)
        """
        pass

    @abstractmethod
    async def add_event(self, ctx, event_data: Dict[str, Any]):
        """
        Add a new event.

        Args:
            ctx: Discord command context
            event_data: Event data dictionary
        """
        pass

    @abstractmethod
    async def remove_event(self, ctx, title: str):
        """
        Remove an event by title.

        Args:
            ctx: Discord command context
            title: Event title to remove
        """
        pass

    @abstractmethod
    def get_notification_timings(self, category: str) -> Dict[str, List[int]]:
        """
        Get notification timing configuration for a category.

        Args:
            category: Event category (Banner, Event, Maintenance, etc.)

        Returns:
            Dictionary with 'start' and 'end' keys containing lists of
            minutes-before-event values
        """
        pass

    async def cleanup_expired_events(self):
        """
        Clean up expired events from the database.

        Default implementation - can be overridden for game-specific logic.
        """
        pass

    async def on_ready(self, bot):
        """
        Called when the bot is ready.

        Can be used to start background tasks.

        Args:
            bot: Discord bot instance
        """
        pass

    async def schedule_update_task(self, update_unix: int, region: Optional[str] = None):
        """
        Schedule a dashboard update at a specific time.

        Args:
            update_unix: Unix timestamp for when to update
            region: Optional region (for regional games)
        """
        pass


class HoyoverseGameModule(GameModule):
    """
    Base class for Hoyoverse games (HSR, ZZZ, Genshin).

    Extends GameModule with regional server support and version tracking.
    """

    # Triple timezone mapping for Hoyoverse games
    TIMEZONES = {
        "Asia": "Asia/Shanghai",        # UTC+8
        "America": "America/New_York",  # UTC-5 (handles DST)
        "Europe": "Europe/Berlin",      # UTC+1 (handles DST)
    }

    # Region name mappings (for database vs display)
    REGION_DISPLAY = {
        "ASIA": "Asia",
        "NA": "America",
        "EU": "Europe",
    }

    def __init__(self, config: GameConfig):
        """Initialize with regional server support enabled."""
        config.has_regional_servers = True
        config.regions = ["ASIA", "NA", "EU"]
        super().__init__(config)

    @abstractmethod
    async def convert_to_all_timezones(self, dt_str: str) -> Optional[Dict]:
        """
        Convert a date string to all regional timezones.

        Args:
            dt_str: Date string to parse (e.g. "2025/06/18 04:00 (UTC+8)")

        Returns:
            Dictionary mapping region to (datetime, unix_timestamp) tuple,
            or None if parsing failed
        """
        pass

    @abstractmethod
    async def get_version_start(self, version_str: str):
        """
        Get the start date for a game version.

        Args:
            version_str: Version number (e.g. "3.5")

        Returns:
            datetime object for the version start
        """
        pass
