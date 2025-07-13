from modules import *
from bot import bot

from collections import deque

import sqlite3
import asyncio
import datetime
import time

PROFILE_EMOJIS = {
    "HSR": "<:Game_HSR:1384176219385237588>",
    "ZZZ": "<:Game_ZZZ:1384176233159589919>",
    "AK": "<:Game_AK:1384176253342449816>",
    "STRI": "<:Game_Strinova:1384176243708264468>",
    "WUWA": "<:Game_WUWA:1384186019901083720>",
}

REGION_EMOJIS = {
    "ASIA": "<:Region_AS:1384176206500593706>",
    "AMERICA": "<:Region_NA:1384176179187159130>",
    "EUROPE": "<:Region_EU:1384176193426690088>"
}

PROFILE_COLORS = {
    "AK": discord.Color.teal(),        # Aqua
    "HSR": discord.Color.fuchsia(),    # Fuchsia
    "ZZZ": discord.Color.yellow(),     # Yellow
    "STRI": discord.Color.orange(),    # Orange
    "WUWA": discord.Color.green(),     # Green
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
def send_log(server_id, message):
    """Logs a message to both the console and the discord.log file, including the server ID."""
    log_entry = f"[Server {server_id}] {message}"
    print(log_entry)
    try:
        with open("discord.log", "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")

# Function to update the notification timing message in the specified channel
async def update_notification_timing_message(guild):
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT channel_id FROM notification_timing_channel WHERE server_id=?", (str(guild.id),))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    channel_id = int(row[0])
    channel = guild.get_channel(channel_id)
    if not channel:
        conn.close()
        return

    c.execute("SELECT category, timing_type, timing_minutes FROM notification_timings WHERE server_id=?", (str(guild.id),))
    timings = c.fetchall()
    conn.close()

    embed = discord.Embed(
        title="Notification Timings",
        description="Current notification timings for each category.",
        color=discord.Color.blue()
    )

    if not timings:
        embed.description = "No notification timings set."
    else:
        # Group by category and timing_type, collect all timings
        timing_dict = {}
        for cat, ttype, mins in timings:
            if cat not in timing_dict:
                timing_dict[cat] = {"start": [], "end": []}
            timing_dict[cat][ttype].append(mins)
        for cat, types in timing_dict.items():
            start_list = sorted(types.get("start", []))
            end_list = sorted(types.get("end", []))
            start_str = ", ".join(format_minutes(m) for m in start_list) if start_list else "Not set"
            end_str = ", ".join(format_minutes(m) for m in end_list) if end_list else "Not set"
            embed.add_field(
                name=f"{cat}",
                value=f"**Start:** {start_str}\n**End:** {end_str}",
                inline=False
            )

    # Try to edit the existing message, or send a new one
    try:
        c = sqlite3.connect('kanami_data.db').cursor()
        c.execute("SELECT message_id FROM notification_timing_channel WHERE server_id=?", (str(guild.id),))
        msg_row = c.fetchone()
        if msg_row and msg_row[0]:
            message_id = int(msg_row[0])
            try:
                msg = await channel.fetch_message(message_id)
                await msg.edit(content=None, embed=embed)
                return
            except Exception:
                pass
        msg = await channel.send(embed=embed)
        c.execute("UPDATE notification_timing_channel SET message_id=? WHERE server_id=?", (str(msg.id), str(guild.id)))
        c.connection.commit()
    except Exception:
        pass

async def schedule_notifications_for_event(event):
    send_log(event['server_id'], f"schedule_notifications_for_event called for event: `{event['title']}` ({event['category']}) [{event['profile']}]")
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT timing_type, timing_minutes FROM notification_timings WHERE server_id=? AND category=?",
              (event['server_id'], event['category']))
    timings = c.fetchall()
    send_log(event['server_id'], f"Found timings for event: {timings}")

    HYV_PROFILES = {"HSR", "ZZZ"}
    if event['profile'].upper() in HYV_PROFILES:
        regions = ["NA", "EU", "ASIA"]
        for region in regions:
            for timing_type, timing_minutes in timings:
                # Use region-specific times if available
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
                    # Prevent duplicate scheduling
                    c.execute(
                        "SELECT 1 FROM pending_notifications WHERE server_id=? AND category=? AND profile=? AND title=? AND timing_type=? AND notify_unix=? AND region=?",
                        (event['server_id'], event['category'], event['profile'], event['title'], timing_type, notify_unix, region)
                    )
                    if not c.fetchone():
                        c.execute(
                            "INSERT INTO pending_notifications (server_id, category, profile, title, timing_type, notify_unix, event_time_unix, sent, region) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                            (event['server_id'], event['category'], event['profile'], event['title'], timing_type, notify_unix, event_time_unix, region)
                        )
    else:
        # Non-HYV games, as before
        for timing_type, timing_minutes in timings:
            event_time_unix = int(event['start_date']) if timing_type == "start" else int(event['end_date'])
            notify_unix = event_time_unix - timing_minutes * 60
            if notify_unix > int(datetime.datetime.now(datetime.timezone.utc).timestamp()):
                c.execute(
                    "SELECT 1 FROM pending_notifications WHERE server_id=? AND category=? AND profile=? AND title=? AND timing_type=? AND notify_unix=?",
                    (event['server_id'], event['category'], event['profile'], event['title'], timing_type, notify_unix)
                )
                if not c.fetchone():
                    c.execute(
                        "INSERT INTO pending_notifications (server_id, category, profile, title, timing_type, notify_unix, event_time_unix, sent) VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                        (event['server_id'], event['category'], event['profile'], event['title'], timing_type, notify_unix, event_time_unix)
                    )
                    send_log(
                        event['server_id'],
                        f"Scheduled notification for `{event['title']}` at <t:{notify_unix}:F> / <t:{notify_unix}:R> (timing_type: {timing_type})"
                    )
            else:
                send_log(
                    event['server_id'],
                    f"Skipped scheduling notification for `{event['title']}` (notify_unix <t:{notify_unix}:F> / <t:{notify_unix}:R> is in the past)"
                )
    conn.commit()
    conn.close()
    guild = bot.get_guild(int(event['server_id']))
    await update_pending_notifications_embed_for_profile(guild, event['profile'])


