"""
Discord Modal components for the bot.

Provides reusable modals for event input, editing, etc.
"""

import discord
from typing import Callable, Optional, Dict, Any


class AddEventModal(discord.ui.Modal):
    """
    Modal for adding a new event.

    Collects: title, start date, end date, image URL
    """

    def __init__(
        self,
        profile: str,
        default_timezone: str = "UTC",
        callback: Optional[Callable] = None
    ):
        """
        Initialize the add event modal.

        Args:
            profile: Game profile this event belongs to
            default_timezone: Default timezone for date parsing hints
            callback: Async callback(interaction, data) when submitted
        """
        super().__init__(title=f"Add {profile} Event")
        self.profile = profile
        self._callback = callback

        # Title input
        self.title_input = discord.ui.TextInput(
            label="Event Title",
            style=discord.TextStyle.short,
            required=True,
            max_length=200,
            placeholder="e.g. Firefly Banner"
        )
        self.add_item(self.title_input)

        # Start date input
        self.start_input = discord.ui.TextInput(
            label=f"Start Date ({default_timezone})",
            style=discord.TextStyle.short,
            required=True,
            placeholder="YYYY-MM-DD HH:MM (e.g. 2025-10-15 10:00)"
        )
        self.add_item(self.start_input)

        # End date input
        self.end_input = discord.ui.TextInput(
            label=f"End Date ({default_timezone})",
            style=discord.TextStyle.short,
            required=True,
            placeholder="YYYY-MM-DD HH:MM (e.g. 2025-10-30 03:59)"
        )
        self.add_item(self.end_input)

        # Image URL input (optional)
        self.image_input = discord.ui.TextInput(
            label="Image URL (Optional)",
            style=discord.TextStyle.short,
            required=False,
            placeholder="https://example.com/image.png"
        )
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        data = {
            "profile": self.profile,
            "title": self.title_input.value.strip(),
            "start": self.start_input.value.strip(),
            "end": self.end_input.value.strip(),
            "image": self.image_input.value.strip() if self.image_input.value else None,
        }

        if self._callback:
            await self._callback(interaction, data)
        else:
            await interaction.response.send_message(
                f"Event data received: {data['title']}",
                ephemeral=True
            )


class EditEventModal(discord.ui.Modal):
    """
    Modal for editing an existing event.

    Pre-fills fields with current event data.
    """

    def __init__(
        self,
        event_id: int,
        current_title: str,
        current_start: str,
        current_end: str,
        current_image: Optional[str] = None,
        profile: str = "HSR",
        callback: Optional[Callable] = None
    ):
        """
        Initialize the edit event modal.

        Args:
            event_id: ID of the event being edited
            current_title: Current event title
            current_start: Current start date string
            current_end: Current end date string
            current_image: Current image URL
            profile: Game profile
            callback: Async callback(interaction, data) when submitted
        """
        super().__init__(title=f"Edit Event")
        self.event_id = event_id
        self.profile = profile
        self._callback = callback

        # Title input
        self.title_input = discord.ui.TextInput(
            label="Event Title",
            style=discord.TextStyle.short,
            required=True,
            default=current_title,
            max_length=200
        )
        self.add_item(self.title_input)

        # Start date input
        self.start_input = discord.ui.TextInput(
            label="Start Date",
            style=discord.TextStyle.short,
            required=True,
            default=current_start
        )
        self.add_item(self.start_input)

        # End date input
        self.end_input = discord.ui.TextInput(
            label="End Date",
            style=discord.TextStyle.short,
            required=True,
            default=current_end
        )
        self.add_item(self.end_input)

        # Image URL input
        self.image_input = discord.ui.TextInput(
            label="Image URL (Optional)",
            style=discord.TextStyle.short,
            required=False,
            default=current_image or ""
        )
        self.add_item(self.image_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        data = {
            "event_id": self.event_id,
            "profile": self.profile,
            "title": self.title_input.value.strip(),
            "start": self.start_input.value.strip(),
            "end": self.end_input.value.strip(),
            "image": self.image_input.value.strip() if self.image_input.value else None,
        }

        if self._callback:
            await self._callback(interaction, data)
        else:
            await interaction.response.send_message(
                f"Event updated: {data['title']}",
                ephemeral=True
            )


class QuickAddModal(discord.ui.Modal):
    """
    Simplified modal for quick event addition.

    Only requires title and uses smart defaults.
    """

    def __init__(
        self,
        profile: str,
        category: str,
        callback: Optional[Callable] = None
    ):
        """
        Initialize the quick add modal.

        Args:
            profile: Game profile
            category: Event category
            callback: Async callback(interaction, data) when submitted
        """
        super().__init__(title=f"Quick Add {category}")
        self.profile = profile
        self.category = category
        self._callback = callback

        # Title input
        self.title_input = discord.ui.TextInput(
            label="Event Title",
            style=discord.TextStyle.short,
            required=True,
            max_length=200
        )
        self.add_item(self.title_input)

        # Duration input (in days)
        self.duration_input = discord.ui.TextInput(
            label="Duration (days)",
            style=discord.TextStyle.short,
            required=True,
            default="14",
            placeholder="Number of days the event lasts"
        )
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        data = {
            "profile": self.profile,
            "category": self.category,
            "title": self.title_input.value.strip(),
            "duration_days": self.duration_input.value.strip(),
        }

        if self._callback:
            await self._callback(interaction, data)
        else:
            await interaction.response.send_message(
                f"Quick add: {data['title']} for {data['duration_days']} days",
                ephemeral=True
            )


class ConfirmationModal(discord.ui.Modal):
    """
    Modal for confirming dangerous actions.

    Requires user to type a confirmation phrase.
    """

    def __init__(
        self,
        action_description: str,
        confirmation_phrase: str = "CONFIRM",
        callback: Optional[Callable] = None
    ):
        """
        Initialize the confirmation modal.

        Args:
            action_description: Description of the action being confirmed
            confirmation_phrase: Phrase user must type to confirm
            callback: Async callback(interaction, confirmed) when submitted
        """
        super().__init__(title="Confirm Action")
        self.confirmation_phrase = confirmation_phrase
        self._callback = callback

        # Confirmation input
        self.confirm_input = discord.ui.TextInput(
            label=f"Type '{confirmation_phrase}' to confirm",
            style=discord.TextStyle.short,
            required=True,
            placeholder=confirmation_phrase
        )
        self.add_item(self.confirm_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        confirmed = self.confirm_input.value.strip().upper() == self.confirmation_phrase.upper()

        if self._callback:
            await self._callback(interaction, confirmed)
        else:
            if confirmed:
                await interaction.response.send_message("Action confirmed.", ephemeral=True)
            else:
                await interaction.response.send_message(
                    "Confirmation failed. Action cancelled.",
                    ephemeral=True
                )
