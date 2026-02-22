"""
Tests for the service layer.

These tests verify that the business logic services work correctly,
matching the behavior of the old code.
"""

import pytest
import time
from datetime import datetime

# Import from new structure
from src.core.services import (
    TimezoneService,
    NotificationScheduler,
    UmaScheduler,
    ChampionsMeetingPhase,
    LegendRaceCharacter,
    ValidationService,
    ValidationError,
    ValidationResult,
    NOTIFICATION_TIMINGS,
    UMA_NOTIFICATION_TIMINGS,
)
from src.core.models import Event, Notification


# =============================================================================
# Timezone Service Tests
# =============================================================================

class TestTimezoneService:
    """Tests for TimezoneService."""

    @pytest.fixture
    def tz_service(self):
        return TimezoneService()

    def test_is_hyv_profile(self, tz_service):
        """Test HYV profile detection."""
        assert tz_service.is_hyv_profile("HSR") is True
        assert tz_service.is_hyv_profile("hsr") is True  # Case insensitive
        assert tz_service.is_hyv_profile("ZZZ") is True
        assert tz_service.is_hyv_profile("WUWA") is True
        assert tz_service.is_hyv_profile("UMA") is False
        assert tz_service.is_hyv_profile("AK") is False

    def test_get_timezone(self, tz_service):
        """Test timezone retrieval."""
        asia_tz = tz_service.get_timezone("ASIA")
        assert asia_tz.zone == "Asia/Shanghai"

        america_tz = tz_service.get_timezone("AMERICA")
        assert america_tz.zone == "America/New_York"

        europe_tz = tz_service.get_timezone("EUROPE")
        assert europe_tz.zone == "Europe/Berlin"

    def test_get_timezone_case_insensitive(self, tz_service):
        """Test that timezone lookup is case insensitive."""
        assert tz_service.get_timezone("asia").zone == "Asia/Shanghai"
        assert tz_service.get_timezone("Asia").zone == "Asia/Shanghai"
        assert tz_service.get_timezone("ASIA").zone == "Asia/Shanghai"

    def test_get_timezone_invalid(self, tz_service):
        """Test that invalid timezone raises error."""
        with pytest.raises(ValueError):
            tz_service.get_timezone("INVALID")

    def test_to_unix_and_back(self, tz_service):
        """Test UNIX timestamp conversion round-trip."""
        now = int(time.time())
        dt = tz_service.from_unix(now)
        back = tz_service.to_unix(dt)
        assert back == now

    def test_convert_to_all_regions_event_time(self, tz_service):
        """Test converting event time to all regions.

        For event times, the same local time applies to each region.
        e.g., "10:00 AM" means 10:00 AM local in Asia, America, AND Europe.
        """
        result = tz_service.convert_to_all_regions("2025-01-15 10:00", is_version_time=False)

        assert "ASIA" in result
        assert "AMERICA" in result
        assert "EUROPE" in result

        # Each region should have the same local time (10:00 AM)
        # But different UNIX timestamps due to different UTC offsets
        asia_dt, asia_unix = result["ASIA"]
        america_dt, america_unix = result["AMERICA"]
        europe_dt, europe_unix = result["EUROPE"]

        # Local hours should all be 10
        assert asia_dt.hour == 10
        assert america_dt.hour == 10
        assert europe_dt.hour == 10

        # UNIX timestamps should be different
        # Asia is UTC+8, America is UTC-5, Europe is UTC+1
        # So Asia happens first, then Europe, then America
        assert asia_unix < europe_unix < america_unix


# =============================================================================
# Notification Scheduler Tests
# =============================================================================

