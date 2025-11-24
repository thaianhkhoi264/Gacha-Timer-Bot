import twitter_handler
import database_handler
import utilities
import notification_handler
import shadowverse_handler
import ml_handler
import hsr_scraper  # Import to register scraper commands
from bot import bot, bot_version, token, handler, logging
from database_handler import init_db
from discord.ui import View, Select
from discord import app_commands
from discord.ext import commands
from tweet_listener import tweet_listener_on_message
from global_config import *

from arknights_module import *
import reminder_module
import control_panel
import uma_module
import api_server  # Import API server

import sys
import aiosqlite
import discord
import signal
import asyncio
import pytz
from datetime import datetime, timedelta
import os

init_db()

# API Server configuration
API_ENABLED = os.getenv('API_ENABLED', 'true').lower() == 'true'
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', '8080'))

# Store API server runner globally
# Store API server runner globally
api_runner = None

# Shutdown message
async def shutdown_message():
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT server_id, announce_channel_id FROM announce_config") as cursor:
            rows = await cursor.fetchall()
    for server_id, channel_id in rows:
        guild = bot.get_guild(int(server_id))
        if guild:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    await channel.send("Gweheh Shindago...")
                except Exception:
                    pass

# Channel assignment view for slash command
from discord.ui import View, Select, Button
from discord import app_commands

class ChannelAssignView(View):
    def __init__(self, profiles, channels):
        super().__init__(timeout=300)
        self.profiles = profiles
        self.channels = channels
        self.assignment_type = None
        self.selected_profile = None
        self.selected_channel = None
        self.required_keywords = None  # NEW
        self.ignored_keywords = None   # NEW
        self.assignments = []
        self.finished = False

        self.type_select = Select(
            placeholder="Select assignment type...",
            options=[
                discord.SelectOption(label="Timer Channel (per profile)", value="timer"),
                discord.SelectOption(label="Announcement Channel", value="announce"),
                discord.SelectOption(label="Notification Channel", value="notification"),
                discord.SelectOption(label="Notification Timing Channel", value="notif_timing"),
                discord.SelectOption(label="Listener Channel (per profile)", value="listener"),  # NEW
            ]
        )
        self.type_select.callback = self.type_callback
        self.add_item(self.type_select)

        self.profile_select = Select(
            placeholder="Select a profile...",
            options=[discord.SelectOption(label=p, value=p) for p in profiles],
            disabled=True
        )
        self.profile_select.callback = self.profile_callback
        self.add_item(self.profile_select)

        self.channel_select = Select(
            placeholder="Select a channel...",
            options=[discord.SelectOption(label=f"#{c.name}", value=str(c.id)) for c in channels]
        )
        self.channel_select.callback = self.channel_callback
        self.add_item(self.channel_select)

        self.confirm_button = Button(label="Confirm", style=discord.ButtonStyle.green)
        self.confirm_button.callback = self.confirm_callback
        self.add_item(self.confirm_button)

        self.finish_button = Button(label="Finish", style=discord.ButtonStyle.red)
        self.finish_button.callback = self.finish_callback
        self.add_item(self.finish_button)

    async def type_callback(self, interaction: discord.Interaction):
        self.assignment_type = self.type_select.values[0]
        self.profile_select.disabled = (self.assignment_type not in ["timer", "listener"])
        await interaction.response.edit_message(
            content=self.get_status_message(),
            view=self
        )

    async def profile_callback(self, interaction: discord.Interaction):
        self.selected_profile = self.profile_select.values[0]
        await interaction.response.edit_message(
            content=self.get_status_message(),
            view=self
        )

    async def channel_callback(self, interaction: discord.Interaction):
        self.selected_channel = int(self.channel_select.values[0])
        await interaction.response.edit_message(
            content=self.get_status_message(),
            view=self
        )

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.assignment_type or not self.selected_channel or (self.assignment_type in ["timer", "listener"] and not self.selected_profile):
            await interaction.response.send_message("Please select all required fields before confirming.", ephemeral=True)
            return

        # If listener, do NOT prompt for keywords anymore
        if self.assignment_type == "listener":
            self.required_keywords = ""
            self.ignored_keywords = ""
            self.assignments.append((
                self.assignment_type,
                self.selected_profile,
                self.selected_channel,
                self.required_keywords,
                self.ignored_keywords
            ))
        else:
            self.assignments.append((
                self.assignment_type,
                self.selected_profile,
                self.selected_channel
            ))

        # Reset selections for next assignment
        self.assignment_type = None
        self.selected_profile = None
        self.selected_channel = None
        self.required_keywords = None
        self.ignored_keywords = None
        self.type_select.placeholder = "Select assignment type..."
        self.profile_select.placeholder = "Select a profile..."
        self.channel_select.placeholder = "Select a channel..."
        self.profile_select.disabled = True
        await interaction.response.edit_message(
            content=self.get_status_message(),
            view=self
        )

    async def finish_callback(self, interaction: discord.Interaction):
        self.finished = True
        self.stop()
        await interaction.response.defer()

    def get_status_message(self):
        msg = "**Assignment Setup:**\n"
        if self.assignments:
            msg += "**Assignments so far:**\n"
            for i, assignment in enumerate(self.assignments, 1):
                atype = assignment[0]
                prof = assignment[1]
                chan = assignment[2]
                if atype == "timer":
                    msg += f"{i}. Timer Channel for **{prof}**: <#{chan}>\n"
                elif atype == "announce":
                    msg += f"{i}. Announcement Channel: <#{chan}>\n"
                elif atype == "notification":
                    msg += f"{i}. Notification Channel: <#{chan}>\n"
                elif atype == "notif_timing":
                    msg += f"{i}. Notification Timing Channel: <#{chan}>\n"
                elif atype == "listener":
                    req = assignment[3] or "None"
                    ign = assignment[4] or "None"
                    msg += f"{i}. Listener Channel for **{prof}**: <#{chan}> (Required: `{req}` | Ignored: `{ign}`)\n"
        msg += "\n**Current Selection:**\n"
        msg += f"• **Type:** {self.assignment_type or 'Not selected'}\n"
        if self.assignment_type in ["timer", "listener"]:
            msg += f"• **Profile:** {self.selected_profile or 'Not selected'}\n"
        msg += f"• **Channel:** <#{self.selected_channel}>" if self.selected_channel else "• **Channel:** Not selected"
        msg += "\n\nClick **Confirm** to add, or **Finish** when done."
        return msg

