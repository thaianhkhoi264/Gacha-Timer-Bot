"""
Global configuration for Kanami.
"""
import discord

# Owner's Discord user ID
OWNER_USER_ID = 680653908259110914

# Server IDs
DEV_SERVER_ID = 1374399849574961152
MAIN_SERVER_ID = 1417179378428805150

# List of allowed servers (bot will only work in these)
ALLOWED_SERVER_IDS = [DEV_SERVER_ID, MAIN_SERVER_ID]

# Listener channels (development server only)
# Format: {profile: channel_id}
LISTENER_CHANNELS = {
    # "HSR": 0,
    # "ZZZ": 0,
    # "AK": 0,
    # "STRI": 0,
    # "WUWA": 0,
}

# Notification channels (by server)
# Format: {server_id: channel_id}
NOTIFICATION_CHANNELS = {
    # DEV_SERVER_ID: 0,
    # MAIN_SERVER_ID: 0,
}

# Current Events channels (main server only, by profile)
# Format: {profile: channel_id}
CURRENT_EVENTS_CHANNELS = {
    # "HSR": 0,
    # "ZZZ": 0,
    # "AK": 0,
    # "STRI": 0,
    # "WUWA": 0,
    # "ALL": 0,
}

# Upcoming Events channels (main server only, by profile)
# Format: {profile: channel_id}
UPCOMING_EVENTS_CHANNELS = {
    # "HSR": 0,
    # "ZZZ": 0,
    # "AK": 0,
    # "STRI": 0,
    # "WUWA": 0,
    # "ALL": 0,
}

# Commands/Announcement channel (similar to Kanami assign)
# Format: {server_id: channel_id}
COMMANDS_CHANNELS = {
    # DEV_SERVER_ID: 0,
    # MAIN_SERVER_ID: 0,
}

# List of supported game profiles (used throughout the bot)
GAME_PROFILES = ["HSR", "ZZZ", "AK", "STRI", "WUWA", "ALL"]

# Mapping from Twitter handles/usernames to profile codes
PROFILE_NORMALIZATION = {
    "arknightsen": "AK",
    "zzz_en": "ZZZ",
    "honkaistarrail": "HSR",
    "strinova_en": "STRI",
    "wuthering_waves": "WUWA",
    "ak": "AK",
    "zzz": "ZZZ",
    "hsr": "HSR",
    "stri": "STRI",
    "wuwa": "WUWA",
    "all": "ALL"
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