async def send_notification(event, timing_type):
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT channel_id FROM notification_channel WHERE server_id=?", (event['server_id'],))
    row = c.fetchone()
    if not row or not row[0]:
        send_log(event['server_id'], f"No notification channel set for server {event['server_id']}")
        conn.close()
        return

    channel_id = int(row[0])
    guild = bot.get_guild(int(event['server_id']))
    channel = guild.get_channel(channel_id)
    if not channel:
        send_log(event['server_id'], f"Notification channel {channel_id} not found in guild {guild}")
        conn.close()
        return

    # --- Determine if this is a Hoyoverse game ---
    HYV_PROFILES = {"HSR", "ZZZ"}
    profile = event['profile'].upper()
    if profile in HYV_PROFILES:
        region = event.get('region')
        if not region:
            send_log(event['server_id'], f"No region found for notification: {event['title']}")
            conn.close()
            return

        combined_role_name = f"{profile} {region}"
        role = discord.utils.get(guild.roles, name=combined_role_name)
        if role:
            role_mention = role.mention
            send_log(event['server_id'], f"Found combined role for {profile} {region}: {role_mention}")
        else:
            send_log(event['server_id'], f"No combined role found for {profile} {region}")
            conn.close()
            return

        unix_time = event['start_date'] if timing_type == "start" else event['end_date']
        time_str = "starting" if timing_type == "start" else "ending"
        try:
            await channel.send(
                f"{role_mention}, the **{event['category']}** **{event['title']}** is {time_str} <t:{unix_time}:R>!"
            )
            send_log(event['server_id'], f"Notification sent to channel {channel_id} for event {event['title']} ({profile} {region})")
        except Exception as e:
            send_log(event['server_id'], f"Failed to send notification for {profile} {region}: {e}")
        conn.close()

        # Pick the correct event time for this region
        unix_time = None
        if region == "NA":
            unix_time = event.get('america_start') if timing_type == "start" else event.get('america_end')
        elif region == "EU":
            unix_time = event.get('europe_start') if timing_type == "start" else event.get('europe_end')
        elif region == "ASIA":
            unix_time = event.get('asia_start') if timing_type == "start" else event.get('asia_end')

        # Fallback to event['start_date']/['end_date'] if region-specific not present
        if not unix_time:
            unix_time = event['start_date'] if timing_type == "start" else event['end_date']

        time_str = "starting" if timing_type == "start" else "ending"
        try:
            await channel.send(
                f"{role_mention}, the **{event['category']}** **{event['title']}** is {time_str} <t:{unix_time}:R>!"
            )
            send_log(event['server_id'], f"Notification sent to channel {channel_id} for event {event['title']} ({profile} {region})")
        except Exception as e:
            send_log(event['server_id'], f"Failed to send notification for {profile} {region}: {e}")
    else:
        # --- Non-HYV games: mention the profile role as before ---
        emoji = PROFILE_EMOJIS.get(profile)
        role_mention = ""
        if emoji:
            c.execute("SELECT role_id FROM role_reactions WHERE server_id=? AND emoji=?", (event['server_id'], emoji))
            role_row = c.fetchone()
            if role_row:
                role = guild.get_role(int(role_row[0]))
                if role:
                    role_mention = role.mention
                    send_log(event['server_id'], f"Found role for profile {profile}: {role_mention}")
                else:
                    send_log(event['server_id'], f"Role ID {role_row[0]} not found in guild for profile {profile}")
            else:
                send_log(event['server_id'], f"No role_id found for emoji {emoji} (profile {profile})")
        else:
            send_log(event['server_id'], f"No emoji found for profile {profile}")

        unix_time = event['start_date'] if timing_type == "start" else event['end_date']
        time_str = "starting" if timing_type == "start" else "ending"
        try:
            await channel.send(
                f"{role_mention}, the **{event['category']}** event **{event['title']}** is {time_str} <t:{unix_time}:R>!"
            )
            send_log(event['server_id'], f"Notification sent to channel {channel_id} for event {event['title']}")
        except Exception as e:
            send_log(event['server_id'], f"Failed to send notification: {e}")
    conn.close()

