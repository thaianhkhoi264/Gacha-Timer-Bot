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
    "HSR": 1419711421763162283,
    "ZZZ": 1419711446081863713,
    "AK": 1419711343958687835,  
    "STRI": 1419711382529769645,
    "WUWA": 1419711476423458947,
    "UMA": 1419711507842732072,
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

# Control Panel channels (main server only, by profile)
# Format: {profile: channel_id}
CONTROL_PANEL_CHANNELS = {
    # "HSR": 1420821600223232030,
    # "ZZZ": 1420821623740825734,
    "AK": 1420821379707699281,
    # "STRI": 1420821566115025068,
    # "WUWA": 1420821653478441230,
    # "UMA": 1420821685334184056,
}

# Role IDs (by profile)
# Format: {profile: role_id}
ROLE_IDS = {
    "HSR": 1419710461301096508,
    "ZZZ": 1419710407249232024,
    "AK": 1419709704204058715,
    "STRI": 1419710297584701632,
    "WUWA": 1419710664821309440,
    "UMA": 1419710615248965754
}

# Role IDs (by region)
# Format: {region: role_id}
REGIONAL_ROLE_IDS = {
    "ASIA": 1419716022046429245,
    "AMERICA": 1419715948214091886,
    "EUROPE": 1419715991813754991,
}

# Combined Regional Role IDs (by profile and region)
# Format: {profile: role_id}
COMBINED_REGIONAL_ROLE_IDS = {
        ("HSR", "AMERICA"): 1419716124794421258,
        ("HSR", "EUROPE"):  1419716153189601321,
        ("HSR", "ASIA"):    1419716172043256000,
        ("ZZZ", "AMERICA"): 1419716204985061396,
        ("ZZZ", "EUROPE"):  1419716225130299412,
        ("ZZZ", "ASIA"):    1419716242419351746,
        ("WUWA", "AMERICA"):1419716257216991282,
        ("WUWA", "EUROPE"): 1419716271611576421,
        ("WUWA", "ASIA"):   1419716304239333457,
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