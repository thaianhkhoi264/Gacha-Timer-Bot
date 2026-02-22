"""
Abstract notifier interface for the Gacha Timer Bot.

This module defines the abstract base class for notification delivery,
allowing different notification backends (Discord, Webhook, etc.).
"""

from abc import ABC, abstractmethod
from typing import Optional

from src.core.models import Notification


class Notifier(ABC):
    """
    Abstract base class for notification delivery.

    This allows the notification system to be platform-agnostic,
    making it easy to add new notification channels (Discord, Webhook, Email, etc.).
    """

    @abstractmethod
    async def send_notification(
        self,
        notification: Notification,
        channel_id: str,
        role_mentions: Optional[str] = None
    ) -> bool:
        """
        Send a notification to a channel.

        Args:
            notification: Notification entity to send
            channel_id: Target channel ID
            role_mentions: Role mention string (e.g., "@HSR @ASIA")

        Returns:
            True if sent successfully, False otherwise
        """
        pass

    @abstractmethod
    async def format_message(self, notification: Notification) -> str:
        """
        Format the notification message.

        Args:
            notification: Notification entity

        Returns:
            Formatted message string
        """
        pass

    @abstractmethod
    async def validate_channel(self, channel_id: str) -> bool:
        """
        Validate that a channel exists and is accessible.

        Args:
            channel_id: Channel ID to validate

        Returns:
            True if valid and accessible, False otherwise
        """
        pass


class DiscordNotifier(Notifier):
    """
    Discord-specific notifier implementation.

    Handles Discord embeds, mentions, and channel operations.
    """

    @abstractmethod
    async def create_embed(self, notification: Notification):
        """
        Create a Discord embed for the notification.

        Args:
            notification: Notification entity

        Returns:
            Discord Embed object
        """
        pass

    @abstractmethod
    async def get_role_mentions(
        self,
        profile: str,
        region: Optional[str] = None
    ) -> str:
        """
        Get the appropriate role mentions for a notification.

        Args:
            profile: Game profile
            region: Region (for Hoyoverse games)

        Returns:
            Role mention string (e.g., "<@&123456> <@&789012>")
        """
        pass


class WebhookNotifier(Notifier):
    """
    Webhook-based notifier for external integrations.
    """

    @abstractmethod
    async def post_webhook(
        self,
        webhook_url: str,
        notification: Notification
    ) -> bool:
        """
        Post notification to a webhook URL.

        Args:
            webhook_url: Target webhook URL
            notification: Notification entity

        Returns:
            True if posted successfully, False otherwise
        """
        pass


class NotifierError(Exception):
    """Base exception for notifier errors."""
    pass


class NotifierConnectionError(NotifierError):
    """Raised when notifier cannot connect to the platform."""
    pass


class NotifierSendError(NotifierError):
    """Raised when notification sending fails."""
    pass