class TestNotificationScheduler:
    """Tests for NotificationScheduler."""

    @pytest.fixture
    def scheduler(self):
        return NotificationScheduler()

    def test_get_timings_for_banner(self, scheduler):
        """Test Banner category timings match old code."""
        timings = scheduler.get_timings_for_category("Banner", "HSR")

        # Banner: start [60, 1440], end [60, 1440]
        assert ("start", 60) in timings
        assert ("start", 1440) in timings
        assert ("end", 60) in timings
        assert ("end", 1440) in timings
        assert len(timings) == 4

    def test_get_timings_for_event(self, scheduler):
        """Test Event category timings match old code."""
        timings = scheduler.get_timings_for_category("Event", "HSR")

        # Event: start [180], end [180, 1440]
        assert ("start", 180) in timings
        assert ("end", 180) in timings
        assert ("end", 1440) in timings
        assert len(timings) == 3

    def test_get_timings_for_maintenance(self, scheduler):
        """Test Maintenance category timings match old code."""
        timings = scheduler.get_timings_for_category("Maintenance", "HSR")

        # Maintenance: start [60], end []
        assert ("start", 60) in timings
        assert len(timings) == 1

    def test_get_timings_for_uma_character_banner(self, scheduler):
        """Test Uma Character Banner timings match old code."""
        timings = scheduler.get_timings_for_category("Character Banner", "UMA")

        # Character Banner: start [1440], end [1440, 1500]
        assert ("start", 1440) in timings
        assert ("end", 1440) in timings
        assert ("end", 1500) in timings
        assert len(timings) == 3

    def test_calculate_notification_times_non_hyv(self, scheduler):
        """Test notification calculation for non-HYV games."""
        now = int(time.time())
        event = Event(
            title="Test Banner",
            start_date=now + 86400,  # 1 day from now
            end_date=now + 86400 * 8,  # 8 days from now
            category="Banner",
            profile="AK",  # Arknights (non-HYV)
        )

        timings = scheduler.calculate_notification_times(event, current_time=now)

        # Should have notifications but NO region
        assert len(timings) > 0
        for timing in timings:
            assert timing.region is None

    def test_calculate_notification_times_hyv(self, scheduler):
        """Test notification calculation for HYV games creates regional notifications."""
        now = int(time.time())
        event = Event(
            title="Test Banner",
            start_date=now + 86400,
            end_date=now + 86400 * 8,
            category="Banner",
            profile="HSR",  # Honkai Star Rail (HYV)
            asia_start=now + 86400,
            asia_end=now + 86400 * 8,
            america_start=now + 86400 + 43200,  # 12 hours later
            america_end=now + 86400 * 8 + 43200,
            europe_start=now + 86400 + 21600,  # 6 hours later
            europe_end=now + 86400 * 8 + 21600,
        )

        timings = scheduler.calculate_notification_times(event, current_time=now)

        # Should have 3x the notifications (one per region)
        regions_found = set()
        for timing in timings:
            assert timing.region in ["ASIA", "AMERICA", "EUROPE"]
            regions_found.add(timing.region)

        assert regions_found == {"ASIA", "AMERICA", "EUROPE"}

    def test_create_notifications(self, scheduler):
        """Test creating Notification objects."""
        now = int(time.time())
        event = Event(
            title="Test Event",
            start_date=now + 86400,
            end_date=now + 86400 * 3,
            category="Event",
            profile="AK",
        )

        notifications = scheduler.create_notifications(event, current_time=now)

        assert len(notifications) > 0
        for notif in notifications:
            assert isinstance(notif, Notification)
            assert notif.title == "Test Event"
            assert notif.profile == "AK"
            assert notif.category == "Event"

    def test_timing_label(self, scheduler):
        """Test human-readable timing labels."""
        assert "1 hour" in scheduler.get_timing_label("start_60")
        assert "1 day" in scheduler.get_timing_label("start_1440")
        assert "3 hours" in scheduler.get_timing_label("end_180")


# =============================================================================
# Uma Scheduler Tests
# =============================================================================

