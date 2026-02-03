"""
Channel Repository for tracking event messages and channel states.

This module handles the tracking of event messages displayed in timer channels,
allowing for efficient updates and cleanup.
"""

from typing import List, Optional, Dict

from .base import BaseRepository


class ChannelRepository(BaseRepository):
    """
    Repository for managing event messages in channels.

    Tracks which messages are associated with which events,
    enabling efficient updates and cleanup of timer channels.
    """

    def __init__(self, db_path: str = "kanami_data.db"):
        """
        Initialize the channel repository.

        Args:
            db_path: Path to the SQLite database file
        """
        super().__init__(db_path)

    async def initialize(self):
        """Initialize the database schema."""
        async with self.get_connection() as conn:
            # Event messages tracking table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS event_messages (
                    event_id INTEGER,
                    server_id TEXT,
                    channel_id TEXT,
                    message_id TEXT,
                    PRIMARY KEY (event_id, channel_id)
                )
            ''')

            # Channel state tracking (for dashboard updates)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS channel_state (
                    server_id TEXT,
                    channel_id TEXT,
                    profile TEXT,
                    last_update INTEGER,
                    message_count INTEGER DEFAULT 0,
                    PRIMARY KEY (server_id, channel_id, profile)
                )
            ''')

            await conn.commit()

        # Create indexes
        await self.create_index_if_not_exists(
            "idx_event_messages_channel",
            "event_messages",
            ["server_id", "channel_id"]
        )

    # ==================== Event Message Methods ====================

    async def get_message_id(
        self,
        event_id: int,
        channel_id: str
    ) -> Optional[str]:
        """
        Get the message ID for an event in a channel.

        Args:
            event_id: Event ID
            channel_id: Discord channel ID

        Returns:
            Message ID or None if not found
        """
        row = await self.fetch_one(
            "SELECT message_id FROM event_messages WHERE event_id = ? AND channel_id = ?",
            (event_id, channel_id)
        )
        return row[0] if row else None

    async def set_message_id(
        self,
        event_id: int,
        server_id: str,
        channel_id: str,
        message_id: str
    ) -> bool:
        """
        Set the message ID for an event in a channel.

        Args:
            event_id: Event ID
            server_id: Discord server ID
            channel_id: Discord channel ID
            message_id: Discord message ID

        Returns:
            True if set successfully
        """
        await self.execute(
            '''INSERT OR REPLACE INTO event_messages
               (event_id, server_id, channel_id, message_id)
               VALUES (?, ?, ?, ?)''',
            (event_id, server_id, channel_id, message_id)
        )
        return True

    async def delete_message_record(
        self,
        event_id: int,
        channel_id: str
    ) -> bool:
        """
        Delete the message record for an event in a channel.

        Args:
            event_id: Event ID
            channel_id: Discord channel ID

        Returns:
            True if deleted successfully
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM event_messages WHERE event_id = ? AND channel_id = ?",
                (event_id, channel_id)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def get_all_messages_in_channel(
        self,
        server_id: str,
        channel_id: str
    ) -> Dict[int, str]:
        """
        Get all event message mappings for a channel.

        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID

        Returns:
            Dictionary mapping event_id to message_id
        """
        rows = await self.fetch_all(
            "SELECT event_id, message_id FROM event_messages WHERE server_id = ? AND channel_id = ?",
            (server_id, channel_id)
        )
        return {row[0]: row[1] for row in rows}

    async def delete_messages_for_event(self, event_id: int) -> int:
        """
        Delete all message records for an event.

        Args:
            event_id: Event ID

        Returns:
            Number of records deleted
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM event_messages WHERE event_id = ?",
                (event_id,)
            )
            await conn.commit()
            return cursor.rowcount

    async def delete_messages_in_channel(
        self,
        server_id: str,
        channel_id: str
    ) -> int:
        """
        Delete all message records for a channel.

        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID

        Returns:
            Number of records deleted
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM event_messages WHERE server_id = ? AND channel_id = ?",
                (server_id, channel_id)
            )
            await conn.commit()
            return cursor.rowcount

    async def get_orphaned_message_ids(
        self,
        server_id: str,
        channel_id: str,
        valid_event_ids: List[int]
    ) -> List[str]:
        """
        Get message IDs for events that no longer exist.

        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID
            valid_event_ids: List of currently valid event IDs

        Returns:
            List of orphaned message IDs
        """
        all_messages = await self.get_all_messages_in_channel(server_id, channel_id)

        orphaned = []
        for event_id, message_id in all_messages.items():
            if event_id not in valid_event_ids:
                orphaned.append(message_id)

        return orphaned

    # ==================== Channel State Methods ====================

    async def update_channel_state(
        self,
        server_id: str,
        channel_id: str,
        profile: str,
        message_count: int
    ) -> bool:
        """
        Update the channel state after a dashboard refresh.

        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID
            profile: Game profile
            message_count: Number of event messages in the channel

        Returns:
            True if updated successfully
        """
        import time
        await self.execute(
            '''INSERT OR REPLACE INTO channel_state
               (server_id, channel_id, profile, last_update, message_count)
               VALUES (?, ?, ?, ?, ?)''',
            (server_id, channel_id, profile, int(time.time()), message_count)
        )
        return True

    async def get_channel_state(
        self,
        server_id: str,
        channel_id: str,
        profile: str
    ) -> Optional[dict]:
        """
        Get the current state of a channel.

        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID
            profile: Game profile

        Returns:
            Dictionary with last_update and message_count, or None
        """
        row = await self.fetch_one(
            '''SELECT last_update, message_count FROM channel_state
               WHERE server_id = ? AND channel_id = ? AND profile = ?''',
            (server_id, channel_id, profile)
        )
        if row:
            return {"last_update": row[0], "message_count": row[1]}
        return None

    async def should_refresh(
        self,
        server_id: str,
        channel_id: str,
        profile: str,
        cooldown_seconds: int = 10
    ) -> bool:
        """
        Check if a channel should be refreshed (cooldown check).

        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID
            profile: Game profile
            cooldown_seconds: Minimum seconds between refreshes

        Returns:
            True if enough time has passed since last refresh
        """
        import time
        state = await self.get_channel_state(server_id, channel_id, profile)

        if not state:
            return True

        elapsed = int(time.time()) - state["last_update"]
        return elapsed >= cooldown_seconds
