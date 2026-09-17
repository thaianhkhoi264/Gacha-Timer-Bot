"""
Example local configuration for Kanami.

Copy this file to local_config.py (which is gitignored) and fill in the
real Discord user/server/channel/role IDs for your deployment.
"""

# Owner's Discord user ID
OWNER_USER_ID = 0

# Server IDs
DEV_SERVER_ID = 0
MAIN_SERVER_ID = 0

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

# Control Panel channels (main server only, by profile)
# Format: {profile: channel_id}
CONTROL_PANEL_CHANNELS = {
    # "HSR": 0,
    # "ZZZ": 0,
    "AK": 0,
    # "STRI": 0,
    # "WUWA": 0,
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
    "UMA": 0,
}

# Role IDs (by region)
# Format: {region: role_id}
REGIONAL_ROLE_IDS = {
    "ASIA": 0,
    "AMERICA": 0,
    "EUROPE": 0,
}

# Combined Regional Role IDs (by profile and region)
# Format: {(profile, region): role_id}
COMBINED_REGIONAL_ROLE_IDS = {
    ("HSR", "AMERICA"): 0,
    ("HSR", "EUROPE"):  0,
    ("HSR", "ASIA"):    0,
    ("ZZZ", "AMERICA"): 0,
    ("ZZZ", "EUROPE"):  0,
    ("ZZZ", "ASIA"):    0,
    ("WUWA", "AMERICA"):0,
    ("WUWA", "EUROPE"): 0,
    ("WUWA", "ASIA"):   0,
}

# Commands/Announcement channel
# Format: {server_id: channel_id}
COMMANDS_CHANNELS = {
    DEV_SERVER_ID: 0,
    MAIN_SERVER_ID: 0,
}

# Map user descriptions (from api_keys.json) to Discord user IDs
# When an API key is used, we look up its description and map it to a Discord ID
USER_DESCRIPTION_TO_ID = {
    "Narisurii": "0",
    "Alfabem": "0",
    "Naito": "0",
    "SteveGHShadow": "0",
}