# Slash command to set channels for various bot functionalities
@bot.tree.command(name="set_channel", description="Assign any bot channel (timer, announce, notification, etc.)")
@app_commands.checks.has_permissions(manage_channels=True)
async def set_channel_slash(interaction: discord.Interaction):
    profiles = ["HSR", "ZZZ", "AK", "STRI", "WUWA", "ALL"]
    channels = [c for c in interaction.guild.text_channels if c.permissions_for(interaction.guild.me).send_messages]
    view = ChannelAssignView(profiles, channels)
    await interaction.response.send_message(
        "Select what you want to assign and to which channel, then click **Confirm** for each, and **Finish** when done:",
        view=view,
        ephemeral=True
    )
    await view.wait()
    if not view.finished or not view.assignments:
        await interaction.followup.send("No assignments made or timed out.", ephemeral=True)
        return

    async with aiosqlite.connect('kanami_data.db') as conn:
        results = []
        for assignment in view.assignments:
            assignment_type = assignment[0]
            selected_profile = assignment[1]
            selected_channel = assignment[2]
            if assignment_type == "timer":
                await conn.execute(
                    "REPLACE INTO config (server_id, profile, timer_channel_id) VALUES (?, ?, ?)",
                    (str(interaction.guild.id), selected_profile, str(selected_channel))
                )
                results.append(f"<#{selected_channel}> set for timer updates for **{selected_profile}**.")
            elif assignment_type == "announce":
                await conn.execute(
                    "REPLACE INTO announce_config (server_id, announce_channel_id) VALUES (?, ?)",
                    (str(interaction.guild.id), str(selected_channel))
                )
                results.append(f"<#{selected_channel}> set as the **announcement channel**.")
            elif assignment_type == "notification":
                await conn.execute(
                    "REPLACE INTO notification_channel (server_id, channel_id) VALUES (?, ?)",
                    (str(interaction.guild.id), str(selected_channel))
                )
                results.append(f"<#{selected_channel}> set as the **notification channel**.")
            elif assignment_type == "notif_timing":
                await conn.execute(
                    "REPLACE INTO notification_timing_channel (server_id, channel_id) VALUES (?, ?)",
                    (str(interaction.guild.id), str(selected_channel))
                )
                results.append(f"<#{selected_channel}> set as the **notification timing channel**.")
            elif assignment_type == "listener":
                required_keywords = assignment[3]
                ignored_keywords = assignment[4]
                await conn.execute('''CREATE TABLE IF NOT EXISTS listener_channels (
                    server_id TEXT,
                    profile TEXT,
                    channel_id TEXT,
                    required_keywords TEXT,
                    ignored_keywords TEXT,
                    PRIMARY KEY (server_id, profile)
                )''')
                await conn.execute(
                    '''REPLACE INTO listener_channels
                    (server_id, profile, channel_id, required_keywords, ignored_keywords)
                    VALUES (?, ?, ?, ?, ?)''',
                    (str(interaction.guild.id), selected_profile, str(selected_channel), required_keywords, ignored_keywords)
                )
                results.append(
                    f"<#{selected_channel}> set as **listener channel** for **{selected_profile}**.\n"
                    f"Required: `{required_keywords or 'None'}` | Ignored: `{ignored_keywords or 'None'}`"
                )
        await conn.commit()
    await interaction.followup.send("\n".join(results), ephemeral=True)

