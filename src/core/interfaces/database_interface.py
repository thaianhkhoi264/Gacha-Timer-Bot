"""
Abstract database interfaces for the Gacha Timer Bot.

This module defines abstract base classes for repositories, following the
Interface Segregation Principle (ISP) from SOLID.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.core.models import Event, Notification


class EventRepository(ABC):
    """Abstract interface for event data access."""

    @abstractmethod
    async def create(self, event: Event) -> int:
        """
        Create a new event in the database.

        Args:
            event: Event entity to create

        Returns:
            ID of the created event
        """
        pass

    @abstractmethod
    async def get_by_id(self, event_id: int) -> Optional[Event]:
        """
        Get an event by its ID.

        Args:
            event_id: Event ID

        Returns:
            Event entity or None if not found
        """
        pass

    @abstractmethod
    async def get_all(
        self,
        server_id: Optional[str] = None,
        profile: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[Event]:
        """
        Get all events matching the given filters.

        Args:
            server_id: Filter by server ID (optional)
            profile: Filter by game profile (optional)
            category: Filter by category (optional)

        Returns:
            List of Event entities
        """
        pass

    @abstractmethod
    async def get_ongoing(
        self,
        server_id: Optional[str] = None,
        profile: Optional[str] = None
    ) -> List[Event]:
        """
        Get all currently ongoing events.

        Args:
            server_id: Filter by server ID (optional)
            profile: Filter by game profile (optional)

        Returns:
            List of ongoing Event entities
        """
        pass

    @abstractmethod
    async def get_upcoming(
        self,
        server_id: Optional[str] = None,
        profile: Optional[str] = None
    ) -> List[Event]:
        """
        Get all upcoming events (not started yet).

        Args:
            server_id: Filter by server ID (optional)
            profile: Filter by game profile (optional)

        Returns:
            List of upcoming Event entities
        """
        pass

    @abstractmethod
    async def update(self, event: Event) -> bool:
        """
        Update an existing event.

        Args:
            event: Event entity with updated data (must have valid ID)

        Returns:
            True if updated successfully, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, event_id: int) -> bool:
        """
        Delete an event by its ID.

        Args:
            event_id: Event ID

        Returns:
            True if deleted successfully, False otherwise
        """
        pass

    @abstractmethod
    async def delete_expired(self, before_timestamp: int) -> int:
        """
        Delete events that ended before the given timestamp.

        Args:
            before_timestamp: UNIX timestamp

        Returns:
            Number of events deleted
        """
        pass


class NotificationRepository(ABC):
    """Abstract interface for notification data access."""

    @abstractmethod
    async def create(self, notification: Notification) -> int:
        """
        Create a new pending notification.

        Args:
            notification: Notification entity to create

        Returns:
            ID of the created notification
        """
        pass

    @abstractmethod
    async def get_by_id(self, notification_id: int) -> Optional[Notification]:
        """
        Get a notification by its ID.

        Args:
            notification_id: Notification ID

        Returns:
            Notification entity or None if not found
        """
        pass

    @abstractmethod
    async def get_pending(
        self,
        profile: Optional[str] = None,
        before_timestamp: Optional[int] = None
    ) -> List[Notification]:
        """
        Get all pending (unsent) notifications.

        Args:
            profile: Filter by game profile (optional)
            before_timestamp: Only get notifications due before this time (optional)

        Returns:
            List of pending Notification entities
        """
        pass

    @abstractmethod
    async def get_for_event(
        self,
        profile: str,
        title: str,
        category: str
    ) -> List[Notification]:
        """
        Get all notifications for a specific event.

        Args:
            profile: Game profile
            title: Event title
            category: Event category

        Returns:
            List of Notification entities for the event
        """
        pass

    @abstractmethod
    async def mark_sent(self, notification_id: int) -> bool:
        """
        Mark a notification as sent.

        Args:
            notification_id: Notification ID

        Returns:
            True if marked successfully, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, notification_id: int) -> bool:
        """
        Delete a notification by its ID.

        Args:
            notification_id: Notification ID

        Returns:
            True if deleted successfully, False otherwise
        """
        pass

    @abstractmethod
    async def delete_for_event(
        self,
        profile: str,
        title: str,
        category: str
    ) -> int:
        """
        Delete all notifications for a specific event.

        Args:
            profile: Game profile
            title: Event title
            category: Event category

        Returns:
            Number of notifications deleted
        """
        pass

    @abstractmethod
    async def delete_expired(self, before_timestamp: int) -> int:
        """
        Delete notifications for events that ended before the given timestamp.

        Args:
            before_timestamp: UNIX timestamp

        Returns:
            Number of notifications deleted
        """
        pass


class ConfigRepository(ABC):
    """Abstract interface for configuration data access."""

    @abstractmethod
    async def get_timer_channel(self, server_id: str, profile: str) -> Optional[str]:
        """
        Get the timer channel ID for a server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile

        Returns:
            Channel ID or None if not configured
        """
        pass

    @abstractmethod
    async def set_timer_channel(self, server_id: str, profile: str, channel_id: str) -> bool:
        """
        Set the timer channel for a server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile
            channel_id: Discord channel ID

        Returns:
            True if set successfully, False otherwise
        """
        pass

    @abstractmethod
    async def get_notification_channel(self, profile: str) -> Optional[str]:
        """
        Get the notification channel ID for a profile.

        Args:
            profile: Game profile

        Returns:
            Channel ID or None if not configured
        """
        pass

    @abstractmethod
    async def get_valid_categories(self, server_id: str, profile: str) -> List[str]:
        """
        Get list of valid categories for a server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile

        Returns:
            List of valid category names
        """
        pass

    @abstractmethod
    async def add_custom_category(
        self,
        server_id: str,
        profile: str,
        category: str
    ) -> bool:
        """
        Add a custom category for a server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile
            category: Category name to add

        Returns:
            True if added successfully, False otherwise
        """
        pass
