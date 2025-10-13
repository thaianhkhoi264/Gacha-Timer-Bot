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
            "SELECT id, title, category, start_date, end_date, image FROM events WHERE id=?",
            (event_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(id=row[0], title=row[1], category=row[2], start=row[3], end=row[4], image=row[5])
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

async def update_event(profile, event_id, title, category, start, end, image=None):
    db_path = PROFILE_CONFIG[profile]["DB_PATH"]
    async with aiosqlite.connect(db_path) as conn:
        if image is not None:
            await conn.execute(
                "UPDATE events SET title=?, category=?, start_date=?, end_date=?, image=? WHERE id=?",
                (title, category, start, end, image, event_id)
            )
        else:
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
        default_tz = PROFILE_CONFIG[profile]["TIMEZONE"]
        self.title_input = discord.ui.TextInput(
            label="Event Title",
            style=discord.TextStyle.short,
            required=True
        )
        self.category_input = discord.ui.TextInput(
            label="Category (Banner/Event/Maintenance)",
            style=discord.TextStyle.short,
            required=True
        )
        self.start_input = discord.ui.TextInput(
            label=f"Start Date (YYYY-MM-DD HH:MM in {default_tz})",
            style=discord.TextStyle.short,
            required=True,
            placeholder=f"e.g. 2025-10-15 10:00 ({default_tz})"
        )
        self.end_input = discord.ui.TextInput(
            label=f"End Date (YYYY-MM-DD HH:MM in {default_tz})",
            style=discord.TextStyle.short,
            required=True,
            placeholder=f"e.g. 2025-10-29 03:59 ({default_tz})"
        )
        self.image_input = discord.ui.TextInput(
            label="Image URL (optional)",
            style=discord.TextStyle.short,
            required=False,
            placeholder="https://example.com/image.png"
        )
        self.add_item(self.title_input)
        self.add_item(self.category_input)
        self.add_item(self.start_input)
        self.add_item(self.end_input)
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Parse dates with profile's default timezone
        import dateparser
        tz = PROFILE_CONFIG[self.profile]["TIMEZONE"]
        
        # Add timezone to date strings
        start_with_tz = f"{self.start_input.value} ({tz})"
        end_with_tz = f"{self.end_input.value} ({tz})"
        
        # Parse to UNIX timestamps
        start_dt = dateparser.parse(start_with_tz, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        end_dt = dateparser.parse(end_with_tz, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        
        if not start_dt or not end_dt:
            await interaction.response.send_message("Failed to parse dates. Please use format: YYYY-MM-DD HH:MM", ephemeral=True)
            return
        
        start_unix = int(start_dt.timestamp())
        end_unix = int(end_dt.timestamp())
        
        # Get image URL (if provided)
        image_url = self.image_input.value.strip() if self.image_input.value else None
        
        event_data = {
            "title": self.title_input.value,
            "category": self.category_input.value,
            "start": str(start_unix),
            "end": str(end_unix),
            "image": image_url
        }
        
        class DummyCtx:
            author = interaction.user
            guild = interaction.guild
            async def send(self, msg, **kwargs):
                await interaction.followup.send(msg, **kwargs)
        
        await interaction.response.defer(ephemeral=True)
        await PROFILE_CONFIG[self.profile]["add_event"](DummyCtx(), event_data)
        await interaction.followup.send("Event added successfully!", ephemeral=True)
        await update_control_panel_messages(self.profile)

class AddEventView(discord.ui.View):
    def __init__(self, profile):
        super().__init__(timeout=None)
        self.profile = profile

    @discord.ui.button(label="Add Event", style=discord.ButtonStyle.green, custom_id="add_event_submit")
    async def add_event_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddEventModal(self.profile))
        
class RemoveEventSelect(discord.ui.Select):
    def __init__(self, profile, events):
        options = [discord.SelectOption(label=f"{e['title']} ({e['category']})", value=str(e['id'])) for e in events]
        super().__init__(placeholder="Select event to remove...", min_values=1, max_values=1, options=options, custom_id=f"remove_event_select_{profile}")
        self.profile = profile

    async def callback(self, interaction: discord.Interaction):
        event_id = self.values[0]
        # Create a new view with a confirmation button
        confirm_view = RemoveEventConfirmView(self.profile, int(event_id))
        await interaction.response.edit_message(content=f"Selected event ID: {event_id}. Click the button below to confirm removal.", view=confirm_view)

class RemoveEventConfirmView(discord.ui.View):
    def __init__(self, profile, event_id):
        super().__init__(timeout=None)
        self.profile = profile
        self.event_id = event_id

    @discord.ui.button(label="Confirm Remove", style=discord.ButtonStyle.red, custom_id="remove_event_confirm")
    async def remove_event_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await remove_event_by_id(self.profile, self.event_id)
        await interaction.response.send_message("Event removed!", ephemeral=True)
        await update_control_panel_messages(self.profile)

class RemoveEventView(discord.ui.View):
    def __init__(self, profile, events):
        super().__init__(timeout=None)
        self.profile = profile
        self.add_item(RemoveEventSelect(profile, events))

class EditEventSelect(discord.ui.Select):
    def __init__(self, profile, events):
        options = [discord.SelectOption(label=f"{e['title']} ({e['category']})", value=str(e['id'])) for e in events]
        super().__init__(placeholder="Select event to edit...", min_values=1, max_values=1, options=options, custom_id=f"edit_event_select_{profile}")
        self.profile = profile
        self.events = {e['id']: e for e in events}

    async def callback(self, interaction: discord.Interaction):
        event_id = int(self.values[0])
        event = self.events.get(event_id)
        if not event:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        await interaction.response.send_modal(EditEventModal(self.profile, event))

class EditEventModal(discord.ui.Modal):
    def __init__(self, profile, event):
        super().__init__(title=f"Edit {profile} Event")
        self.profile = profile
        self.event_id = event["id"]
        tz = PROFILE_CONFIG[profile]["TIMEZONE"]
        
        self.title_input = discord.ui.TextInput(
            label="Event Title", 
            default=event["title"], 
            style=discord.TextStyle.short, 
            required=True
        )
        self.category_input = discord.ui.TextInput(
            label="Category", 
            default=event["category"], 
            style=discord.TextStyle.short, 
            required=True
        )
        self.start_input = discord.ui.TextInput(
            label=f"Start Date (YYYY-MM-DD HH:MM in {tz})", 
            default="", 
            style=discord.TextStyle.short, 
            required=True
        )
        self.end_input = discord.ui.TextInput(
            label=f"End Date (YYYY-MM-DD HH:MM in {tz})", 
            default="", 
            style=discord.TextStyle.short, 
            required=True
        )
        self.image_input = discord.ui.TextInput(
            label="Image URL (optional)",
            default=event.get("image", "") or "",
            style=discord.TextStyle.short,
            required=False,
            placeholder="https://example.com/image.png"
        )
        
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
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        import dateparser
        tz = PROFILE_CONFIG[self.profile]["TIMEZONE"]
        
        # Add timezone to date strings
        start_with_tz = f"{self.start_input.value} ({tz})"
        end_with_tz = f"{self.end_input.value} ({tz})"
        
        # Parse to UNIX timestamps
        start_dt = dateparser.parse(start_with_tz, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        end_dt = dateparser.parse(end_with_tz, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        
        if not start_dt or not end_dt:
            await interaction.response.send_message("Failed to parse dates. Please use format: YYYY-MM-DD HH:MM", ephemeral=True)
            return
        
        start_unix = int(start_dt.timestamp())
        end_unix = int(end_dt.timestamp())
        
        # Get image URL (if provided)
        image_url = self.image_input.value.strip() if self.image_input.value else None
        
        # Update event with image
        await update_event(
            self.profile, 
            self.event_id, 
            self.title_input.value, 
            self.category_input.value, 
            str(start_unix), 
            str(end_unix),
            image_url
        )
        await interaction.response.send_message("Event updated!", ephemeral=True)
        await update_control_panel_messages(self.profile)

class EditEventView(discord.ui.View):
    def __init__(self, profile, events):
        super().__init__(timeout=None)
        self.profile = profile
        self.add_item(EditEventSelect(profile, events))

class PendingNotifSelect(discord.ui.Select):
    def __init__(self, notifs, profile, event):
        options = [discord.SelectOption(label=f"{n['timing_type']} <t:{n['notify_unix']}:F>", value=str(n['id'])) for n in notifs]
        super().__init__(placeholder="Select pending notification...", min_values=1, max_values=1, options=options, custom_id=f"pending_notif_select_{profile}")
        self.profile = profile
        self.event = event

    async def callback(self, interaction: discord.Interaction):
        notif_id = self.values[0]
        # Show action buttons after selection
        action_view = PendingNotifActionView(self.profile, self.event, int(notif_id))
        await interaction.response.edit_message(content=f"Selected notification ID: {notif_id}. Choose an action below.", view=action_view)

class PendingNotifActionView(discord.ui.View):
    def __init__(self, profile, event, notif_id):
        super().__init__(timeout=None)
        self.profile = profile
        self.event = event
        self.notif_id = notif_id

    @discord.ui.button(label="Remove Selected", style=discord.ButtonStyle.red, custom_id="remove_pending_confirm")
    async def remove_pending_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await remove_pending_notification(self.notif_id)
        await interaction.response.send_message("Pending notification removed!", ephemeral=True)
        await update_control_panel_messages(self.profile)

    @discord.ui.button(label="Refresh All", style=discord.ButtonStyle.blurple, custom_id="refresh_pending_confirm")
    async def refresh_pending_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await refresh_pending_notifications_for_event(self.profile, self.event["id"])
        await interaction.response.send_message("Pending notifications refreshed!", ephemeral=True)
        await update_control_panel_messages(self.profile)

class PendingNotifView(discord.ui.View):
    def __init__(self, profile, event, notifs):
        super().__init__(timeout=None)
        self.profile = profile
        self.event = event
        self.add_item(PendingNotifSelect(notifs, profile, event))

# --- Control Panel Message Management ---

# Store control panel message IDs: {profile: {"add": msg_id, "remove": msg_id, "edit": msg_id, "notifs": {event_id: msg_id}}}
CONTROL_PANEL_MESSAGE_IDS = {}

async def update_control_panel_messages(profile):
    """
    Updates control panel messages by editing existing ones instead of recreating.
    This avoids Discord rate limits.
    """
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

    # Initialize message ID storage for this profile
    if profile not in CONTROL_PANEL_MESSAGE_IDS:
        CONTROL_PANEL_MESSAGE_IDS[profile] = {"add": None, "remove": None, "edit": None, "notifs": {}}

    events = await get_events(profile)
    print(f"[ControlPanel] Found {len(events)} events for profile {profile}.")

    # --- Add Event Panel ---
    try:
        add_view = AddEventView(profile)
        if CONTROL_PANEL_MESSAGE_IDS[profile]["add"]:
            try:
                msg = await channel.fetch_message(CONTROL_PANEL_MESSAGE_IDS[profile]["add"])
                await msg.edit(content="**Add Event**", view=add_view)
                print(f"[ControlPanel] Edited Add Event message: {msg.id}")
            except discord.NotFound:
                # Message was deleted, create a new one
                msg = await channel.send("**Add Event**", view=add_view)
                CONTROL_PANEL_MESSAGE_IDS[profile]["add"] = msg.id
                print(f"[ControlPanel] Sent new Add Event message: {msg.id}")
        else:
            msg = await channel.send("**Add Event**", view=add_view)
            CONTROL_PANEL_MESSAGE_IDS[profile]["add"] = msg.id
            print(f"[ControlPanel] Sent Add Event message: {msg.id}")
    except Exception as e:
        print(f"[ControlPanel] Error updating Add Event panel: {e}")

    # --- Remove Event Panel ---
    try:
        remove_view = RemoveEventView(profile, events)
        if CONTROL_PANEL_MESSAGE_IDS[profile]["remove"]:
            try:
                msg = await channel.fetch_message(CONTROL_PANEL_MESSAGE_IDS[profile]["remove"])
                await msg.edit(content="**Remove Event**", view=remove_view)
                print(f"[ControlPanel] Edited Remove Event message: {msg.id}")
            except discord.NotFound:
                msg = await channel.send("**Remove Event**", view=remove_view)
                CONTROL_PANEL_MESSAGE_IDS[profile]["remove"] = msg.id
                print(f"[ControlPanel] Sent new Remove Event message: {msg.id}")
        else:
            msg = await channel.send("**Remove Event**", view=remove_view)
            CONTROL_PANEL_MESSAGE_IDS[profile]["remove"] = msg.id
            print(f"[ControlPanel] Sent Remove Event message: {msg.id}")
    except Exception as e:
        print(f"[ControlPanel] Error updating Remove Event panel: {e}")

    # --- Edit Event Panel ---
    try:
        edit_view = EditEventView(profile, events)
        if CONTROL_PANEL_MESSAGE_IDS[profile]["edit"]:
            try:
                msg = await channel.fetch_message(CONTROL_PANEL_MESSAGE_IDS[profile]["edit"])
                await msg.edit(content="**Edit Event**", view=edit_view)
                print(f"[ControlPanel] Edited Edit Event message: {msg.id}")
            except discord.NotFound:
                msg = await channel.send("**Edit Event**", view=edit_view)
                CONTROL_PANEL_MESSAGE_IDS[profile]["edit"] = msg.id
                print(f"[ControlPanel] Sent new Edit Event message: {msg.id}")
        else:
            msg = await channel.send("**Edit Event**", view=edit_view)
            CONTROL_PANEL_MESSAGE_IDS[profile]["edit"] = msg.id
            print(f"[ControlPanel] Sent Edit Event message: {msg.id}")
    except Exception as e:
        print(f"[ControlPanel] Error updating Edit Event panel: {e}")

    # --- Pending Notifications (one per event) ---
    current_event_ids = {event["id"] for event in events}
    stored_event_ids = set(CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"].keys())
    
    # Remove messages for events that no longer exist
    for event_id in stored_event_ids - current_event_ids:
        try:
            msg_id = CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event_id]
            msg = await channel.fetch_message(msg_id)
            await msg.delete()
            print(f"[ControlPanel] Deleted notification panel for removed event {event_id}")
        except Exception as e:
            print(f"[ControlPanel] Error deleting notification panel for event {event_id}: {e}")
        finally:
            del CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event_id]
    
    # Update or create notification panels for current events
    for event in events:
        notifs = await get_pending_notifications_for_event(profile, event["id"])
        print(f"[ControlPanel] Event '{event['title']}' has {len(notifs)} pending notifications.")
        if not notifs:
            # If there are no notifications, delete the panel if it exists
            if event["id"] in CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"]:
                try:
                    msg_id = CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event["id"]]
                    msg = await channel.fetch_message(msg_id)
                    await msg.delete()
                    print(f"[ControlPanel] Deleted empty notification panel for event {event['id']}")
                except Exception as e:
                    print(f"[ControlPanel] Error deleting empty notification panel: {e}")
                finally:
                    del CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event["id"]]
            continue
        
        try:
            notif_view = PendingNotifView(profile, event, notifs)
            content = f"**Pending Notifications for {event['title']}**"
            
            if event["id"] in CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"]:
                try:
                    msg_id = CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event["id"]]
                    msg = await channel.fetch_message(msg_id)
                    await msg.edit(content=content, view=notif_view)
                    print(f"[ControlPanel] Edited notification panel for event '{event['title']}'")
                except discord.NotFound:
                    msg = await channel.send(content, view=notif_view)
                    CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event["id"]] = msg.id
                    print(f"[ControlPanel] Sent new notification panel for event '{event['title']}'")
            else:
                msg = await channel.send(content, view=notif_view)
                CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event["id"]] = msg.id
                print(f"[ControlPanel] Sent notification panel for event '{event['title']}'")
        except Exception as e:
            print(f"[ControlPanel] Error updating notification panel for event '{event['title']}': {e}")
    
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