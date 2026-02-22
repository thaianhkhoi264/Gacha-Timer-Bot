"""
Notification Scheduler Service for Gacha Timer Bot.

Handles the calculation and scheduling of notifications for events.
Different event categories have different notification timings.
"""

import time
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

from ..models import Event, Notification, GameProfile
from ..interfaces import NotificationRepository


# Standard notification timings by category
# Values are minutes before event start/end
NOTIFICATION_TIMINGS: Dict[str, Dict[str, List[int]]] = {
    "Banner": {"start": [60, 1440], "end": [60, 1440]},        # 1h, 1d before
    "Event": {"start": [180], "end": [180, 1440]},              # 3h before start; 3h, 1d before end
    "Maintenance": {"start": [60], "end": []},                  # 1h before start only
    "Offer": {"start": [180, 1440], "end": [1440]},            # 3h, 1d before start; 1d before end
}

# Uma Musume specific timings
UMA_NOTIFICATION_TIMINGS: Dict[str, Dict[str, List[int]]] = {
    "Character Banner": {"start": [1440], "end": [1440, 1500]},    # 1d before; 1d + 1h before end
    "Support Banner": {"start": [1440], "end": [1440, 1500]},
    "Paid Banner": {"start": [1440], "end": [1440, 1500]},
    "Story Event": {"start": [1440], "end": [4320, 4380]},         # 1d before; 3d + 1h before end
    "Champions Meeting": {"start": [], "end": []},                  # Custom scheduling
    "Legend Race": {"start": [], "end": []},                        # Custom scheduling
    "Selection Gacha": {"start": [1440], "end": [1440]},
}

# Profiles that use regional notifications (create 3 copies per notification)
HYV_PROFILES: Set[str] = {"HSR", "ZZZ", "WUWA"}

# Regions for HYV games
HYV_REGIONS: List[str] = ["ASIA", "AMERICA", "EUROPE"]


@dataclass
class NotificationTiming:
    """Represents a calculated notification time."""
    timing_type: str       # e.g., "start_60", "end_1440"
    notify_unix: int       # When to send the notification
    event_time_unix: int   # The event time this notification refers to
    region: Optional[str]  # For HYV games


