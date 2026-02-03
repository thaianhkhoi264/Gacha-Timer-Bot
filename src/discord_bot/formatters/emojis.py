"""
Emoji definitions for Discord messages.

Centralizes all custom emoji IDs and fallback emojis.
"""

from typing import Optional


# Profile/Game emojis (custom server emojis)
PROFILE_EMOJIS = {
    "HSR": "<:Game_HSR:1384176219385237588>",
    "ZZZ": "<:Game_ZZZ:1384176233159589919>",
    "AK": "<:Game_AK:1384176253342449816>",
    "STRI": "<:Game_Strinova:1384176243708264468>",
    "WUWA": "<:Game_WUWA:1384186019901083720>",
    "UMA": "<:Game_UMA:1394905581328007240>",
}

# Region emojis (for HYV games)
REGION_EMOJIS = {
    "ASIA": "<:Region_AS:1384176206500593706>",
    "AMERICA": "<:Region_NA:1384176179187159130>",
    "EUROPE": "<:Region_EU:1384176193426690088>",
    # Aliases
    "AS": "<:Region_AS:1384176206500593706>",
    "NA": "<:Region_NA:1384176179187159130>",
    "EU": "<:Region_EU:1384176193426690088>",
}

# Special emojis
KANAMI_HEART = "<:KanamiHeart:1374409597628186624>"

# Fallback unicode emojis (when custom emojis aren't available)
FALLBACK_PROFILE_EMOJIS = {
    "HSR": "\U0001F31F",  # Star
    "ZZZ": "\U0001F4A4",  # Zzz
    "AK": "\U0001F3AF",  # Target
    "STRI": "\U0001F3AE",  # Game controller
    "WUWA": "\U0001F30A",  # Wave
    "UMA": "\U0001F3C7",  # Horse racing
}

FALLBACK_REGION_EMOJIS = {
    "ASIA": "\U0001F30F",     # Globe Asia
    "AMERICA": "\U0001F30E",  # Globe Americas
    "EUROPE": "\U0001F30D",   # Globe Europe/Africa
}

# Category emojis (unicode)
CATEGORY_EMOJIS = {
    "Banner": "\U0001F3AB",       # Ticket
    "Event": "\U0001F389",        # Party popper
    "Maintenance": "\U0001F527",  # Wrench
    "Offer": "\U0001F4B0",        # Money bag
    "Ended": "\U0001F6D1",        # Stop sign
    # Uma Musume specific
    "Character Banner": "\U0001F3AB",
    "Support Banner": "\U0001F4DA",      # Books
    "Paid Banner": "\U0001F4B3",         # Credit card
    "Story Event": "\U0001F4D6",         # Book
    "Champions Meeting": "\U0001F3C6",   # Trophy
    "Legend Race": "\U0001F3C7",         # Horse racing
}

# Timing emojis
TIMING_EMOJIS = {
    "start": "\U0001F7E2",   # Green circle
    "end": "\U0001F534",     # Red circle
    "reminder": "\U0001F514", # Bell
}


def get_profile_emoji(profile: str, use_fallback: bool = False) -> str:
    """
    Get emoji for a game profile.

    Args:
        profile: Game profile (e.g., "HSR", "UMA")
        use_fallback: Use unicode fallback instead of custom emoji

    Returns:
        Emoji string
    """
    profile = profile.upper()
    if use_fallback:
        return FALLBACK_PROFILE_EMOJIS.get(profile, "\U0001F3AE")
    return PROFILE_EMOJIS.get(profile, FALLBACK_PROFILE_EMOJIS.get(profile, ""))


def get_region_emoji(region: str, use_fallback: bool = False) -> str:
    """
    Get emoji for a region.

    Args:
        region: Region name (e.g., "ASIA", "NA")
        use_fallback: Use unicode fallback instead of custom emoji

    Returns:
        Emoji string
    """
    region = region.upper()
    if use_fallback:
        # Normalize aliases
        if region in ("NA", "AMERICA"):
            return FALLBACK_REGION_EMOJIS["AMERICA"]
        if region in ("EU", "EUROPE"):
            return FALLBACK_REGION_EMOJIS["EUROPE"]
        if region in ("AS", "ASIA"):
            return FALLBACK_REGION_EMOJIS["ASIA"]
        return FALLBACK_REGION_EMOJIS.get(region, "\U0001F310")

    return REGION_EMOJIS.get(region, FALLBACK_REGION_EMOJIS.get(region, ""))


def get_category_emoji(category: str) -> str:
    """
    Get emoji for an event category.

    Args:
        category: Event category

    Returns:
        Unicode emoji string
    """
    return CATEGORY_EMOJIS.get(category, "\U0001F4C5")  # Calendar as default


def get_timing_emoji(timing_type: str) -> str:
    """
    Get emoji for a timing type (start/end/reminder).

    Args:
        timing_type: Timing type string

    Returns:
        Unicode emoji string
    """
    if "start" in timing_type.lower():
        return TIMING_EMOJIS["start"]
    elif "end" in timing_type.lower():
        return TIMING_EMOJIS["end"]
    elif "reminder" in timing_type.lower():
        return TIMING_EMOJIS["reminder"]
    return "\U0001F552"  # Clock as default


def format_profile_with_emoji(
    profile: str,
    include_name: bool = True,
    use_fallback: bool = False
) -> str:
    """
    Format profile name with its emoji.

    Args:
        profile: Game profile
        include_name: Include the profile name after emoji
        use_fallback: Use unicode fallback emoji

    Returns:
        Formatted string like "<emoji> HSR" or just "<emoji>"
    """
    emoji = get_profile_emoji(profile, use_fallback)
    if include_name:
        return f"{emoji} {profile.upper()}"
    return emoji


def format_region_with_emoji(
    region: str,
    include_name: bool = True,
    use_fallback: bool = False
) -> str:
    """
    Format region name with its emoji.

    Args:
        region: Region name
        include_name: Include the region name after emoji
        use_fallback: Use unicode fallback emoji

    Returns:
        Formatted string
    """
    emoji = get_region_emoji(region, use_fallback)

    # Normalize display name
    display_name = region.upper()
    if display_name == "NA":
        display_name = "America"
    elif display_name == "EU":
        display_name = "Europe"
    elif display_name == "AS":
        display_name = "Asia"

    if include_name:
        return f"{emoji} {display_name}"
    return emoji
