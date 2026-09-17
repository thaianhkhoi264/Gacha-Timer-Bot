"""
Global configuration for Kanami.

Sensitive values (Discord user/server/channel/role IDs) live in
local_config.py, which is gitignored. Copy local_config.example.py to
local_config.py and fill in real values.
"""
import os
import discord

from local_config import (
    OWNER_USER_ID,
    DEV_SERVER_ID,
    MAIN_SERVER_ID,
    LISTENER_CHANNELS,
    NOTIFICATION_CHANNELS,
    ONGOING_EVENTS_CHANNELS,
    UPCOMING_EVENTS_CHANNELS,
    CONTROL_PANEL_CHANNELS,
    ROLE_IDS,
    REGIONAL_ROLE_IDS,
    COMBINED_REGIONAL_ROLE_IDS,
    COMMANDS_CHANNELS,
)

# List of allowed servers (bot will only work in these)
ALLOWED_SERVER_IDS = [DEV_SERVER_ID, MAIN_SERVER_ID]

# Notification webhook URLs (profile → Discord webhook URL)
# Set each via environment variable (see config/.env.example)
NOTIFICATION_WEBHOOK_URLS = {
    "UMA":  os.getenv("WEBHOOK_UMA", ""),
    "AK":   os.getenv("WEBHOOK_AK", ""),
    "STRI": os.getenv("WEBHOOK_STRI", ""),
    "HSR":  os.getenv("WEBHOOK_HSR", ""),
    "ZZZ":  os.getenv("WEBHOOK_ZZZ", ""),
    "WUWA": os.getenv("WEBHOOK_WUWA", ""),
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