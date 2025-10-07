from modules import *
from bot import bot

from collections import deque
import asyncio
import datetime
import time
import aiosqlite
import os

from global_config import *

# --- Ensure notification DB and tables exist ---
NOTIF_DB_PATH = os.path.join("data", "notification_data.db")

async def init_notification_db():
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        # Pending notifications (persistent scheduling)
        await conn.execute('''CREATE TABLE IF NOT EXISTS pending_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            profile TEXT,
            title TEXT,
            timing_type TEXT,
            notify_unix INTEGER,
            event_time_unix INTEGER,
            sent INTEGER DEFAULT 0,
            region TEXT
        )''')
        # UNIQUE index to prevent duplicates (including region for HYV)
        await conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_pending_notif
            ON pending_notifications (category, profile, title, timing_type, notify_unix, region)
        ''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS pending_notifications_messages (
            profile TEXT,
            message_id TEXT,
            PRIMARY KEY (profile, message_id)
        )''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS role_reaction_messages (
            type TEXT PRIMARY KEY,
            message_id TEXT
        )''')
        await conn.commit()

PROFILE_EMOJIS = {
    "HSR": "<:Game_HSR:1384176219385237588>",
    "ZZZ": "<:Game_ZZZ:1384176233159589919>",
    "AK": "<:Game_AK:1384176253342449816>",
    "STRI": "<:Game_Strinova:1384176243708264468>",
    "WUWA": "<:Game_WUWA:1384186019901083720>",
    "UMA": "<:Game_UMA:1394905581328007240>",
}

REGION_EMOJIS = {
    "ASIA": "<:Region_AS:1384176206500593706>",
    "AMERICA": "<:Region_NA:1384176179187159130>",
    "EUROPE": "<:Region_EU:1384176193426690088>"
}

NOTIFICATION_TIMINGS = {
    "Banner":    {"start": [60, 1440], "end": [60, 1440]},
    "Event":     {"start": [180], "end": [180, 1440]},
    "Maintenance": {"start": [60], "end": [0]},
    "Offer":     {"start": [180, 1440], "end": [1440]},
}

MAX_FIELDS = 25

def safe_int(val, fallback):
    try:
        return int(val)
    except (TypeError, ValueError):
        return int(fallback)

# Global variable to track the last log time
_last_log_time = 0

# refresh pending notification logs path + Owner ID
DEBUG_LOG_PATH = "debug_refresh_pending.log"
IMPORTANT_DM_USER_ID = 680653908259110914

# Global anti-notification spam failsafe variables
recent_notification_times = deque(maxlen=10)  # Track last 10 notifications
recently_sent_notifications = set()  # Track sent notifications to prevent duplicates

# Function to format minutes into hours or days
def format_minutes(minutes):
    parts = []
    days = minutes // 1440
    if days:
        parts.append(f"{days}d")
    minutes %= 1440
    hours = minutes // 60
    if hours:
        parts.append(f"{hours}h")
    minutes %= 60
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "0m"

# Function to log messages to both console and a file
def send_log(*args):
    """Logs a message to both the console and the discord.log file. Accepts any arguments and joins them as a string."""
    # If the first argument looks like a server ID, skip it
    if len(args) > 1 and (str(args[0]).isdigit() or args[0] in ("N/A", MAIN_SERVER_ID)):
        args = args[1:]
    message = " ".join(str(arg) for arg in args if arg is not None)
    print(message)
    try:
        with open("discord.log", "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")

# Function to remove duplicate pending notifications
async def remove_duplicate_pending_notifications():
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        await conn.execute("""
            DELETE FROM pending_notifications
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM pending_notifications
                GROUP BY category, profile, title, timing_type, notify_unix, region
            )
        """)
        await conn.commit()
    print("Duplicate pending_notifications removed.")

def get_notification_timings(category):
    # Returns a list of (timing_type, timing_minutes) tuples for the given category
    timings = []
    cat_timings = NOTIFICATION_TIMINGS.get(category, {})
    for timing_type in ("start", "end"):
        for minutes in cat_timings.get(timing_type, []):
            timings.append((timing_type, minutes))
    return timings

async def schedule_notifications_for_event(event):
    """
    Schedules notifications for an event using only profile-based channels and hardcoded timings.
    """
    send_log(MAIN_SERVER_ID, f"schedule_notifications_for_event called for event: `{event['title']}` ({event['category']}) [{event['profile']}]")
    timings = get_notification_timings(event['category'])
    send_log(MAIN_SERVER_ID, f"Using timings for event: {timings}")

    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        HYV_PROFILES = {"HSR", "ZZZ"}
        if event['profile'].upper() in HYV_PROFILES:
            regions = ["NA", "EU", "ASIA"]
            for region in regions:
                for timing_type, timing_minutes in timings:
                    if region == "NA":
                        event_time_unix = safe_int(event.get('america_start'), event.get('start_date')) if timing_type == "start" else safe_int(event.get('america_end'), event.get('end_date'))
                    elif region == "EU":
                        event_time_unix = safe_int(event.get('europe_start'), event.get('start_date')) if timing_type == "start" else safe_int(event.get('europe_end'), event.get('end_date'))
                    elif region == "ASIA":
                        event_time_unix = safe_int(event.get('asia_start'), event.get('start_date')) if timing_type == "start" else safe_int(event.get('asia_end'), event.get('end_date'))
                    else:
                        event_time_unix = int(event['start_date']) if timing_type == "start" else int(event['end_date'])
                    notify_unix = event_time_unix - timing_minutes * 60
                    if notify_unix > int(datetime.datetime.now(datetime.timezone.utc).timestamp()):
                        async with conn.execute(
                            "SELECT 1 FROM pending_notifications WHERE category=? AND profile=? AND title=? AND timing_type=? AND notify_unix=? AND region=?",
                            (event['category'], event['profile'], event['title'], timing_type, notify_unix, region)
                        ) as check_cursor:
                            exists = await check_cursor.fetchone()
                        if not exists:
                            await conn.execute(
                                "INSERT INTO pending_notifications (category, profile, title, timing_type, notify_unix, event_time_unix, sent, region) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                                (event['category'], event['profile'], event['title'], timing_type, notify_unix, event_time_unix, region)
                            )
        else:
            for timing_type, timing_minutes in timings:
                event_time_unix = int(event['start_date']) if timing_type == "start" else int(event['end_date'])
                notify_unix = event_time_unix - timing_minutes * 60
                if notify_unix > int(datetime.datetime.now(datetime.timezone.utc).timestamp()):
                    async with conn.execute(
                        "SELECT 1 FROM pending_notifications WHERE category=? AND profile=? AND title=? AND timing_type=? AND notify_unix=?",
                        (event['category'], event['profile'], event['title'], timing_type, notify_unix)
                    ) as check_cursor:
                        exists = await check_cursor.fetchone()
                    if not exists:
                        await conn.execute(
                            "INSERT INTO pending_notifications (category, profile, title, timing_type, notify_unix, event_time_unix, sent) VALUES (?, ?, ?, ?, ?, ?, 0)",
                            (event['category'], event['profile'], event['title'], timing_type, notify_unix, event_time_unix)
                        )
                        send_log(
                            MAIN_SERVER_ID,
                            f"Scheduled notification for `{event['title']}` at <t:{notify_unix}:F> / <t:{notify_unix}:R> (timing_type: {timing_type})"
                        )
                else:
                    send_log(
                        MAIN_SERVER_ID,
                        f"Skipped scheduling notification for `{event['title']}` (notify_unix <t:{notify_unix}:F> / <t:{notify_unix}:R> is in the past)"
                    )
        await conn.commit()
    guild = bot.get_guild(MAIN_SERVER_ID)
    await update_pending_notifications_embed_for_profile(guild, event['profile'])

async def delete_notifications_for_event(title, category, profile):
    """
    Deletes all pending notifications for a specific event (profile-based).
    """
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM pending_notifications WHERE title=? AND category=? AND profile=?",
            (title, category, profile)
        )
        await conn.commit()

async def send_notification(event, timing_type):
    """
    Sends a notification to the correct profile-specific channel, using global_config.py for channel lookup.
    """
    from global_config import NOTIFICATION_CHANNELS, MAIN_SERVER_ID

    profile = event['profile'].upper()
    channel_id = NOTIFICATION_CHANNELS.get(profile)
    if not channel_id:
        send_log(event.get('server_id', 'N/A'), f"No notification channel set for profile {profile}")
        return

    guild = bot.get_guild(MAIN_SERVER_ID)
    channel = guild.get_channel(channel_id)
    if not channel:
        send_log(event.get('server_id', 'N/A'), f"No notification channel found for profile {profile}")
        return

    HYV_PROFILES = {"HSR", "ZZZ"}
    if profile in HYV_PROFILES:
        region = event.get('region')
        if not region:
            send_log(event.get('server_id', 'N/A'), f"No region found for notification: {event['title']}")
            return

        combined_role_name = f"{profile} {region}"
        role = discord.utils.get(guild.roles, name=combined_role_name)
        if role:
            role_mention = role.mention
            send_log(event.get('server_id', 'N/A'), f"Found combined role for {profile} {region}: {role_mention}")
        else:
            send_log(event.get('server_id', 'N/A'), f"No combined role found for {profile} {region}")
            return
        unix_time = None
        if region == "NA":
            unix_time = event.get('america_start') if timing_type == "start" else event.get('america_end')
        elif region == "EU":
            unix_time = event.get('europe_start') if timing_type == "start" else event.get('europe_end')
        elif region == "ASIA":
            unix_time = event.get('asia_start') if timing_type == "start" else event.get('asia_end')
        if not unix_time:
            unix_time = event['start_date'] if timing_type == "start" else event['end_date']
        time_str = "starting" if timing_type == "start" else "ending"
        try:
            await channel.send(
                f"{role_mention}, the **{event['category']}** **{event['title']}** is {time_str} <t:{unix_time}:R>!"
            )
            send_log(event.get('server_id', 'N/A'), f"Notification sent to channel {channel_id} for event {event['title']} ({profile} {region})")
        except Exception as e:
            send_log(event.get('server_id', 'N/A'), f"Failed to send notification for {profile} {region}: {e}")
    else:
        emoji = PROFILE_EMOJIS.get(profile)
        role_mention = ""
        if emoji:
            role_id = ROLE_IDS.get(profile)
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    role_mention = role.mention
                    send_log(event.get('server_id', 'N/A'), f"Found role for profile {profile}: {role_mention}")
                else:
                    send_log(event.get('server_id', 'N/A'), f"Role ID {role_id} not found in guild for profile {profile}")
            else:
                send_log(event.get('server_id', 'N/A'), f"No role_id found for profile {profile}")
        else:
            send_log(event.get('server_id', 'N/A'), f"No emoji found for profile {profile}")

        unix_time = event['start_date'] if timing_type == "start" else event['end_date']
        time_str = "starting" if timing_type == "start" else "ending"
        try:
            await channel.send(
                f"{role_mention}, the **{event['category']}** event **{event['title']}** is {time_str} <t:{unix_time}:R>!"
            )
            send_log(event.get('server_id', 'N/A'), f"Notification sent to channel {channel_id} for event {event['title']}")
        except Exception as e:
            send_log(event.get('server_id', 'N/A'), f"Failed to send notification: {e}")

async def load_and_schedule_pending_notifications(bot):
    """
    Batch notification loop: checks for due notifications and sends them immediately.
    Should be called in a background loop every 30-60 seconds.
    """
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        async with conn.execute("""
            SELECT id, category, profile, title, timing_type, notify_unix, event_time_unix, region
            FROM pending_notifications
            WHERE sent=0 AND notify_unix <= ?
        """, (now + 60,)) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            notif_id, category, profile, title, timing_type, notify_unix, event_time_unix, region = row
            event = {
                'category': category,
                'profile': profile,
                'title': title,
                'start_date': event_time_unix if timing_type == "start" else None,
                'end_date': event_time_unix if timing_type == "end" else None,
                'region': region
            }
            await conn.execute("UPDATE pending_notifications SET sent=1 WHERE id=?", (notif_id,))
            await send_notification(event, timing_type)
        await conn.commit()

async def update_all_pending_notifications_embeds(guild):
    """Update all game embeds in the pending notifications channel."""
    # Always show all supported profiles, even if they have no notifications
    profiles = ["AK", "HSR", "ZZZ", "STRI", "WUWA"]
    for profile in profiles:
        await update_pending_notifications_embed_for_profile(guild, profile)

async def update_pending_notifications_embed_for_profile(guild, profile):
    import math

    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        # Get the channel for pending notifications for this profile from global_config
        # from global_config import PENDING_NOTIFICATIONS_CHANNELS
        # channel_id = PENDING_NOTIFICATIONS_CHANNELS.get(profile)
        channel_id = None
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return

        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        async with conn.execute("""
            SELECT title, category, timing_type, notify_unix, event_time_unix, region
            FROM pending_notifications
            WHERE profile=? AND notify_unix > ?
            ORDER BY event_time_unix ASC, notify_unix ASC
        """, (profile, now)) as cursor:
            rows = await cursor.fetchall()

        color = PROFILE_COLORS.get(profile, discord.Color.default())
        HYV_PROFILES = {"HSR", "ZZZ"}

        fields = []
        if profile in HYV_PROFILES:
            # Group by (title, category)
            grouped = {}
            for title, category, timing_type, notify_unix, event_time_unix, region in rows:
                key = (title, category)
                if key not in grouped:
                    grouped[key] = {}
                if timing_type not in grouped[key]:
                    grouped[key][timing_type] = {}
                event_region_key = (event_time_unix, region)
                if event_region_key not in grouped[key][timing_type]:
                    grouped[key][timing_type][event_region_key] = []
                grouped[key][timing_type][event_region_key].append(notify_unix)

            for (title, category), types in grouped.items():
                value_lines = []
                for timing_type in ("start", "end"):
                    if timing_type in types:
                        for (event_time_unix, region) in sorted(types[timing_type].keys()):
                            notify_times = types[timing_type][(event_time_unix, region)]
                            notify_strs = [f"<t:{n}:R>" for n in sorted(notify_times)]
                            event_time_str = f"<t:{event_time_unix}:F>"
                            region_str = f"**Region:** `{region}`" if region else "**Region:** `Unknown`"
                            value_lines.append(
                                f"{region_str}\n"
                                f"**Type:** `{timing_type}`\n"
                                f"Event Time: {event_time_str}\n"
                                f"Notify: {', '.join(notify_strs)}"
                            )
                if value_lines:
                    max_field_name_length = 256
                    field_name = f"{title} ({category})"
                    if len(field_name) > max_field_name_length:
                        field_name = field_name[:max_field_name_length - 3] + "..."
                    value = "\n\n".join(value_lines)
                    if len(value) > 1024:
                        value = value[:1021] + "..."
                    fields.append({
                        "name": field_name,
                        "value": value
                    })
        else:
            # Group by (title, category)
            grouped = {}
            for title, category, timing_type, notify_unix, event_time_unix, _ in rows:
                key = (title, category)
                if key not in grouped:
                    grouped[key] = {}
                if timing_type not in grouped[key]:
                    grouped[key][timing_type] = {}
                if event_time_unix not in grouped[key][timing_type]:
                    grouped[key][timing_type][event_time_unix] = []
                grouped[key][timing_type][event_time_unix].append(notify_unix)

            for (title, category), types in grouped.items():
                value_lines = []
                for timing_type in ("start", "end"):
                    if timing_type in types:
                        for event_time_unix in sorted(types[timing_type].keys()):
                            notify_times = types[timing_type][event_time_unix]
                            notify_strs = [f"<t:{n}:R>" for n in sorted(notify_times)]
                            event_time_str = f"<t:{event_time_unix}:F>"
                            value_lines.append(
                                f"**Type:** `{timing_type}`\n"
                                f"Event Time: {event_time_str}\n"
                                f"Notify: {', '.join(notify_strs)}"
                            )
                if value_lines:
                    fields.append({
                        "name": f"{title} ({category})",
                        "value": "\n\n".join(value_lines)
                    })

        # Split fields into chunks of 25 for Discord embed limit
        chunks = [fields[i:i+MAX_FIELDS] for i in range(0, max(1, len(fields)), MAX_FIELDS)]

        # Fetch all existing dashboard messages for this profile
        async with conn.execute(
            "SELECT message_id FROM pending_notifications_messages WHERE profile=? ORDER BY message_id ASC",
            (profile,)
        ) as cursor:
            old_msgs = [msg_id async for (msg_id,) in cursor]

        new_msg_ids = []
        for idx, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"Pending Notifications: {profile}" + (f" (Page {idx+1})" if len(chunks) > 1 else ""),
                description="All upcoming scheduled notifications for {} in this server.".format(profile) if chunk else "No pending notifications.",
                color=color
            )
            if not chunk:
                embed.description = "No pending notifications."
            else:
                for field in chunk:
                    embed.add_field(name=field["name"], value=field["value"], inline=False)
            # Edit existing message or send new one
            msg_id = old_msgs[idx] if idx < len(old_msgs) else None
            msg = None
            try:
                if msg_id:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.edit(embed=embed)
                else:
                    msg = await channel.send(embed=embed)
            except Exception:
                msg = await channel.send(embed=embed)
            new_msg_ids.append(str(msg.id))

        # Remove any extra old messages if the number of embeds decreased
        for msg_id in old_msgs[len(chunks):]:
            try:
                msg = await channel.fetch_message(int(msg_id))
                await msg.delete()
            except Exception:
                pass

        # Update the DB with the new set of message IDs
        await conn.execute(
            "DELETE FROM pending_notifications_messages WHERE profile=?",
            (profile,)
        )
        for msg_id in new_msg_ids:
            await conn.execute(
                "INSERT INTO pending_notifications_messages (profile, message_id) VALUES (?, ?)",
                (profile, msg_id)
            )
        await conn.commit()

async def update_combined_roles(member):
    """
    Assigns/removes combined roles based on the user's game and region roles.
    Only applies to HSR, ZZZ, WUWA.
    """
    games = ["HSR", "ZZZ", "WUWA"]
    regions = ["America", "Europe", "Asia"]
    guild = member.guild
    user_role_ids = {r.id for r in member.roles}

    for game in games:
        game_role_id = ROLE_IDS.get(game)
        has_game = game_role_id in user_role_ids
        for region in regions:
            region_role_id = REGIONAL_ROLE_IDS.get(region)
            has_region = region_role_id in user_role_ids
            combined_role_id = COMBINED_REGIONAL_ROLE_IDS.get((game, region))
            if combined_role_id:
                combined_role = guild.get_role(combined_role_id)
                if not combined_role:
                    continue
                if has_game and has_region:
                    if combined_role not in member.roles:
                        await member.add_roles(combined_role, reason="Auto combined role update")
                else:
                    if combined_role in member.roles:
                        await member.remove_roles(combined_role, reason="Auto combined role update")
# Listeners for reaction roles
@bot.event
async def on_raw_reaction_add(payload):
    if payload.member is None or payload.member.bot:
        return
    
    # Check if this is a tracked role reaction message
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        async with conn.execute("SELECT type FROM role_reaction_messages WHERE message_id=?", (str(payload.message_id),)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return  # Not a role reaction message
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    # Profile roles
    for profile, emoji in PROFILE_EMOJIS.items():
        if str(payload.emoji) == emoji:
            role_id = ROLE_IDS.get(profile)
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    await payload.member.add_roles(role, reason="Profile role reaction add")
    # Region roles
    for region, emoji in REGION_EMOJIS.items():
        if str(payload.emoji) == emoji:
            role_id = REGIONAL_ROLE_IDS.get(region.upper())
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    await payload.member.add_roles(role, reason="Region role reaction add")
    # After adding, update combined roles
    await update_combined_roles(payload.member)

@bot.event
async def on_raw_reaction_remove(payload):
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    # Check if this is a tracked role reaction message
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        async with conn.execute("SELECT type FROM role_reaction_messages WHERE message_id=?", (str(payload.message_id),)) as cursor:
            row = await cursor.fetchone()
    
    if not row:
        return  # Not a role reaction message
        
    member = guild.get_member(payload.user_id)
    if not member:
        return

    # Profile roles
    for profile, emoji in PROFILE_EMOJIS.items():
        if str(payload.emoji) == emoji:
            role_id = ROLE_IDS.get(profile)
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    await member.remove_roles(role, reason="Profile role reaction remove")
    
    # Region roles
    for region, emoji in REGION_EMOJIS.items():
        if str(payload.emoji) == emoji:
            role_id = REGIONAL_ROLE_IDS.get(region.upper())
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    await member.remove_roles(role, reason="Region role reaction remove")
    
    # After removing, update combined roles
    await update_combined_roles(member)

@bot.command()
@commands.has_permissions(manage_roles=True)
async def create_role_reaction(ctx):
    """
    Sends a message for users to react and get profile/region roles.
    Uses hardcoded role IDs and emojis from global_config.py.
    """
    guild = ctx.guild

    # Profile roles
    profile_msg = await ctx.send("React to this message to get notification roles for each game.")
    for profile, emoji in PROFILE_EMOJIS.items():
        role_id = ROLE_IDS.get(profile)
        if role_id:
            await profile_msg.add_reaction(emoji)
    
    # Region roles
    region_msg = await ctx.send("React to this message to get your region role. (This only matters for Star Rail, Zenless Zone Zero and Wuthering Waves)")
    for region, emoji in REGION_EMOJIS.items():
        role_id = REGIONAL_ROLE_IDS.get(region.upper())
        if role_id:
            await region_msg.add_reaction(emoji)
    
    # Save message IDs to database
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        await conn.execute("REPLACE INTO role_reaction_messages (type, message_id) VALUES (?, ?)", ("profile", str(profile_msg.id)))
        await conn.execute("REPLACE INTO role_reaction_messages (type, message_id) VALUES (?, ?)", ("region", str(region_msg.id)))
        await conn.commit()
    
    await ctx.send("React to the above messages to assign yourself roles!")
    

@bot.command()
@commands.has_permissions(administrator=True)
async def update_all_combined_roles(ctx):
    """Checks all members and updates their combined roles."""
    count = 0
    for member in ctx.guild.members:
        if not member.bot:
            await update_combined_roles(member)
            count += 1
    await ctx.send(f"Updated combined roles for {count} members.")

@bot.command()
@commands.has_permissions(administrator=True)
async def clear_pending_notifications(ctx):
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        await conn.execute("DELETE FROM pending_notifications")
        await conn.commit()
    await ctx.send("Cleared all pending notifications.")
    await update_all_pending_notifications_embeds(ctx.guild)

async def debug_log(message, bot=None, important=False):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    # Write to file
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"Failed to write debug log: {e}")
    # Optionally send DM for important messages
    if important and bot is not None:
        try:
            user = await bot.fetch_user(IMPORTANT_DM_USER_ID)
            await user.send(f"[Kanami Debug]\n{log_entry}")
        except Exception as e:
            print(f"Failed to send debug DM: {e}")

