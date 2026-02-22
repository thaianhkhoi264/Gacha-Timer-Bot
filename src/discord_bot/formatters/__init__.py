"""
Discord formatting utilities for the Gacha Timer Bot.

This package provides:
- colors: Embed color mappings by profile/category
- emojis: Custom and fallback emoji definitions
- timestamps: Discord timestamp formatting utilities
- embeds: Embed builder and factory functions
- messages: Notification message templates
"""

from .colors import (
    PROFILE_COLORS,
    CATEGORY_COLORS,
    DEFAULT_COLOR,
    get_profile_color,
    get_category_color,
    get_event_color,
    get_notification_color,
)

from .emojis import (
    PROFILE_EMOJIS,
    REGION_EMOJIS,
    CATEGORY_EMOJIS,
    TIMING_EMOJIS,
    KANAMI_HEART,
    get_profile_emoji,
    get_region_emoji,
    get_category_emoji,
    get_timing_emoji,
    format_profile_with_emoji,
    format_region_with_emoji,
)

from .timestamps import (
    TimestampFormat,
    format_timestamp,
    format_timestamp_full,
    format_timestamp_relative,
    format_timestamp_dual,
    format_event_times,
    format_hyv_regional_times,
    format_notification_time,
    get_time_until,
    is_past,
    is_future,
)

from .embeds import (
    EmbedBuilder,
    create_event_embed,
    create_event_embed_simple,
    create_hyv_event_embed,
    create_notification_embed,
    create_pending_notifications_embed,
    create_help_embed,
    create_error_embed,
    create_success_embed,
)

from .messages import (
    MESSAGE_TEMPLATES,
    DEFAULT_TEMPLATE,
    get_template,
    get_template_key,
    format_notification_message,
    format_simple_notification,
    format_confirmation_message,
    format_error_message,
)


__all__ = [
    # Colors
    'PROFILE_COLORS',
    'CATEGORY_COLORS',
    'DEFAULT_COLOR',
    'get_profile_color',
    'get_category_color',
    'get_event_color',
    'get_notification_color',
    # Emojis
    'PROFILE_EMOJIS',
    'REGION_EMOJIS',
    'CATEGORY_EMOJIS',
    'TIMING_EMOJIS',
    'KANAMI_HEART',
    'get_profile_emoji',
    'get_region_emoji',
    'get_category_emoji',
    'get_timing_emoji',
    'format_profile_with_emoji',
    'format_region_with_emoji',
    # Timestamps
    'TimestampFormat',
    'format_timestamp',
    'format_timestamp_full',
    'format_timestamp_relative',
    'format_timestamp_dual',
    'format_event_times',
    'format_hyv_regional_times',
    'format_notification_time',
    'get_time_until',
    'is_past',
    'is_future',
    # Embeds
    'EmbedBuilder',
    'create_event_embed',
    'create_event_embed_simple',
    'create_hyv_event_embed',
    'create_notification_embed',
    'create_pending_notifications_embed',
    'create_help_embed',
    'create_error_embed',
    'create_success_embed',
    # Messages
    'MESSAGE_TEMPLATES',
    'DEFAULT_TEMPLATE',
    'get_template',
    'get_template_key',
    'format_notification_message',
    'format_simple_notification',
    'format_confirmation_message',
    'format_error_message',
]
