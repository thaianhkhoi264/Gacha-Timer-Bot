"""
Notification entity model for the Gacha Timer Bot.

This module defines the Notification dataclass that represents a scheduled notification.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .enums import NotificationTimingType


@dataclass
class Notification:
    """
    Represents a scheduled notification for a game event.

    Attributes:
        id: Database ID (None for new notifications)
        category: Event category
        profile: Game profile
        title: Event title
        timing_type: Type of notification (reminder/start_1h/end_24h/etc.)
        notify_unix: UNIX timestamp when notification should be sent
        event_time_unix: UNIX timestamp of the actual event time
        sent: Whether the notification has been sent (0/1)
        region: Region for Hoyoverse games (ASIA/AMERICA/EUROPE/None)
        send_time: Human-readable send time string
        message_template: Template key for the notification message
        custom_message: Custom message override
        phase: Phase number for Champions Meeting
        character_name: Character name for Legend Race
    """

    # Required fields
    category: str
    profile: str
    title: str
    timing_type: str
    notify_unix: int
    event_time_unix: int

    # Optional fields with defaults
    id: Optional[int] = None
    sent: int = 0
    region: Optional[str] = None
    send_time: Optional[str] = None
    message_template: Optional[str] = None
    custom_message: Optional[str] = None
    phase: Optional[str] = None
    character_name: Optional[str] = None

    def __post_init__(self):
        """Validate notification data after initialization."""
        # Ensure notify_unix is before event_time_unix for start notifications
        # (End notifications can be sent after event starts)
        if "start" in self.timing_type.lower() and self.notify_unix > self.event_time_unix:
            raise ValueError(
                f"Start notification time ({self.notify_unix}) must be before "
                f"event start time ({self.event_time_unix})"
            )

    def is_due(self, current_time: Optional[int] = None, buffer_seconds: int = 60) -> bool:
        """
        Check if notification is due to be sent.

        Args:
            current_time: UNIX timestamp to check against (defaults to now)
            buffer_seconds: Buffer time in seconds (notifications due within this buffer are considered due)

        Returns:
            True if notification is due, False otherwise
        """
        if current_time is None:
            current_time = int(datetime.now().timestamp())

        # Notification is due if current time is within buffer of notify_unix
        return current_time >= (self.notify_unix - buffer_seconds)

    def is_sent(self) -> bool:
        """Check if notification has been sent."""
        return self.sent == 1

    def mark_sent(self):
        """Mark notification as sent."""
        self.sent = 1

    def is_expired(self, current_time: Optional[int] = None) -> bool:
        """
        Check if notification is expired (past event time).

        Args:
            current_time: UNIX timestamp to check against (defaults to now)

        Returns:
            True if notification is expired, False otherwise
        """
        if current_time is None:
            current_time = int(datetime.now().timestamp())

        return current_time > self.event_time_unix

    def to_dict(self) -> dict:
        """Convert notification to dictionary for database storage."""
        return {
            'id': self.id,
            'category': self.category,
            'profile': self.profile,
            'title': self.title,
            'timing_type': self.timing_type,
            'notify_unix': self.notify_unix,
            'event_time_unix': self.event_time_unix,
            'sent': self.sent,
            'region': self.region,
            'send_time': self.send_time,
            'message_template': self.message_template,
            'custom_message': self.custom_message,
            'phase': self.phase,
            'character_name': self.character_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Notification':
        """Create Notification instance from dictionary."""
        return cls(
            id=data.get('id'),
            category=data['category'],
            profile=data['profile'],
            title=data['title'],
            timing_type=data['timing_type'],
            notify_unix=data['notify_unix'],
            event_time_unix=data['event_time_unix'],
            sent=data.get('sent', 0),
            region=data.get('region'),
            send_time=data.get('send_time'),
            message_template=data.get('message_template'),
            custom_message=data.get('custom_message'),
            phase=data.get('phase'),
            character_name=data.get('character_name'),
        )

    @classmethod
    def from_db_row(cls, row: tuple) -> 'Notification':
        """
        Create Notification instance from database row.

        Args:
            row: Database row tuple from pending_notifications table

        Returns:
            Notification instance
        """
        # Handle rows with varying column counts (older vs newer schema)
        return cls(
            id=row[0] if len(row) > 0 else None,
            category=row[1] if len(row) > 1 else "",
            profile=row[2] if len(row) > 2 else "",
            title=row[3] if len(row) > 3 else "",
            timing_type=row[4] if len(row) > 4 else "",
            notify_unix=row[5] if len(row) > 5 else 0,
            event_time_unix=row[6] if len(row) > 6 else 0,
            sent=row[7] if len(row) > 7 else 0,
            region=row[8] if len(row) > 8 else None,
            send_time=row[9] if len(row) > 9 else None,
            message_template=row[10] if len(row) > 10 else None,
            custom_message=row[11] if len(row) > 11 else None,
            phase=row[12] if len(row) > 12 else None,
            character_name=row[13] if len(row) > 13 else None,
        )

    def get_minutes_until(self, current_time: Optional[int] = None) -> int:
        """
        Get minutes until notification should be sent.

        Args:
            current_time: UNIX timestamp to check against (defaults to now)

        Returns:
            Minutes until notification (negative if overdue)
        """
        if current_time is None:
            current_time = int(datetime.now().timestamp())

        seconds_until = self.notify_unix - current_time
        return seconds_until // 60

    def get_hours_until(self, current_time: Optional[int] = None) -> float:
        """
        Get hours until notification should be sent.

        Args:
            current_time: UNIX timestamp to check against (defaults to now)

        Returns:
            Hours until notification (negative if overdue)
        """
        if current_time is None:
            current_time = int(datetime.now().timestamp())

        seconds_until = self.notify_unix - current_time
        return seconds_until / 3600

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"Notification(id={self.id}, profile={self.profile}, "
            f"title='{self.title}', timing_type={self.timing_type}, "
            f"region={self.region}, sent={self.sent})"
        )
