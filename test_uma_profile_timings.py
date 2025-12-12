"""
Test File 2: Profile-Specific Notification Timings

Tests that Uma events get correct notification timings based on their category.
"""

import asyncio
import datetime

# Uma-specific notification timings (in minutes before event time)
UMA_NOTIFICATION_TIMINGS = {
    # Character/Support/Paid Banners: 1 day before start, 1 day + 1 hour before end
    "Character Banner": {"start": [1440], "end": [1440, 1500]},
    "Support Banner": {"start": [1440], "end": [1440, 1500]},
    "Paid Banner": {"start": [1440], "end": [1440, 1500]},
    
    # Story Events: 1 day before start, 3 days + 1 hour before end
    "Story Event": {"start": [1440], "end": [4320, 4380]},
    
    # Champions Meeting: Custom handling (placeholder)
    "Champions Meeting": {"start": [], "end": []},  # Handled separately
    
    # Legend Race: Custom handling (placeholder)
    "Legend Race": {"start": [], "end": []},  # Handled separately
}

# Generic timings (existing system)
GENERIC_NOTIFICATION_TIMINGS = {
    "Banner":    {"start": [60, 1440], "end": [60, 1440]},  # 1h, 1d before
    "Event":     {"start": [180], "end": [180, 1440]},      # 3h before start, 3h + 1d before end
    "Maintenance": {"start": [60], "end": [0]},
    "Offer":     {"start": [180, 1440], "end": [1440]},
}

def get_notification_timings_generic(category):
    """Current implementation - generic timings"""
    timings = []
    cat_timings = GENERIC_NOTIFICATION_TIMINGS.get(category, {})
    for timing_type in ("start", "end"):
        for minutes in cat_timings.get(timing_type, []):
            timings.append((timing_type, minutes))
    return timings

def get_notification_timings_profile_aware(category, profile):
    """New implementation - profile-aware timings"""
    timings = []
    
    # Check if profile has custom timings
    if profile == "UMA":
        cat_timings = UMA_NOTIFICATION_TIMINGS.get(category, {})
        if cat_timings:
            for timing_type in ("start", "end"):
                for minutes in cat_timings.get(timing_type, []):
                    timings.append((timing_type, minutes))
            return timings
    
    # Fall back to generic timings if no profile-specific ones
    cat_timings = GENERIC_NOTIFICATION_TIMINGS.get(category, {})
    for timing_type in ("start", "end"):
        for minutes in cat_timings.get(timing_type, []):
            timings.append((timing_type, minutes))
    return timings

def format_minutes(minutes):
    """Format minutes into readable string"""
    parts = []
    days = minutes // 1440
    if days:
        parts.append(f"{days}d")
    minutes %= 1440
    hours = minutes // 60
    if hours:
        parts.append(f"{hours}h")
    minutes %= 60
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "0m"

def calculate_notification_times(event_start, event_end, timings):
    """Calculate actual notification timestamps"""
    notifications = []
    for timing_type, minutes in timings:
        event_time = event_start if timing_type == "start" else event_end
        notify_time = event_time - (minutes * 60)
        notifications.append({
            'type': timing_type,
            'minutes_before': minutes,
            'notify_timestamp': notify_time,
            'event_timestamp': event_time,
            'readable': format_minutes(minutes)
        })
    return notifications

def test_character_banner():
    """Test Character Banner timings"""
    print("\n=== Test 1: Character Banner ===")
    
    # Create test event (2 weeks duration)
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    event_start = now + 86400 * 2  # 2 days from now
    event_end = now + 86400 * 16   # 16 days from now
    
    # Generic timings
    generic_timings = get_notification_timings_generic("Banner")
    print(f"\nGeneric 'Banner' timings: {generic_timings}")
    generic_notifications = calculate_notification_times(event_start, event_end, generic_timings)
    print("Generic notifications:")
    for n in generic_notifications:
        print(f"  - {n['type'].upper()}: {n['readable']} before ({n['minutes_before']} minutes)")
    
    # Uma-specific timings
    uma_timings = get_notification_timings_profile_aware("Character Banner", "UMA")
    print(f"\nUma 'Character Banner' timings: {uma_timings}")
    uma_notifications = calculate_notification_times(event_start, event_end, uma_timings)
    print("Uma notifications:")
    for n in uma_notifications:
        print(f"  - {n['type'].upper()}: {n['readable']} before ({n['minutes_before']} minutes)")
    
    # Verify correctness
    print("\n✓ Expected: 1 day before start, 1 day + 1 hour before end")
    assert len(uma_notifications) == 3, f"Expected 3 notifications, got {len(uma_notifications)}"
    assert uma_notifications[0]['minutes_before'] == 1440, "Start notification should be 1440 minutes (1 day)"
    assert uma_notifications[1]['minutes_before'] == 1440, "End notification 1 should be 1440 minutes (1 day)"
    assert uma_notifications[2]['minutes_before'] == 1500, "End notification 2 should be 1500 minutes (1d + 1h)"
    print("✓ PASS: Character Banner timings correct")

