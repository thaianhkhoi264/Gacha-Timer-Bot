"""
SQLite implementation of the Event Repository.

This module provides concrete implementation of the EventRepository interface
for SQLite databases.
"""

import time
from typing import List, Optional

from src.core.interfaces import EventRepository
from src.core.models import Event
from .base import BaseRepository, safe_int


class SQLiteEventRepository(BaseRepository, EventRepository):
    """
    SQLite implementation of EventRepository.

    Handles event CRUD operations for the main events database.
    """

    def __init__(self, db_path: str = "kanami_data.db"):
        """
        Initialize the event repository.

        Args:
            db_path: Path to the SQLite database file
        """
        super().__init__(db_path)

    async def initialize(self):
        """Initialize the database schema."""
        async with self.get_connection() as conn:
            # Create main events table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    server_id TEXT,
                    title TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    image TEXT,
                    category TEXT,
                    is_hyv INTEGER DEFAULT 0,
                    asia_start TEXT,
                    asia_end TEXT,
                    america_start TEXT,
                    america_end TEXT,
                    europe_start TEXT,
                    europe_end TEXT,
                    profile TEXT
                )
            ''')

            # Create event messages tracking table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS event_messages (
                    event_id INTEGER,
                    server_id TEXT,
                    channel_id TEXT,
                    message_id TEXT,
                    PRIMARY KEY (event_id, channel_id)
                )
            ''')

            await conn.commit()

        # Create indexes for common queries
        await self.create_index_if_not_exists(
            "idx_events_server_profile",
            "user_data",
            ["server_id", "profile"]
        )
        await self.create_index_if_not_exists(
            "idx_events_category",
            "user_data",
            ["category"]
        )
        await self.create_index_if_not_exists(
            "idx_events_end_date",
            "user_data",
            ["end_date"]
        )

    async def create(self, event: Event) -> int:
        """
        Create a new event in the database.

        Args:
            event: Event entity to create

        Returns:
            ID of the created event
        """
        query = '''
            INSERT INTO user_data (
                user_id, server_id, title, start_date, end_date, image, category,
                is_hyv, asia_start, asia_end, america_start, america_end,
                europe_start, europe_end, profile
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            event.user_id,
            event.server_id,
            event.title,
            str(event.start_date),
            str(event.end_date),
            event.image,
            event.category,
            int(event.is_hyv),
            str(event.asia_start) if event.asia_start else None,
            str(event.asia_end) if event.asia_end else None,
            str(event.america_start) if event.america_start else None,
            str(event.america_end) if event.america_end else None,
            str(event.europe_start) if event.europe_start else None,
            str(event.europe_end) if event.europe_end else None,
            event.profile,
        )
        return await self.execute(query, params)

    async def get_by_id(self, event_id: int) -> Optional[Event]:
        """
        Get an event by its ID.

        Args:
            event_id: Event ID

        Returns:
            Event entity or None if not found
        """
        row = await self.fetch_one(
            '''SELECT id, user_id, server_id, title, start_date, end_date, image,
                      category, is_hyv, asia_start, asia_end, america_start,
                      america_end, europe_start, europe_end, profile
               FROM user_data WHERE id = ?''',
            (event_id,)
        )
        if row:
            return self._row_to_event(row)
        return None

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
        query = '''
            SELECT id, user_id, server_id, title, start_date, end_date, image,
                   category, is_hyv, asia_start, asia_end, america_start,
                   america_end, europe_start, europe_end, profile
            FROM user_data WHERE 1=1
        '''
        params = []

        if server_id:
            query += " AND server_id = ?"
            params.append(server_id)
        if profile:
            query += " AND profile = ?"
            params.append(profile)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY id DESC"

        rows = await self.fetch_all(query, tuple(params))
        return [self._row_to_event(row) for row in rows]

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
        now = int(time.time())
        query = '''
            SELECT id, user_id, server_id, title, start_date, end_date, image,
                   category, is_hyv, asia_start, asia_end, america_start,
                   america_end, europe_start, europe_end, profile
            FROM user_data
            WHERE CAST(start_date AS INTEGER) <= ?
              AND CAST(end_date AS INTEGER) > ?
              AND category != 'Ended'
        '''
        params = [now, now]

        if server_id:
            query += " AND server_id = ?"
            params.append(server_id)
        if profile:
            query += " AND profile = ?"
            params.append(profile)

        query += " ORDER BY CAST(end_date AS INTEGER) ASC"

        rows = await self.fetch_all(query, tuple(params))
        return [self._row_to_event(row) for row in rows]

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
        now = int(time.time())
        query = '''
            SELECT id, user_id, server_id, title, start_date, end_date, image,
                   category, is_hyv, asia_start, asia_end, america_start,
                   america_end, europe_start, europe_end, profile
            FROM user_data
            WHERE CAST(start_date AS INTEGER) > ?
              AND category != 'Ended'
        '''
        params = [now]

        if server_id:
            query += " AND server_id = ?"
            params.append(server_id)
        if profile:
            query += " AND profile = ?"
            params.append(profile)

        query += " ORDER BY CAST(start_date AS INTEGER) ASC"

        rows = await self.fetch_all(query, tuple(params))
        return [self._row_to_event(row) for row in rows]

    async def update(self, event: Event) -> bool:
        """
        Update an existing event.

        Args:
            event: Event entity with updated data (must have valid ID)

        Returns:
            True if updated successfully, False otherwise
        """
        if not event.id:
            return False

        query = '''
            UPDATE user_data SET
                user_id = ?, server_id = ?, title = ?, start_date = ?,
                end_date = ?, image = ?, category = ?, is_hyv = ?,
                asia_start = ?, asia_end = ?, america_start = ?,
                america_end = ?, europe_start = ?, europe_end = ?, profile = ?
            WHERE id = ?
        '''
        params = (
            event.user_id,
            event.server_id,
            event.title,
            str(event.start_date),
            str(event.end_date),
            event.image,
            event.category,
            int(event.is_hyv),
            str(event.asia_start) if event.asia_start else None,
            str(event.asia_end) if event.asia_end else None,
            str(event.america_start) if event.america_start else None,
            str(event.america_end) if event.america_end else None,
            str(event.europe_start) if event.europe_start else None,
            str(event.europe_end) if event.europe_end else None,
            event.profile,
            event.id,
        )

        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()
            return cursor.rowcount > 0

    async def delete(self, event_id: int) -> bool:
        """
        Delete an event by its ID.

        Args:
            event_id: Event ID

        Returns:
            True if deleted successfully, False otherwise
        """
        async with self.get_connection() as conn:
            # Delete associated event messages first
            await conn.execute(
                "DELETE FROM event_messages WHERE event_id = ?",
                (event_id,)
            )
            # Delete the event
            cursor = await conn.execute(
                "DELETE FROM user_data WHERE id = ?",
                (event_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_expired(self, before_timestamp: int) -> int:
        """
        Delete events that ended before the given timestamp.

        Args:
            before_timestamp: UNIX timestamp

        Returns:
            Number of events deleted
        """
        async with self.get_connection() as conn:
            # Get IDs of expired events
            async with conn.execute(
                "SELECT id FROM user_data WHERE CAST(end_date AS INTEGER) < ?",
                (before_timestamp,)
            ) as cursor:
                expired_ids = [row[0] async for row in cursor]

            if not expired_ids:
                return 0

            # Delete associated messages
            placeholders = ",".join("?" * len(expired_ids))
            await conn.execute(
                f"DELETE FROM event_messages WHERE event_id IN ({placeholders})",
                expired_ids
            )

            # Delete events
            cursor = await conn.execute(
                f"DELETE FROM user_data WHERE id IN ({placeholders})",
                expired_ids
            )
            await conn.commit()
            return cursor.rowcount

    async def mark_ended(self, server_id: str) -> int:
        """
        Mark expired events as 'Ended'.

        Args:
            server_id: Discord server ID

        Returns:
            Number of events marked as ended
        """
        now = int(time.time())
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                '''UPDATE user_data SET category='Ended'
                   WHERE server_id=? AND category != 'Ended'
                   AND end_date != '' AND CAST(end_date AS INTEGER) < ?''',
                (server_id, now)
            )
            await conn.commit()
            return cursor.rowcount

    async def get_by_title(
        self,
        title: str,
        profile: Optional[str] = None,
        server_id: Optional[str] = None
    ) -> Optional[Event]:
        """
        Get an event by its title.

        Args:
            title: Event title
            profile: Filter by game profile (optional)
            server_id: Filter by server ID (optional)

        Returns:
            Event entity or None if not found
        """
        query = '''
            SELECT id, user_id, server_id, title, start_date, end_date, image,
                   category, is_hyv, asia_start, asia_end, america_start,
                   america_end, europe_start, europe_end, profile
            FROM user_data WHERE title = ?
        '''
        params = [title]

        if profile:
            query += " AND profile = ?"
            params.append(profile)
        if server_id:
            query += " AND server_id = ?"
            params.append(server_id)

        row = await self.fetch_one(query, tuple(params))
        if row:
            return self._row_to_event(row)
        return None

    def _row_to_event(self, row: tuple) -> Event:
        """
        Convert a database row to an Event entity.

        Args:
            row: Database row tuple

        Returns:
            Event entity
        """
        return Event(
            id=row[0],
            user_id=row[1],
            server_id=row[2],
            title=row[3],
            start_date=safe_int(row[4], 0),
            end_date=safe_int(row[5], 0),
            image=row[6],
            category=row[7],
            is_hyv=bool(safe_int(row[8], 0)),
            asia_start=safe_int(row[9], 0) if row[9] else None,
            asia_end=safe_int(row[10], 0) if row[10] else None,
            america_start=safe_int(row[11], 0) if row[11] else None,
            america_end=safe_int(row[12], 0) if row[12] else None,
            europe_start=safe_int(row[13], 0) if row[13] else None,
            europe_end=safe_int(row[14], 0) if row[14] else None,
            profile=row[15] if len(row) > 15 else "Unknown",
        )


class ProfileEventRepository(SQLiteEventRepository):
    """
    Event repository for profile-specific databases.

    Used for games that have their own database (e.g., Arknights, Uma Musume, HSR).
    """

    def __init__(self, profile: str, db_path: str):
        """
        Initialize the profile-specific event repository.

        Args:
            profile: Game profile code (e.g., "AK", "UMA", "HSR")
            db_path: Path to the profile-specific database
        """
        super().__init__(db_path)
        self.profile = profile

    async def initialize(self):
        """Initialize the database schema for profile-specific events."""
        async with self.get_connection() as conn:
            # Create events table (schema may vary by profile)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    title TEXT,
                    start_date INTEGER,
                    end_date INTEGER,
                    image TEXT,
                    category TEXT,
                    description TEXT,
                    source_url TEXT,
                    created_at INTEGER,
                    updated_at INTEGER
                )
            ''')
            await conn.commit()

        # Create indexes
        await self.create_index_if_not_exists(
            "idx_profile_events_category",
            "events",
            ["category"]
        )
        await self.create_index_if_not_exists(
            "idx_profile_events_end_date",
            "events",
            ["end_date"]
        )

    async def create(self, event: Event) -> int:
        """Create a new event in the profile database."""
        now = int(time.time())
        query = '''
            INSERT INTO events (
                user_id, title, start_date, end_date, image,
                category, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            event.user_id,
            event.title,
            event.start_date,
            event.end_date,
            event.image,
            event.category,
            now,
            now,
        )
        return await self.execute(query, params)

    async def get_all(
        self,
        server_id: Optional[str] = None,
        profile: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[Event]:
        """Get all events from the profile database."""
        query = '''
            SELECT id, user_id, title, start_date, end_date, image, category
            FROM events WHERE 1=1
        '''
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY id DESC"

        rows = await self.fetch_all(query, tuple(params))
        return [self._profile_row_to_event(row) for row in rows]

    def _profile_row_to_event(self, row: tuple) -> Event:
        """Convert a profile database row to an Event entity."""
        return Event(
            id=row[0],
            user_id=row[1],
            server_id=None,
            title=row[2],
            start_date=safe_int(row[3], 0),
            end_date=safe_int(row[4], 0),
            image=row[5],
            category=row[6],
            profile=self.profile,
        )