class NotificationScheduler:
    """
    Service for calculating and scheduling event notifications.

    Responsibilities:
    - Calculate notification times based on event category
    - Handle regional notifications for HYV games
    - Generate Notification objects ready for database insertion
    """

    def __init__(self, notification_repo: Optional[NotificationRepository] = None):
        """
        Initialize the scheduler.

        Args:
            notification_repo: Optional repository for database operations.
                             If provided, enables create_for_event().
        """
        self.repo = notification_repo

    def get_timings_for_category(
        self,
        category: str,
        profile: str
    ) -> List[Tuple[str, int]]:
        """
        Get notification timing definitions for an event category.

        Args:
            category: Event category (e.g., "Banner", "Event")
            profile: Game profile (e.g., "HSR", "UMA")

        Returns:
            List of (timing_type, minutes) tuples
            e.g., [("start", 60), ("start", 1440), ("end", 60), ("end", 1440)]
        """
        # Check Uma-specific timings first
        if profile.upper() == "UMA" and category in UMA_NOTIFICATION_TIMINGS:
            timings_def = UMA_NOTIFICATION_TIMINGS[category]
        elif category in NOTIFICATION_TIMINGS:
            timings_def = NOTIFICATION_TIMINGS[category]
        else:
            # Default to Banner timings
            timings_def = NOTIFICATION_TIMINGS["Banner"]

        result = []
        for timing_type in ["start", "end"]:
            for minutes in timings_def.get(timing_type, []):
                result.append((timing_type, minutes))

        return result

    def calculate_notification_times(
        self,
        event: Event,
        current_time: Optional[int] = None
    ) -> List[NotificationTiming]:
        """
        Calculate all notification times for an event.

        Args:
            event: The event to calculate notifications for
            current_time: Current UNIX timestamp (defaults to now)

        Returns:
            List of NotificationTiming objects for future notifications
        """
        if current_time is None:
            current_time = int(time.time())

        timings = self.get_timings_for_category(event.category, event.profile)
        results = []

        is_hyv = event.profile.upper() in HYV_PROFILES

        if is_hyv:
            # HYV games: create notifications for each region
            for region in HYV_REGIONS:
                for timing_type, minutes in timings:
                    notification_timing = self._calculate_hyv_timing(
                        event, timing_type, minutes, region, current_time
                    )
                    if notification_timing:
                        results.append(notification_timing)
        else:
            # Non-HYV games: single notification per timing
            for timing_type, minutes in timings:
                notification_timing = self._calculate_single_timing(
                    event, timing_type, minutes, current_time
                )
                if notification_timing:
                    results.append(notification_timing)

        return results

    def _calculate_single_timing(
        self,
        event: Event,
        timing_type: str,
        minutes: int,
        current_time: int
    ) -> Optional[NotificationTiming]:
        """Calculate a single notification timing (non-HYV games)."""
        if timing_type == "start":
            event_time = event.start_date
        else:  # "end"
            event_time = event.end_date

        if not event_time:
            return None

        notify_unix = event_time - (minutes * 60)

        # Only schedule future notifications
        if notify_unix <= current_time:
            return None

        return NotificationTiming(
            timing_type=f"{timing_type}_{minutes}",
            notify_unix=notify_unix,
            event_time_unix=event_time,
            region=None
        )

    def _calculate_hyv_timing(
        self,
        event: Event,
        timing_type: str,
        minutes: int,
        region: str,
        current_time: int
    ) -> Optional[NotificationTiming]:
        """Calculate a regional notification timing (HYV games)."""
        # Get regional times
        if timing_type == "start":
            event_time = event.get_regional_start(region)
        else:  # "end"
            event_time = event.get_regional_end(region)

        if not event_time:
            return None

        notify_unix = event_time - (minutes * 60)

        # Only schedule future notifications
        if notify_unix <= current_time:
            return None

        return NotificationTiming(
            timing_type=f"{timing_type}_{minutes}",
            notify_unix=notify_unix,
            event_time_unix=event_time,
            region=region
        )

    def create_notifications(
        self,
        event: Event,
        current_time: Optional[int] = None
    ) -> List[Notification]:
        """
        Create Notification objects for an event (not yet saved).

        Args:
            event: The event to create notifications for
            current_time: Current UNIX timestamp (defaults to now)

        Returns:
            List of Notification objects ready for database insertion
        """
        timings = self.calculate_notification_times(event, current_time)
        notifications = []

        for timing in timings:
            notification = Notification(
                category=event.category,
                profile=event.profile,
                title=event.title,
                timing_type=timing.timing_type,
                notify_unix=timing.notify_unix,
                event_time_unix=timing.event_time_unix,
                region=timing.region,
            )
            notifications.append(notification)

        return notifications

    async def schedule_for_event(
        self,
        event: Event,
        current_time: Optional[int] = None
    ) -> List[int]:
        """
        Calculate and save notifications for an event.

        Requires notification_repo to be set.

        Args:
            event: The event to schedule notifications for
            current_time: Current UNIX timestamp (defaults to now)

        Returns:
            List of created notification IDs

        Raises:
            RuntimeError: If notification_repo is not set
        """
        if self.repo is None:
            raise RuntimeError("NotificationRepository not set. Use create_notifications() instead.")

        notifications = self.create_notifications(event, current_time)
        return await self.repo.create_many(notifications)

    def get_timing_label(self, timing_type: str) -> str:
        """
        Get a human-readable label for a timing type.

        Args:
            timing_type: e.g., "start_60", "end_1440"

        Returns:
            Human-readable string like "1 hour before start"
        """
        parts = timing_type.split("_")
        if len(parts) != 2:
            return timing_type

        event_type, minutes_str = parts
        try:
            minutes = int(minutes_str)
        except ValueError:
            return timing_type

        # Convert to hours/days
        if minutes >= 1440:
            days = minutes // 1440
            unit = "day" if days == 1 else "days"
            time_str = f"{days} {unit}"
        else:
            hours = minutes // 60
            unit = "hour" if hours == 1 else "hours"
            time_str = f"{hours} {unit}"

        event_label = "starts" if event_type == "start" else "ends"
        return f"{time_str} before {event_label}"