async def load_and_schedule_pending_notifications(bot):
    """
    Batch notification loop: checks for due notifications and sends them immediately.
    Should be called in a background loop every 30-60 seconds.
    """
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    # Get all notifications due in the past or next 60 seconds, and not sent
    c.execute("""
        SELECT id, server_id, category, profile, title, timing_type, notify_unix, event_time_unix, region
        FROM pending_notifications
        WHERE sent=0 AND notify_unix <= ?
    """, (now + 60,))
    rows = c.fetchall()

    for row in rows:
        notif_id, server_id, category, profile, title, timing_type, notify_unix, event_time_unix, region = row
        event = {
            'server_id': server_id,
            'category': category,
            'profile': profile,
            'title': title,
            'start_date': event_time_unix if timing_type == "start" else None,
            'end_date': event_time_unix if timing_type == "end" else None,
            'region': region
        }
        # Mark as sent
        c.execute("UPDATE pending_notifications SET sent=1 WHERE id=?", (notif_id,))
        # Send notification
        await send_notification(event, timing_type)

    conn.commit()
    conn.close()

"""async def send_persistent_notification(bot, notif_id, event, timing_type, delay):
    # Defensive: Don't sleep negative time
    if delay > 0:
        await asyncio.sleep(delay)

    # --- Failsafe: Global rate limit ---
    now = time.time()
    # Remove timestamps older than 10 seconds
    while recent_notification_times and now - recent_notification_times[0] > 10:
        recent_notification_times.popleft()
    if len(recent_notification_times) >= 5:
        # Too many notifications in last 10 seconds, wait a bit
        await asyncio.sleep(5)
    recent_notification_times.append(now)

    # --- Failsafe 2: skip if this notif_id was just sent (in case of weird race) ---
    if notif_id in recently_sent_notifications:
        return
    recently_sent_notifications.add(notif_id)
    # Optionally, clean up old IDs after some time
    if len(recently_sent_notifications) > 1000:
        recently_sent_notifications.clear()

    # Double-check before sending and atomically mark as sent
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Use a single UPDATE statement to mark as sent only if not already sent
    c.execute("UPDATE pending_notifications SET sent=1 WHERE id=? AND sent=0", (notif_id,))
    conn.commit()
    # Check if the row was actually updated (i.e., not already sent)
    if c.rowcount == 0:
        conn.close()
        return  # Already sent or deleted
    conn.close()
    await send_notification(event, timing_type)
    send_log(event['server_id'], f"Marked notification as sent for event: {event['title']}")
    guild = bot.get_guild(int(event['server_id']))
    await update_pending_notifications_embed_for_profile(guild, event['profile'])"""

