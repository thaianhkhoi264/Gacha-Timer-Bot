import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime
from global_config import CONTROL_PANEL_CHANNELS, GAME_PROFILES, MAIN_SERVER_ID

# --- Profile-specific imports ---
from arknights_module import AK_DB_PATH, add_ak_event, delete_event_message, arknights_update_timers, AK_TIMEZONE
# from hsr_module import HSR_DB_PATH, add_hsr_event, ... (future)
# from zzz_module import ZZZ_DB_PATH, add_zzz_event, ... (future)
from notification_handler import NOTIF_DB_PATH, delete_notifications_for_event, schedule_notifications_for_event

from bot import bot

# --- Profile-specific config ---
PROFILE_CONFIG = {
    "AK": {
        "DB_PATH": AK_DB_PATH,
        "add_event": add_ak_event,
        "delete_event_message": delete_event_message,
        "update_timers": arknights_update_timers,
        "TIMEZONE": AK_TIMEZONE,
    },
    # "HSR": {...},  # Add these as you implement other modules
    # "ZZZ": {...},
}

# --- Utility Functions ---

async def get_events(profile):
    db_path = PROFILE_CONFIG[profile]["DB_PATH"]
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute(
            "SELECT id, title, category, start_date, end_date FROM events WHERE profile=? ORDER BY start_date ASC",
            (profile,)
        ) as cursor:
            return [dict(id=row[0], title=row[1], category=row[2], start=row[3], end=row[4]) async for row in cursor]