# Daily report task to send a summary of today's notifications
async def send_daily_report():
    await bot.wait_until_ready()
    OWNER_ID = 680653908259110914
    tz = pytz.timezone("Asia/Bangkok")  # GMT+7
    while not bot.is_closed():
        now = datetime.now(tz)
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        today_start = next_run.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        unix_start = int(today_start.timestamp())
        unix_end = int(today_end.timestamp())

        async with aiosqlite.connect('kanami_data.db') as conn:
            async with conn.execute("""
                SELECT category, profile, title, timing_type, notify_unix, event_time_unix, region
                FROM pending_notifications
                WHERE notify_unix >= ? AND notify_unix < ? AND sent=0
                ORDER BY notify_unix ASC
            """, (unix_start, unix_end)) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            report = "No notifications scheduled for today."
        else:
            report = f"**Daily Notification Report for {today_start.strftime('%Y-%m-%d')} (GMT+7):**\n"
            for cat, prof, title, ttype, notify_unix, event_time_unix, region in rows:
                notify_time = datetime.fromtimestamp(notify_unix, tz).strftime('%H:%M')
                event_time = datetime.fromtimestamp(event_time_unix, tz).strftime('%H:%M')
                region_str = f" [{region}]" if region else ""
                report += (
                    f"- [{prof}]{region_str} **{title}** ({cat})\n"
                    f"  • {ttype.capitalize()} at {event_time}, notify at {notify_time}\n"
                )

        try:
            owner = await bot.fetch_user(OWNER_ID)
            await owner.send(report)
        except Exception as e:
            print(f"[Daily Report] Failed to send DM: {e}")

# Task to periodically clean up expired events
async def expired_event_cleanup_task():
    while True:
        now = int(datetime.now().timestamp())
        async with aiosqlite.connect('kanami_data.db') as conn:
            async with conn.execute("SELECT server_id, id, title FROM user_data WHERE end_date != '' AND CAST(end_date AS INTEGER) < ?", (now,)) as cursor:
                expired = await cursor.fetchall()
            for server_id, event_id, title in expired:
                await conn.execute("DELETE FROM user_data WHERE id=?", (event_id,))
                await conn.execute("DELETE FROM pending_notifications WHERE server_id=? AND LOWER(title)=LOWER(?)", (server_id, title))
                async with conn.execute("SELECT channel_id, message_id FROM event_messages WHERE event_id=?", (event_id,)) as msg_cursor:
                    msg_rows = await msg_cursor.fetchall()
                for channel_id, message_id in msg_rows:
                    guild = bot.get_guild(int(server_id))
                    if guild:
                        channel = guild.get_channel(int(channel_id))
                        if channel:
                            try:
                                msg = await channel.fetch_message(int(message_id))
                                await msg.delete()
                            except Exception:
                                pass
                await conn.execute("DELETE FROM event_messages WHERE event_id=?", (event_id,))
            await conn.commit()
            async with conn.execute("SELECT DISTINCT server_id FROM user_data") as cursor:
                server_ids = [row[0] async for row in cursor]
        for server_id in server_ids:
            guild = bot.get_guild(int(server_id))
            if not guild:
                continue
            async with aiosqlite.connect('kanami_data.db') as conn2:
                async with conn2.execute("SELECT profile FROM config WHERE server_id=?", (server_id,)) as cursor:
                    profiles = [row[0] async for row in cursor]
            for profile in profiles:
                await database_handler.update_timer_channel(guild, bot, profile=profile)
        await asyncio.sleep(43200)

