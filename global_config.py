"""
Global configuration for Kanami.
"""
import discord

# Owner's Discord user ID
OWNER_USER_ID = 0

# Server IDs
DEV_SERVER_ID = 0
MAIN_SERVER_ID = 0

# List of allowed servers (bot will only work in these)
ALLOWED_SERVER_IDS = [DEV_SERVER_ID, MAIN_SERVER_ID]

# Listener channels (development server only)
# Format: {profile: channel_id}
LISTENER_CHANNELS = {
    "HSR": 0,
    "ZZZ": 0,
    "AK": 0,
    "STRI": 0,
    "WUWA": 0,    
}

# Notification channels (by server)
# Format: {server_id: channel_id}
NOTIFICATION_CHANNELS = {
    "HSR": 0,
    "ZZZ": 0,
    "AK": 0,  
    "STRI": 0,
    "WUWA": 0,
    "UMA": 0,
}

# Ongoing Events channels (main server only, by profile)
# Format: {profile: channel_id}
ONGOING_EVENTS_CHANNELS = {
    "HSR": 0,
    "ZZZ": 0,
    "AK": 0,
    "STRI": 0,
    "WUWA": 0,
    "UMA": 0,
}

# Upcoming Events channels (main server only, by profile)
# Format: {profile: channel_id}
UPCOMING_EVENTS_CHANNELS = {
    "HSR": 0,
    "ZZZ": 0,
    "AK": 0,
    "STRI": 0,
    "WUWA": 0,
    "UMA": 0,
}

# Role IDs (by profile)
# Format: {profile: role_id}
ROLE_IDS = {
    "HSR": 0,
    "ZZZ": 0,
    "AK": 0,
    "STRI": 0,
    "WUWA": 0,
    "UMA": 0
}

# Role IDs (by region)
# Format: {region: role_id}
REGIONAL_ROLE_IDS = {
    "Asia": 0,
    "America": 0,
    "Europe": 0,
}

# Combined Regional Role IDs (by profile and region)
# Format: {profile: role_id}
COMBINED_REGIONAL_ROLE_IDS = {
        ("HSR", "America"): 0,
        ("HSR", "Europe"):  0,
        ("HSR", "Asia"):    0,
        ("ZZZ", "America"): 0,
        ("ZZZ", "Europe"):  0,
        ("ZZZ", "Asia"):    0,
        ("WUWA", "America"):0,
        ("WUWA", "Europe"): 0,
        ("WUWA", "Asia"):   0,
}

# Commands/Announcement channel
# Format: {server_id: channel_id}
COMMANDS_CHANNELS = {
    DEV_SERVER_ID: 0,
    MAIN_SERVER_ID: 0,
}

# List of supported game profiles (used throughout the bot)
GAME_PROFILES = ["HSR", "ZZZ", "AK", "STRI", "WUWA", "UMA"]

# Mapping from Twitter handles/usernames to profile codes
PROFILE_NORMALIZATION = {
    "arknightsen": "AK",
    "zzz_en": "ZZZ",
    "honkaistarrail": "HSR",
    "strinova_en": "STRI",
    "wuthering_waves": "WUWA",
    "umamusume_eng": "UMA",
    "ak": "AK",
    "zzz": "ZZZ",
    "hsr": "HSR",
    "stri": "STRI",
    "wuwa": "WUWA",
    "uma": "UMA"
}

# Set of poster usernames that use triple timezone display (Hoyoverse games)
HYV_ACCOUNTS = {"honkaistarrail", "zzz_en"}

# Triple timezone mapping for Hoyoverse games
HYV_TIMEZONES = {
    "Asia": "Asia/Shanghai",        # UTC+8
    "America": "America/New_York",  # UTC-5 (handles DST)
    "Europe": "Europe/Berlin",      # UTC+1 (handles DST)
}

PROFILE_COLORS = {
    "AK": discord.Color.teal(),
    "HSR": discord.Color.fuchsia(),
    "ZZZ": discord.Color.yellow(),
    "STRI": discord.Color.orange(),
    "WUWA": discord.Color.green(),
}