def test_story_event():
    """Test Story Event timings"""
    print("\n=== Test 2: Story Event ===")
    
    # Create test event (2 weeks duration)
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    event_start = now + 86400 * 2
    event_end = now + 86400 * 16
    
    # Generic timings
    generic_timings = get_notification_timings_generic("Event")
    print(f"\nGeneric 'Event' timings: {generic_timings}")
    generic_notifications = calculate_notification_times(event_start, event_end, generic_timings)
    print("Generic notifications:")
    for n in generic_notifications:
        print(f"  - {n['type'].upper()}: {n['readable']} before ({n['minutes_before']} minutes)")
    
    # Uma-specific timings
    uma_timings = get_notification_timings_profile_aware("Story Event", "UMA")
    print(f"\nUma 'Story Event' timings: {uma_timings}")
    uma_notifications = calculate_notification_times(event_start, event_end, uma_timings)
    print("Uma notifications:")
    for n in uma_notifications:
        print(f"  - {n['type'].upper()}: {n['readable']} before ({n['minutes_before']} minutes)")
    
    # Verify correctness
    print("\n✓ Expected: 1 day before start, 3 days + 1 hour before end")
    assert len(uma_notifications) == 3, f"Expected 3 notifications, got {len(uma_notifications)}"
    assert uma_notifications[0]['minutes_before'] == 1440, "Start notification should be 1440 minutes (1 day)"
    assert uma_notifications[1]['minutes_before'] == 4320, "End notification 1 should be 4320 minutes (3 days)"
    assert uma_notifications[2]['minutes_before'] == 4380, "End notification 2 should be 4380 minutes (3d + 1h)"
    print("✓ PASS: Story Event timings correct")

def test_support_banner():
    """Test Support Banner timings"""
    print("\n=== Test 3: Support Banner ===")
    
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    event_start = now + 86400 * 2
    event_end = now + 86400 * 16
    
    uma_timings = get_notification_timings_profile_aware("Support Banner", "UMA")
    print(f"\nUma 'Support Banner' timings: {uma_timings}")
    uma_notifications = calculate_notification_times(event_start, event_end, uma_timings)
    print("Uma notifications:")
    for n in uma_notifications:
        print(f"  - {n['type'].upper()}: {n['readable']} before ({n['minutes_before']} minutes)")
    
    print("\n✓ Expected: Same as Character Banner (1d before start, 1d + 1h before end)")
    assert len(uma_notifications) == 3, f"Expected 3 notifications, got {len(uma_notifications)}"
    assert uma_notifications[0]['minutes_before'] == 1440
    assert uma_notifications[1]['minutes_before'] == 1440
    assert uma_notifications[2]['minutes_before'] == 1500
    print("✓ PASS: Support Banner timings correct")

def test_paid_banner():
    """Test Paid Banner timings"""
    print("\n=== Test 4: Paid Banner ===")
    
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    event_start = now + 86400 * 2
    event_end = now + 86400 * 16
    
    uma_timings = get_notification_timings_profile_aware("Paid Banner", "UMA")
    print(f"\nUma 'Paid Banner' timings: {uma_timings}")
    uma_notifications = calculate_notification_times(event_start, event_end, uma_timings)
    print("Uma notifications:")
    for n in uma_notifications:
        print(f"  - {n['type'].upper()}: {n['readable']} before ({n['minutes_before']} minutes)")
    
    print("\n✓ Expected: Same as Character Banner (1d before start, 1d + 1h before end)")
    assert len(uma_notifications) == 3, f"Expected 3 notifications, got {len(uma_notifications)}"
    assert uma_notifications[0]['minutes_before'] == 1440
    assert uma_notifications[1]['minutes_before'] == 1440
    assert uma_notifications[2]['minutes_before'] == 1500
    print("✓ PASS: Paid Banner timings correct")

def test_fallback_to_generic():
    """Test that AK events still use generic timings"""
    print("\n=== Test 5: Fallback to Generic (AK Banner) ===")
    
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    event_start = now + 86400 * 2
    event_end = now + 86400 * 16
    
    # AK should use generic timings
    ak_timings = get_notification_timings_profile_aware("Banner", "AK")
    print(f"\nAK 'Banner' timings: {ak_timings}")
    ak_notifications = calculate_notification_times(event_start, event_end, ak_timings)
    print("AK notifications:")
    for n in ak_notifications:
        print(f"  - {n['type'].upper()}: {n['readable']} before ({n['minutes_before']} minutes)")
    
    print("\n✓ Expected: Generic timings (1h + 1d before start, 1h + 1d before end)")
    assert len(ak_notifications) == 4, f"Expected 4 notifications, got {len(ak_notifications)}"
    print("✓ PASS: AK falls back to generic timings correctly")

def main():
    print("=" * 60)
    print("Uma Profile-Specific Notification Timings Test")
    print("=" * 60)
    
    try:
        test_character_banner()
        test_story_event()
        test_support_banner()
        test_paid_banner()
        test_fallback_to_generic()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nSummary:")
        print("- Character/Support/Paid Banners: 1d before start, 1d + 1h before end")
        print("- Story Events: 1d before start, 3d + 1h before end")
        print("- Non-Uma profiles: Fall back to generic timings")
        print("\nReady to implement in notification_handler.py!")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