# Notification loop function to load and schedule pending notifications
async def notification_loop():
    while True:
        await notification_handler.load_and_schedule_pending_notifications(bot)
        await asyncio.sleep(30)  # Check every 30 seconds

# Get latest git commit message for version info
def get_latest_commit_message():
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        return "No commit info"

@bot.event
async def on_ready():
    global api_runner
    
    print(f'\n{"="*50}')
    print(f'Kanami is ready to go!')
    print(f'Logged in as: {bot.user.name} (ID: {bot.user.id})')
    print(f'Bot version: {bot_version}')
    print(f'Connected to {len(bot.guilds)} guild(s)')
    print(f'{"="*50}\n')

    # Start API server if enabled
    if API_ENABLED:
        try:
            # Set bot instance in api_server to avoid circular import
            api_server.bot_instance = bot
            api_runner = await api_server.start_api_server(host=API_HOST, port=API_PORT)
            print(f'\n{"="*50}')
            print(f'API Server Status: ENABLED')
            print(f'Listening on: http://{API_HOST}:{API_PORT}')
            print(f'{"="*50}\n')
        except Exception as e:
            print(f'\n{"="*50}')
            print(f'API Server Status: FAILED TO START')
            print(f'Error: {e}')
            import traceback
            traceback.print_exc()
            print(f'Bot will continue without API server.')
            print(f'{"="*50}\n')
    else:
        print(f'\n{"="*50}')
        print(f'API Server Status: DISABLED')
        print(f'Set API_ENABLED=true in environment to enable.')
        print(f'{"="*50}\n')

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT server_id, announce_channel_id FROM announce_config") as cursor:
            rows = await cursor.fetchall()
    commit_msg = get_latest_commit_message()
    for server_id, channel_id in rows:
        guild = bot.get_guild(int(server_id))
        if guild:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    await channel.send(
                        f"Kanami is ready to go! (version {bot_version})\n"
                        f"Latest commit: `{commit_msg}`"
                    )
                except Exception:
                    pass

    if not hasattr(bot, "_notif_db_initialized"):
        bot._notif_db_initialized = True
        await notification_handler.init_notification_db()

    # Register persistent views BEFORE ensure_control_panels
    print("[DEBUG] Registering persistent views...")
    for profile in CONTROL_PANEL_CHANNELS:
        bot.add_view(control_panel.AddEventView(profile))
    print("[DEBUG] Persistent views registered.")

    # Create background tasks FIRST (so they start immediately)
    print("[DEBUG] Creating background tasks...")
    asyncio.create_task(reminder_module.daily_reminder_task())
    print("[DEBUG] Reminder task created.")
    asyncio.create_task(notification_loop())
    print("[DEBUG] Notification loop task created.")
    asyncio.create_task(send_daily_report())
    print("[DEBUG] Daily report task created.")
    asyncio.create_task(expired_event_cleanup_task())
    print("[DEBUG] Expired event cleanup task created.")
    asyncio.create_task(hsr_scraper.periodic_hsr_scraping_task())
    print("[DEBUG] HSR periodic scraping task created.")

    # Initialize Uma Musume database BEFORE control panels (control panel needs DB to exist)
    print("[DEBUG] Initializing Uma Musume database...")
    try:
        await uma_module.init_uma_db()
        print("[DEBUG] Uma Musume database initialized.")
    except Exception as e:
        print(f"[ERROR] Uma Musume database initialization failed: {e}")
        import traceback
        traceback.print_exc()

    # Now initialize control panels
    print("[DEBUG] About to call ensure_control_panels...")
    await control_panel.ensure_control_panels()
    print("[DEBUG] ensure_control_panels completed.")
    
    # Cleanup ghost notifications and validate event notifications
    print("[DEBUG] Running notification maintenance...")
    await notification_handler.cleanup_ghost_notifications()
    await notification_handler.validate_event_notifications()
    print("[DEBUG] Notification maintenance completed.")

    # Initialize AK DB and tasks
    print("[DEBUG] Creating init_ak_db task...")
    asyncio.create_task(init_ak_db())
    print("[DEBUG] Loading scheduled AK update tasks...")
    await load_scheduled_ak_update_tasks()
    print("[DEBUG] Running periodic AK cleanup as background task...")
    asyncio.create_task(periodic_ak_cleanup())
    print("[DEBUG] AK initialization completed.")

    print("[DEBUG] Initializing Shadowverse DB...")
    await shadowverse_handler.init_sv_db()
    print("[DEBUG] Shadowverse DB initialized.")
    
    # Initialize Uma Musume background tasks (DB init + initial update + periodic updates)
    print("[DEBUG] Initializing Uma Musume background tasks...")
    try:
        await uma_module.start_uma_background_tasks()
        print("[DEBUG] Uma Musume tasks initialized successfully.")
    except Exception as e:
        print(f"[ERROR] Uma Musume initialization failed: {e}")
        import traceback
        traceback.print_exc()
    
    await ml_handler.check_llm_table()  # Ensure LLM table exists

