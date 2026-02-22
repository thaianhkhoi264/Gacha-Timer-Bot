"""
Event Service for Gacha Timer Bot.

High-level event operations that coordinate between repositories
and other services.
"""

import time
from typing import List, Optional, Tuple

from ..models import Event, Notification, GameProfile
from ..interfaces import EventRepository, NotificationRepository
from .notification_scheduler import NotificationScheduler
from .uma_scheduler import UmaScheduler


class EventService:
    """
    High-level service for event operations.

    Coordinates between:
    - EventRepository: Storing and retrieving events
    - NotificationRepository: Managing notifications
    - NotificationScheduler: Calculating notification times
    - UmaScheduler: Special Uma Musume event handling
    """

    def __init__(
        self,
        event_repo: EventRepository,
        notification_repo: Optional[NotificationRepository] = None,
        notification_scheduler: Optional[NotificationScheduler] = None,
        uma_scheduler: Optional[UmaScheduler] = None,
    ):
        """
        Initialize the EventService.

        Args:
            event_repo: Repository for event data
            notification_repo: Repository for notification data (optional)
            notification_scheduler: Service for calculating notifications (optional)
            uma_scheduler: Service for Uma Musume special events (optional)
        """
        self.event_repo = event_repo
        self.notification_repo = notification_repo
        self.notification_scheduler = notification_scheduler or NotificationScheduler(notification_repo)
        self.uma_scheduler = uma_scheduler or UmaScheduler()

    async def create_event(
        self,
        event: Event,
        schedule_notifications: bool = True
    ) -> Tuple[int, List[int]]:
        """
        Create an event and optionally schedule its notifications.

        Args:
            event: The event to create
            schedule_notifications: Whether to also create notifications

        Returns:
            Tuple of (event_id, list of notification_ids)
        """
        # Save the event
        event_id = await self.event_repo.create(event)

        notification_ids = []
        if schedule_notifications and self.notification_repo:
            notifications = self._create_notifications_for_event(event)
            notification_ids = await self.notification_repo.create_many(notifications)

        return event_id, notification_ids

    def _create_notifications_for_event(self, event: Event) -> List[Notification]:
        """Create notification objects based on event type."""
        # Special handling for Uma Musume events
        if event.profile.upper() == "UMA":
            if event.category == "Champions Meeting":
                return self.uma_scheduler.create_champions_meeting_notifications(
                    event.title, event.start_date, event.end_date
                )
            elif event.category == "Legend Race":
                # Try to parse characters from description (if available)
                description = getattr(event, 'description', '') or ''
                characters = self.uma_scheduler.parse_legend_race_characters(description)
                if characters:
                    return self.uma_scheduler.create_legend_race_notifications(
                        event.title, event.start_date, event.end_date, characters
                    )

        # Standard notification scheduling
        return self.notification_scheduler.create_notifications(event)

    async def update_event(
        self,
        event: Event,
        reschedule_notifications: bool = True
    ) -> bool:
        """
        Update an event and optionally reschedule its notifications.

        Args:
            event: The event with updated data (must have id set)
            reschedule_notifications: Whether to recalculate notifications

        Returns:
            True if successful
        """
        if event.id is None:
            raise ValueError("Event must have an id to update")

        success = await self.event_repo.update(event)

        if success and reschedule_notifications and self.notification_repo:
            # Delete existing notifications for this event
            await self.notification_repo.delete_for_event(
                event.profile, event.title, event.category
            )

            # Create new notifications
            notifications = self._create_notifications_for_event(event)
            await self.notification_repo.create_many(notifications)

        return success

    async def delete_event(
        self,
        event_id: int,
        profile: Optional[str] = None,
        title: Optional[str] = None,
        category: Optional[str] = None
    ) -> bool:
        """
        Delete an event and its associated notifications.

        Args:
            event_id: The event ID to delete
            profile: Event profile (needed for notification cleanup)
            title: Event title (needed for notification cleanup)
            category: Event category (needed for notification cleanup)

        Returns:
            True if successful
        """
        # Get event details if not provided
        if not all([profile, title, category]):
            event = await self.event_repo.get_by_id(event_id)
            if event:
                profile = profile or event.profile
                title = title or event.title
                category = category or event.category

        # Delete notifications first
        if self.notification_repo and profile and title and category:
            await self.notification_repo.delete_for_event(profile, title, category)

        # Delete the event
        return await self.event_repo.delete(event_id)

    async def get_ongoing_events(
        self,
        server_id: Optional[str] = None,
        profile: Optional[str] = None,
        category: Optional[str] = None,
        current_time: Optional[int] = None
    ) -> List[Event]:
        """
        Get all currently ongoing events.

        Args:
            server_id: Filter by server (optional)
            profile: Filter by game profile (optional)
            category: Filter by category (optional)
            current_time: Override current time (defaults to now)

        Returns:
            List of ongoing events
        """
        if current_time is None:
            current_time = int(time.time())

        return await self.event_repo.get_ongoing(
            server_id=server_id,
            profile=profile,
            category=category,
            current_time=current_time
        )

    async def get_upcoming_events(
        self,
        server_id: Optional[str] = None,
        profile: Optional[str] = None,
        category: Optional[str] = None,
        current_time: Optional[int] = None,
        limit: int = 50
    ) -> List[Event]:
        """
        Get upcoming events (not yet started).

        Args:
            server_id: Filter by server (optional)
            profile: Filter by game profile (optional)
            category: Filter by category (optional)
            current_time: Override current time (defaults to now)
            limit: Maximum number of events to return

        Returns:
            List of upcoming events, sorted by start date
        """
        if current_time is None:
            current_time = int(time.time())

        return await self.event_repo.get_upcoming(
            server_id=server_id,
            profile=profile,
            category=category,
            current_time=current_time,
            limit=limit
        )

    async def mark_ended_events(
        self,
        server_id: str,
        current_time: Optional[int] = None
    ) -> int:
        """
        Mark events as ended if their end time has passed.

        Args:
            server_id: Server ID to process
            current_time: Override current time (defaults to now)

        Returns:
            Number of events marked as ended
        """
        if current_time is None:
            current_time = int(time.time())

        return await self.event_repo.mark_ended(server_id, current_time)

    async def cleanup_expired_events(
        self,
        server_id: Optional[str] = None,
        days_old: int = 7
    ) -> int:
        """
        Delete events that ended more than N days ago.

        Args:
            server_id: Filter by server (optional, None = all servers)
            days_old: Delete events ended more than this many days ago

        Returns:
            Number of events deleted
        """
        cutoff = int(time.time()) - (days_old * 86400)
        return await self.event_repo.delete_expired(server_id, cutoff)

    async def get_events_for_display(
        self,
        server_id: str,
        profile: str,
        categories: Optional[List[str]] = None,
        include_ended: bool = False
    ) -> dict:
        """
        Get events organized for display in a Discord channel.

        Args:
            server_id: Server ID
            profile: Game profile
            categories: Categories to include (None = all)
            include_ended: Whether to include ended events

        Returns:
            Dict with 'ongoing', 'upcoming', and optionally 'ended' lists
        """
        current_time = int(time.time())
        result = {
            'ongoing': [],
            'upcoming': [],
        }

        # Get all events for this profile
        all_events = await self.event_repo.get_all(
            server_id=server_id,
            profile=profile
        )

        for event in all_events:
            # Filter by category if specified
            if categories and event.category not in categories:
                continue

            if event.is_ongoing(current_time):
                result['ongoing'].append(event)
            elif event.is_upcoming(current_time):
                result['upcoming'].append(event)
            elif include_ended and event.is_expired(current_time):
                if 'ended' not in result:
                    result['ended'] = []
                result['ended'].append(event)

        # Sort by start date
        result['ongoing'].sort(key=lambda e: e.end_date or 0)
        result['upcoming'].sort(key=lambda e: e.start_date or 0)
        if 'ended' in result:
            result['ended'].sort(key=lambda e: e.end_date or 0, reverse=True)

        return result
