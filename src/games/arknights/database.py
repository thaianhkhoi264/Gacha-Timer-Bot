"""
Arknights-specific database operations.

This module handles Arknights event data persistence including:
- Event CRUD operations (single timezone)
- Event message tracking
- Scheduled update task management
"""

import aiosqlite
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from src.core.repositories import BaseRepository


class ArknightsEventRepository(BaseRepository):
    """
    Repository for Arknights events.

    Arknights uses a single timezone (UTC-7 for Global),
    so no regional timestamp handling is needed.
    """

    def __init__(self, db_path: str = None):
        """
        Initialize the Arknights event repository.

        Args:
            db_path: Path to the Arknights database file
        """
        if db_path is None:
            db_path = os.path.join("data", "arknights_data.db")
        super().__init__(db_path)

    async def initialize(self):
        """Initialize the database schema."""
        async with self.get_connection() as conn:
            # Events table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    title TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    image TEXT,
                    category TEXT,
                    profile TEXT DEFAULT 'AK'
                )
            ''')

            # Event messages tracking
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS event_messages (
                    event_id INTEGER,
                    channel_id TEXT,
                    message_id TEXT,
                    PRIMARY KEY (event_id, channel_id)
                )
            ''')

            # Scheduled update tasks
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_update_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    update_unix INTEGER,
                    status TEXT DEFAULT 'pending'
                )
            ''')
            await conn.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_update_time
                ON scheduled_update_tasks (update_unix)
            ''')

            await conn.commit()

    # ==================== Event Methods ====================

    async def create_event(self, event_data: Dict[str, Any]) -> int:
        """
        Create a new Arknights event.

        Args:
            event_data: Dictionary with event fields

        Returns:
            New event ID
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                '''INSERT INTO events
                   (user_id, title, start_date, end_date, image, category, profile)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (
                    event_data.get("user_id", ""),
                    event_data["title"],
                    str(event_data["start_date"]),
                    str(event_data["end_date"]),
                    event_data.get("image"),
                    event_data["category"],
                    "AK",
                )
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_all_events(self) -> List[Dict[str, Any]]:
        """Get all Arknights events."""
        rows = await self.fetch_all(
            '''SELECT id, title, start_date, end_date, image, category
               FROM events ORDER BY start_date ASC'''
        )
        return [
            {
                "id": row[0],
                "title": row[1],
                "start_date": int(row[2]) if row[2] else 0,
                "end_date": int(row[3]) if row[3] else 0,
                "image": row[4],
                "category": row[5],
            }
            for row in rows
        ]

    async def get_ongoing_events(self, now: int) -> List[Dict[str, Any]]:
        """Get events that are currently ongoing."""
        rows = await self.fetch_all(
            '''SELECT id, title, start_date, end_date, image, category
               FROM events
               WHERE CAST(start_date AS INTEGER) <= ? AND CAST(end_date AS INTEGER) > ?
               ORDER BY start_date ASC''',
            (now, now)
        )
        return [
            {
                "id": row[0],
                "title": row[1],
                "start_date": int(row[2]) if row[2] else 0,
                "end_date": int(row[3]) if row[3] else 0,
                "image": row[4],
                "category": row[5],
            }
            for row in rows
        ]

    async def get_upcoming_events(self, now: int) -> List[Dict[str, Any]]:
        """Get events that haven't started yet."""
        rows = await self.fetch_all(
            '''SELECT id, title, start_date, end_date, image, category
               FROM events
               WHERE CAST(start_date AS INTEGER) > ?
               ORDER BY start_date ASC''',
            (now,)
        )
        return [
            {
                "id": row[0],
                "title": row[1],
                "start_date": int(row[2]) if row[2] else 0,
                "end_date": int(row[3]) if row[3] else 0,
                "image": row[4],
                "category": row[5],
            }
            for row in rows
        ]

    async def get_event_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Get an event by title (case-insensitive)."""
        row = await self.fetch_one(
            '''SELECT id, title, start_date, end_date, image, category
               FROM events WHERE LOWER(title) = ?''',
            (title.lower(),)
        )
        if not row:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "start_date": int(row[2]) if row[2] else 0,
            "end_date": int(row[3]) if row[3] else 0,
            "image": row[4],
            "category": row[5],
        }

    async def get_event_by_id(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Get an event by ID."""
        row = await self.fetch_one(
            '''SELECT id, title, start_date, end_date, image, category
               FROM events WHERE id = ?''',
            (event_id,)
        )
        if not row:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "start_date": int(row[2]) if row[2] else 0,
            "end_date": int(row[3]) if row[3] else 0,
            "image": row[4],
            "category": row[5],
        }

    async def update_event(self, event_id: int, event_data: Dict[str, Any]):
        """Update an existing event."""
        await self.execute(
            '''UPDATE events
               SET title = ?, start_date = ?, end_date = ?, image = ?, category = ?
               WHERE id = ?''',
            (
                event_data["title"],
                str(event_data["start_date"]),
                str(event_data["end_date"]),
                event_data.get("image"),
                event_data["category"],
                event_id,
            )
        )

    async def delete_event(self, event_id: int):
        """Delete an event by ID."""
        await self.execute("DELETE FROM events WHERE id = ?", (event_id,))

    async def delete_expired_events(self, now: int) -> int:
        """Delete events that have ended."""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM events WHERE CAST(end_date AS INTEGER) < ?",
                (now,)
            )
            await conn.commit()
            return cursor.rowcount

    # ==================== Message Tracking Methods ====================

    async def get_message_id(self, event_id: int, channel_id: str) -> Optional[str]:
        """Get the message ID for an event in a channel."""
        row = await self.fetch_one(
            "SELECT message_id FROM event_messages WHERE event_id = ? AND channel_id = ?",
            (event_id, channel_id)
        )
        return row[0] if row else None

    async def set_message_id(self, event_id: int, channel_id: str, message_id: str):
        """Set the message ID for an event in a channel."""
        await self.execute(
            "REPLACE INTO event_messages (event_id, channel_id, message_id) VALUES (?, ?, ?)",
            (event_id, channel_id, message_id)
        )

    async def delete_message_record(self, event_id: int, channel_id: str):
        """Delete the message record for an event in a channel."""
        await self.execute(
            "DELETE FROM event_messages WHERE event_id = ? AND channel_id = ?",
            (event_id, channel_id)
        )

    async def delete_messages_for_event(self, event_id: int):
        """Delete all message records for an event."""
        await self.execute(
            "DELETE FROM event_messages WHERE event_id = ?",
            (event_id,)
        )

    # ==================== Scheduled Task Methods ====================

    async def get_pending_update_tasks(self) -> List[int]:
        """Get all pending scheduled update task timestamps."""
        rows = await self.fetch_all(
            "SELECT update_unix FROM scheduled_update_tasks WHERE status = 'pending'"
        )
        return [row[0] for row in rows]

    async def schedule_update_task(self, update_unix: int) -> bool:
        """
        Schedule an update task if no similar task exists within ±15 minutes.

        Args:
            update_unix: Unix timestamp for the update

        Returns:
            True if task was scheduled, False if similar task exists
        """
        min_time = update_unix - 900
        max_time = update_unix + 900

        async with self.get_connection() as conn:
            async with conn.execute(
                "SELECT 1 FROM scheduled_update_tasks WHERE update_unix BETWEEN ? AND ?",
                (min_time, max_time)
            ) as cursor:
                if await cursor.fetchone():
                    return False

            await conn.execute(
                "INSERT OR IGNORE INTO scheduled_update_tasks (update_unix) VALUES (?)",
                (update_unix,)
            )
            await conn.commit()
            return True

    async def mark_task_done(self, update_unix: int):
        """Mark an update task as done."""
        await self.execute(
            "UPDATE scheduled_update_tasks SET status = 'done' WHERE update_unix = ?",
            (update_unix,)
        )

    async def cleanup_old_tasks(self, cutoff_unix: int):
        """Delete completed tasks older than the cutoff."""
        await self.execute(
            "DELETE FROM scheduled_update_tasks WHERE status = 'done' AND update_unix < ?",
            (cutoff_unix,)
        )