@bot.event # Checks for "good girl" and "good boy" in messages
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore messages from the bot itself

    # Forward DMs from non-owner users to the owner
    if isinstance(message.channel, discord.DMChannel) and message.author.id != OWNER_USER_ID:
        try:
            owner = await bot.fetch_user(OWNER_USER_ID)
            embed = discord.Embed(
                title="📬 Forwarded DM",
                description=message.content,
                color=discord.Color.blue(),
                timestamp=message.created_at
            )
            embed.set_author(
                name=f"{message.author.name} ({message.author.id})",
                icon_url=message.author.display_avatar.url
            )
            
            # Add attachments if any
            if message.attachments:
                attachment_urls = "\n".join([att.url for att in message.attachments])
                embed.add_field(name="Attachments", value=attachment_urls, inline=False)
            
            await owner.send(embed=embed)
            print(f"[DM Forward] Forwarded message from {message.author.name} ({message.author.id}) to owner")
        except Exception as e:
            print(f"[DM Forward] Failed to forward DM to owner: {e}")
        return  # Don't process DMs further

    # Call the tweet listener function to handle Twitter/X messages
    # if await tweet_listener_on_message(message):
    #     return

    # Call the shadowverse handler to process Shadowverse messages
    if await shadowverse_handler.shadowverse_on_message(message):
        return
    
    # Call the games' module to process tweet messages
    if await arknights_on_message(message, force=False):
        return
    
    # Check for games' notification refresh
    if await arknights_notification_refresh(message):
        return

    if "good girl" in message.content.lower():
        emoji = "<:KanamiHeart:1374409597628186624>"
        await message.channel.send(emoji)

    if "good boy" in message.content.lower():
        await message.channel.send(f"Go more more jump off a bridge")

    await bot.process_commands(message)  # Ensure other commands still work

@bot.event
async def on_raw_reaction_add(payload):
    """
    Handles reactions on messages
    """
    print(f"[REACTION] Raw reaction added: {payload.emoji} by user_id={payload.user_id}")
    
    # Ignore bot reactions
    if payload.user_id == bot.user.id:
        print(f"[REACTION] Ignoring bot's own reaction")
        return
    
    # Check if it's the ❌ emoji
    emoji_str = str(payload.emoji)
    print(f"[REACTION] Emoji string: '{emoji_str}'")
    
    if emoji_str == "❌":
        print(f"[REACTION] ❌ detected! Channel: {payload.channel_id}, Message: {payload.message_id}")
        
        # Check if this is in a listener channel
        from global_config import LISTENER_CHANNELS
        print(f"[REACTION] Listener channels: {LISTENER_CHANNELS}")
        
        if payload.channel_id not in LISTENER_CHANNELS.values():
            print(f"[REACTION] Channel {payload.channel_id} not in listener channels, ignoring")
            return
        
        print(f"[REACTION] Channel is a listener channel! Fetching message...")
        
        # Fetch the channel and message
        channel = bot.get_channel(payload.channel_id)
        if not channel:
            print(f"[REACTION] Could not find channel {payload.channel_id}")
            return
        
        try:
            message = await channel.fetch_message(payload.message_id)
            print(f"[REACTION] Message fetched! Content preview: {message.content[:100]}")
        except Exception as e:
            print(f"[REACTION] Failed to fetch message: {e}")
            return
        
        print(f"[REACTION] Calling arknights_on_message with force=True")
        # Call arknights_on_message with force=True to re-read
        from arknights_module import arknights_on_message
        result = await arknights_on_message(message, force=True)
        print(f"[REACTION] arknights_on_message completed, result={result}")
    else:
        print(f"[REACTION] Not ❌ emoji (got '{emoji_str}'), ignoring")