class TestUmaScheduler:
    """Tests for UmaScheduler (Champions Meeting and Legend Race)."""

    @pytest.fixture
    def uma_scheduler(self):
        return UmaScheduler()

    def test_champions_meeting_phases(self, uma_scheduler):
        """Test Champions Meeting phase calculation.

        Phases are calculated BACKWARDS from end:
        - Finals: Last 1 day
        - Final Registration: 1 day before Finals
        - Round 2: 2 days before Final Registration
        - Round 1: 2 days before Round 2
        - League Selection: Remaining time
        """
        # 10-day event
        start = 1000000
        end = start + 10 * 86400  # 10 days later

        phases = uma_scheduler.calculate_champions_meeting_phases(start, end)

        # Should have 5 phases
        assert len(phases) == 5

        # Check phase names in order
        phase_names = [p.name for p in phases]
        assert phase_names == [
            "League Selection",
            "Round 1",
            "Round 2",
            "Final Registration",
            "Finals"
        ]

        # Check Finals is last 1 day
        finals = phases[-1]
        assert finals.name == "Finals"
        assert finals.end_unix == end
        assert finals.duration_days == 1

        # Check Final Registration is before Finals
        final_reg = phases[-2]
        assert final_reg.name == "Final Registration"
        assert final_reg.end_unix == finals.start_unix
        assert final_reg.duration_days == 1

        # Check League Selection starts at event start
        league_sel = phases[0]
        assert league_sel.name == "League Selection"
        assert league_sel.start_unix == start

    def test_champions_meeting_notifications(self, uma_scheduler):
        """Test Champions Meeting notification creation."""
        now = int(time.time())
        start = now + 86400 * 2  # 2 days from now (so reminder at 1 day out is in future)
        end = start + 10 * 86400  # 10 days long

        notifications = uma_scheduler.create_champions_meeting_notifications(
            "Test CM",
            start,
            end,
            current_time=now
        )

        # Should have: 1 reminder + 5 phases + 1 end = 7 notifications
        assert len(notifications) == 7

        # Check all have correct profile/category
        for notif in notifications:
            assert notif.profile == "UMA"
            assert notif.category == "Champions Meeting"
            assert notif.title == "Test CM"

    def test_parse_legend_race_characters_format1(self, uma_scheduler):
        """Test parsing Legend Race characters from format: '- Name (...)'"""
        description = """
        **Legend Race Characters:**
        - Tokai Teio (Spring)
        - Mejiro McQueen (Autumn)
        - Special Week (Champion)
        """

        characters = uma_scheduler.parse_legend_race_characters(description)

        assert len(characters) == 3
        assert "Tokai Teio" in characters
        assert "Mejiro McQueen" in characters
        assert "Special Week" in characters

    def test_parse_legend_race_characters_format2(self, uma_scheduler):
        """Test parsing Legend Race characters from markdown links."""
        description = """
        **Characters:** [Tokai Teio](url1) [Mejiro McQueen](url2) [Special Week](url3)
        """

        characters = uma_scheduler.parse_legend_race_characters(description)

        assert len(characters) == 3
        assert "Tokai Teio" in characters

    def test_legend_race_character_calculation(self, uma_scheduler):
        """Test Legend Race character time windows.

        Each character gets 3 days.
        """
        start = 1000000
        end = start + 9 * 86400  # 9-day event
        character_names = ["Char1", "Char2", "Char3"]

        characters = uma_scheduler.calculate_legend_race_characters(start, end, character_names)

        assert len(characters) == 3

        # First character starts at event start
        assert characters[0].name == "Char1"
        assert characters[0].start_unix == start
        assert characters[0].end_unix == start + 3 * 86400

        # Second character starts when first ends
        assert characters[1].name == "Char2"
        assert characters[1].start_unix == characters[0].end_unix

        # Third character
        assert characters[2].name == "Char3"
        assert characters[2].start_unix == characters[1].end_unix

    def test_legend_race_notifications(self, uma_scheduler):
        """Test Legend Race notification creation."""
        now = int(time.time())
        start = now + 86400 * 2  # 2 days from now (so reminder at 1 day out is in future)
        end = start + 9 * 86400
        characters = ["Char1", "Char2", "Char3"]

        notifications = uma_scheduler.create_legend_race_notifications(
            "Test LR",
            start,
            end,
            characters,
            current_time=now
        )

        # Should have: 1 reminder + 3 characters + 1 end = 5 notifications
        assert len(notifications) == 5

        # Check character notifications have character_name set
        char_notifs = [n for n in notifications if n.character_name]
        assert len(char_notifs) == 3


# =============================================================================
# Validation Service Tests
# =============================================================================