async def get_event_by_id(profile, event_id):
    db_path = PROFILE_CONFIG[profile]["DB_PATH"]
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute(
            "SELECT id, title, category, start_date, end_date FROM events WHERE id=?",
            (event_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(id=row[0], title=row[1], category=row[2], start=row[3], end=row[4])
    return None

async def remove_event_by_id(profile, event_id):
    db_path = PROFILE_CONFIG[profile]["DB_PATH"]
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("SELECT title, category, profile FROM events WHERE id=?", (event_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return False
        title, category, profile_code = row
        main_guild = bot.get_guild(MAIN_SERVER_ID)
        from global_config import ONGOING_EVENTS_CHANNELS, UPCOMING_EVENTS_CHANNELS
        await PROFILE_CONFIG[profile]["delete_event_message"](main_guild, ONGOING_EVENTS_CHANNELS[profile], event_id)
        await PROFILE_CONFIG[profile]["delete_event_message"](main_guild, UPCOMING_EVENTS_CHANNELS[profile], event_id)
        await conn.execute("DELETE FROM events WHERE id=?", (event_id,))
        await conn.commit()
    await delete_notifications_for_event(title, category, profile_code)
    await PROFILE_CONFIG[profile]["update_timers"]()
    return True

async def update_event(profile, event_id, title, category, start, end):
    db_path = PROFILE_CONFIG[profile]["DB_PATH"]
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "UPDATE events SET title=?, category=?, start_date=?, end_date=? WHERE id=?",
            (title, category, start, end, event_id)
        )
        await conn.commit()
    event = await get_event_by_id(profile, event_id)
    if event:
        event_for_notification = {
            'category': event['category'],
            'profile': profile,
            'title': event['title'],
            'start_date': str(event['start']),
            'end_date': str(event['end'])
        }
        await delete_notifications_for_event(event['title'], event['category'], profile)
        await schedule_notifications_for_event(event_for_notification)
        await PROFILE_CONFIG[profile]["update_timers"]()

async def get_pending_notifications_for_event(profile, event_id):
    event = await get_event_by_id(profile, event_id)
    if not event:
        return []
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        async with conn.execute(
            "SELECT id, timing_type, notify_unix FROM pending_notifications WHERE title=? AND profile=? ORDER BY notify_unix ASC",
            (event['title'], profile)
        ) as cursor:
            return [dict(id=row[0], timing_type=row[1], notify_unix=row[2]) async for row in cursor]

async def remove_pending_notification(notif_id):
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        await conn.execute("DELETE FROM pending_notifications WHERE id=?", (notif_id,))
        await conn.commit()

async def refresh_pending_notifications_for_event(profile, event_id):
    event = await get_event_by_id(profile, event_id)
    if not event:
        return
    await delete_notifications_for_event(event['title'], event['category'], profile)
    event_for_notification = {
        'category': event['category'],
        'profile': profile,
        'title': event['title'],
        'start_date': str(event['start']),
        'end_date': str(event['end'])
    }
    await schedule_notifications_for_event(event_for_notification)

# --- Discord UI Components ---

class AddEventModal(discord.ui.Modal):
    def __init__(self, profile):
        super().__init__(title=f"Add {profile} Event")
        self.profile = profile
        self.title_input = discord.ui.TextInput(label="Event Title", style=discord.TextStyle.short, required=True)
        self.category_input = discord.ui.TextInput(label="Category (Banner/Event/Maintenance)", style=discord.TextStyle.short, required=True)
        self.start_input = discord.ui.TextInput(label="Start Date (YYYY-MM-DD HH:MM)", style=discord.TextStyle.short, required=True)
        self.end_input = discord.ui.TextInput(label="End Date (YYYY-MM-DD HH:MM)", style=discord.TextStyle.short, required=True)
        self.add_item(self.title_input)
        self.add_item(self.category_input)
        self.add_item(self.start_input)
        self.add_item(self.end_input)

    async def on_submit(self, interaction: discord.Interaction):
        tz = PROFILE_CONFIG[self.profile]["TIMEZONE"]
        start = f"{self.start_input.value} ({tz})"
        end = f"{self.end_input.value} ({tz})"
        event_data = {
            "title": self.title_input.value,
            "category": self.category_input.value,
            "start": start,
            "end": end,
            "image": None
        }
        class DummyCtx:
            author = interaction.user
            guild = interaction.guild
            async def send(self, msg, **kwargs):
                await interaction.followup.send(msg, **kwargs)
        await PROFILE_CONFIG[self.profile]["add_event"](DummyCtx(), event_data)
        await interaction.response.send_message("Event added!", ephemeral=True)
        await update_control_panel_messages(self.profile)

class AddEventView(discord.ui.View):
    def __init__(self, profile):
        super().__init__(timeout=None)
        self.profile = profile

    @discord.ui.button(label="Add Event", style=discord.ButtonStyle.green)
    async def add_event_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        profile = self.profile
        await interaction.response.send_modal(AddEventModal(profile))

class RemoveEventSelect(discord.ui.Select):
    def __init__(self, profile, events):
        options = [discord.SelectOption(label=f"{e['title']} ({e['category']})", value=str(e['id'])) for e in events]
        super().__init__(placeholder="Select event to remove...", min_values=1, max_values=1, options=options, custom_id=f"remove_event_select_{profile}")

class RemoveEventView(discord.ui.View):
    def __init__(self, profile, events):
        super().__init__(timeout=None)
        self.profile = profile
        self.add_item(RemoveEventSelect(profile, events))
        self.add_item(discord.ui.Button(label="Remove Event", style=discord.ButtonStyle.red, custom_id=f"remove_event_submit_{profile}"))

    @discord.ui.button(label="Remove Event", style=discord.ButtonStyle.red)
    async def remove_event_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        select: RemoveEventSelect = self.children[0]
        event_id = select.values[0]
        await remove_event_by_id(self.profile, int(event_id))
        await interaction.response.send_message("Event removed!", ephemeral=True)
        await update_control_panel_messages(self.profile)

class EditEventSelect(discord.ui.Select):
    def __init__(self, profile, events):
        options = [discord.SelectOption(label=f"{e['title']} ({e['category']})", value=str(e['id'])) for e in events]
        super().__init__(placeholder="Select event to edit...", min_values=1, max_values=1, options=options, custom_id=f"edit_event_select_{profile}")

class EditEventModal(discord.ui.Modal):
    def __init__(self, profile, event):
        super().__init__(title=f"Edit {profile} Event")
        self.profile = profile
        self.event_id = event["id"]
        self.title_input = discord.ui.TextInput(label="Event Title", default=event["title"], style=discord.TextStyle.short, required=True)
        self.category_input = discord.ui.TextInput(label="Category", default=event["category"], style=discord.TextStyle.short, required=True)
        self.start_input = discord.ui.TextInput(label="Start Date (YYYY-MM-DD HH:MM)", default="", style=discord.TextStyle.short, required=True)
        self.end_input = discord.ui.TextInput(label="End Date (YYYY-MM-DD HH:MM)", default="", style=discord.TextStyle.short, required=True)
        try:
            self.start_input.default = datetime.utcfromtimestamp(int(event["start"])).strftime("%Y-%m-%d %H:%M")
            self.end_input.default = datetime.utcfromtimestamp(int(event["end"])).strftime("%Y-%m-%d %H:%M")
        except Exception:
            self.start_input.default = str(event["start"])
            self.end_input.default = str(event["end"])
        self.add_item(self.title_input)
        self.add_item(self.category_input)
        self.add_item(self.start_input)
        self.add_item(self.end_input)

    async def on_submit(self, interaction: discord.Interaction):
        tz = PROFILE_CONFIG[self.profile]["TIMEZONE"]
        start = f"{self.start_input.value} ({tz})"
        end = f"{self.end_input.value} ({tz})"
        await update_event(self.profile, self.event_id, self.title_input.value, self.category_input.value, start, end)
        await interaction.response.send_message("Event updated!", ephemeral=True)
        await update_control_panel_messages(self.profile)

class EditEventView(discord.ui.View):
    def __init__(self, profile, events):
        super().__init__(timeout=None)
        self.profile = profile
        self.add_item(EditEventSelect(profile, events))
        self.add_item(discord.ui.Button(label="Edit Event", style=discord.ButtonStyle.blurple, custom_id=f"edit_event_submit_{profile}"))

    @discord.ui.button(label="Edit Event", style=discord.ButtonStyle.blurple)
    async def edit_event_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        select: EditEventSelect = self.children[0]
        event_id = select.values[0]
        event = await get_event_by_id(self.profile, int(event_id))
        if not event:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        await interaction.response.send_modal(EditEventModal(self.profile, event))

class PendingNotifSelect(discord.ui.Select):
    def __init__(self, notifs, profile):
        options = [discord.SelectOption(label=f"{n['timing_type']} <t:{n['notify_unix']}:F>", value=str(n['id'])) for n in notifs]
        super().__init__(placeholder="Select pending notification...", min_values=1, max_values=1, options=options, custom_id=f"pending_notif_select_{profile}")

class PendingNotifView(discord.ui.View):
    def __init__(self, profile, event, notifs):
        super().__init__(timeout=None)
        self.profile = profile
        self.event = event
        self.add_item(PendingNotifSelect(notifs, profile))
        self.add_item(discord.ui.Button(label="Remove Selected", style=discord.ButtonStyle.red, custom_id=f"remove_pending_submit_{profile}"))
        self.add_item(discord.ui.Button(label="Refresh All", style=discord.ButtonStyle.blurple, custom_id=f"refresh_pending_submit_{profile}"))

    @discord.ui.button(label="Remove Selected", style=discord.ButtonStyle.red)
    async def remove_pending_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        select: PendingNotifSelect = self.children[0]
        notif_id = select.values[0]
        await remove_pending_notification(int(notif_id))
        await interaction.response.send_message("Pending notification removed!", ephemeral=True)
        await update_control_panel_messages(self.profile)

    @discord.ui.button(label="Refresh All", style=discord.ButtonStyle.blurple)
    async def refresh_pending_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await refresh_pending_notifications_for_event(self.profile, self.event["id"])
        await interaction.response.send_message("Pending notifications refreshed!", ephemeral=True)
        await update_control_panel_messages(self.profile)

# --- Control Panel Message Management ---

async def update_control_panel_messages(profile):
    # Debug: Show profile and channel ID
    print(f"[ControlPanel] Updating control panel for profile: {profile}")
    channel_id = CONTROL_PANEL_CHANNELS.get(profile)
    print(f"[ControlPanel] Channel ID from config: {channel_id}")
    if not channel_id:
        print(f"[ControlPanel] No channel ID found for profile {profile}.")
        return
    guild = bot.get_guild(MAIN_SERVER_ID)
    print(f"[ControlPanel] Guild object: {guild} (ID: {MAIN_SERVER_ID})")
    channel = guild.get_channel(channel_id) if guild else None
    print(f"[ControlPanel] Channel object: {channel}")
    if not channel:
        print(f"[ControlPanel] Channel {channel_id} not found in guild {MAIN_SERVER_ID}.")
        return

    # Clean up old control panel messages
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            try:
                await msg.delete()
                print(f"[ControlPanel] Deleted old control panel message: {msg.id}")
            except Exception as e:
                print(f"[ControlPanel] Failed to delete message {msg.id}: {e}")

    # Add Event
    print(f"[ControlPanel] Sending Add Event view for profile {profile}...")
    await channel.send("**Add Event**", view=AddEventView(profile))

    # Remove Event
    events = await get_events(profile)
    print(f"[ControlPanel] Found {len(events)} events for profile {profile}.")
    await channel.send("**Remove Event**", view=RemoveEventView(profile, events))

    # Edit Event
    await channel.send("**Edit Event**", view=EditEventView(profile, events))

    # Pending Notifications (one per event)
    for event in events:
        notifs = await get_pending_notifications_for_event(profile, event["id"])
        print(f"[ControlPanel] Event '{event['title']}' has {len(notifs)} pending notifications.")
        if not notifs:
            continue
        await channel.send(f"**Pending Notifications for {event['title']}**", view=PendingNotifView(profile, event, notifs))
    print(f"[ControlPanel] Finished updating control panel for profile {profile}.")

# --- Startup Task ---
async def ensure_control_panels():
    for profile in CONTROL_PANEL_CHANNELS:
        await update_control_panel_messages(profile)
        
@bot.command()
async def test_control_panel(ctx):
    import control_panel
    await control_panel.update_control_panel_messages("AK")
    await ctx.send("Triggered control panel update for AK.")

# --- End of control_panel.py ---