@bot.command() # "assign" command to assign the bot to announce its readiness in this channel
@commands.has_permissions(manage_channels=True)
async def assign(ctx):
    async with aiosqlite.connect('kanami_data.db') as conn:
        await conn.execute(
            "REPLACE INTO announce_config (server_id, announce_channel_id) VALUES (?, ?)",
            (str(ctx.guild.id), str(ctx.channel.id))
        )
        await conn.commit()
    await ctx.send("This channel has been assigned for bot announcements.")

@bot.command()  # "checkchannels" command to show all assigned channels
async def check_channels(ctx):
    guild_id = str(ctx.guild.id)
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT announce_channel_id FROM announce_config WHERE server_id=?", (guild_id,)) as cursor:
            announce_row = await cursor.fetchone()
        announce_channel = ctx.guild.get_channel(int(announce_row[0])) if announce_row and announce_row[0] else None

        async with conn.execute("SELECT profile, timer_channel_id FROM config WHERE server_id=?", (guild_id,)) as cursor:
            timer_rows = await cursor.fetchall()

        async with conn.execute("SELECT profile, channel_id, required_keywords, ignored_keywords FROM listener_channels WHERE server_id=?", (guild_id,)) as cursor:
            listener_rows = await cursor.fetchall()

        async with conn.execute("SELECT channel_id FROM notification_channel WHERE server_id=?", (guild_id,)) as cursor:
            notif_row = await cursor.fetchone()
        notif_channel = ctx.guild.get_channel(int(notif_row[0])) if notif_row and notif_row[0] else None

        async with conn.execute("SELECT channel_id FROM notification_timing_channel WHERE server_id=?", (guild_id,)) as cursor:
            notif_timing_row = await cursor.fetchone()
        notif_timing_channel = ctx.guild.get_channel(int(notif_timing_row[0])) if notif_timing_row and notif_timing_row[0] else None

        async with conn.execute("SELECT profile, channel_id FROM pending_notifications_channel WHERE server_id=?", (guild_id,)) as cursor:
            pending_rows = await cursor.fetchall()

    msg = "**Assigned Channels:**\n"
    msg += f"**Announcement Channel:** {announce_channel.mention if announce_channel else 'Not set'}\n"

    # Timer Channels
    if timer_rows:
        msg += "**Timer Channels:**\n"
        for profile, channel_id in timer_rows:
            channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
            msg += f"  • **{profile}**: {channel.mention if channel else 'Not set'}\n"
    else:
        msg += "**Timer Channels:** Not set\n"

    # Listener Channels
    if listener_rows:
        msg += "**Listener Channels:**\n"
        for profile, channel_id, req, ign in listener_rows:
            channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
            msg += (
                f"  • **{profile}**: {channel.mention if channel else 'Not set'}"
                f" (Required: `{req or 'None'}` | Ignored: `{ign or 'None'}`)\n"
            )
    else:
        msg += "**Listener Channels:** Not set\n"

    # Notification Channel
    msg += f"**Notification Channel:** {notif_channel.mention if notif_channel else 'Not set'}\n"

    # Notification Timing Channel
    msg += f"**Notification Timing Channel:** {notif_timing_channel.mention if notif_timing_channel else 'Not set'}\n"

    # Pending Notifications Channel
    if pending_rows:
        msg += "**Pending Notifications Channels:**\n"
        for profile, channel_id in pending_rows:
            channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
            msg += f"  • **{profile}**: {channel.mention if channel else 'Not set'}\n"
    else:
        msg += "**Pending Notifications Channels:** Not set\n"

    await ctx.send(msg)

