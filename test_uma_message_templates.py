"""
Test File 3: Message Template System

Tests custom notification messages for different event types and profiles.
"""

import asyncio
import aiosqlite
import datetime

TEST_NOTIF_DB = "test_message_templates.db"

# Message templates
MESSAGE_TEMPLATES = {
    # Default template (used when no specific template exists)
    "default": "{role}, The {category} {name} is {action} {time}!",
    
    # Uma Musume - Champions Meeting phases
    "uma_champions_meeting_registration_start": "{role}, {name} Registration has started!",
    "uma_champions_meeting_round1_start": "{role}, {name} Round 1 has started!",
    "uma_champions_meeting_round2_start": "{role}, {name} Round 2 has started!",
    "uma_champions_meeting_final_registration_start": "{role}, {name} Final Registration has started!",
    "uma_champions_meeting_finals_start": "{role}, {name} Finals has started! Good luck!",
    "uma_champions_meeting_end": "{role}, {name} has ended! Hope you got a good placement!",
    "uma_champions_meeting_reminder": "{role}, {name} is starting in {time}!",
    
    # Uma Musume - Legend Race
    "uma_legend_race_character_start": "{role}, {character}'s Legend Race has started!",
    "uma_legend_race_end": "{role}, {name} has ended!",
    "uma_legend_race_reminder": "{role}, {name} is starting in 1 day!",
}

def format_message(template_key, **kwargs):
    """Format a message using a template and provided variables"""
    template = MESSAGE_TEMPLATES.get(template_key, MESSAGE_TEMPLATES["default"])
    try:
        return template.format(**kwargs)
    except KeyError as e:
        print(f"Warning: Missing variable {e} in template '{template_key}'")
        return template

def get_template_key(profile, category, timing_type, phase=None, is_character=False):
    """
    Determine which template to use based on event details.
    
    Args:
        profile: Event profile (e.g., "UMA", "AK")
        category: Event category (e.g., "Champions Meeting", "Legend Race")
        timing_type: "start" or "end" or "reminder"
        phase: Champions Meeting phase (e.g., "registration", "round1")
        is_character: True if this is a per-character notification (Legend Race)
    
    Returns:
        Template key string
    """
    if profile == "UMA":
        # Champions Meeting
        if category == "Champions Meeting":
            if phase:
                return f"uma_champions_meeting_{phase}_{timing_type}"
            elif timing_type == "reminder":
                return "uma_champions_meeting_reminder"
            elif timing_type == "end":
                return "uma_champions_meeting_end"
        
        # Legend Race
        elif category == "Legend Race":
            if is_character and timing_type == "start":
                return "uma_legend_race_character_start"
            elif timing_type == "end":
                return "uma_legend_race_end"
            elif timing_type == "reminder":
                return "uma_legend_race_reminder"
    
    # Fall back to default
    return "default"

