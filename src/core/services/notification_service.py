"""
Notification Service for Gacha Timer Bot.

Handles notification retrieval, processing, and cleanup operations.
"""

import time
from typing import Callable, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

from ..models import Notification
from ..interfaces import NotificationRepository


@dataclass
class NotificationBatch:
    """A batch of notifications grouped for sending."""
    profile: str
    region: Optional[str]
    notifications: List[Notification]


class NotificationService:
    """
    Service for notification management and processing.

    Responsibilities:
    - Retrieve due notifications
    - Mark notifications as sent
    - Clean up expired/orphaned notifications
    - Group notifications for efficient sending
    """

    def __init__(self, notification_repo: NotificationRepository):
        """
        Initialize the NotificationService.

        Args:
            notification_repo: Repository for notification data
        """
        self.repo = notification_repo

    async def get_due_notifications(
        self,
        current_time: Optional[int] = None,
        buffer_seconds: int = 60
    ) -> List[Notification]:
        """
        Get notifications that are due to be sent.

        Args:
            current_time: Override current time (defaults to now)
            buffer_seconds: Include notifications due within this many seconds

        Returns:
            List of due notifications (unsent only)
        """
        if current_time is None:
            current_time = int(time.time())

        return await self.repo.get_due(current_time, buffer_seconds)

    async def get_due_grouped(
        self,
        current_time: Optional[int] = None,
        buffer_seconds: int = 60
    ) -> List[NotificationBatch]:
        """
        Get due notifications grouped by profile and region.

        Useful for sending notifications to the correct channels.

        Args:
            current_time: Override current time (defaults to now)
            buffer_seconds: Include notifications due within this many seconds

        Returns:
            List of NotificationBatch objects
        """
        notifications = await self.get_due_notifications(current_time, buffer_seconds)

        # Group by (profile, region)
        groups: Dict[Tuple[str, Optional[str]], List[Notification]] = {}
        for notif in notifications:
            key = (notif.profile, notif.region)
            if key not in groups:
                groups[key] = []
            groups[key].append(notif)

        # Convert to batches
        batches = []
        for (profile, region), notifs in groups.items():
            batches.append(NotificationBatch(
                profile=profile,
                region=region,
                notifications=notifs
            ))

        return batches

    async def mark_sent(self, notification_id: int) -> bool:
        """
        Mark a notification as sent.

        Args:
            notification_id: The notification ID

        Returns:
            True if successful
        """
        return await self.repo.mark_sent(notification_id)

    async def mark_many_sent(self, notification_ids: List[int]) -> int:
        """
        Mark multiple notifications as sent.

        Args:
            notification_ids: List of notification IDs

        Returns:
            Number of notifications marked
        """
        count = 0
        for notif_id in notification_ids:
            if await self.repo.mark_sent(notif_id):
                count += 1
        return count

    async def process_notifications(
        self,
        send_callback: Callable[[Notification], bool],
        current_time: Optional[int] = None,
        buffer_seconds: int = 60
    ) -> Tuple[int, int]:
        """
        Process and send due notifications using a callback.

        Args:
            send_callback: Function that sends a notification, returns True if successful
            current_time: Override current time
            buffer_seconds: Include notifications due within this many seconds

        Returns:
            Tuple of (sent_count, failed_count)
        """
        notifications = await self.get_due_notifications(current_time, buffer_seconds)

        sent = 0
        failed = 0

        for notif in notifications:
            try:
                if send_callback(notif):
                    await self.mark_sent(notif.id)
                    sent += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        return sent, failed

    async def get_pending_count(
        self,
        profile: Optional[str] = None,
        category: Optional[str] = None
    ) -> int:
        """
        Get count of pending (unsent) notifications.

        Args:
            profile: Filter by profile (optional)
            category: Filter by category (optional)

        Returns:
            Count of pending notifications
        """
        return await self.repo.count_pending(profile, category)

    async def get_notifications_for_event(
        self,
        profile: str,
        title: str,
        category: str
    ) -> List[Notification]:
        """
        Get all notifications for a specific event.

        Args:
            profile: Event profile
            title: Event title
            category: Event category

        Returns:
            List of notifications for this event
        """
        return await self.repo.get_for_event(profile, title, category)

    async def delete_for_event(
        self,
        profile: str,
        title: str,
        category: str
    ) -> int:
        """
        Delete all notifications for an event.

        Args:
            profile: Event profile
            title: Event title
            category: Event category

        Returns:
            Number of notifications deleted
        """
        return await self.repo.delete_for_event(profile, title, category)

    async def cleanup_expired(
        self,
        days_old: int = 7,
        current_time: Optional[int] = None
    ) -> int:
        """
        Delete old sent notifications.

        Args:
            days_old: Delete sent notifications older than this
            current_time: Override current time

        Returns:
            Number of notifications deleted
        """
        if current_time is None:
            current_time = int(time.time())

        cutoff = current_time - (days_old * 86400)
        return await self.repo.delete_expired(cutoff)

    async def remove_duplicates(self) -> int:
        """
        Remove duplicate pending notifications.

        Duplicates are determined by:
        (category, profile, title, timing_type, notify_unix, region)

        Returns:
            Number of duplicates removed
        """
        return await self.repo.remove_duplicates()

    async def cleanup_orphaned(
        self,
        valid_events: Set[Tuple[str, str, str]]
    ) -> int:
        """
        Remove notifications for events that no longer exist.

        Args:
            valid_events: Set of (profile, title, category) tuples for valid events

        Returns:
            Number of orphaned notifications removed
        """
        # Get all pending notifications
        pending = await self.repo.get_pending()

        orphaned_ids = []
        for notif in pending:
            key = (notif.profile, notif.title, notif.category)
            if key not in valid_events:
                orphaned_ids.append(notif.id)

        # Delete orphaned notifications
        deleted = 0
        for notif_id in orphaned_ids:
            # We need to add a delete method to the repo
            # For now, mark as sent (effectively removes from pending)
            if await self.repo.mark_sent(notif_id):
                deleted += 1

        return deleted

    def format_notification_message(
        self,
        notification: Notification,
        templates: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Format a notification into a human-readable message.

        Args:
            notification: The notification to format
            templates: Optional custom message templates

        Returns:
            Formatted message string
        """
        # Use custom template if provided
        if templates and notification.message_template in templates:
            template = templates[notification.message_template]
            return template.format(
                title=notification.title,
                category=notification.category,
                profile=notification.profile,
                phase=notification.phase or "",
                character_name=notification.character_name or "",
            )

        # Default formatting
        timing = notification.timing_type

        if "start" in timing:
            action = "starts"
        elif "end" in timing:
            action = "ends"
        elif notification.phase:
            action = f"{notification.phase} begins"
        elif notification.character_name:
            action = f"{notification.character_name} is available"
        else:
            action = "notification"

        region_suffix = f" ({notification.region})" if notification.region else ""

        return f"**{notification.title}** {action}{region_suffix}"
