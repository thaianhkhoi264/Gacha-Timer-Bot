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
    "HSR": 1385187382692937888,
    "ZZZ": 1385187400589906020,
    "AK": 1385187480646713364,
    "STRI": 1385187533977157643,
    "WUWA": 1385187549194223666,
}

# Notification channels (by server)
# Format: {server_id: channel_id}
NOTIFICATION_CHANNELS = {
    MAIN_SERVER_ID: 1417202133530443859
}

# Ongoing Events channels (main server only, by profile)
# Format: {profile: channel_id}
ONGOING_EVENTS_CHANNELS = {
    "HSR": 1417203732831142132,
    "ZZZ": 1417203783292813552,
    "AK": 1417203099843563703,
    "STRI": 1417203665613226259,
    "WUWA": 1417203888129577065,
    "UMA": 1417203942353272882,
}

# Upcoming Events channels (main server only, by profile)
# Format: {profile: channel_id}
UPCOMING_EVENTS_CHANNELS = {
    "HSR": 1417203760681189417,
    "ZZZ": 1417203812476911737,
    "AK": 1417203130763841566,
    "STRI": 1417203690279932107,
    "WUWA": 1417203942353272882,
    "UMA": 1417203965308964966,
}

# Commands/Announcement channel
# Format: {server_id: channel_id}
COMMANDS_CHANNELS = {
    DEV_SERVER_ID: 1374401175381606581,
    MAIN_SERVER_ID: 1417209387877138613,
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