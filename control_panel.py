import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime
import pytz
import asyncio
from global_config import CONTROL_PANEL_CHANNELS, GAME_PROFILES, MAIN_SERVER_ID

# --- Rate Limiting for Control Panel Updates ---
_last_update_time = {}  # Track last update time per profile
_update_cooldown = 10  # Minimum seconds between updates
_pending_updates = {}  # Track pending update tasks

# --- Profile-specific imports ---
from arknights_module import AK_DB_PATH, add_ak_event, delete_event_message, arknights_update_timers, AK_TIMEZONE
from uma_module import UMA_DB_PATH, add_uma_event, delete_event_message as uma_delete_event_message, uma_update_timers
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
    "UMA": {
        "DB_PATH": UMA_DB_PATH,
        "add_event": add_uma_event,
        "delete_event_message": uma_delete_event_message,
        "update_timers": uma_update_timers,
        "TIMEZONE": "UTC",  # Uma Musume uses UTC
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
        self.start_input = discord.ui.TextInput(
            label=f"Start Date (YYYY-MM-DD HH:MM)",
            style=discord.TextStyle.short,
            required=True,
            placeholder=f"e.g. 2025-10-15 10:00"
        )
        self.end_input = discord.ui.TextInput(
            label=f"End Date (YYYY-MM-DD HH:MM)",
            style=discord.TextStyle.short,
            required=True,
            placeholder=f"e.g. 2025-10-29 03:59"
        )
        self.image_input = discord.ui.TextInput(
            label="Image URL (optional)",
            style=discord.TextStyle.short,
            required=False,
            placeholder="https://example.com/image.png"
        )
        self.add_item(self.title_input)
        self.add_item(self.start_input)
        self.add_item(self.end_input)
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Get image URL (if provided)
        image_url = self.image_input.value.strip() if self.image_input.value else None
        
        # Show the options select view (category and timezone)
        options_view = EventOptionsSelectView(
            self.profile,
            self.title_input.value,
            self.start_input.value,
            self.end_input.value,
            image_url
        )
        await interaction.response.send_message(
            f"**Category:** Event (default)\n**Timezone:** {PROFILE_CONFIG[self.profile]['TIMEZONE']} (default)\n\nSelect category and timezone, then click **Confirm**.",
            view=options_view,
            ephemeral=True
        )

class AddEventView(discord.ui.View):
    def __init__(self, profile):
        super().__init__(timeout=None)
        self.profile = profile

    @discord.ui.button(label="Add Event", style=discord.ButtonStyle.green, custom_id="add_event_submit")
    async def add_event_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddEventModal(self.profile))

# --- Event Options Select View (Category & Timezone) ---

