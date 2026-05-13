"""
Special Event Game Module - Base class for games with non-standard event types.

This module extends the GameModule interface to support games that have special
event types requiring custom notification scheduling (e.g., Uma Musume with
Champions Meeting and Legend Race events).
"""

from abc import abstractmethod
from typing import Optional, List, Dict, Any
from src.games.base.game_module import GameModule, GameConfig


class SpecialEventGameModule(GameModule):
    """
    Base class for games with non-standard event types.

    Unlike standard GameModule implementations that use fixed notification
    timings, this class allows injection of a custom event scheduler that
    can create dynamic notification schedules based on event category and data.

    Example Use Cases:
    - Uma Musume: Champions Meeting (5 phases), Legend Race (character rotations)
    - Event types where notification count/timing varies per event
    """

    def __init__(self, config: GameConfig, event_scheduler=None):
        """
        Initialize the special event game module.

        Args:
            config: GameConfig with profile settings
            event_scheduler: Optional scheduler service for creating custom
                           notification schedules (e.g., UmaScheduler)
        """
        super().__init__(config)
        self.event_scheduler = event_scheduler

    @abstractmethod
    async def get_notification_schedule(
        self,
        category: str,
        event_data: Dict[str, Any]
    ) -> List:
        """
        Get custom notification schedule for an event.

        This method should:
        1. Check if the category requires special handling
        2. Delegate to event_scheduler if needed
        3. Fall back to get_notification_timings() for standard events

        Args:
            category: Event category (e.g., "Champions Meeting", "Legend Race")
            event_data: Dictionary containing event details:
                - title: Event title
                - start_date: Unix timestamp for event start
                - end_date: Unix timestamp for event end
                - description: Optional description (may contain special data)
                - Other game-specific fields

        Returns:
            List of Notification objects with custom scheduling

        Example Implementation:
            ```python
            async def get_notification_schedule(self, category, event_data):
                if category == "Champions Meeting":
                    return self.event_scheduler.create_champions_meeting_notifications(
                        event_data["title"],
                        event_data["start_date"],
                        event_data["end_date"]
                    )
                elif category == "Legend Race":
                    characters = self.event_scheduler.parse_legend_race_characters(
                        event_data.get("description", "")
                    )
                    return self.event_scheduler.create_legend_race_notifications(
                        event_data["title"],
                        event_data["start_date"],
                        event_data["end_date"],
                        characters
                    )
                else:
                    # Fall back to standard timing
                    return super().get_notification_timings(category)
            ```
        """
        pass

    def get_notification_timings(self, category: str) -> Dict[str, List[int]]:
        """
        Get standard notification timing configuration.

        This method provides default timings for categories that don't require
        special handling. Override if your game has different defaults.

        Args:
            category: Event category

        Returns:
            Dictionary with 'start' and 'end' keys containing lists of
            minutes-before-event values
        """
        # Default timings for most games
        return {
            "Banner": {
                "start": [1440, 180, 60],  # 1 day, 3 hours, 1 hour before start
                "end": [1500, 1440, 180, 60]  # Reminders before end
            },
            "Event": {
                "start": [1440, 180, 60],
                "end": [1500, 1440, 180, 60]
            },
            "Maintenance": {
                "start": [180, 60, 30],  # Shorter warnings for maintenance
                "end": [30, 15]
            },
        }.get(category, {"start": [1440, 60], "end": [1440, 60]})

    async def schedule_notifications_for_event(
        self,
        event_id: int,
        category: str,
        event_data: Dict[str, Any],
        notification_service
    ) -> int:
        """
        Schedule notifications for an event using custom scheduling.

        This is a helper method that bridges the gap between the module and
        the notification service. It uses get_notification_schedule() to
        determine what notifications to create.

        Args:
            event_id: Database ID of the event
            category: Event category
            event_data: Event details
            notification_service: NotificationService instance

        Returns:
            Number of notifications created
        """
        try:
            # Get custom notification schedule
            notifications = await self.get_notification_schedule(category, event_data)

            if not notifications:
                self.logger.warning(
                    f"No notifications returned for event '{event_data.get('title')}' "
                    f"(category: {category})"
                )
                return 0

            # Schedule each notification
            count = 0
            for notification in notifications:
                await notification_service.create_notification(
                    event_id=event_id,
                    profile=self.profile,
                    category=category,
                    title=event_data.get("title", "Unknown"),
                    timing_type=notification.timing_type,
                    notify_unix=notification.notify_unix,
                    event_time_unix=notification.event_time_unix,
                    message_template=notification.message_template,
                    phase=getattr(notification, 'phase', None),
                    character_name=getattr(notification, 'character_name', None),
                )
                count += 1

            self.logger.info(
                f"Scheduled {count} notifications for event '{event_data.get('title')}'"
            )
            return count

        except Exception as e:
            self.logger.error(
                f"Failed to schedule notifications for event '{event_data.get('title')}': {e}",
                exc_info=True
            )
            return 0


__all__ = ['SpecialEventGameModule']