async def setup_test_db():
    """Create test database with message template columns"""
    async with aiosqlite.connect(TEST_NOTIF_DB) as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                profile TEXT NOT NULL,
                title TEXT NOT NULL,
                timing_type TEXT NOT NULL,
                notify_unix INTEGER NOT NULL,
                event_time_unix INTEGER NOT NULL,
                sent INTEGER DEFAULT 0,
                region TEXT,
                message_template TEXT,
                custom_message TEXT,
                phase TEXT,
                character_name TEXT
            )
        ''')
        await conn.commit()
    print("✓ Created test database with message template columns")

async def test_default_message():
    """Test default message template"""
    print("\n=== Test 1: Default Message Template ===")
    
    template_key = get_template_key("AK", "Banner", "start")
    message = format_message(
        template_key,
        role="@Arknights",
        category="Banner",
        name="Exusiai Rate-Up",
        action="starting",
        time="<t:1733976000:R>"
    )
    
    print(f"Template key: {template_key}")
    print(f"Message: {message}")
    
    expected = "@Arknights, The Banner Exusiai Rate-Up is starting <t:1733976000:R>!"
    assert message == expected, f"Expected: {expected}\nGot: {message}"
    print("✓ PASS: Default template works")

async def test_champions_meeting_messages():
    """Test Champions Meeting phase messages"""
    print("\n=== Test 2: Champions Meeting Phase Messages ===")
    
    phases = [
        ("registration", "start"),
        ("round1", "start"),
        ("round2", "start"),
        ("final_registration", "start"),
        ("finals", "start"),
        (None, "end"),
        (None, "reminder")
    ]
    
    for phase, timing_type in phases:
        template_key = get_template_key("UMA", "Champions Meeting", timing_type, phase=phase)
        
        kwargs = {
            "role": "@Umamusume",
            "name": "Champions Meeting: Libra Cup"
        }
        
        if timing_type == "reminder":
            kwargs["time"] = "1 day"
        
        message = format_message(template_key, **kwargs)
        print(f"Phase: {phase or 'N/A'}, Type: {timing_type}")
        print(f"  Template: {template_key}")
        print(f"  Message: {message}")
    
    # Test specific messages
    reg_start = format_message(
        get_template_key("UMA", "Champions Meeting", "start", phase="registration"),
        role="@Umamusume",
        name="Champions Meeting: Libra Cup"
    )
    assert "Registration has started!" in reg_start
    
    finals_start = format_message(
        get_template_key("UMA", "Champions Meeting", "start", phase="finals"),
        role="@Umamusume",
        name="Champions Meeting: Libra Cup"
    )
    assert "Good luck!" in finals_start
    
    ended = format_message(
        get_template_key("UMA", "Champions Meeting", "end"),
        role="@Umamusume",
        name="Champions Meeting: Libra Cup"
    )
    assert "Hope you got a good placement!" in ended
    
    print("✓ PASS: Champions Meeting templates work")

async def test_legend_race_messages():
    """Test Legend Race character messages"""
    print("\n=== Test 3: Legend Race Character Messages ===")
    
    # Character start
    char_start = format_message(
        get_template_key("UMA", "Legend Race", "start", is_character=True),
        role="@Umamusume",
        character="Air Groove (Wedding)"
    )
    print(f"Character start: {char_start}")
    assert "Air Groove (Wedding)'s Legend Race has started!" in char_start
    
    # Event end
    event_end = format_message(
        get_template_key("UMA", "Legend Race", "end"),
        role="@Umamusume",
        name="Tenno Sho (Autumn) Legend Race"
    )
    print(f"Event end: {event_end}")
    assert "has ended!" in event_end
    
    # Reminder
    reminder = format_message(
        get_template_key("UMA", "Legend Race", "reminder"),
        role="@Umamusume",
        name="Tenno Sho (Autumn) Legend Race"
    )
    print(f"Reminder: {reminder}")
    assert "is starting in 1 day!" in reminder
    
    print("✓ PASS: Legend Race templates work")

async def test_database_storage():
    """Test storing and retrieving custom messages from database"""
    print("\n=== Test 4: Database Storage ===")
    
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    
    # Insert notification with message template
    async with aiosqlite.connect(TEST_NOTIF_DB) as conn:
        await conn.execute('''
            INSERT INTO pending_notifications 
            (category, profile, title, timing_type, notify_unix, event_time_unix, 
             message_template, custom_message, phase, character_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            "Champions Meeting",
            "UMA",
            "Champions Meeting: Libra Cup",
            "start",
            now + 3600,
            now + 7200,
            "uma_champions_meeting_registration_start",
            None,  # No custom message yet
            "registration",
            None
        ))
        
        # Insert notification with custom message
        await conn.execute('''
            INSERT INTO pending_notifications 
            (category, profile, title, timing_type, notify_unix, event_time_unix, 
             message_template, custom_message, phase, character_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            "Legend Race",
            "UMA",
            "Tenno Sho Legend Race",
            "start",
            now + 3600,
            now + 7200,
            "uma_legend_race_character_start",
            "@Umamusume, Custom message: Air Groove's race begins!",  # Custom override
            None,
            "Air Groove"
        ))
        
        await conn.commit()
    
    # Retrieve and verify
    async with aiosqlite.connect(TEST_NOTIF_DB) as conn:
        async with conn.execute(
            'SELECT message_template, custom_message, phase, character_name FROM pending_notifications WHERE title LIKE ?',
            ("%Champions Meeting%",)
        ) as cursor:
            row = await cursor.fetchone()
            print(f"Champions Meeting notification:")
            print(f"  Template: {row[0]}")
            print(f"  Custom: {row[1]}")
            print(f"  Phase: {row[2]}")
            print(f"  Character: {row[3]}")
            assert row[0] == "uma_champions_meeting_registration_start"
            assert row[2] == "registration"
        
        async with conn.execute(
            'SELECT message_template, custom_message, character_name FROM pending_notifications WHERE title LIKE ?',
            ("%Legend Race%",)
        ) as cursor:
            row = await cursor.fetchone()
            print(f"\nLegend Race notification:")
            print(f"  Template: {row[0]}")
            print(f"  Custom: {row[1]}")
            print(f"  Character: {row[2]}")
            assert row[0] == "uma_legend_race_character_start"
            assert row[1] is not None  # Has custom message
            assert row[2] == "Air Groove"
    
    print("✓ PASS: Database storage works")

async def cleanup_test_db():
    """Clean up test database"""
    import os
    if os.path.exists(TEST_NOTIF_DB):
        os.remove(TEST_NOTIF_DB)
        print(f"✓ Cleaned up {TEST_NOTIF_DB}")

async def main():
    print("=" * 60)
    print("Message Template System Test")
    print("=" * 60)
    
    try:
        await setup_test_db()
        await test_default_message()
        await test_champions_meeting_messages()
        await test_legend_race_messages()
        await test_database_storage()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSummary:")
        print("- Default template works for generic events")
        print("- Champions Meeting phases have custom messages")
        print("- Legend Race has per-character messages")
        print("- Custom messages can override templates")
        print("- Database columns support message customization")
        print("\nNext: Add database migration and implement in notification_handler.py")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await cleanup_test_db()
    
    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))