class CategorySelect(discord.ui.Select):
    def __init__(self, parent_view, current_category=None):
        options = [
            discord.SelectOption(
                label="Banner",
                value="Banner",
                description="Limited-time character or item banner",
                default=(current_category == "Banner")
            ),
            discord.SelectOption(
                label="Event",
                value="Event",
                description="In-game event with rewards or story",
                default=(current_category == "Event")
            ),
            discord.SelectOption(
                label="Maintenance",
                value="Maintenance",
                description="Scheduled server maintenance",
                default=(current_category == "Maintenance")
            ),
        ]
        super().__init__(
            placeholder="Select category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="category_select"
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_category = self.values[0]
        # Update the message to show selection feedback
        await interaction.response.edit_message(
            content=f"**Category:** {self.values[0]}\n**Timezone:** {self.parent_view.selected_timezone}\n\nClick **Confirm** when ready.",
            view=self.parent_view
        )

class TimezoneSelect(discord.ui.Select):
    def __init__(self, parent_view):
        options = [
            discord.SelectOption(label="UTC (GMT+0)", value="UTC", description="Coordinated Universal Time"),
            discord.SelectOption(label="UTC-7 (PDT)", value="UTC-7", description="Pacific Daylight Time"),
            discord.SelectOption(label="America/New_York (EDT)", value="America/New_York", description="Eastern Time"),
            discord.SelectOption(label="Europe/Berlin (CEST)", value="Europe/Berlin", description="Central European Time"),
            discord.SelectOption(label="Asia/Shanghai (CST)", value="Asia/Shanghai", description="China Standard Time"),
            discord.SelectOption(label="Asia/Tokyo (JST)", value="Asia/Tokyo", description="Japan Standard Time"),
        ]
        super().__init__(
            placeholder="Select timezone...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="timezone_select"
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_timezone = self.values[0]
        # Update the message to show selection feedback
        await interaction.response.edit_message(
            content=f"**Category:** {self.parent_view.selected_category}\n**Timezone:** {self.values[0]}\n\nClick **Confirm** when ready.",
            view=self.parent_view
        )

class EventOptionsSelectView(discord.ui.View):
    def __init__(self, profile, title, start, end, image, is_edit=False, event_id=None, current_category=None):
        super().__init__(timeout=180)
        self.profile = profile
        self.title = title
        self.start = start
        self.end = end
        self.image = image
        self.is_edit = is_edit
        self.event_id = event_id
        self.selected_category = current_category or "Event"
        self.selected_timezone = PROFILE_CONFIG[profile]["TIMEZONE"]
        
        self.add_item(CategorySelect(self, current_category))
        self.add_item(TimezoneSelect(self))
        self.add_item(ConfirmEventButton(self))

class ConfirmEventButton(discord.ui.Button):
    def __init__(self, parent_view):
        super().__init__(
            label="Confirm",
            style=discord.ButtonStyle.green,
            custom_id="confirm_event_button"
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        import dateparser
        
        # Add timezone to date strings
        start_with_tz = f"{self.parent_view.start} ({self.parent_view.selected_timezone})"
        end_with_tz = f"{self.parent_view.end} ({self.parent_view.selected_timezone})"
        
        # Parse to UNIX timestamps
        start_dt = dateparser.parse(start_with_tz, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        end_dt = dateparser.parse(end_with_tz, settings={'RETURN_AS_TIMEZONE_AWARE': True})
        
        if not start_dt or not end_dt:
            await interaction.response.send_message(
                "Failed to parse dates. Please use format: YYYY-MM-DD HH:MM",
                ephemeral=True
            )
            return
        
        start_unix = int(start_dt.timestamp())
        end_unix = int(end_dt.timestamp())
        
        if self.parent_view.is_edit:
            # Update existing event
            await update_event(
                self.parent_view.profile,
                self.parent_view.event_id,
                self.parent_view.title,
                self.parent_view.selected_category,
                str(start_unix),
                str(end_unix),
                self.parent_view.image
            )
            await interaction.response.send_message("Event updated successfully!", ephemeral=True)
        else:
            # Add new event
            event_data = {
                "title": self.parent_view.title,
                "category": self.parent_view.selected_category,
                "start": str(start_unix),
                "end": str(end_unix),
                "image": self.parent_view.image
            }
            
            class DummyCtx:
                author = interaction.user
                guild = interaction.guild
                async def send(self, msg, **kwargs):
                    await interaction.followup.send(msg, **kwargs)
            
            await interaction.response.defer(ephemeral=True)
            await PROFILE_CONFIG[self.parent_view.profile]["add_event"](DummyCtx(), event_data)
            await interaction.followup.send("Event added successfully!", ephemeral=True)
        
        await update_control_panel_messages(self.parent_view.profile)

# --- Remove Event Components ---

class RemoveEventSelect(discord.ui.Select):
    def __init__(self, profile, events):
        # Truncate long titles to fit Discord's 100 character limit for select option labels
        options = []
        for e in events:
            title = e['title']
            category = e['category']
            # Discord limit is 100 chars for label, leave room for category
            max_title_len = 90 - len(category)
            if len(title) > max_title_len:
                title = title[:max_title_len-3] + "..."
            options.append(discord.SelectOption(label=f"{title} ({category})", value=str(e['id'])))
        super().__init__(placeholder="Select event to remove...", min_values=1, max_values=1, options=options, custom_id=f"remove_event_select_{profile}")
        self.profile = profile
        self.events = {e['id']: e for e in events}

    async def callback(self, interaction: discord.Interaction):
        event_id = int(self.values[0])
        event = self.events.get(event_id)
        if not event:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        # Create a new view with a confirmation button, passing event name
        confirm_view = RemoveEventConfirmView(self.profile, event_id, event['title'])
        await interaction.response.edit_message(
            content=f"Are you sure you want to remove **{event['title']}**? Click the button below to confirm.",
            view=confirm_view
        )

class RemoveEventConfirmView(discord.ui.View):
    def __init__(self, profile, event_id, event_title):
        super().__init__(timeout=None)
        self.profile = profile
        self.event_id = event_id
        self.event_title = event_title

    @discord.ui.button(label="Confirm Remove", style=discord.ButtonStyle.red, custom_id="remove_event_confirm")
    async def remove_event_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await remove_event_by_id(self.profile, self.event_id)
        await interaction.response.send_message(f"Event **{self.event_title}** removed successfully!", ephemeral=True)
        await update_control_panel_messages(self.profile)

class RemoveEventView(discord.ui.View):
    def __init__(self, profile, events):
        super().__init__(timeout=None)
        self.profile = profile
        self.add_item(RemoveEventSelect(profile, events))

class EditEventSelect(discord.ui.Select):
    def __init__(self, profile, events):
        # Truncate long titles to fit Discord's 100 character limit for select option labels
        options = []
        for e in events:
            title = e['title']
            category = e['category']
            # Discord limit is 100 chars for label, leave room for category
            max_title_len = 90 - len(category)
            if len(title) > max_title_len:
                title = title[:max_title_len-3] + "..."
            options.append(discord.SelectOption(label=f"{title} ({category})", value=str(e['id'])))
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
        self.current_category = event["category"]
        tz = PROFILE_CONFIG[profile]["TIMEZONE"]
        
        self.title_input = discord.ui.TextInput(
            label="Event Title", 
            default=event["title"], 
            style=discord.TextStyle.short, 
            required=True
        )
        self.start_input = discord.ui.TextInput(
            label=f"Start Date (YYYY-MM-DD HH:MM)", 
            default="", 
            style=discord.TextStyle.short, 
            required=True
        )
        self.end_input = discord.ui.TextInput(
            label=f"End Date (YYYY-MM-DD HH:MM)", 
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
        self.add_item(self.start_input)
        self.add_item(self.end_input)
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Get image URL (if provided)
        image_url = self.image_input.value.strip() if self.image_input.value else None
        
        # Show the options select view (category and timezone)
        options_view = EventOptionsSelectView(
            self.profile,
            self.title_input.value,
            self.start_input.value,
            self.end_input.value,
            image_url,
            is_edit=True,
            event_id=self.event_id,
            current_category=self.current_category
        )
        await interaction.response.send_message(
            f"**Category:** {self.current_category}\n**Timezone:** {PROFILE_CONFIG[self.profile]['TIMEZONE']} (default)\n\nSelect category and timezone, then click **Confirm**.",
            view=options_view,
            ephemeral=True
        )

class EditEventView(discord.ui.View):
    def __init__(self, profile, events):
        super().__init__(timeout=None)
        self.profile = profile
        self.add_item(EditEventSelect(profile, events))

class PendingNotifSelect(discord.ui.Select):
    def __init__(self, notifs, profile, event):
        # Truncate if needed (timing_type is usually short, but be safe)
        options = []
        est_tz = pytz.timezone("US/Eastern")
        
        for n in notifs:
            # Convert Unix timestamp to EST datetime
            dt_utc = datetime.fromtimestamp(n['notify_unix'], tz=pytz.UTC)
            dt_est = dt_utc.astimezone(est_tz)
            est_time_str = dt_est.strftime("%m/%d/%Y %I:%M %p EST")
            
            label = f"{n['timing_type']} {est_time_str}"
            # Discord limit is 100 chars for label
            if len(label) > 100:
                label = label[:97] + "..."
            options.append(discord.SelectOption(label=label, value=str(n['id'])))
        super().__init__(placeholder="Select pending notification...", min_values=1, max_values=1, options=options, custom_id=f"pending_notif_select_{profile}")
        self.profile = profile
        self.event = event

    async def callback(self, interaction: discord.Interaction):
        notif_id = self.values[0]
        # Show action buttons after selection
        action_view = PendingNotifActionView(self.profile, self.event, int(notif_id))
        await interaction.response.edit_message(content=f"Selected notification ID: {notif_id}. Choose an action below.", view=action_view)

class EditMessageModal(discord.ui.Modal):
    """Modal for editing a notification's custom message."""
    def __init__(self, profile, notif_id, current_message=None):
        super().__init__(title="Edit Notification Message")
        self.profile = profile
        self.notif_id = notif_id
        
        # Text input for custom message
        self.custom_message_input = discord.ui.TextInput(
            label="Custom Notification Message",
            style=discord.TextStyle.paragraph,
            placeholder="Enter custom message or leave blank to use template",
            default=current_message if current_message else "",
            required=False,
            max_length=2000
        )
        self.add_item(self.custom_message_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Get custom message (or None if empty)
        custom_message = self.custom_message_input.value.strip() if self.custom_message_input.value else None
        
        # Update database
        async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
            await conn.execute(
                "UPDATE pending_notifications SET custom_message=? WHERE id=?",
                (custom_message, self.notif_id)
            )
            await conn.commit()
        
        # Send confirmation
        if custom_message:
            await interaction.response.send_message(
                f"✅ Custom message saved!\n\n**Preview:** {custom_message[:100]}{'...' if len(custom_message) > 100 else ''}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "✅ Custom message cleared. Template message will be used.",
                ephemeral=True
            )
        
        # Refresh control panel
        await update_control_panel_messages(self.profile)

class PendingNotifActionView(discord.ui.View):
    def __init__(self, profile, event, notif_id):
        super().__init__(timeout=None)
        self.profile = profile
        self.event = event
        self.notif_id = notif_id

    @discord.ui.button(label="Edit Message", style=discord.ButtonStyle.gray, custom_id="edit_pending_message")
    async def edit_pending_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get current custom message from database
        async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
            async with conn.execute(
                "SELECT custom_message FROM pending_notifications WHERE id=?",
                (self.notif_id,)
            ) as cursor:
                row = await cursor.fetchone()
                current_message = row[0] if row and row[0] else None
        
        # Show edit modal
        await interaction.response.send_modal(EditMessageModal(self.profile, self.notif_id, current_message))

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

async def load_control_panel_message_ids():
    """Load control panel message IDs from database on bot startup."""
    global CONTROL_PANEL_MESSAGE_IDS
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        async with conn.execute("SELECT profile, panel_type, event_id, message_id FROM control_panel_messages") as cursor:
            async for row in cursor:
                profile, panel_type, event_id, message_id = row
                if profile not in CONTROL_PANEL_MESSAGE_IDS:
                    CONTROL_PANEL_MESSAGE_IDS[profile] = {"add": None, "remove": None, "edit": None, "notifs": {}}
                
                if panel_type in ["add", "remove", "edit"]:
                    CONTROL_PANEL_MESSAGE_IDS[profile][panel_type] = int(message_id)
                elif panel_type == "notif" and event_id is not None:
                    CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][int(event_id)] = int(message_id)
    print(f"[ControlPanel] Loaded message IDs: {CONTROL_PANEL_MESSAGE_IDS}")

async def save_control_panel_message_id(profile, panel_type, message_id, event_id=None):
    """Save a control panel message ID to database."""
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        # Delete existing entry first (in case it's an update)
        if event_id is not None:
            await conn.execute("DELETE FROM control_panel_messages WHERE profile=? AND panel_type=? AND event_id=?", 
                             (profile, panel_type, event_id))
        else:
            await conn.execute("DELETE FROM control_panel_messages WHERE profile=? AND panel_type=? AND event_id IS NULL", 
                             (profile, panel_type))
        
        # Insert new entry
        await conn.execute("INSERT INTO control_panel_messages (profile, panel_type, event_id, message_id) VALUES (?, ?, ?, ?)",
                         (profile, panel_type, event_id, str(message_id)))
        await conn.commit()

async def delete_control_panel_message_id(profile, panel_type, event_id=None):
    """Delete a control panel message ID from database."""
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        if event_id is not None:
            await conn.execute("DELETE FROM control_panel_messages WHERE profile=? AND panel_type=? AND event_id=?", 
                             (profile, panel_type, event_id))
        else:
            await conn.execute("DELETE FROM control_panel_messages WHERE profile=? AND panel_type=? AND event_id IS NULL", 
                             (profile, panel_type))
        await conn.commit()

async def init_control_panel_db():
    """Initialize control panel message tracking table."""
    async with aiosqlite.connect(NOTIF_DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS control_panel_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile TEXT NOT NULL,
                panel_type TEXT NOT NULL,
                event_id INTEGER,
                message_id TEXT NOT NULL,
                UNIQUE(profile, panel_type, event_id)
            )
        """)
        await conn.commit()
    print("[ControlPanel] Database initialized.")

async def cleanup_old_control_panel_messages(channel, profile):
    """
    Deletes all messages in the control panel channel that are not tracked in CONTROL_PANEL_MESSAGE_IDS.
    This prevents duplicate messages on bot restart.
    """
    print(f"[ControlPanel] Cleaning up old messages for profile: {profile}")
    tracked_ids = set()
    
    # Collect all tracked message IDs for this profile
    if profile in CONTROL_PANEL_MESSAGE_IDS:
        panel = CONTROL_PANEL_MESSAGE_IDS[profile]
        if panel.get("add"):
            tracked_ids.add(int(panel["add"]))
        if panel.get("remove"):
            tracked_ids.add(int(panel["remove"]))
        if panel.get("edit"):
            tracked_ids.add(int(panel["edit"]))
        for event_id, msg_id in panel.get("notifs", {}).items():
            tracked_ids.add(int(msg_id))
    
    # Fetch recent messages and delete untracked ones
    try:
        async for message in channel.history(limit=100):
            if message.author == bot.user and message.id not in tracked_ids:
                try:
                    await message.delete()
                    print(f"[ControlPanel] Deleted untracked message {message.id}")
                except Exception as e:
                    print(f"[ControlPanel] Failed to delete message {message.id}: {e}")
    except Exception as e:
        print(f"[ControlPanel] Error during cleanup: {e}")

async def update_single_event_panels(profile, event_id):
    """
    Updates only the panels affected by a single event:
    - Remove Event dropdown
    - Edit Event dropdown  
    - Pending Notifications for that specific event
    
    This is much more efficient than updating the entire control panel.
    """
    print(f"[ControlPanel] Updating panels for single event (profile: {profile}, event_id: {event_id})")
    
    channel_id = CONTROL_PANEL_CHANNELS.get(profile)
    if not channel_id:
        print(f"[ControlPanel] No channel ID found for profile {profile}.")
        return
    
    guild = bot.get_guild(MAIN_SERVER_ID)
    channel = guild.get_channel(channel_id) if guild else None
    if not channel:
        print(f"[ControlPanel] Channel {channel_id} not found.")
        return
    
    # Initialize if needed
    if profile not in CONTROL_PANEL_MESSAGE_IDS:
        CONTROL_PANEL_MESSAGE_IDS[profile] = {"add": None, "remove": None, "edit": None, "notifs": {}}
    
    events = await get_events(profile)
    
    # Update Remove Event Panel
    try:
        remove_view = RemoveEventView(profile, events)
        if CONTROL_PANEL_MESSAGE_IDS[profile]["remove"]:
            try:
                msg = await channel.fetch_message(CONTROL_PANEL_MESSAGE_IDS[profile]["remove"])
                await msg.edit(content="**Remove Event**", view=remove_view)
                print(f"[ControlPanel] Updated Remove Event dropdown")
            except discord.NotFound:
                print(f"[ControlPanel] Remove Event message not found, skipping update")
            except discord.HTTPException as e:
                if e.code == 30046:  # Too many edits
                    print(f"[ControlPanel] Rate limited on Remove Event panel, will update later")
                else:
                    raise
    except Exception as e:
        print(f"[ControlPanel] Error updating Remove Event panel: {e}")
    
    # Update Edit Event Panel
    try:
        edit_view = EditEventView(profile, events)
        if CONTROL_PANEL_MESSAGE_IDS[profile]["edit"]:
            try:
                msg = await channel.fetch_message(CONTROL_PANEL_MESSAGE_IDS[profile]["edit"])
                await msg.edit(content="**Edit Event**", view=edit_view)
                print(f"[ControlPanel] Updated Edit Event dropdown")
            except discord.NotFound:
                print(f"[ControlPanel] Edit Event message not found, skipping update")
            except discord.HTTPException as e:
                if e.code == 30046:  # Too many edits
                    print(f"[ControlPanel] Rate limited on Edit Event panel, will update later")
                else:
                    raise
    except Exception as e:
        print(f"[ControlPanel] Error updating Edit Event panel: {e}")
    
    # Update Pending Notification for this specific event
    try:
        event = await get_event_by_id(profile, event_id)
        if event:
            notifs = await get_pending_notifications_for_event(profile, event_id)
            print(f"[ControlPanel] Event '{event['title']}' has {len(notifs)} pending notifications.")
            
            if notifs:
                # Create or update notification panel
                notif_view = PendingNotifView(profile, notifs, event)
                content = f"**Pending Notifications for {event['title']}**"
                
                if event_id in CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"]:
                    try:
                        msg_id = CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event_id]
                        msg = await channel.fetch_message(msg_id)
                        await msg.edit(content=content, view=notif_view)
                        print(f"[ControlPanel] Updated notification panel for event {event_id}")
                    except discord.NotFound:
                        # Message deleted, create new one
                        msg = await channel.send(content, view=notif_view)
                        CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event_id] = msg.id
                        await save_control_panel_message_id(profile, "notif", event_id, msg.id)
                        print(f"[ControlPanel] Created new notification panel for event {event_id}")
                else:
                    # Create new notification panel
                    msg = await channel.send(content, view=notif_view)
                    CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event_id] = msg.id
                    await save_control_panel_message_id(profile, "notif", event_id, msg.id)
                    print(f"[ControlPanel] Created notification panel for event {event_id}")
            else:
                # No notifications, delete panel if it exists
                if event_id in CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"]:
                    try:
                        msg_id = CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event_id]
                        msg = await channel.fetch_message(msg_id)
                        await msg.delete()
                        await delete_control_panel_message_id(profile, "notif", event_id)
                        del CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event_id]
                        print(f"[ControlPanel] Deleted notification panel (no notifications)")
                    except Exception as e:
                        print(f"[ControlPanel] Error deleting empty notification panel: {e}")
    except Exception as e:
        print(f"[ControlPanel] Error updating notification panel: {e}")
    
    print(f"[ControlPanel] Finished updating panels for event {event_id}")

async def update_control_panel_messages(profile):
    """
    Updates control panel messages by editing existing ones instead of recreating.
    Includes rate limiting to prevent Discord 429 errors.
    """
    global _last_update_time, _pending_updates
    
    current_time = datetime.now().timestamp()
    last_update = _last_update_time.get(profile, 0)
    time_since_last = current_time - last_update
    
    # If an update happened recently, schedule a delayed update instead
    if time_since_last < _update_cooldown:
        cooldown_remaining = _update_cooldown - time_since_last
        print(f"[ControlPanel] Rate limit: Update for {profile} requested too soon ({time_since_last:.1f}s ago). Scheduling delayed update in {cooldown_remaining:.1f}s.")
        
        # Cancel any existing pending update
        if profile in _pending_updates and not _pending_updates[profile].done():
            _pending_updates[profile].cancel()
            print(f"[ControlPanel] Cancelled previous pending update for {profile}")
        
        # Schedule a new delayed update
        async def delayed_update():
            await asyncio.sleep(cooldown_remaining)
            print(f"[ControlPanel] Executing delayed update for {profile}")
            await _do_update_control_panel(profile)
        
        _pending_updates[profile] = asyncio.create_task(delayed_update())
        return
    
    # Proceed with immediate update
    await _do_update_control_panel(profile)

async def _do_update_control_panel(profile):
    """
    Internal function that performs the actual control panel update.
    This is separated so it can be called both immediately and after a delay.
    """
    global _last_update_time
    
    print(f"[ControlPanel] Updating control panel for profile: {profile}")
    _last_update_time[profile] = datetime.now().timestamp()
    
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
    
    # Clean up old messages not in database (prevent duplicates on restart)
    await cleanup_old_control_panel_messages(channel, profile)

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
                await save_control_panel_message_id(profile, "add", msg.id)
                print(f"[ControlPanel] Sent new Add Event message: {msg.id}")
        else:
            msg = await channel.send("**Add Event**", view=add_view)
            CONTROL_PANEL_MESSAGE_IDS[profile]["add"] = msg.id
            await save_control_panel_message_id(profile, "add", msg.id)
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
                await save_control_panel_message_id(profile, "remove", msg.id)
                print(f"[ControlPanel] Sent new Remove Event message: {msg.id}")
        else:
            msg = await channel.send("**Remove Event**", view=remove_view)
            CONTROL_PANEL_MESSAGE_IDS[profile]["remove"] = msg.id
            await save_control_panel_message_id(profile, "remove", msg.id)
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
                await save_control_panel_message_id(profile, "edit", msg.id)
                print(f"[ControlPanel] Sent new Edit Event message: {msg.id}")
        else:
            msg = await channel.send("**Edit Event**", view=edit_view)
            CONTROL_PANEL_MESSAGE_IDS[profile]["edit"] = msg.id
            await save_control_panel_message_id(profile, "edit", msg.id)
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
            await delete_control_panel_message_id(profile, "notif", event_id)
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
                    await delete_control_panel_message_id(profile, "notif", event["id"])
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
                    await save_control_panel_message_id(profile, "notif", msg.id, event["id"])
                    print(f"[ControlPanel] Sent new notification panel for event '{event['title']}'")
            else:
                msg = await channel.send(content, view=notif_view)
                CONTROL_PANEL_MESSAGE_IDS[profile]["notifs"][event["id"]] = msg.id
                await save_control_panel_message_id(profile, "notif", msg.id, event["id"])
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