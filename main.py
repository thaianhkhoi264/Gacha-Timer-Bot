import twitter_handler
import database_handler
import utilities
import notification_handler
from bot import bot, bot_version, token, handler, logging
from database_handler import init_db
from discord.ui import View, Select
from discord import app_commands
from discord.ext import commands
from tweet_listener import tweet_listener_on_message

import sqlite3
import discord
import signal
import asyncio

init_db()

# Shutdown message
async def shutdown_message():
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT server_id, announce_channel_id FROM announce_config")
    rows = c.fetchall()
    conn.close()
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

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    results = []
    for assignment in view.assignments:
        assignment_type = assignment[0]
        selected_profile = assignment[1]
        selected_channel = assignment[2]
        if assignment_type == "timer":
            c.execute(
                "REPLACE INTO config (server_id, profile, timer_channel_id) VALUES (?, ?, ?)",
                (str(interaction.guild.id), selected_profile, str(selected_channel))
            )
            results.append(f"<#{selected_channel}> set for timer updates for **{selected_profile}**.")
        elif assignment_type == "announce":
            c.execute(
                "REPLACE INTO announce_config (server_id, announce_channel_id) VALUES (?, ?)",
                (str(interaction.guild.id), str(selected_channel))
            )
            results.append(f"<#{selected_channel}> set as the **announcement channel**.")
        elif assignment_type == "notification":
            c.execute(
                "REPLACE INTO notification_channel (server_id, channel_id) VALUES (?, ?)",
                (str(interaction.guild.id), str(selected_channel))
            )
            results.append(f"<#{selected_channel}> set as the **notification channel**.")
        elif assignment_type == "notif_timing":
            c.execute(
                "REPLACE INTO notification_timing_channel (server_id, channel_id) VALUES (?, ?)",
                (str(interaction.guild.id), str(selected_channel))
            )
            results.append(f"<#{selected_channel}> set as the **notification timing channel**.")
        elif assignment_type == "listener":
            required_keywords = assignment[3]
            ignored_keywords = assignment[4]
            # Create table if not exists
            c.execute('''CREATE TABLE IF NOT EXISTS listener_channels (
                server_id TEXT,
                profile TEXT,
                channel_id TEXT,
                required_keywords TEXT,
                ignored_keywords TEXT,
                PRIMARY KEY (server_id, profile)
            )''')
            c.execute(
                '''REPLACE INTO listener_channels
                   (server_id, profile, channel_id, required_keywords, ignored_keywords)
                   VALUES (?, ?, ?, ?, ?)''',
                (str(interaction.guild.id), selected_profile, str(selected_channel), required_keywords, ignored_keywords)
            )
            results.append(
                f"<#{selected_channel}> set as **listener channel** for **{selected_profile}**.\n"
                f"Required: `{required_keywords or 'None'}` | Ignored: `{ignored_keywords or 'None'}`"
            )
    conn.commit()
    conn.close()
    await interaction.followup.send("\n".join(results), ephemeral=True)


# Notification loop function to load and schedule pending notifications
async def notification_loop():
    while True:
        await notification_handler.load_and_schedule_pending_notifications(bot)
        await asyncio.sleep(30)  # Check every 30 seconds

@bot.event
async def on_ready():
    print(f"Kanami is ready to go!")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

    # Announce in all assigned announcement channels
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("SELECT server_id, announce_channel_id FROM announce_config")
    rows = c.fetchall()
    conn.close()
    for server_id, channel_id in rows:
        guild = bot.get_guild(int(server_id))
        if guild:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    await channel.send(f"Kanami is ready to go! (version {bot_version})")
                except Exception:
                    pass

    # Update all timer channels for all servers
    for guild in bot.guilds:
        conn = sqlite3.connect('kanami_data.db')
        c = conn.cursor()
        c.execute("SELECT profile FROM config WHERE server_id=?", (str(guild.id),))
        profiles = [row[0] for row in c.fetchall()]
        conn.close()
        if not profiles:
            continue  # No timer channels set for this server
        for profile in profiles:
            await notification_handler.update_timer_channel(guild, bot, profile=profile)
    # load and schedule pending notifications
    bot.loop.create_task(notification_loop())

