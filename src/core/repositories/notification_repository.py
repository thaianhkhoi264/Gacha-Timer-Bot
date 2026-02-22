"""
SQLite implementation of the Notification Repository.

This module provides concrete implementation of the NotificationRepository interface
for SQLite databases.
"""

import os
import time
from typing import List, Optional

from src.core.interfaces import NotificationRepository
from src.core.models import Notification
from .base import BaseRepository, safe_int


class SQLiteNotificationRepository(BaseRepository, NotificationRepository):
    """
    SQLite implementation of NotificationRepository.

    Handles notification scheduling and persistence.
    """

    DEFAULT_DB_PATH = os.path.join("data", "notification_data.db")

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the notification repository.

        Args:
            db_path: Path to the SQLite database file (defaults to data/notification_data.db)
        """
        super().__init__(db_path or self.DEFAULT_DB_PATH)

    async def initialize(self):
        """Initialize the database schema."""
        async with self.get_connection() as conn:
            # Create pending notifications table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    profile TEXT,
                    title TEXT,
                    timing_type TEXT,
                    notify_unix INTEGER,
                    event_time_unix INTEGER,
                    sent INTEGER DEFAULT 0,
                    region TEXT,
                    send_time TEXT,
                    message_template TEXT,
                    custom_message TEXT,
                    phase TEXT,
                    character_name TEXT
                )
            ''')

            # Create pending notification messages table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_notifications_messages (
                    profile TEXT,
                    message_id TEXT,
                    PRIMARY KEY (profile, message_id)
                )
            ''')

            # Create role reaction messages table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS role_reaction_messages (
                    type TEXT PRIMARY KEY,
                    message_id TEXT
                )
            ''')

            await conn.commit()

        # Add columns if they don't exist (for schema migration)
        await self._migrate_schema()

        # Create unique index to prevent duplicates
        await self.create_index_if_not_exists(
            "idx_unique_pending_notif",
            "pending_notifications",
            ["category", "profile", "title", "timing_type", "notify_unix", "region"],
            unique=True
        )

        # Create index for pending queries
        await self.create_index_if_not_exists(
            "idx_pending_sent",
            "pending_notifications",
            ["sent", "notify_unix"]
        )

        # Create index for profile queries
        await self.create_index_if_not_exists(
            "idx_pending_profile",
            "pending_notifications",
            ["profile"]
        )

    async def _migrate_schema(self):
        """Add new columns if they don't exist (for existing databases)."""
        columns_to_add = [
            ("send_time", "TEXT"),
            ("message_template", "TEXT"),
            ("custom_message", "TEXT"),
            ("phase", "TEXT"),
            ("character_name", "TEXT"),
        ]

        for column_name, column_type in columns_to_add:
            await self.add_column_if_not_exists(
                "pending_notifications",
                column_name,
                column_type
            )

    async def create(self, notification: Notification) -> int:
        """
        Create a new pending notification.

        Args:
            notification: Notification entity to create

        Returns:
            ID of the created notification

        Note:
            Uses INSERT OR IGNORE to handle duplicates gracefully
        """
        query = '''
            INSERT OR IGNORE INTO pending_notifications (
                category, profile, title, timing_type, notify_unix,
                event_time_unix, sent, region, send_time, message_template,
                custom_message, phase, character_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            notification.category,
            notification.profile,
            notification.title,
            notification.timing_type,
            notification.notify_unix,
            notification.event_time_unix,
            notification.sent,
            notification.region,
            notification.send_time,
            notification.message_template,
            notification.custom_message,
            notification.phase,
            notification.character_name,
        )
        return await self.execute(query, params)

    async def create_many(self, notifications: List[Notification]) -> int:
        """
        Create multiple notifications at once.

        Args:
            notifications: List of Notification entities to create

        Returns:
            Number of notifications created
        """
        query = '''
            INSERT OR IGNORE INTO pending_notifications (
                category, profile, title, timing_type, notify_unix,
                event_time_unix, sent, region, send_time, message_template,
                custom_message, phase, character_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params_list = [
            (
                n.category, n.profile, n.title, n.timing_type, n.notify_unix,
                n.event_time_unix, n.sent, n.region, n.send_time, n.message_template,
                n.custom_message, n.phase, n.character_name,
            )
            for n in notifications
        ]
        return await self.execute_many(query, params_list)

    async def get_by_id(self, notification_id: int) -> Optional[Notification]:
        """
        Get a notification by its ID.

        Args:
            notification_id: Notification ID

        Returns:
            Notification entity or None if not found
        """
        row = await self.fetch_one(
            '''SELECT id, category, profile, title, timing_type, notify_unix,
                      event_time_unix, sent, region, send_time, message_template,
                      custom_message, phase, character_name
               FROM pending_notifications WHERE id = ?''',
            (notification_id,)
        )
        if row:
            return self._row_to_notification(row)
        return None

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
        query = '''
            SELECT id, category, profile, title, timing_type, notify_unix,
                   event_time_unix, sent, region, send_time, message_template,
                   custom_message, phase, character_name
            FROM pending_notifications
            WHERE sent = 0
        '''
        params = []

        if profile:
            query += " AND profile = ?"
            params.append(profile)
        if before_timestamp:
            query += " AND notify_unix <= ?"
            params.append(before_timestamp)

        query += " ORDER BY notify_unix ASC"

        rows = await self.fetch_all(query, tuple(params))
        return [self._row_to_notification(row) for row in rows]

    async def get_due(self, buffer_seconds: int = 60) -> List[Notification]:
        """
        Get all notifications that are due to be sent.

        Args:
            buffer_seconds: Buffer time in seconds

        Returns:
            List of due Notification entities
        """
        now = int(time.time())
        threshold = now + buffer_seconds

        return await self.get_pending(before_timestamp=threshold)

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
        rows = await self.fetch_all(
            '''SELECT id, category, profile, title, timing_type, notify_unix,
                      event_time_unix, sent, region, send_time, message_template,
                      custom_message, phase, character_name
               FROM pending_notifications
               WHERE profile = ? AND title = ? AND category = ?
               ORDER BY notify_unix ASC''',
            (profile, title, category)
        )
        return [self._row_to_notification(row) for row in rows]

    async def mark_sent(self, notification_id: int) -> bool:
        """
        Mark a notification as sent.

        Args:
            notification_id: Notification ID

        Returns:
            True if marked successfully, False otherwise
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "UPDATE pending_notifications SET sent = 1 WHERE id = ?",
                (notification_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete(self, notification_id: int) -> bool:
        """
        Delete a notification by its ID.

        Args:
            notification_id: Notification ID

        Returns:
            True if deleted successfully, False otherwise
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM pending_notifications WHERE id = ?",
                (notification_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0

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
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                '''DELETE FROM pending_notifications
                   WHERE profile = ? AND title = ? AND category = ?''',
                (profile, title, category)
            )
            await conn.commit()
            return cursor.rowcount

    async def delete_expired(self, before_timestamp: int) -> int:
        """
        Delete notifications for events that ended before the given timestamp.

        Args:
            before_timestamp: UNIX timestamp

        Returns:
            Number of notifications deleted
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM pending_notifications WHERE event_time_unix < ?",
                (before_timestamp,)
            )
            await conn.commit()
            return cursor.rowcount

    async def delete_sent(self) -> int:
        """
        Delete all sent notifications.

        Returns:
            Number of notifications deleted
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM pending_notifications WHERE sent = 1"
            )
            await conn.commit()
            return cursor.rowcount

    async def remove_duplicates(self) -> int:
        """
        Remove duplicate pending notifications.

        Returns:
            Number of duplicates removed
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute('''
                DELETE FROM pending_notifications
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM pending_notifications
                    GROUP BY category, profile, title, timing_type, notify_unix, region
                )
            ''')
            await conn.commit()
            return cursor.rowcount

    async def count_pending(self, profile: Optional[str] = None) -> int:
        """
        Count pending notifications.

        Args:
            profile: Filter by game profile (optional)

        Returns:
            Number of pending notifications
        """
        if profile:
            row = await self.fetch_one(
                "SELECT COUNT(*) FROM pending_notifications WHERE sent = 0 AND profile = ?",
                (profile,)
            )
        else:
            row = await self.fetch_one(
                "SELECT COUNT(*) FROM pending_notifications WHERE sent = 0"
            )
        return row[0] if row else 0

    async def get_all_grouped_by_profile(self) -> dict:
        """
        Get all pending notifications grouped by profile.

        Returns:
            Dictionary mapping profile to list of notifications
        """
        rows = await self.fetch_all(
            '''SELECT id, category, profile, title, timing_type, notify_unix,
                      event_time_unix, sent, region, send_time, message_template,
                      custom_message, phase, character_name
               FROM pending_notifications
               WHERE sent = 0
               ORDER BY profile, notify_unix ASC'''
        )

        grouped = {}
        for row in rows:
            notification = self._row_to_notification(row)
            if notification.profile not in grouped:
                grouped[notification.profile] = []
            grouped[notification.profile].append(notification)

        return grouped

    def _row_to_notification(self, row: tuple) -> Notification:
        """
        Convert a database row to a Notification entity.

        Args:
            row: Database row tuple

        Returns:
            Notification entity
        """
        return Notification(
            id=row[0],
            category=row[1],
            profile=row[2],
            title=row[3],
            timing_type=row[4],
            notify_unix=safe_int(row[5], 0),
            event_time_unix=safe_int(row[6], 0),
            sent=safe_int(row[7], 0),
            region=row[8],
            send_time=row[9] if len(row) > 9 else None,
            message_template=row[10] if len(row) > 10 else None,
            custom_message=row[11] if len(row) > 11 else None,
            phase=row[12] if len(row) > 12 else None,
            character_name=row[13] if len(row) > 13 else None,
        )
