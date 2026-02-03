"""
SQLite implementation of the Config Repository.

This module provides concrete implementation of the ConfigRepository interface
for SQLite databases, handling channel configurations, roles, and settings.
"""

from typing import List, Optional, Dict

from src.core.interfaces import ConfigRepository
from src.core.models import GameProfile, EventCategory
from .base import BaseRepository


class SQLiteConfigRepository(BaseRepository, ConfigRepository):
    """
    SQLite implementation of ConfigRepository.

    Handles channel configurations, role mappings, and server settings.
    """

    # Default categories that are always available
    DEFAULT_CATEGORIES = [
        EventCategory.BANNER.value,
        EventCategory.EVENT.value,
        EventCategory.MAINTENANCE.value,
        EventCategory.OFFER.value,
    ]

    def __init__(self, db_path: str = "kanami_data.db"):
        """
        Initialize the config repository.

        Args:
            db_path: Path to the SQLite database file
        """
        super().__init__(db_path)

    async def initialize(self):
        """Initialize the database schema."""
        async with self.get_connection() as conn:
            # Timer channel config
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS config (
                    server_id TEXT,
                    profile TEXT,
                    timer_channel_id TEXT,
                    PRIMARY KEY (server_id, profile)
                )
            ''')

            # Announcement channel config
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS announce_config (
                    server_id TEXT PRIMARY KEY,
                    announce_channel_id TEXT
                )
            ''')

            # Notification channel (per profile)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notification_channel (
                    server_id TEXT,
                    profile TEXT,
                    channel_id TEXT,
                    PRIMARY KEY (server_id, profile)
                )
            ''')

            # Notification timing status channel/message
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notification_timing_channel (
                    server_id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    message_id TEXT
                )
            ''')

            # Notification timings per category and type
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notification_timings (
                    server_id TEXT,
                    category TEXT,
                    timing_type TEXT,
                    timing_minutes INTEGER,
                    PRIMARY KEY (server_id, category, timing_type)
                )
            ''')

            # Role reaction emoji-role mapping
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS role_reactions (
                    server_id TEXT,
                    message_id TEXT,
                    emoji TEXT,
                    role_id TEXT,
                    PRIMARY KEY (server_id, emoji)
                )
            ''')

            # Custom categories per server/profile
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS custom_categories (
                    server_id TEXT,
                    profile TEXT,
                    category TEXT,
                    PRIMARY KEY (server_id, profile, category)
                )
            ''')

            # Listener channels for Twitter/X monitoring
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS listener_channels (
                    server_id TEXT,
                    profile TEXT,
                    channel_id TEXT,
                    required_keywords TEXT,
                    ignored_keywords TEXT,
                    PRIMARY KEY (server_id, profile)
                )
            ''')

            # Control panel channels
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS control_panel_channels (
                    server_id TEXT,
                    profile TEXT,
                    channel_id TEXT,
                    message_id TEXT,
                    PRIMARY KEY (server_id, profile)
                )
            ''')

            await conn.commit()

    # ==================== Timer Channel Methods ====================

    async def get_timer_channel(self, server_id: str, profile: str) -> Optional[str]:
        """
        Get the timer channel ID for a server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile

        Returns:
            Channel ID or None if not configured
        """
        # First try exact profile match
        row = await self.fetch_one(
            "SELECT timer_channel_id FROM config WHERE server_id = ? AND profile = ?",
            (server_id, profile)
        )
        if row:
            return row[0]

        # Fall back to ALL profile
        row = await self.fetch_one(
            "SELECT timer_channel_id FROM config WHERE server_id = ? AND profile = 'ALL'",
            (server_id,)
        )
        return row[0] if row else None

    async def set_timer_channel(self, server_id: str, profile: str, channel_id: str) -> bool:
        """
        Set the timer channel for a server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile
            channel_id: Discord channel ID

        Returns:
            True if set successfully
        """
        await self.execute(
            '''INSERT OR REPLACE INTO config (server_id, profile, timer_channel_id)
               VALUES (?, ?, ?)''',
            (server_id, profile, channel_id)
        )
        return True

    async def get_all_timer_channels(self, server_id: str) -> Dict[str, str]:
        """
        Get all timer channels for a server.

        Args:
            server_id: Discord server ID

        Returns:
            Dictionary mapping profile to channel ID
        """
        rows = await self.fetch_all(
            "SELECT profile, timer_channel_id FROM config WHERE server_id = ?",
            (server_id,)
        )
        return {row[0]: row[1] for row in rows}

    # ==================== Notification Channel Methods ====================

    async def get_notification_channel(self, profile: str) -> Optional[str]:
        """
        Get the notification channel ID for a profile.

        Args:
            profile: Game profile

        Returns:
            Channel ID or None if not configured
        """
        # Note: This method looks up by profile across all servers
        # In a multi-server setup, you'd want to include server_id
        row = await self.fetch_one(
            "SELECT channel_id FROM notification_channel WHERE profile = ?",
            (profile,)
        )
        return row[0] if row else None

    async def get_notification_channel_for_server(
        self,
        server_id: str,
        profile: str
    ) -> Optional[str]:
        """
        Get the notification channel for a specific server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile

        Returns:
            Channel ID or None if not configured
        """
        row = await self.fetch_one(
            '''SELECT channel_id FROM notification_channel
               WHERE server_id = ? AND profile = ?''',
            (server_id, profile)
        )
        return row[0] if row else None

    async def set_notification_channel(
        self,
        server_id: str,
        profile: str,
        channel_id: str
    ) -> bool:
        """
        Set the notification channel for a server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile
            channel_id: Discord channel ID

        Returns:
            True if set successfully
        """
        await self.execute(
            '''INSERT OR REPLACE INTO notification_channel (server_id, profile, channel_id)
               VALUES (?, ?, ?)''',
            (server_id, profile, channel_id)
        )
        return True

    # ==================== Category Methods ====================

    async def get_valid_categories(self, server_id: str, profile: str) -> List[str]:
        """
        Get list of valid categories for a server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile

        Returns:
            List of valid category names
        """
        # Start with default categories
        categories = list(self.DEFAULT_CATEGORIES)

        # Add Uma Musume specific categories if applicable
        if profile == "UMA":
            categories.extend(EventCategory.uma_categories())

        # Add custom categories
        rows = await self.fetch_all(
            '''SELECT category FROM custom_categories
               WHERE server_id = ? AND profile = ?''',
            (server_id, profile)
        )
        for row in rows:
            if row[0] not in categories:
                categories.append(row[0])

        return categories

    async def add_custom_category(
        self,
        server_id: str,
        profile: str,
        category: str
    ) -> bool:
        """
        Add a custom category for a server and profile.

        Args:
            server_id: Discord server ID
            profile: Game profile
            category: Category name to add

        Returns:
            True if added successfully
        """
        await self.execute(
            '''INSERT OR IGNORE INTO custom_categories (server_id, profile, category)
               VALUES (?, ?, ?)''',
            (server_id, profile, category)
        )
        return True

    async def remove_custom_category(
        self,
        server_id: str,
        profile: str,
        category: str
    ) -> bool:
        """
        Remove a custom category.

        Args:
            server_id: Discord server ID
            profile: Game profile
            category: Category name to remove

        Returns:
            True if removed successfully
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                '''DELETE FROM custom_categories
                   WHERE server_id = ? AND profile = ? AND category = ?''',
                (server_id, profile, category)
            )
            await conn.commit()
            return cursor.rowcount > 0

    # ==================== Role Reaction Methods ====================

    async def get_role_for_emoji(
        self,
        server_id: str,
        emoji: str
    ) -> Optional[str]:
        """
        Get the role ID for a reaction emoji.

        Args:
            server_id: Discord server ID
            emoji: Emoji string

        Returns:
            Role ID or None if not mapped
        """
        row = await self.fetch_one(
            "SELECT role_id FROM role_reactions WHERE server_id = ? AND emoji = ?",
            (server_id, emoji)
        )
        return row[0] if row else None

    async def set_role_reaction(
        self,
        server_id: str,
        message_id: str,
        emoji: str,
        role_id: str
    ) -> bool:
        """
        Set a role reaction mapping.

        Args:
            server_id: Discord server ID
            message_id: Message ID with the reaction
            emoji: Emoji string
            role_id: Role ID to assign

        Returns:
            True if set successfully
        """
        await self.execute(
            '''INSERT OR REPLACE INTO role_reactions
               (server_id, message_id, emoji, role_id)
               VALUES (?, ?, ?, ?)''',
            (server_id, message_id, emoji, role_id)
        )
        return True

    async def get_all_role_reactions(self, server_id: str) -> List[dict]:
        """
        Get all role reaction mappings for a server.

        Args:
            server_id: Discord server ID

        Returns:
            List of role reaction mappings
        """
        rows = await self.fetch_all(
            "SELECT message_id, emoji, role_id FROM role_reactions WHERE server_id = ?",
            (server_id,)
        )
        return [
            {"message_id": row[0], "emoji": row[1], "role_id": row[2]}
            for row in rows
        ]

    # ==================== Listener Channel Methods ====================

    async def get_listener_channel(
        self,
        server_id: str,
        profile: str
    ) -> Optional[dict]:
        """
        Get listener channel configuration.

        Args:
            server_id: Discord server ID
            profile: Game profile

        Returns:
            Dictionary with channel_id, required_keywords, ignored_keywords
            or None if not configured
        """
        row = await self.fetch_one(
            '''SELECT channel_id, required_keywords, ignored_keywords
               FROM listener_channels WHERE server_id = ? AND profile = ?''',
            (server_id, profile)
        )
        if row:
            return {
                "channel_id": row[0],
                "required_keywords": row[1].split(",") if row[1] else [],
                "ignored_keywords": row[2].split(",") if row[2] else [],
            }
        return None

    async def set_listener_channel(
        self,
        server_id: str,
        profile: str,
        channel_id: str,
        required_keywords: Optional[List[str]] = None,
        ignored_keywords: Optional[List[str]] = None
    ) -> bool:
        """
        Set listener channel configuration.

        Args:
            server_id: Discord server ID
            profile: Game profile
            channel_id: Discord channel ID
            required_keywords: Keywords that must appear in tweets
            ignored_keywords: Keywords that skip tweets

        Returns:
            True if set successfully
        """
        await self.execute(
            '''INSERT OR REPLACE INTO listener_channels
               (server_id, profile, channel_id, required_keywords, ignored_keywords)
               VALUES (?, ?, ?, ?, ?)''',
            (
                server_id,
                profile,
                channel_id,
                ",".join(required_keywords) if required_keywords else None,
                ",".join(ignored_keywords) if ignored_keywords else None,
            )
        )
        return True

    # ==================== Control Panel Methods ====================

    async def get_control_panel(
        self,
        server_id: str,
        profile: str
    ) -> Optional[dict]:
        """
        Get control panel configuration.

        Args:
            server_id: Discord server ID
            profile: Game profile

        Returns:
            Dictionary with channel_id and message_id, or None
        """
        row = await self.fetch_one(
            '''SELECT channel_id, message_id FROM control_panel_channels
               WHERE server_id = ? AND profile = ?''',
            (server_id, profile)
        )
        if row:
            return {"channel_id": row[0], "message_id": row[1]}
        return None

    async def set_control_panel(
        self,
        server_id: str,
        profile: str,
        channel_id: str,
        message_id: str
    ) -> bool:
        """
        Set control panel configuration.

        Args:
            server_id: Discord server ID
            profile: Game profile
            channel_id: Discord channel ID
            message_id: Control panel message ID

        Returns:
            True if set successfully
        """
        await self.execute(
            '''INSERT OR REPLACE INTO control_panel_channels
               (server_id, profile, channel_id, message_id)
               VALUES (?, ?, ?, ?)''',
            (server_id, profile, channel_id, message_id)
        )
        return True

    # ==================== Announcement Channel Methods ====================

    async def get_announce_channel(self, server_id: str) -> Optional[str]:
        """
        Get the announcement channel for a server.

        Args:
            server_id: Discord server ID

        Returns:
            Channel ID or None if not configured
        """
        row = await self.fetch_one(
            "SELECT announce_channel_id FROM announce_config WHERE server_id = ?",
            (server_id,)
        )
        return row[0] if row else None

    async def set_announce_channel(self, server_id: str, channel_id: str) -> bool:
        """
        Set the announcement channel for a server.

        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID

        Returns:
            True if set successfully
        """
        await self.execute(
            '''INSERT OR REPLACE INTO announce_config (server_id, announce_channel_id)
               VALUES (?, ?)''',
            (server_id, channel_id)
        )
        return True