async def update_all_pending_notifications_embeds(guild):
    """Update all game embeds in the pending notifications channel."""
    # Always show all supported profiles, even if they have no notifications
    profiles = ["AK", "HSR", "ZZZ", "STRI", "WUWA"]
    for profile in profiles:
        await update_pending_notifications_embed_for_profile(guild, profile)

async def update_pending_notifications_embed_for_profile(guild, profile):
    import math
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT channel_id FROM pending_notifications_channel WHERE server_id=? AND profile=?",
              (str(guild.id), profile))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    channel_id = row[0]
    channel = guild.get_channel(int(channel_id))
    if not channel:
        conn.close()
        return

    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    c.execute("""
        SELECT title, category, timing_type, notify_unix, event_time_unix, region
        FROM pending_notifications
        WHERE server_id=? AND profile=? AND notify_unix > ?
        ORDER BY event_time_unix ASC, notify_unix ASC
    """, (str(guild.id), profile, now))
    rows = c.fetchall()

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
            # Group by (event_time_unix, region)
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
                fields.append({
                    "name": f"{title} ({category})",
                    "value": "\n\n".join(value_lines)
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
    c.execute("SELECT message_id FROM pending_notifications_messages WHERE server_id=? AND profile=? ORDER BY message_id ASC",
              (str(guild.id), profile))
    old_msgs = [msg_id for (msg_id,) in c.fetchall()]

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
    c.execute("DELETE FROM pending_notifications_messages WHERE server_id=? AND profile=?", (str(guild.id), profile))
    for msg_id in new_msg_ids:
        c.execute(
            "INSERT INTO pending_notifications_messages (server_id, profile, message_id) VALUES (?, ?, ?)",
            (str(guild.id), profile, msg_id)
        )
    conn.commit()
    conn.close()

async def update_combined_roles(member):
    """Assigns/removes combined roles based on the user's game and region roles."""
    games = ["HSR", "ZZZ"]
    regions = ["NA", "EU", "ASIA"]
    guild = member.guild
    user_roles = [r.name for r in member.roles]

    for game in games:
        has_game = game in user_roles
        for region in regions:
            has_region = region in user_roles
            combined_role = discord.utils.get(guild.roles, name=f"{game} {region}")
            if combined_role:
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
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT role_id FROM role_reactions WHERE server_id=? AND message_id=? AND emoji=?",
              (str(payload.guild_id), str(payload.message_id), str(payload.emoji)))
    row = c.fetchone()
    conn.close()
    if row:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(int(row[0]))
        if role:
            member = guild.get_member(payload.user_id)
            if member:
                await member.add_roles(role, reason="Role reaction add")
                await update_combined_roles(member) # Update combined roles after adding the role
                # Send a confirmation message in the channel
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    try:
                        confirm_msg = await channel.send(f"{member.mention}, Kanami will notify you about `{role.name}` news!")
                        await asyncio.sleep(5)
                        await confirm_msg.delete()
                    except Exception:
                        pass

@bot.event
async def on_raw_reaction_remove(payload):
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT role_id FROM role_reactions WHERE server_id=? AND message_id=? AND emoji=?",
              (str(payload.guild_id), str(payload.message_id), str(payload.emoji)))
    row = c.fetchone()
    conn.close()
    if row:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(int(row[0]))
        if role:
            member = guild.get_member(payload.user_id)
            if member:
                await member.remove_roles(role, reason="Role reaction remove")
                await update_combined_roles(member)
                # Send a confirmation message in the channel
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    try:
                        confirm_msg = await channel.send(f"{member.mention}, Kanami won't notify you about `{role.name}` anymore...")
                        await asyncio.sleep(5)
                        await confirm_msg.delete()
                    except Exception:
                        pass


