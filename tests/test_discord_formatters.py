"""
Tests for the Discord presentation layer (formatters).

These tests verify that colors, emojis, timestamps, and embeds
match the patterns used in the old code.
"""

import pytest
import discord
import time

from src.discord_bot.formatters import (
    # Colors
    PROFILE_COLORS,
    CATEGORY_COLORS,
    get_profile_color,
    get_category_color,
    get_event_color,
    get_notification_color,
    # Emojis
    PROFILE_EMOJIS,
    REGION_EMOJIS,
    get_profile_emoji,
    get_region_emoji,
    get_category_emoji,
    format_profile_with_emoji,
    format_region_with_emoji,
    # Timestamps
    format_timestamp,
    format_timestamp_full,
    format_timestamp_relative,
    format_timestamp_dual,
    format_event_times,
    format_hyv_regional_times,
    get_time_until,
    # Embeds
    EmbedBuilder,
    create_event_embed_simple,
    create_hyv_event_embed,
    create_error_embed,
    create_success_embed,
    # Messages
    MESSAGE_TEMPLATES,
    get_template,
    get_template_key,
    format_notification_message,
    format_simple_notification,
)


# =============================================================================
# Color Tests
# =============================================================================

class TestColors:
    """Tests for color formatting matching old code."""

    def test_profile_colors_match_old_code(self):
        """Verify profile colors match global_config.py values."""
        # From global_config.py lines 139-145
        assert get_profile_color("AK") == discord.Color.teal()
        assert get_profile_color("HSR") == discord.Color.fuchsia()
        assert get_profile_color("ZZZ") == discord.Color.yellow()
        assert get_profile_color("STRI") == discord.Color.orange()
        assert get_profile_color("WUWA") == discord.Color.green()

    def test_category_colors_match_old_code(self):
        """Verify category colors match database_handler.py values."""
        # From database_handler.py lines 136-150
        assert get_category_color("Banner") == discord.Color.blue()
        assert get_category_color("Event") == discord.Color.gold()
        assert get_category_color("Maintenance") == discord.Color.green()
        assert get_category_color("Offer") == discord.Color.fuchsia()
        assert get_category_color("Ended") == discord.Color.red()

    def test_uma_event_colors(self):
        """Verify Uma Musume event colors match uma_module.py logic."""
        # From uma_module.py lines 71-110
        assert get_event_color("banner", "UMA", "Paid Banner Test") == discord.Color.orange()
        assert get_event_color("banner", "UMA", "Support Card") == discord.Color.green()
        assert get_event_color("banner", "UMA", "Character Pick Up") == discord.Color.blue()
        assert get_event_color("Champions Meeting", "UMA") == discord.Color.purple()
        assert get_event_color("Legend Race", "UMA") == discord.Color.magenta()
        assert get_event_color("event", "UMA", "Story Event") == discord.Color.gold()

    def test_profile_color_case_insensitive(self):
        """Test that profile color lookup is case insensitive."""
        assert get_profile_color("hsr") == get_profile_color("HSR")
        assert get_profile_color("Zzz") == get_profile_color("ZZZ")


# =============================================================================
# Emoji Tests
# =============================================================================

class TestEmojis:
    """Tests for emoji formatting matching old code."""

    def test_profile_emojis_match_old_code(self):
        """Verify profile emojis match notification_handler.py values."""
        # From notification_handler.py lines 78-85
        assert get_profile_emoji("HSR") == "<:Game_HSR:1384176219385237588>"
        assert get_profile_emoji("ZZZ") == "<:Game_ZZZ:1384176233159589919>"
        assert get_profile_emoji("AK") == "<:Game_AK:1384176253342449816>"
        assert get_profile_emoji("STRI") == "<:Game_Strinova:1384176243708264468>"
        assert get_profile_emoji("WUWA") == "<:Game_WUWA:1384186019901083720>"
        assert get_profile_emoji("UMA") == "<:Game_UMA:1394905581328007240>"

    def test_region_emojis_match_old_code(self):
        """Verify region emojis match notification_handler.py values."""
        # From notification_handler.py lines 87-91
        assert get_region_emoji("ASIA") == "<:Region_AS:1384176206500593706>"
        assert get_region_emoji("AMERICA") == "<:Region_NA:1384176179187159130>"
        assert get_region_emoji("EUROPE") == "<:Region_EU:1384176193426690088>"

    def test_region_emoji_aliases(self):
        """Test that region aliases work (NA, EU, AS)."""
        assert get_region_emoji("NA") == get_region_emoji("AMERICA")
        assert get_region_emoji("EU") == get_region_emoji("EUROPE")
        assert get_region_emoji("AS") == get_region_emoji("ASIA")

    def test_fallback_emojis(self):
        """Test that fallback emojis are unicode characters."""
        emoji = get_profile_emoji("HSR", use_fallback=True)
        # Should be a unicode emoji, not a Discord custom emoji
        assert not emoji.startswith("<:")
        assert len(emoji) <= 4  # Unicode emojis are 1-4 chars

    def test_format_profile_with_emoji(self):
        """Test profile + emoji formatting."""
        result = format_profile_with_emoji("HSR")
        assert "HSR" in result
        assert "<:Game_HSR:" in result

    def test_format_region_with_emoji(self):
        """Test region + emoji formatting."""
        result = format_region_with_emoji("ASIA")
        assert "ASIA" in result or "Asia" in result  # Either case is fine
        assert "<:Region_AS:" in result


