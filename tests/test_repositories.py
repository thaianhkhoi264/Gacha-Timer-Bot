"""
Tests for repository implementations.

These tests verify that the new repository classes work identically to the old
database_handler.py and notification_handler.py code patterns.

The tests:
1. Create databases using the OLD code patterns (raw SQL matching original code)
2. Verify the NEW repository classes can read/write data correctly
3. Ensure backwards compatibility with existing database files
"""

import pytest
import aiosqlite
import os
import time
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.models import Event, Notification, GameProfile, EventCategory
from src.core.repositories import (
    SQLiteEventRepository,
    SQLiteNotificationRepository,
    SQLiteConfigRepository,
    ChannelRepository,
)


# =============================================================================
# Fixtures that create databases using OLD CODE patterns
# =============================================================================

@pytest.fixture
async def old_style_event_db(tmp_path):
    """
    Create a database using the EXACT schema from the old database_handler.py init_db().
    This simulates what the production database looks like.
    """
    db_path = str(tmp_path / "kanami_data.db")

    # This is the EXACT code from database_handler.py init_db()
    import sqlite3
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Event data - exact schema from old code
    c.execute('''CREATE TABLE IF NOT EXISTS user_data (
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
                )''')

    # Event messages IDs
    c.execute('''CREATE TABLE IF NOT EXISTS event_messages (
                    event_id INTEGER,
                    server_id TEXT,
                    channel_id TEXT,
                    message_id TEXT,
                    PRIMARY KEY (event_id, channel_id)
                )''')

    # Timer channel config
    c.execute('''CREATE TABLE IF NOT EXISTS config (
                    server_id TEXT,
                    profile TEXT,
                    timer_channel_id TEXT,
                    PRIMARY KEY (server_id, profile)
                )''')

    # Announcement channel config
    c.execute('''CREATE TABLE IF NOT EXISTS announce_config (
                    server_id TEXT PRIMARY KEY,
                    announce_channel_id TEXT
                )''')

    # Role reaction emoji-role mapping
    c.execute('''CREATE TABLE IF NOT EXISTS role_reactions (
                    server_id TEXT,
                    message_id TEXT,
                    emoji TEXT,
                    role_id TEXT,
                    PRIMARY KEY (server_id, emoji)
                )''')

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
async def old_style_notification_db(tmp_path):
    """
    Create a notification database using the EXACT schema from notification_handler.py.
    """
    db_path = str(tmp_path / "notification_data.db")

    async with aiosqlite.connect(db_path) as conn:
        # Exact schema from notification_handler.py init_notification_db()
        await conn.execute('''CREATE TABLE IF NOT EXISTS pending_notifications (
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
        )''')

        # UNIQUE index to prevent duplicates
        await conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_pending_notif
            ON pending_notifications (category, profile, title, timing_type, notify_unix, region)
        ''')

        await conn.execute('''CREATE TABLE IF NOT EXISTS pending_notifications_messages (
            profile TEXT,
            message_id TEXT,
            PRIMARY KEY (profile, message_id)
        )''')

        await conn.execute('''CREATE TABLE IF NOT EXISTS role_reaction_messages (
            type TEXT PRIMARY KEY,
            message_id TEXT
        )''')

        await conn.commit()

    yield db_path

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def sample_event_data():
    """Sample event data matching production patterns."""
    now = int(time.time())
    return {
        "user_id": "123456789",
        "server_id": "987654321",
        "title": "Test Banner Event",
        "start_date": str(now + 3600),  # 1 hour from now
        "end_date": str(now + 86400),   # 1 day from now
        "image": "https://example.com/image.png",
        "category": "Banner",
        "is_hyv": 0,
        "asia_start": None,
        "asia_end": None,
        "america_start": None,
        "america_end": None,
        "europe_start": None,
        "europe_end": None,
        "profile": "AK",
    }


@pytest.fixture
def sample_hyv_event_data():
    """Sample Hoyoverse event data with regional timings."""
    now = int(time.time())
    return {
        "user_id": "123456789",
        "server_id": "987654321",
        "title": "HSR Version Update",
        "start_date": str(now + 3600),
        "end_date": str(now + 86400),
        "image": "https://example.com/hsr.png",
        "category": "Event",
        "is_hyv": 1,
        "asia_start": str(now + 3600),
        "asia_end": str(now + 86400),
        "america_start": str(now + 3600 + 43200),  # 12h offset
        "america_end": str(now + 86400 + 43200),
        "europe_start": str(now + 3600 + 28800),   # 8h offset
        "europe_end": str(now + 86400 + 28800),
        "profile": "HSR",
    }


# =============================================================================
# Event Repository Tests
# =============================================================================

class TestEventRepository:
    """Tests for SQLiteEventRepository."""

    @pytest.mark.asyncio
    async def test_create_and_read_event(self, old_style_event_db, sample_event_data):
        """Test creating an event and reading it back."""
        repo = SQLiteEventRepository(old_style_event_db)

        # Create event using new repository
        event = Event(
            user_id=sample_event_data["user_id"],
            server_id=sample_event_data["server_id"],
            title=sample_event_data["title"],
            start_date=int(sample_event_data["start_date"]),
            end_date=int(sample_event_data["end_date"]),
            image=sample_event_data["image"],
            category=sample_event_data["category"],
            profile=sample_event_data["profile"],
        )

        event_id = await repo.create(event)
        assert event_id > 0

        # Read it back
        retrieved = await repo.get_by_id(event_id)
        assert retrieved is not None
        assert retrieved.title == sample_event_data["title"]
        assert retrieved.category == sample_event_data["category"]
        assert retrieved.profile == sample_event_data["profile"]

    @pytest.mark.asyncio
    async def test_read_old_format_data(self, old_style_event_db, sample_event_data):
        """Test reading data that was written using OLD code patterns."""
        # Insert data using OLD code pattern (raw SQL)
        import sqlite3
        conn = sqlite3.connect(old_style_event_db)
        c = conn.cursor()
        c.execute('''
            INSERT INTO user_data (user_id, server_id, title, start_date, end_date,
                                   image, category, is_hyv, profile)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            sample_event_data["user_id"],
            sample_event_data["server_id"],
            sample_event_data["title"],
            sample_event_data["start_date"],
            sample_event_data["end_date"],
            sample_event_data["image"],
            sample_event_data["category"],
            sample_event_data["is_hyv"],
            sample_event_data["profile"],
        ))
        conn.commit()
        event_id = c.lastrowid
        conn.close()

        # Read using NEW repository
        repo = SQLiteEventRepository(old_style_event_db)
        retrieved = await repo.get_by_id(event_id)

        assert retrieved is not None
        assert retrieved.title == sample_event_data["title"]
        assert retrieved.start_date == int(sample_event_data["start_date"])
        assert retrieved.end_date == int(sample_event_data["end_date"])

    @pytest.mark.asyncio
    async def test_hyv_event_regional_times(self, old_style_event_db, sample_hyv_event_data):
        """Test Hoyoverse events with regional timing data."""
        # Insert using old pattern
        import sqlite3
        conn = sqlite3.connect(old_style_event_db)
        c = conn.cursor()
        c.execute('''
            INSERT INTO user_data (user_id, server_id, title, start_date, end_date,
                                   image, category, is_hyv, asia_start, asia_end,
                                   america_start, america_end, europe_start, europe_end, profile)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            sample_hyv_event_data["user_id"],
            sample_hyv_event_data["server_id"],
            sample_hyv_event_data["title"],
            sample_hyv_event_data["start_date"],
            sample_hyv_event_data["end_date"],
            sample_hyv_event_data["image"],
            sample_hyv_event_data["category"],
            sample_hyv_event_data["is_hyv"],
            sample_hyv_event_data["asia_start"],
            sample_hyv_event_data["asia_end"],
            sample_hyv_event_data["america_start"],
            sample_hyv_event_data["america_end"],
            sample_hyv_event_data["europe_start"],
            sample_hyv_event_data["europe_end"],
            sample_hyv_event_data["profile"],
        ))
        conn.commit()
        event_id = c.lastrowid
        conn.close()

        # Read using new repository
        repo = SQLiteEventRepository(old_style_event_db)
        retrieved = await repo.get_by_id(event_id)

        assert retrieved is not None
        assert retrieved.is_hyv == True
        assert retrieved.asia_start == int(sample_hyv_event_data["asia_start"])
        assert retrieved.america_start == int(sample_hyv_event_data["america_start"])
        assert retrieved.europe_start == int(sample_hyv_event_data["europe_start"])

    @pytest.mark.asyncio
    async def test_get_ongoing_events(self, old_style_event_db):
        """Test filtering for ongoing events."""
        repo = SQLiteEventRepository(old_style_event_db)
        now = int(time.time())

        # Create an ongoing event
        ongoing = Event(
            title="Ongoing Event",
            start_date=now - 3600,  # Started 1 hour ago
            end_date=now + 3600,    # Ends in 1 hour
            category="Event",
            profile="AK",
            server_id="123",
        )
        await repo.create(ongoing)

        # Create an upcoming event
        upcoming = Event(
            title="Upcoming Event",
            start_date=now + 7200,  # Starts in 2 hours
            end_date=now + 86400,
            category="Event",
            profile="AK",
            server_id="123",
        )
        await repo.create(upcoming)

        # Get ongoing
        ongoing_events = await repo.get_ongoing(server_id="123")
        assert len(ongoing_events) == 1
        assert ongoing_events[0].title == "Ongoing Event"

    @pytest.mark.asyncio
    async def test_update_event(self, old_style_event_db, sample_event_data):
        """Test updating an event."""
        repo = SQLiteEventRepository(old_style_event_db)

        # Create event
        event = Event(
            title=sample_event_data["title"],
            start_date=int(sample_event_data["start_date"]),
            end_date=int(sample_event_data["end_date"]),
            category=sample_event_data["category"],
            profile=sample_event_data["profile"],
        )
        event_id = await repo.create(event)

        # Update it
        event.id = event_id
        event.title = "Updated Title"
        success = await repo.update(event)

        assert success

        # Verify update
        retrieved = await repo.get_by_id(event_id)
        assert retrieved.title == "Updated Title"

    @pytest.mark.asyncio
    async def test_delete_event(self, old_style_event_db, sample_event_data):
        """Test deleting an event."""
        repo = SQLiteEventRepository(old_style_event_db)

        # Create event
        event = Event(
            title=sample_event_data["title"],
            start_date=int(sample_event_data["start_date"]),
            end_date=int(sample_event_data["end_date"]),
            category=sample_event_data["category"],
            profile=sample_event_data["profile"],
        )
        event_id = await repo.create(event)

        # Delete it
        success = await repo.delete(event_id)
        assert success

        # Verify deletion
        retrieved = await repo.get_by_id(event_id)
        assert retrieved is None


# =============================================================================
# Notification Repository Tests
# =============================================================================

class TestNotificationRepository:
    """Tests for SQLiteNotificationRepository."""

    @pytest.mark.asyncio
    async def test_create_and_read_notification(self, old_style_notification_db):
        """Test creating a notification and reading it back."""
        repo = SQLiteNotificationRepository(old_style_notification_db)
        await repo.initialize()

        now = int(time.time())
        notification = Notification(
            category="Banner",
            profile="AK",
            title="Test Event",
            timing_type="start_1h",
            notify_unix=now + 3600,
            event_time_unix=now + 7200,
        )

        notif_id = await repo.create(notification)
        assert notif_id > 0

        # Read it back
        retrieved = await repo.get_by_id(notif_id)
        assert retrieved is not None
        assert retrieved.title == "Test Event"
        assert retrieved.timing_type == "start_1h"

    @pytest.mark.asyncio
    async def test_read_old_format_notification(self, old_style_notification_db):
        """Test reading notifications written with OLD code patterns."""
        now = int(time.time())

        # Insert using OLD code pattern
        async with aiosqlite.connect(old_style_notification_db) as conn:
            await conn.execute('''
                INSERT INTO pending_notifications
                (category, profile, title, timing_type, notify_unix, event_time_unix, sent, region)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            ''', ("Banner", "HSR", "Old Style Event", "start_3h", now + 10800, now + 14400, "ASIA"))
            await conn.commit()

        # Read using NEW repository
        repo = SQLiteNotificationRepository(old_style_notification_db)
        pending = await repo.get_pending(profile="HSR")

        assert len(pending) == 1
        assert pending[0].title == "Old Style Event"
        assert pending[0].region == "ASIA"

    @pytest.mark.asyncio
    async def test_duplicate_prevention(self, old_style_notification_db):
        """Test that duplicate notifications are prevented (matching old behavior)."""
        repo = SQLiteNotificationRepository(old_style_notification_db)
        await repo.initialize()

        now = int(time.time())
        # Use region="ASIA" because SQLite treats NULL as distinct in unique indexes
        # This matches production behavior where HYV games always have region set
        notification = Notification(
            category="Banner",
            profile="HSR",
            title="Test Event",
            timing_type="start_1h",
            notify_unix=now + 3600,
            event_time_unix=now + 7200,
            region="ASIA",  # Non-NULL region for unique constraint to work
        )

        # Create first
        id1 = await repo.create(notification)

        # Try to create duplicate - should be ignored due to unique index
        id2 = await repo.create(notification)

        # Count should still be 1
        count = await repo.count_pending()
        assert count == 1

    @pytest.mark.asyncio
    async def test_mark_sent(self, old_style_notification_db):
        """Test marking notification as sent."""
        repo = SQLiteNotificationRepository(old_style_notification_db)
        await repo.initialize()

        now = int(time.time())
        notification = Notification(
            category="Event",
            profile="UMA",
            title="Test",
            timing_type="reminder",
            notify_unix=now,
            event_time_unix=now + 86400,
        )

        notif_id = await repo.create(notification)

        # Mark as sent
        success = await repo.mark_sent(notif_id)
        assert success

        # Should not appear in pending
        pending = await repo.get_pending()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_champions_meeting_notification(self, old_style_notification_db):
        """Test Uma Musume Champions Meeting notification with phase data."""
        repo = SQLiteNotificationRepository(old_style_notification_db)
        await repo.initialize()

        now = int(time.time())
        notification = Notification(
            category="Champions Meeting",
            profile="UMA",
            title="January Champions Meeting",
            timing_type="phase_start",
            notify_unix=now + 3600,
            event_time_unix=now + 3600,
            message_template="uma_champions_meeting_round1_start",
            phase="Round 1",
        )

        notif_id = await repo.create(notification)
        retrieved = await repo.get_by_id(notif_id)

        assert retrieved.phase == "Round 1"
        assert retrieved.message_template == "uma_champions_meeting_round1_start"

    @pytest.mark.asyncio
    async def test_delete_for_event(self, old_style_notification_db):
        """Test deleting all notifications for a specific event."""
        repo = SQLiteNotificationRepository(old_style_notification_db)
        await repo.initialize()

        now = int(time.time())

        # Create multiple notifications for same event
        for timing in ["reminder", "start_1h", "start_3h", "end_1h"]:
            notification = Notification(
                category="Banner",
                profile="AK",
                title="Multi-Notif Event",
                timing_type=timing,
                notify_unix=now + 3600,
                event_time_unix=now + 7200,
            )
            await repo.create(notification)

        # Should have 4 notifications
        notifs = await repo.get_for_event("AK", "Multi-Notif Event", "Banner")
        assert len(notifs) == 4

        # Delete all for event
        deleted = await repo.delete_for_event("AK", "Multi-Notif Event", "Banner")
        assert deleted == 4

        # Should have 0 now
        notifs = await repo.get_for_event("AK", "Multi-Notif Event", "Banner")
        assert len(notifs) == 0


# =============================================================================
# Config Repository Tests
# =============================================================================

class TestConfigRepository:
    """Tests for SQLiteConfigRepository."""

    @pytest.mark.asyncio
    async def test_timer_channel_config(self, old_style_event_db):
        """Test timer channel configuration."""
        repo = SQLiteConfigRepository(old_style_event_db)
        await repo.initialize()

        # Set timer channel
        await repo.set_timer_channel("server123", "AK", "channel456")

        # Get it back
        channel_id = await repo.get_timer_channel("server123", "AK")
        assert channel_id == "channel456"

    @pytest.mark.asyncio
    async def test_timer_channel_fallback_to_all(self, old_style_event_db):
        """Test that timer channel falls back to ALL profile."""
        repo = SQLiteConfigRepository(old_style_event_db)
        await repo.initialize()

        # Set only ALL profile
        await repo.set_timer_channel("server123", "ALL", "channel_all")

        # Query for specific profile should fall back to ALL
        channel_id = await repo.get_timer_channel("server123", "HSR")
        assert channel_id == "channel_all"

    @pytest.mark.asyncio
    async def test_read_old_config_format(self, old_style_event_db):
        """Test reading config written with OLD code patterns."""
        # Insert using old pattern
        import sqlite3
        conn = sqlite3.connect(old_style_event_db)
        c = conn.cursor()
        c.execute("INSERT INTO config (server_id, profile, timer_channel_id) VALUES (?, ?, ?)",
                  ("old_server", "UMA", "old_channel"))
        conn.commit()
        conn.close()

        # Read using new repository
        repo = SQLiteConfigRepository(old_style_event_db)
        channel_id = await repo.get_timer_channel("old_server", "UMA")
        assert channel_id == "old_channel"

    @pytest.mark.asyncio
    async def test_valid_categories(self, old_style_event_db):
        """Test getting valid categories including defaults."""
        repo = SQLiteConfigRepository(old_style_event_db)
        await repo.initialize()

        # Default categories
        categories = await repo.get_valid_categories("server123", "AK")
        assert "Banner" in categories
        assert "Event" in categories
        assert "Maintenance" in categories
        assert "Offer" in categories

    @pytest.mark.asyncio
    async def test_uma_categories(self, old_style_event_db):
        """Test Uma Musume specific categories."""
        repo = SQLiteConfigRepository(old_style_event_db)
        await repo.initialize()

        categories = await repo.get_valid_categories("server123", "UMA")
        assert "Champions Meeting" in categories
        assert "Legend Race" in categories
        assert "Character Banner" in categories


# =============================================================================
# Channel Repository Tests
# =============================================================================

class TestChannelRepository:
    """Tests for ChannelRepository."""

    @pytest.mark.asyncio
    async def test_event_message_tracking(self, old_style_event_db):
        """Test tracking event messages in channels."""
        repo = ChannelRepository(old_style_event_db)
        await repo.initialize()

        # Set message ID for an event
        await repo.set_message_id(1, "server123", "channel456", "message789")

        # Get it back
        msg_id = await repo.get_message_id(1, "channel456")
        assert msg_id == "message789"

    @pytest.mark.asyncio
    async def test_read_old_event_messages(self, old_style_event_db):
        """Test reading event messages written with OLD code patterns."""
        # Insert using old pattern
        import sqlite3
        conn = sqlite3.connect(old_style_event_db)
        c = conn.cursor()
        c.execute(
            "REPLACE INTO event_messages (event_id, server_id, channel_id, message_id) VALUES (?, ?, ?, ?)",
            (42, "old_server", "old_channel", "old_message")
        )
        conn.commit()
        conn.close()

        # Read using new repository
        repo = ChannelRepository(old_style_event_db)
        msg_id = await repo.get_message_id(42, "old_channel")
        assert msg_id == "old_message"

    @pytest.mark.asyncio
    async def test_get_all_messages_in_channel(self, old_style_event_db):
        """Test getting all event messages in a channel."""
        repo = ChannelRepository(old_style_event_db)
        await repo.initialize()

        # Add multiple events
        await repo.set_message_id(1, "server", "channel", "msg1")
        await repo.set_message_id(2, "server", "channel", "msg2")
        await repo.set_message_id(3, "server", "channel", "msg3")

        messages = await repo.get_all_messages_in_channel("server", "channel")
        assert len(messages) == 3
        assert messages[1] == "msg1"
        assert messages[2] == "msg2"
        assert messages[3] == "msg3"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
