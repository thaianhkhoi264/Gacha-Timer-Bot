"""
Discord Button components for the bot.

Provides reusable buttons for common actions.
"""

import discord
from typing import Callable, Optional


class ConfirmButton(discord.ui.Button):
    """
    Green confirm button.
    """

    def __init__(
        self,
        label: str = "Confirm",
        callback: Optional[Callable] = None,
        custom_id: str = "confirm_button"
    ):
        """
        Initialize the confirm button.

        Args:
            label: Button label
            callback: Async callback(interaction) when clicked
            custom_id: Custom ID for the button
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.green,
            custom_id=custom_id
        )
        self._custom_callback = callback

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        if self._custom_callback:
            await self._custom_callback(interaction)
        else:
            await interaction.response.defer()


class CancelButton(discord.ui.Button):
    """
    Grey cancel button.
    """

    def __init__(
        self,
        label: str = "Cancel",
        callback: Optional[Callable] = None,
        custom_id: str = "cancel_button"
    ):
        """
        Initialize the cancel button.

        Args:
            label: Button label
            callback: Async callback(interaction) when clicked
            custom_id: Custom ID for the button
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.grey,
            custom_id=custom_id
        )
        self._custom_callback = callback

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        if self._custom_callback:
            await self._custom_callback(interaction)
        else:
            await interaction.response.defer()


class DeleteButton(discord.ui.Button):
    """
    Red delete/remove button.
    """

    def __init__(
        self,
        label: str = "Delete",
        callback: Optional[Callable] = None,
        custom_id: str = "delete_button"
    ):
        """
        Initialize the delete button.

        Args:
            label: Button label
            callback: Async callback(interaction) when clicked
            custom_id: Custom ID for the button
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.red,
            custom_id=custom_id
        )
        self._custom_callback = callback

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        if self._custom_callback:
            await self._custom_callback(interaction)
        else:
            await interaction.response.defer()


class EditButton(discord.ui.Button):
    """
    Blue edit button.
    """

    def __init__(
        self,
        label: str = "Edit",
        callback: Optional[Callable] = None,
        custom_id: str = "edit_button"
    ):
        """
        Initialize the edit button.

        Args:
            label: Button label
            callback: Async callback(interaction) when clicked
            custom_id: Custom ID for the button
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=custom_id
        )
        self._custom_callback = callback

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        if self._custom_callback:
            await self._custom_callback(interaction)
        else:
            await interaction.response.defer()


class RefreshButton(discord.ui.Button):
    """
    Secondary refresh button.
    """

    def __init__(
        self,
        label: str = "Refresh",
        callback: Optional[Callable] = None,
        custom_id: str = "refresh_button"
    ):
        """
        Initialize the refresh button.

        Args:
            label: Button label
            callback: Async callback(interaction) when clicked
            custom_id: Custom ID for the button
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=custom_id,
            emoji="\U0001F504"  # Counterclockwise arrows
        )
        self._custom_callback = callback

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        if self._custom_callback:
            await self._custom_callback(interaction)
        else:
            await interaction.response.defer()


class PaginationButton(discord.ui.Button):
    """
    Navigation button for pagination.
    """

    def __init__(
        self,
        direction: str,  # "prev", "next", "first", "last"
        callback: Optional[Callable] = None,
        disabled: bool = False
    ):
        """
        Initialize the pagination button.

        Args:
            direction: Navigation direction
            callback: Async callback(interaction, direction) when clicked
            disabled: Whether button is disabled
        """
        labels = {
            "first": "\u23EE",  # Rewind
            "prev": "\u25C0",   # Left arrow
            "next": "\u25B6",   # Right arrow
            "last": "\u23ED",   # Fast forward
        }

        super().__init__(
            label=labels.get(direction, direction),
            style=discord.ButtonStyle.secondary,
            custom_id=f"pagination_{direction}",
            disabled=disabled
        )
        self.direction = direction
        self._custom_callback = callback

    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        if self._custom_callback:
            await self._custom_callback(interaction, self.direction)
        else:
            await interaction.response.defer()


class LinkButton(discord.ui.Button):
    """
    URL button that opens a link.
    """

    def __init__(
        self,
        label: str,
        url: str
    ):
        """
        Initialize the link button.

        Args:
            label: Button label
            url: URL to open
        """
        super().__init__(
            label=label,
            style=discord.ButtonStyle.link,
            url=url
        )