class TestValidationService:
    """Tests for ValidationService."""

    @pytest.fixture
    def validator(self):
        return ValidationService()

    def test_validate_event_success(self, validator):
        """Test validation passes for valid event."""
        now = int(time.time())
        event = Event(
            title="Valid Event",
            start_date=now + 3600,
            end_date=now + 86400,
            category="Banner",
            profile="HSR",
        )

        result = validator.validate_event(event)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_event_missing_title(self, validator):
        """Test validation fails for missing title."""
        now = int(time.time())
        event = Event(
            title="",
            start_date=now + 3600,
            end_date=now + 86400,
            category="Banner",
            profile="HSR",
        )

        result = validator.validate_event(event)

        assert result.is_valid is False
        assert any(e.field == "title" for e in result.errors)

    def test_validate_event_invalid_dates(self, validator):
        """Test validation fails when duration is too short."""
        now = int(time.time())
        # Event model validates start < end, so test duration instead
        event = Event(
            title="Test Event",
            start_date=now + 86400,      # Tomorrow
            end_date=now + 86400 + 1800,  # Only 30 minutes later (too short)
            category="Banner",
            profile="HSR",
        )

        result = validator.validate_event(event)

        assert result.is_valid is False
        assert any(e.field == "duration" for e in result.errors)

    def test_validate_event_invalid_category(self, validator):
        """Test validation fails for invalid category."""
        now = int(time.time())
        event = Event(
            title="Test Event",
            start_date=now + 3600,
            end_date=now + 86400,
            category="Invalid Category",
            profile="HSR",
        )

        result = validator.validate_event(event)

        assert result.is_valid is False
        assert any(e.field == "category" for e in result.errors)

    def test_normalize_profile(self, validator):
        """Test profile normalization."""
        assert validator.normalize_profile("hsr") == "HSR"
        assert validator.normalize_profile("Honkai Star Rail") == "HSR"
        assert validator.normalize_profile("zenless") == "ZZZ"
        assert validator.normalize_profile("uma musume") == "UMA"

    def test_normalize_category(self, validator):
        """Test category normalization."""
        assert validator.normalize_category("banner", "HSR") == "Banner"
        assert validator.normalize_category("CHARACTER BANNER", "UMA") == "Character Banner"
        assert validator.normalize_category("maint", "HSR") == "Maintenance"
        assert validator.normalize_category("champions meeting", "UMA") == "Champions Meeting"

    def test_clean_title(self, validator):
        """Test title cleaning."""
        assert validator.clean_title("  Test   Title  ") == "Test Title"
        assert validator.clean_title("Title <script>") == "Title script"

    def test_is_duplicate_event(self, validator):
        """Test duplicate detection."""
        now = int(time.time())

        existing = [
            Event(
                title="Existing Event",
                start_date=now + 3600,
                end_date=now + 86400,
                category="Banner",
                profile="HSR",
            )
        ]

        # Same event (duplicate)
        duplicate = Event(
            title="Existing Event",
            start_date=now + 3600,
            end_date=now + 86400,
            category="Banner",
            profile="HSR",
        )

        # Different event
        different = Event(
            title="Different Event",
            start_date=now + 3600,
            end_date=now + 86400,
            category="Banner",
            profile="HSR",
        )

        assert validator.is_duplicate_event(duplicate, existing) is True
        assert validator.is_duplicate_event(different, existing) is False

    def test_get_valid_categories(self, validator):
        """Test getting valid categories for profiles."""
        hsr_cats = validator.get_valid_categories("HSR")
        assert "Banner" in hsr_cats
        assert "Event" in hsr_cats
        assert "Maintenance" in hsr_cats

        uma_cats = validator.get_valid_categories("UMA")
        assert "Champions Meeting" in uma_cats
        assert "Legend Race" in uma_cats
        assert "Character Banner" in uma_cats


# =============================================================================
# Integration Tests
# =============================================================================

class TestServicesIntegration:
    """Integration tests to verify services work together."""

    def test_notification_timings_match_old_code(self):
        """Verify notification timings match the old code constants."""
        # These values are from notification_handler.py lines 93-113
        old_timings = {
            "Banner": {"start": [60, 1440], "end": [60, 1440]},
            "Event": {"start": [180], "end": [180, 1440]},
            "Maintenance": {"start": [60], "end": []},
            "Offer": {"start": [180, 1440], "end": [1440]},
        }

        for category, timings in old_timings.items():
            assert NOTIFICATION_TIMINGS[category] == timings, f"Mismatch for {category}"

    def test_uma_timings_match_old_code(self):
        """Verify Uma timings match the old code constants."""
        old_uma_timings = {
            "Character Banner": {"start": [1440], "end": [1440, 1500]},
            "Support Banner": {"start": [1440], "end": [1440, 1500]},
            "Paid Banner": {"start": [1440], "end": [1440, 1500]},
            "Story Event": {"start": [1440], "end": [4320, 4380]},
        }

        for category, timings in old_uma_timings.items():
            assert UMA_NOTIFICATION_TIMINGS[category] == timings, f"Mismatch for {category}"