@bot.event # Checks for "good girl" and "good boy" in messages
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore messages from the bot itself

    # Call the tweet listener function to handle Twitter/X messages
    if await tweet_listener_on_message(message):
        return

    if "good girl" in message.content.lower():
        emoji = "<:KanamiHeart:1374409597628186624>"  # Custom emoji with the given ID
        await message.channel.send(emoji)

    if "good boy" in message.content.lower():
        await message.channel.send(f"Go more more jump off a bridge")

    await bot.process_commands(message)  # Ensure other commands still work

@bot.command() # "assign" command to assign the bot to announce its readiness in this channel
@commands.has_permissions(manage_channels=True)
async def assign(ctx):
    """
    Assigns the bot to announce its readiness in this channel on startup.
    Usage: Kanami assign
    """
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute("REPLACE INTO announce_config (server_id, announce_channel_id) VALUES (?, ?)", (str(ctx.guild.id), str(ctx.channel.id)))
    conn.commit()
    conn.close()
    await ctx.send("This channel has been assigned for bot announcements.")

@bot.command()  # "checkchannels" command to show all assigned channels
async def check_channels(ctx):
    """
    Shows all channels set for announcements, timer updates, listeners, and notifications in this server.
    Usage: Kanami check_channels
    """
    guild_id = str(ctx.guild.id)
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()

    # Announcement channel
    c.execute("SELECT announce_channel_id FROM announce_config WHERE server_id=?", (guild_id,))
    announce_row = c.fetchone()
    announce_channel = ctx.guild.get_channel(int(announce_row[0])) if announce_row and announce_row[0] else None

    # Timer channels (per profile)
    c.execute("SELECT profile, timer_channel_id FROM config WHERE server_id=?", (guild_id,))
    timer_rows = c.fetchall()

    # Listener channels (per profile)
    c.execute("SELECT profile, channel_id, required_keywords, ignored_keywords FROM listener_channels WHERE server_id=?", (guild_id,))
    listener_rows = c.fetchall()

    # Notification channel
    c.execute("SELECT channel_id FROM notification_channel WHERE server_id=?", (guild_id,))
    notif_row = c.fetchone()
    notif_channel = ctx.guild.get_channel(int(notif_row[0])) if notif_row and notif_row[0] else None

    # Notification timing channel
    c.execute("SELECT channel_id FROM notification_timing_channel WHERE server_id=?", (guild_id,))
    notif_timing_row = c.fetchone()
    notif_timing_channel = ctx.guild.get_channel(int(notif_timing_row[0])) if notif_timing_row and notif_timing_row[0] else None

    # Pending notifications channel (per profile)
    c.execute("SELECT profile, channel_id FROM pending_notifications_channel WHERE server_id=?", (guild_id,))
    pending_rows = c.fetchall()

    conn.close()

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


@bot.command() # "update" command to manually update all timer channels for all profiles
async def update(ctx):
    """Manually update all timer channels for all profiles in this server."""
    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    # Get all profiles set for this server
    c.execute("SELECT profile FROM config WHERE server_id=?", (str(ctx.guild.id),))
    profiles = [row[0] for row in c.fetchall()]
    conn.close()
    if not profiles:
        await ctx.send("No timer channels are set for this server.")
        return
    # Update each profile's timer channel
    for profile in profiles:
        await notification_handler.update_timer_channel(ctx.guild, bot, profile=profile)
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

    conn = sqlite3.connect('kanami_data.db')
    c = conn.cursor()
    c.execute(
        "REPLACE INTO config (server_id, profile, timer_channel_id) VALUES (?, ?, ?)",
        (str(ctx.guild.id), profile, str(channel.id))
    )
    await ctx.send(f"{channel.mention} is now set for timer updates for **{profile}**.")
    conn.commit()
    conn.close()

def handle_shutdown(*args):
    loop = asyncio.get_event_loop()
    loop.create_task(shutdown_message())
    # Optionally, stop the bot after sending the message:
    # loop.create_task(bot.close())

signal.signal(signal.SIGINT, lambda s, f: handle_shutdown())
signal.signal(signal.SIGTERM, lambda s, f: handle_shutdown())

bot.run(token,log_handler=handler, log_level=logging.DEBUG)