# =============================================================================
# Timestamp Tests
# =============================================================================

class TestTimestamps:
    """Tests for timestamp formatting matching Discord format."""

    def test_timestamp_format(self):
        """Test basic Discord timestamp format."""
        unix = 1700000000  # Fixed timestamp
        result = format_timestamp(unix, "F")
        assert result == "<t:1700000000:F>"

    def test_timestamp_full(self):
        """Test full datetime format."""
        unix = 1700000000
        result = format_timestamp_full(unix)
        assert result == "<t:1700000000:F>"

    def test_timestamp_relative(self):
        """Test relative format."""
        unix = 1700000000
        result = format_timestamp_relative(unix)
        assert result == "<t:1700000000:R>"

    def test_timestamp_dual_format(self):
        """Test dual format (full + relative) matching old code pattern."""
        # From database_handler.py line 162
        unix = 1700000000
        result = format_timestamp_dual(unix)
        assert "<t:1700000000:F>" in result
        assert "<t:1700000000:R>" in result

    def test_event_times_format(self):
        """Test event times format matching old code."""
        # From database_handler.py line 162
        start = 1700000000
        end = 1700100000
        result = format_event_times(start, end)
        assert "**Start:**" in result
        assert "**End:**" in result
        assert f"<t:{start}:F>" in result
        assert f"<t:{end}:F>" in result

    def test_hyv_regional_times_format(self):
        """Test HYV regional times format matching old code."""
        # From database_handler.py lines 153-162
        result = format_hyv_regional_times(
            asia_start=1700000000, asia_end=1700100000,
            america_start=1700050000, america_end=1700150000,
            europe_start=1700030000, europe_end=1700130000
        )
        assert "**Asia Server:**" in result
        assert "**America Server:**" in result
        assert "**Europe Server:**" in result

    def test_get_time_until(self):
        """Test human-readable time until calculation."""
        now = int(time.time())
        future = now + 86400 + 3600  # 1 day + 1 hour
        result = get_time_until(future, now)
        assert "1d" in result
        assert "1h" in result


# =============================================================================
# Embed Tests
# =============================================================================

class TestEmbeds:
    """Tests for embed creation."""

    def test_embed_builder_basic(self):
        """Test basic embed builder functionality."""
        embed = EmbedBuilder() \
            .set_title("Test Title") \
            .set_description("Test Description") \
            .set_color(discord.Color.blue()) \
            .build()

        assert embed.title == "Test Title"
        assert embed.description == "Test Description"
        assert embed.color == discord.Color.blue()

    def test_embed_builder_fields(self):
        """Test adding fields to embed."""
        embed = EmbedBuilder() \
            .set_title("Test") \
            .add_field("Field 1", "Value 1") \
            .add_field("Field 2", "Value 2", inline=True) \
            .build()

        assert len(embed.fields) == 2
        assert embed.fields[0].name == "Field 1"
        assert embed.fields[1].inline is True

    def test_embed_builder_image(self):
        """Test setting embed image."""
        embed = EmbedBuilder() \
            .set_title("Test") \
            .set_image("https://example.com/image.png") \
            .build()

        assert embed.image.url == "https://example.com/image.png"

    def test_create_event_embed_simple(self):
        """Test simple event embed creation."""
        embed = create_event_embed_simple(
            title="Test Banner",
            start_unix=1700000000,
            end_unix=1700100000,
            category="Banner",
            profile="HSR"
        )

        assert embed.title == "Test Banner"
        assert embed.color == discord.Color.blue()  # Banner color
        assert "**Start:**" in embed.description
        assert "**End:**" in embed.description

    def test_create_hyv_event_embed(self):
        """Test HYV event embed with regional times."""
        embed = create_hyv_event_embed(
            title="Test Version",
            category="Maintenance",
            profile="HSR",
            asia_start=1700000000, asia_end=1700100000,
            america_start=1700050000, america_end=1700150000,
            europe_start=1700030000, europe_end=1700130000
        )

        assert embed.title == "Test Version"
        assert "**Asia Server:**" in embed.description
        assert "**America Server:**" in embed.description
        assert "**Europe Server:**" in embed.description

    def test_create_error_embed(self):
        """Test error embed creation."""
        embed = create_error_embed("Test Error", "Something went wrong")
        assert embed.title == "Test Error"
        assert embed.color == discord.Color.red()

    def test_create_success_embed(self):
        """Test success embed creation."""
        embed = create_success_embed("Success!", "It worked")
        assert embed.title == "Success!"
        assert embed.color == discord.Color.green()


