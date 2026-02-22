"""
HSR-specific database operations.

This module handles HSR event data persistence including:
- Event CRUD operations with regional timestamps
- Event message tracking per region
- Scheduled update task management
- Version tracking
"""

import aiosqlite
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from src.core.repositories import BaseRepository


class HSREventRepository(BaseRepository):
    """
    Repository for HSR events with regional server support.

    Events are stored with separate timestamps for each region
    (Asia, America, Europe).
    """

    def __init__(self, db_path: str = None):
        """
        Initialize the HSR event repository.

        Args:
            db_path: Path to the HSR database file
        """
        if db_path is None:
            db_path = os.path.join("data", "hsr_data.db")
        super().__init__(db_path)

    async def initialize(self):
        """Initialize the database schema."""
        async with self.get_connection() as conn:
            # Events table with regional timestamps
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    title TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    image TEXT,
                    category TEXT,
                    profile TEXT DEFAULT 'HSR',
                    asia_start TEXT,
                    asia_end TEXT,
                    america_start TEXT,
                    america_end TEXT,
                    europe_start TEXT,
                    europe_end TEXT
                )
            ''')

            # Event messages tracking (per region)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS event_messages (
                    event_id INTEGER,
                    channel_id TEXT,
                    message_id TEXT,
                    region TEXT,
                    PRIMARY KEY (event_id, channel_id, region)
                )
            ''')

            # Scheduled update tasks
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_update_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    update_unix INTEGER,
                    region TEXT,
                    status TEXT DEFAULT 'pending'
                )
            ''')
            await conn.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_update_time_region
                ON scheduled_update_tasks (update_unix, region)
            ''')

            # Version tracking
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS version_tracker (
                    profile TEXT PRIMARY KEY,
                    version TEXT,
                    start_date TEXT
                )
            ''')

            await conn.commit()

    # ==================== Event Methods ====================

    async def create_event(self, event_data: Dict[str, Any]) -> int:
        """
        Create a new HSR event.

        Args:
            event_data: Dictionary with event fields

        Returns:
            New event ID
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                '''INSERT INTO events
                   (user_id, title, start_date, end_date, image, category, profile,
                    asia_start, asia_end, america_start, america_end, europe_start, europe_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    event_data.get("user_id", ""),
                    event_data["title"],
                    "",  # start_date not used for regional events
                    "",  # end_date not used for regional events
                    event_data.get("image"),
                    event_data["category"],
                    "HSR",
                    event_data["asia_start"],
                    event_data["asia_end"],
                    event_data["america_start"],
                    event_data["america_end"],
                    event_data["europe_start"],
                    event_data["europe_end"],
                )
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_all_events(self) -> List[Dict[str, Any]]:
        """Get all HSR events."""
        rows = await self.fetch_all(
            '''SELECT id, title, image, category,
                      asia_start, asia_end, america_start, america_end,
                      europe_start, europe_end
               FROM events ORDER BY asia_start ASC'''
        )
        return [
            {
                "id": row[0],
                "title": row[1],
                "image": row[2],
                "category": row[3],
                "asia_start": int(row[4]) if row[4] else 0,
                "asia_end": int(row[5]) if row[5] else 0,
                "america_start": int(row[6]) if row[6] else 0,
                "america_end": int(row[7]) if row[7] else 0,
                "europe_start": int(row[8]) if row[8] else 0,
                "europe_end": int(row[9]) if row[9] else 0,
            }
            for row in rows
        ]

    async def get_event_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Get an event by title (case-insensitive)."""
        row = await self.fetch_one(
            '''SELECT id, title, image, category,
                      asia_start, asia_end, america_start, america_end,
                      europe_start, europe_end
               FROM events WHERE LOWER(title) = ?''',
            (title.lower(),)
        )
        if not row:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "image": row[2],
            "category": row[3],
            "asia_start": int(row[4]) if row[4] else 0,
            "asia_end": int(row[5]) if row[5] else 0,
            "america_start": int(row[6]) if row[6] else 0,
            "america_end": int(row[7]) if row[7] else 0,
            "europe_start": int(row[8]) if row[8] else 0,
            "europe_end": int(row[9]) if row[9] else 0,
        }

    async def delete_event(self, event_id: int):
        """Delete an event by ID."""
        await self.execute("DELETE FROM events WHERE id = ?", (event_id,))

    async def delete_event_by_title(self, title: str) -> bool:
        """Delete an event by title (case-insensitive)."""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM events WHERE LOWER(title) = ?",
                (title.lower(),)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def is_event_ended(self, event: Dict[str, Any], now: int) -> bool:
        """Check if an event has ended in all regions."""
        return all(
            event.get(f"{region}_end", 0) < now
            for region in ["asia", "america", "europe"]
        )

    # ==================== Message Tracking Methods ====================

    async def get_message_id(
        self, event_id: int, channel_id: str, region: str
    ) -> Optional[str]:
        """Get the message ID for an event in a channel for a specific region."""
        row = await self.fetch_one(
            '''SELECT message_id FROM event_messages
               WHERE event_id = ? AND channel_id = ? AND region = ?''',
            (event_id, channel_id, region)
        )
        return row[0] if row else None

    async def set_message_id(
        self, event_id: int, channel_id: str, message_id: str, region: str
    ):
        """Set the message ID for an event in a channel for a specific region."""
        await self.execute(
            '''REPLACE INTO event_messages (event_id, channel_id, message_id, region)
               VALUES (?, ?, ?, ?)''',
            (event_id, channel_id, message_id, region)
        )

    async def delete_message_record(
        self, event_id: int, channel_id: str, region: str
    ):
        """Delete the message record for an event in a channel for a specific region."""
        await self.execute(
            '''DELETE FROM event_messages
               WHERE event_id = ? AND channel_id = ? AND region = ?''',
            (event_id, channel_id, region)
        )

    # ==================== Scheduled Task Methods ====================

    async def get_pending_update_tasks(self) -> List[tuple]:
        """Get all pending scheduled update tasks."""
        return await self.fetch_all(
            "SELECT update_unix, region FROM scheduled_update_tasks WHERE status = 'pending'"
        )

    async def schedule_update_task(self, update_unix: int, region: str) -> bool:
        """
        Schedule an update task if no similar task exists within ±15 minutes.

        Args:
            update_unix: Unix timestamp for the update
            region: Region to update

        Returns:
            True if task was scheduled, False if similar task exists
        """
        min_time = update_unix - 900
        max_time = update_unix + 900

        async with self.get_connection() as conn:
            async with conn.execute(
                '''SELECT 1 FROM scheduled_update_tasks
                   WHERE update_unix BETWEEN ? AND ? AND region = ?''',
                (min_time, max_time, region)
            ) as cursor:
                if await cursor.fetchone():
                    return False

            await conn.execute(
                '''INSERT OR IGNORE INTO scheduled_update_tasks (update_unix, region)
                   VALUES (?, ?)''',
                (update_unix, region)
            )
            await conn.commit()
            return True

    async def mark_task_done(self, update_unix: int, region: str):
        """Mark an update task as done."""
        await self.execute(
            '''UPDATE scheduled_update_tasks SET status = 'done'
               WHERE update_unix = ? AND region = ?''',
            (update_unix, region)
        )

    async def cleanup_old_tasks(self, cutoff_unix: int):
        """Delete completed tasks older than the cutoff."""
        await self.execute(
            "DELETE FROM scheduled_update_tasks WHERE status = 'done' AND update_unix < ?",
            (cutoff_unix,)
        )

    # ==================== Version Tracking Methods ====================

    async def get_version_info(self, profile: str = "HSR") -> Optional[tuple]:
        """Get the tracked version info for the profile."""
        row = await self.fetch_one(
            "SELECT version, start_date FROM version_tracker WHERE profile = ?",
            (profile,)
        )
        return row

    async def update_version_info(
        self, version: str, start_date: str, profile: str = "HSR"
    ):
        """Update the version tracker."""
        await self.execute(
            '''INSERT OR REPLACE INTO version_tracker (profile, version, start_date)
               VALUES (?, ?, ?)''',
            (profile, version, start_date)
        )
