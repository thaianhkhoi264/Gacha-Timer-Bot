"""
Message templates and formatting for Discord notifications.

Centralizes all notification message templates used throughout the bot.
"""

from typing import Dict, Optional
from .timestamps import format_timestamp_relative
from .emojis import get_profile_emoji, get_region_emoji


# =============================================================================
# Message Templates
# =============================================================================

# Default notification template
DEFAULT_TEMPLATE = "{role}, The {category} **{name}** is {action} {time}!"

# Standard notification templates
MESSAGE_TEMPLATES: Dict[str, str] = {
    # Default
    "default": DEFAULT_TEMPLATE,

    # Uma Musume - Champions Meeting phases
    "uma_champions_meeting_reminder": "{role}, **{name}** starts tomorrow! Get ready!",
    "uma_champions_meeting_registration_start": "{role}, **{name}** League Selection has started!",
    "uma_champions_meeting_round1_start": "{role}, **{name}** Round 1 has started!",
    "uma_champions_meeting_round2_start": "{role}, **{name}** Round 2 has started!",
    "uma_champions_meeting_final_registration_start": "{role}, **{name}** Final Registration has started!",
    "uma_champions_meeting_finals_start": "{role}, **{name}** Finals have started! Good luck!",
    "uma_champions_meeting_end": "{role}, **{name}** has ended!",

    # Uma Musume - Legend Race
    "uma_legend_race_reminder": "{role}, **{name}** starts tomorrow!",
    "uma_legend_race_character_start": "{role}, **{character}**'s Legend Race has started!",
    "uma_legend_race_end": "{role}, **{name}** has ended!",

    # Generic event templates
    "event_start": "{role}, **{name}** has started!",
    "event_end": "{role}, **{name}** has ended!",
    "event_reminder": "{role}, **{name}** starts {time}!",

    # Banner templates
    "banner_start": "{role}, The **{name}** banner is now available!",
    "banner_end": "{role}, The **{name}** banner ends {time}!",

    # Maintenance templates
    "maintenance_start": "{role}, Maintenance for **{name}** starts {time}!",
}


def get_template(template_key: str) -> str:
    """
    Get a message template by key.

    Args:
        template_key: Template key (e.g., "uma_champions_meeting_round1_start")

    Returns:
        Template string, or default template if key not found
    """
    return MESSAGE_TEMPLATES.get(template_key, DEFAULT_TEMPLATE)


def get_template_key(
    profile: str,
    category: str,
    timing_type: str,
    phase: Optional[str] = None,
    character_name: Optional[str] = None
) -> str:
    """
    Determine which message template to use based on event details.

    Args:
        profile: Game profile (e.g., "UMA", "HSR")
        category: Event category
        timing_type: Notification timing type (e.g., "start_60", "end", "reminder")
        phase: Champions Meeting phase (optional)
        character_name: Legend Race character (optional)

    Returns:
        Template key string
    """
    profile = profile.upper()

    # Uma Musume special templates
    if profile == "UMA":
        if category == "Champions Meeting":
            if timing_type == "reminder":
                return "uma_champions_meeting_reminder"
            elif timing_type == "end":
                return "uma_champions_meeting_end"
            elif phase:
                # Map phase names to template keys
                phase_map = {
                    "League Selection": "uma_champions_meeting_registration_start",
                    "Round 1": "uma_champions_meeting_round1_start",
                    "Round 2": "uma_champions_meeting_round2_start",
                    "Final Registration": "uma_champions_meeting_final_registration_start",
                    "Finals": "uma_champions_meeting_finals_start",
                }
                return phase_map.get(phase, "default")

        elif category == "Legend Race":
            if timing_type == "reminder":
                return "uma_legend_race_reminder"
            elif timing_type == "end":
                return "uma_legend_race_end"
            elif character_name:
                return "uma_legend_race_character_start"

    # Generic templates based on timing
    if "start" in timing_type:
        if category == "Banner":
            return "banner_start"
        elif category == "Maintenance":
            return "maintenance_start"
        return "event_start"

    if "end" in timing_type:
        if category == "Banner":
            return "banner_end"
        return "event_end"

    if timing_type == "reminder":
        return "event_reminder"

    return "default"


def format_notification_message(
    template_key: str,
    role_mention: str,
    name: str,
    category: str,
    timing_type: str,
    event_time_unix: int,
    phase: Optional[str] = None,
    character_name: Optional[str] = None,
    custom_message: Optional[str] = None
) -> str:
    """
    Format a notification message using templates.

    Priority:
    1. Custom message (if provided)
    2. Template-based message
    3. Default fallback

    Args:
        template_key: Template key to use
        role_mention: Discord role mention string
        name: Event name
        category: Event category
        timing_type: Notification timing type
        event_time_unix: Event time UNIX timestamp
        phase: Champions Meeting phase (optional)
        character_name: Legend Race character (optional)
        custom_message: Custom message override (optional)

    Returns:
        Formatted message string
    """
    # Priority 1: Custom message
    if custom_message:
        return custom_message

    # Determine action word
    if "start" in timing_type.lower():
        action = "starting"
    elif "end" in timing_type.lower():
        action = "ending"
    else:
        action = "happening"

    # Format time
    time_str = format_timestamp_relative(event_time_unix)

    # Priority 2: Template-based message
    template = get_template(template_key)

    try:
        message = template.format(
            role=role_mention,
            name=name,
            category=category,
            action=action,
            time=time_str,
            phase=phase or "",
            character=character_name or ""
        )
        return message
    except KeyError:
        pass  # Fall through to default

    # Priority 3: Default fallback
    return f"{role_mention}, the **{category}** **{name}** is {action} {time_str}!"


def format_simple_notification(
    role_mention: str,
    title: str,
    category: str,
    is_starting: bool,
    event_time_unix: int,
    region: Optional[str] = None
) -> str:
    """
    Format a simple notification message.

    Args:
        role_mention: Discord role mention
        title: Event title
        category: Event category
        is_starting: True if event is starting, False if ending
        event_time_unix: Event time
        region: Server region (optional, for HYV games)

    Returns:
        Formatted message
    """
    action = "starting" if is_starting else "ending"
    time_str = format_timestamp_relative(event_time_unix)

    if region:
        region_emoji = get_region_emoji(region)
        return f"{role_mention}, [{region_emoji} {region}] The **{category}** **{title}** is {action} {time_str}!"

    return f"{role_mention}, The **{category}** **{title}** is {action} {time_str}!"


def format_confirmation_message(
    action: str,
    title: str,
    category: str,
    profile: str
) -> str:
    """
    Format a confirmation message for CRUD operations.

    Args:
        action: Action performed (e.g., "Added", "Updated", "Removed")
        title: Event title
        category: Event category
        profile: Game profile

    Returns:
        Confirmation message string
    """
    profile_emoji = get_profile_emoji(profile)
    return f"{profile_emoji} {action} `{title}` as **{category}** for **{profile}**!"


def format_error_message(error: str, context: Optional[str] = None) -> str:
    """
    Format an error message.

    Args:
        error: Error description
        context: Additional context (optional)

    Returns:
        Formatted error message
    """
    if context:
        return f"Error: {error}\n*Context: {context}*"
    return f"Error: {error}"