@bot.command() # "convert" command to convert date and time to Unix timestamp
async def convert(ctx, time: str, date: str = None):
    """
    Command to convert a given date and time into a Unix timestamp.
    If no date is provided, it assumes today's date.
    """
    try:
        # Use today's date if no date is provided
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        unix_timestamp = utilities.convert_to_unix(date, time)
        await ctx.send(f"The Unix timestamp for {date} {time} is: `{unix_timestamp}`")
        await ctx.send(f"Which is <t:{unix_timestamp}:F> your time or <t:{unix_timestamp}:R>")
    except ValueError:
        await ctx.send("Invalid date or time format. Please use `YYYY-MM-DD` for the date and `HH:MM` (24-hour) for the time.")

@bot.command() # "converttz" command to convert date and time to Unix timestamp with timezone
async def converttz(ctx, time: str, date: str = None, timezone_str: str = "UTC"):
    """
    Converts a given date and time in a specified timezone or offset into a Unix timestamp.
    Supports IANA tz names (e.g., 'Asia/Tokyo') and offsets like 'UTC-8', 'GMT+5', etc.
    """
    try:
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        unix_timestamp = utilities.convert_to_unix_tz(date, time, timezone_str)
        await ctx.send(
            f"The Unix timestamp for {date} {time} in `{timezone_str}` is: `{unix_timestamp}`"
        )
        await ctx.send(
            f"Which is <t:{unix_timestamp}:F> your time or <t:{unix_timestamp}:R>"
        )
    except ValueError as e:
        await ctx.send(
            str(e) if "Unknown timezone" in str(e) else
            "Invalid date or time format. Please use `YYYY-MM-DD` for the date and `HH:MM` (24-hour) for the time."
        )
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")
        print(f"[DEBUG] converttz error: {e}")


@bot.command() # "update" command to manually update all timer channels for all profiles
async def update(ctx):
    async with aiosqlite.connect('kanami_data.db') as conn:
        async with conn.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),)) as cursor:
            profiles = [row[0] async for row in cursor]
    if not profiles:
        await ctx.send("No timer channels are set for this server.")
        return
    # Update each profile's timer channel
    for profile in profiles:
        await database_handler.update_timer_channel(ctx.guild, bot, profile=profile)
    await ctx.send(f"Timer channels updated for profiles: {', '.join(profiles)}.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def set_timer_channel(ctx, channel: discord.TextChannel, profile: str = None):
    """
    Set the specified channel as the timer display channel.
    Usage: Kanami set_timer_channel #channel [profile]
    """
    profile = profile.upper() if profile else "ALL"
    valid_profiles = {
        "HSR": "honkaistarrail",
        "ZZZ": "zzz_en",
        "AK": "ArknightsEN",
        "STRI": "Strinova_EN",
        "WUWA": "Wuthering_Waves",
        "ALL": "ALL"
    }

    if profile not in valid_profiles:
        await ctx.send(f"Unknown profile `{profile}`. Valid options: {', '.join(valid_profiles.keys())}")
        return
    async with aiosqlite.connect('kanami_data.db') as conn:
        await conn.execute(
            "REPLACE INTO config (server_id, profile, timer_channel_id) VALUES (?, ?, ?)",
            (str(ctx.guild.id), profile, str(channel.id))
        )
        await conn.commit()
    await ctx.send(f"{channel.mention} is now set for timer updates for **{profile}**.")

def handle_shutdown(signum, frame):
    print(f"[Shutdown] Received signal {signum}, shutting down gracefully...")
    asyncio.create_task(shutdown_and_exit())

async def shutdown_and_exit():
    global api_runner
    
    print("\n[Shutdown] Starting graceful shutdown...")
    
    # Send shutdown messages to Discord
    await shutdown_message()
    
    # Stop Uma Musume background tasks
    print("[Shutdown] Stopping Uma Musume background tasks...")
    try:
        await uma_module.stop_uma_background_tasks()
        print("[Shutdown] Uma Musume tasks stopped.")
    except Exception as e:
        print(f"[Shutdown] Error stopping Uma tasks: {e}")
    
    # Stop API server if running
    if api_runner:
        print("[Shutdown] Stopping API server...")
        try:
            await api_runner.cleanup()
            print("[Shutdown] API server stopped.")
        except Exception as e:
            print(f"[Shutdown] Error stopping API server: {e}")
    
    # Close bot connection
    print("[Shutdown] Closing bot connection...")
    await bot.close()
    
    print("[Shutdown] Shutdown complete.")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

bot.run(token,log_handler=handler, log_level=logging.INFO)