# Assign a role to a profile for reaction roles
@bot.command()
@commands.has_permissions(manage_roles=True)
async def assign_profile_role(ctx, profile: str, *, role: discord.Role):
    """
    Assigns a Discord role to a profile for reaction roles.
    Usage: Kanami assign_profile_role <profile> @Role
    Example: Kanami assign_profile_role HSR @HonkaiStarRail
    """
    profile = profile.upper()
    if profile not in PROFILE_EMOJIS:
        await ctx.send(f"Profile must be one of: {', '.join(PROFILE_EMOJIS.keys())}")
        return

    emoji = PROFILE_EMOJIS[profile]
    guild = ctx.guild

    # Save to DB (role will be added to the reaction message later)
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO role_reactions (server_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
        (str(guild.id), None, emoji, str(role.id))
    )
    conn.commit()
    conn.close()
    await ctx.send(f"Assigned role {role.mention} to profile `{profile}` with emoji {emoji}.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def assign_region_role(ctx, region: str, *, role: discord.Role):
    """
    Assigns a Discord role to a region for reaction roles.
    Usage: Kanami assign_region_role <region> @Role
    Example: Kanami assign_region_role ASIA @AsiaRole
    """
    region = region.upper()
    if region not in REGION_EMOJIS:
        await ctx.send(f"Region must be one of: {', '.join(REGION_EMOJIS.keys())}")
        return

    emoji = REGION_EMOJIS[region]
    guild = ctx.guild

    # Save to DB (role will be added to the reaction message later)
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO role_reactions (server_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
        (str(guild.id), None, emoji, str(role.id))
    )
    conn.commit()
    conn.close()
    await ctx.send(f"Assigned role {role.mention} to region `{region}` with emoji {emoji}.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def delete_role(ctx, *, role_name: str):
    """Deletes a role with the given name."""
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        await ctx.send(f"Role `{role_name}` does not exist.")
        return

    try:
        await role.delete()
        await ctx.send(f"Role `{role_name}` deleted.")
        # Remove from DB
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        c.execute("DELETE FROM role_reactions WHERE server_id=? AND role_id=?", (str(guild.id), str(role.id)))
        conn.commit()
        conn.close()
    except discord.Forbidden:
        await ctx.send("I don't have permission to delete roles.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def create_role_reaction(ctx):
    """Creates two role reaction messages: one for profiles, one for regions."""
    guild = ctx.guild
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute(
        "SELECT emoji, role_id FROM role_reactions WHERE server_id=? AND role_id IS NOT NULL",
        (str(guild.id),)
    )
    rows = c.fetchall()
    conn.close()

    # Split into profiles and regions
    profile_rows = [row for row in rows if row[0] in PROFILE_EMOJIS.values()]
    region_rows = [row for row in rows if row[0] in REGION_EMOJIS.values()]

    # Profile roles message
    if profile_rows:
        msg1 = await ctx.send("React to this message to get notification roles for each game.")
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        for emoji, role_id in profile_rows:
            await msg1.add_reaction(emoji)
            c.execute("UPDATE role_reactions SET message_id=? WHERE server_id=? AND emoji=?",
                      (str(msg1.id), str(guild.id), emoji))
        conn.commit()
        conn.close()
    else:
        await ctx.send("No profiles with assigned roles found. Use the assign_profile_role command first.")

    # Region roles message
    if region_rows:
        msg2 = await ctx.send("React to this message to get your region role. (This only matterss for Hoyoverse Games)")
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        for emoji, role_id in region_rows:
            await msg2.add_reaction(emoji)
            c.execute("UPDATE role_reactions SET message_id=? WHERE server_id=? AND emoji=?",
                      (str(msg2.id), str(guild.id), emoji))
        conn.commit()
        conn.close()
    else:
        await ctx.send("No regions with assigned roles found. Use the assign_profile_role command for regions too.")
    

@bot.command()
@commands.has_permissions(manage_roles=True)
async def update_role_reaction(ctx):
    """Deletes the current role reaction message and creates a new one."""
    guild = ctx.guild
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Get the current message_id (if any)
    c.execute("SELECT DISTINCT message_id FROM role_reactions WHERE server_id=? AND message_id IS NOT NULL", (str(guild.id),))
    row = c.fetchone()
    old_message_id = row[0] if row else None

    # Get all emoji-role pairs
    c.execute("SELECT emoji, role_id FROM role_reactions WHERE server_id=? AND role_id IS NOT NULL", (str(guild.id),))
    rows = c.fetchall()
    conn.close()

    # Delete the old message if it exists
    if old_message_id:
        for channel in guild.text_channels:
            try:
                old_msg = await channel.fetch_message(int(old_message_id))
                if old_msg.author == guild.me:
                    await old_msg.delete()
                    break
            except Exception:
                continue

    if not rows:
        await ctx.send("No roles with emojis found. Use the create_role command first.")
        return

    # Create new role reaction message
    msg = await ctx.send("React to this message to get notification for each game.")
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    for emoji, role_id in rows:
        await msg.add_reaction(emoji)
        c.execute("UPDATE role_reactions SET message_id=? WHERE server_id=? AND emoji=?",
                  (str(msg.id), str(guild.id), emoji))
    conn.commit()
    conn.close()
    await ctx.send("Role reaction message updated!")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def create_combined_roles(ctx):
    """Creates 6 combined roles for HSR and ZZZ with each region."""
    guild = ctx.guild
    games = ["HSR", "ZZZ"]
    regions = ["NA", "EU", "ASIA"]
    created = []
    for game in games:
        for region in regions:
            role_name = f"{game} {region}"
            if not discord.utils.get(guild.roles, name=role_name):
                role = await guild.create_role(name=role_name)
                created.append(role_name)
    await ctx.send(f"Created roles: {', '.join(created) if created else 'All roles already exist.'}")

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
@commands.has_permissions(manage_channels=True)
async def set_notification_channel(ctx, channel: discord.TextChannel):
    """Sets the notification channel for the server."""
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO notification_channel (server_id, channel_id) VALUES (?, ?)",
              (str(ctx.guild.id), str(channel.id)))
    conn.commit()
    conn.close()
    await ctx.send(f"Notification channel set to {channel.mention}.")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def add_notification_timing(ctx, category: str, timing_type: str, minutes: int):
    """
    Adds a notification timing (in minutes before event) for a category and type (start/end).
    Usage: Kanami add_notification_timing <category> <start|end> <minutes>
    Now supports custom categories!
    """
    server_id = str(ctx.guild.id)

    # Get built-in and custom categories
    built_in = {"Banner", "Event", "Maintenance", "Offer"}
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS custom_categories (server_id TEXT, category TEXT, PRIMARY KEY (server_id, category))")
    c.execute("SELECT category FROM custom_categories WHERE server_id=?", (server_id,))
    custom = {row[0] for row in c.fetchall()}
    conn.close()
    allowed_categories = built_in | custom

    if category not in allowed_categories:
        await ctx.send(f"Category must be one of: {', '.join(allowed_categories)}.")
        return

    timing_type = timing_type.lower()
    if timing_type not in ("start", "end"):
        await ctx.send("timing_type must be 'start' or 'end'.")
        return

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO notification_timings (server_id, category, timing_type, timing_minutes) VALUES (?, ?, ?, ?)",
            (server_id, category, timing_type, minutes)
        )
        conn.commit()
        await ctx.send(f"Added notification timing for `{category}` `{timing_type}`: {minutes} minutes before event.")
    except sqlite3.IntegrityError:
        await ctx.send(f"Notification timing `{category}` `{timing_type}` `{minutes}` min already exists.")
    finally:
        conn.close()
    await update_notification_timing_message(ctx.guild)

@bot.command()
@commands.has_permissions(manage_guild=True)
async def clear_notification_timing(ctx, category: str, timing_type: str):
    """
    Clears all notification timings for a specific category and timing type.
    Usage: Kanami clear_notification_timing <category> <start|end>
    """
    timing_type = timing_type.lower()
    if timing_type not in ("start", "end"):
        await ctx.send("timing_type must be 'start' or 'end'.")
        return
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute(
        "DELETE FROM notification_timings WHERE server_id=? AND category=? AND timing_type=?",
        (str(ctx.guild.id), category, timing_type)
    )
    conn.commit()
    conn.close()
    await ctx.send(f"Cleared all `{timing_type}` notification timings for category `{category}`.")
    await update_notification_timing_message(ctx.guild)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def set_notification_timing_channel(ctx, channel: discord.TextChannel):
    """Sets the channel where notification timings are displayed and updated."""
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO notification_timing_channel (server_id, channel_id) VALUES (?, ?)",
              (str(ctx.guild.id), str(channel.id)))
    conn.commit()
    conn.close()
    await ctx.send(f"Notification timing status channel set to {channel.mention}.")
    await update_notification_timing_message(ctx.guild)

