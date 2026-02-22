"""
Discord Bot package for the Gacha Timer Bot.

This package contains the Discord presentation layer:
- formatters: Embed creation, message formatting, colors, emojis
- ui: Interactive components (buttons, selects, modals, views)
- commands: Bot command implementations
- handlers: Event and message handlers
"""

from .formatters import (
    # Colors
    get_profile_color,
    get_category_color,
    get_event_color,
    # Emojis
    get_profile_emoji,
    get_region_emoji,
    format_profile_with_emoji,
    format_region_with_emoji,
    # Timestamps
    format_timestamp,
    format_timestamp_full,
    format_timestamp_relative,
    format_event_times,
    format_hyv_regional_times,
    # Embeds
    EmbedBuilder,
    create_event_embed,
    create_hyv_event_embed,
    create_notification_embed,
    create_error_embed,
    create_success_embed,
    # Messages
    format_notification_message,
    format_simple_notification,
)

from .ui import (
    # Buttons
    ConfirmButton,
    CancelButton,
    DeleteButton,
    EditButton,
    # Selects
    CategorySelect,
    TimezoneSelect,
    ProfileSelect,
    RegionSelect,
    # Modals
    AddEventModal,
    EditEventModal,
    # Views
    ConfirmationView,
    DeleteConfirmationView,
    EventOptionsView,
    PaginatedView,
)


__all__ = [
    # Formatters
    'get_profile_color',
    'get_category_color',
    'get_event_color',
    'get_profile_emoji',
    'get_region_emoji',
    'format_profile_with_emoji',
    'format_region_with_emoji',
    'format_timestamp',
    'format_timestamp_full',
    'format_timestamp_relative',
    'format_event_times',
    'format_hyv_regional_times',
    'EmbedBuilder',
    'create_event_embed',
    'create_hyv_event_embed',
    'create_notification_embed',
    'create_error_embed',
    'create_success_embed',
    'format_notification_message',
    'format_simple_notification',
    # UI Components
    'ConfirmButton',
    'CancelButton',
    'DeleteButton',
    'EditButton',
    'CategorySelect',
    'TimezoneSelect',
    'ProfileSelect',
    'RegionSelect',
    'AddEventModal',
    'EditEventModal',
    'ConfirmationView',
    'DeleteConfirmationView',
    'EventOptionsView',
    'PaginatedView',
]