# =============================================================================
# Message Template Tests
# =============================================================================

class TestMessages:
    """Tests for message templates matching old code."""

    def test_uma_templates_exist(self):
        """Verify Uma Musume templates exist."""
        # From notification_handler.py lines 116-133
        assert "uma_champions_meeting_registration_start" in MESSAGE_TEMPLATES
        assert "uma_champions_meeting_round1_start" in MESSAGE_TEMPLATES
        assert "uma_champions_meeting_round2_start" in MESSAGE_TEMPLATES
        assert "uma_champions_meeting_finals_start" in MESSAGE_TEMPLATES
        assert "uma_legend_race_character_start" in MESSAGE_TEMPLATES

    def test_get_template_key_uma_cm(self):
        """Test template key selection for Champions Meeting."""
        key = get_template_key("UMA", "Champions Meeting", "start", phase="Round 1")
        assert key == "uma_champions_meeting_round1_start"

        key = get_template_key("UMA", "Champions Meeting", "reminder")
        assert key == "uma_champions_meeting_reminder"

    def test_get_template_key_uma_lr(self):
        """Test template key selection for Legend Race."""
        key = get_template_key("UMA", "Legend Race", "start", character_name="Tokai Teio")
        assert key == "uma_legend_race_character_start"

    def test_format_notification_message(self):
        """Test notification message formatting."""
        message = format_notification_message(
            template_key="default",
            role_mention="@everyone",
            name="Test Banner",
            category="Banner",
            timing_type="start",
            event_time_unix=1700000000
        )

        assert "@everyone" in message
        assert "Banner" in message
        assert "Test Banner" in message
        assert "<t:1700000000:R>" in message

    def test_format_simple_notification(self):
        """Test simple notification formatting."""
        message = format_simple_notification(
            role_mention="@role",
            title="Event Name",
            category="Event",
            is_starting=True,
            event_time_unix=1700000000
        )

        assert "@role" in message
        assert "Event Name" in message
        assert "starting" in message

    def test_format_simple_notification_with_region(self):
        """Test notification with region for HYV games."""
        message = format_simple_notification(
            role_mention="@role",
            title="Version 2.0",
            category="Maintenance",
            is_starting=True,
            event_time_unix=1700000000,
            region="ASIA"
        )

        assert "@role" in message
        assert "ASIA" in message


# =============================================================================
# Integration Tests
# =============================================================================

class TestFormatterIntegration:
    """Integration tests to verify formatters work together."""

    def test_full_event_embed_workflow(self):
        """Test creating a complete event embed."""
        now = int(time.time())
        embed = EmbedBuilder() \
            .set_title("Firefly Banner") \
            .set_color_for_event("Banner", "HSR", "Firefly Banner") \
            .set_description(format_event_times(now + 86400, now + 86400 * 14)) \
            .set_image("https://example.com/firefly.png") \
            .build()

        assert embed.title == "Firefly Banner"
        assert embed.color == discord.Color.blue()  # Banner color
        assert "**Start:**" in embed.description
        assert embed.image.url == "https://example.com/firefly.png"

    def test_notification_with_emoji(self):
        """Test notification message with profile emoji."""
        profile = "HSR"
        emoji = get_profile_emoji(profile)
        message = f"{emoji} New event for {profile}!"

        assert "<:Game_HSR:" in message
        assert "HSR" in message