@bot.command()
@commands.has_permissions(administrator=True)
async def clear_pending_notifications(ctx):
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM pending_notifications")
    conn.commit()
    conn.close()
    await ctx.send("Cleared all pending notifications.")
    await update_all_pending_notifications_embeds(ctx.guild)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def set_pending_notifications_channel(ctx, channel: discord.TextChannel):
    """
    Sets the channel where all pending notifications are displayed in per-game embeds.
    """
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_notifications_channel (
            server_id TEXT,
            profile TEXT,
            channel_id TEXT,
            message_id TEXT,
            PRIMARY KEY (server_id, profile)
        )
    """)
    # Remove all old rows for this server
    c.execute("DELETE FROM pending_notifications_channel WHERE server_id=?", (str(ctx.guild.id),))
    # Insert a row for each profile you want to support
    for profile in ["AK", "HSR", "ZZZ","STRI","WUWA"]:
        c.execute(
            "INSERT OR REPLACE INTO pending_notifications_channel (server_id, profile, channel_id, message_id) VALUES (?, ?, ?, NULL)",
            (str(ctx.guild.id), profile, str(channel.id))
        )
    conn.commit()
    conn.close()
    await ctx.send(f"Pending notifications channel set to {channel.mention}.")
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

# In your refresh_pending_notifications command:
@bot.command(name="refresh_pending_notifications")
@commands.has_permissions(administrator=True)
async def refresh_pending_notifications(ctx):
    """Clears all pending notifications and recreates them from current events, including region times for HSR/ZZZ."""
    from database_handler import update_timer_channel
    server_id = str(ctx.guild.id)
    await debug_log(f"Starting refresh_pending_notifications for server {server_id}", bot, important=True)

    # Delete all pending notifications for this server
    try:
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        c.execute("DELETE FROM pending_notifications WHERE server_id=?", (server_id,))
        conn.commit()
        await debug_log("Deleted all pending notifications.", bot)
    except Exception as e:
        await debug_log(f"Error deleting pending notifications: {e}", bot, important=True)
        await ctx.send("Error deleting pending notifications.")
        return

    # Recreate pending notifications from current events
    try:
        c.execute("""
            SELECT title, start_date, end_date, category, profile,
                   asia_start, asia_end, america_start, america_end, europe_start, europe_end
            FROM user_data WHERE server_id=?
        """, (server_id,))
        events = c.fetchall()
        await debug_log(f"Fetched {len(events)} events from user_data.", bot)
    except Exception as e:
        await debug_log(f"Error fetching events: {e}", bot, important=True)
        await ctx.send("Error fetching events.")
        return
    finally:
        conn.close()

    # --- Clear all event messages in timer channels for this server ---
    try:
        conn2 = sqlite3.connect('kanami_data.db')
        c2 = conn2.cursor()
        c2.execute("SELECT timer_channel_id FROM config WHERE server_id=?", (server_id,))
        timer_channels = {row[0] for row in c2.fetchall()}
        c2.execute("SELECT event_id, channel_id, message_id FROM event_messages WHERE server_id=?", (server_id,))
        event_msgs = c2.fetchall()
        await debug_log(f"Found {len(event_msgs)} event messages to check for deletion.", bot)
        for event_id, channel_id, message_id in event_msgs:
            if channel_id in timer_channels:
                guild = ctx.guild
                channel = guild.get_channel(int(channel_id))
                if channel:
                    try:
                        msg = await channel.fetch_message(int(message_id))
                        await msg.delete()
                        await debug_log(f"Deleted message {message_id} in channel {channel_id}.", bot)
                    except Exception as e:
                        await debug_log(f"Failed to delete message {message_id} in channel {channel_id}: {e}", bot)
                # Remove from DB
                c2c = sqlite3.connect('kanami_data.db')
                c2c_cur = c2c.cursor()
                c2c_cur.execute("DELETE FROM event_messages WHERE event_id=? AND channel_id=?", (event_id, channel_id))
                c2c.commit()
                c2c.close()
        conn2.commit()
        conn2.close()
    except Exception as e:
        await debug_log(f"Error clearing event messages: {e}", bot, important=True)

    recreated = 0
    for title, start_unix, end_unix, category, profile, asia_start, asia_end, america_start, america_end, europe_start, europe_end in events:
        profile_upper = profile.upper()
        try:
            if profile_upper in ("HSR", "ZZZ"):
                # Schedule for each region
                region_data = [
                    ("NA", america_start, america_end),
                    ("EU", europe_start, europe_end),
                    ("ASIA", asia_start, asia_end)
                ]
                for region, region_start, region_end in region_data:
                    event = {
                        'server_id': server_id,
                        'category': category,
                        'profile': profile,
                        'title': title,
                        'start_date': str(region_start),
                        'end_date': str(region_end),
                        'region': region
                    }
                    await schedule_notifications_for_event(event)
                    recreated += 1
                    await debug_log(f"Scheduled notification for {title} [{profile_upper}] region {region}.", bot)
            else:
                # Non-HYV games
                event = {
                    'server_id': server_id,
                    'category': category,
                    'profile': profile,
                    'title': title,
                    'start_date': str(start_unix),
                    'end_date': str(end_unix)
                }
                await schedule_notifications_for_event(event)
                recreated += 1
                await debug_log(f"Scheduled notification for {title} [{profile_upper}].", bot)
        except Exception as e:
            await debug_log(f"Error scheduling event {title} [{profile_upper}]: {e}", bot, important=True)

    # --- Re-post timer channel messages for all profiles ---
    try:
        conn3 = sqlite3.connect('kanami_data.db')
        c3 = conn3.cursor()
        c3.execute("SELECT profile FROM config WHERE server_id=?", (server_id,))
        profiles = [row[0] for row in c3.fetchall()]
        conn3.close()
        for profile in profiles:
            await update_timer_channel(ctx.guild, bot, profile=profile)
            await debug_log(f"Updated timer channel for profile {profile}.", bot)
    except Exception as e:
        await debug_log(f"Error updating timer channels: {e}", bot, important=True)

    await ctx.send(f"Cleared all pending notifications and recreated {recreated} from current events.")
    await debug_log(f"Finished refresh_pending_notifications for server {server_id}. Recreated {recreated} events.", bot, important=True)