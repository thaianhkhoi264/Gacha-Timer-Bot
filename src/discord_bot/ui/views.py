"""
Discord View classes for the bot.

Combines UI components into complete interactive views.
"""

import discord
from typing import Callable, Optional, List, Dict, Any

from .buttons import (
    ConfirmButton,
    CancelButton,
    DeleteButton,
    EditButton,
    RefreshButton,
    PaginationButton,
)
from .selects import (
    CategorySelect,
    TimezoneSelect,
    ProfileSelect,
    RegionSelect,
    EventSelect,
)


class ConfirmationView(discord.ui.View):
    """
    Simple confirmation view with Confirm/Cancel buttons.
    """

    def __init__(
        self,
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
        timeout: float = 60.0
    ):
        """
        Initialize the confirmation view.

        Args:
            on_confirm: Async callback when confirmed
            on_cancel: Async callback when cancelled
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.confirmed: Optional[bool] = None
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel

        self.add_item(ConfirmButton(callback=self._handle_confirm))
        self.add_item(CancelButton(callback=self._handle_cancel))

    async def _handle_confirm(self, interaction: discord.Interaction):
        """Handle confirm button."""
        self.confirmed = True
        if self._on_confirm:
            await self._on_confirm(interaction)
        self.stop()

    async def _handle_cancel(self, interaction: discord.Interaction):
        """Handle cancel button."""
        self.confirmed = False
        if self._on_cancel:
            await self._on_cancel(interaction)
        self.stop()


class DeleteConfirmationView(discord.ui.View):
    """
    Confirmation view for delete actions (with red button).
    """

    def __init__(
        self,
        item_name: str,
        on_delete: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the delete confirmation view.

        Args:
            item_name: Name of item being deleted (for label)
            on_delete: Async callback when delete confirmed
            on_cancel: Async callback when cancelled
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.deleted = False
        self._on_delete = on_delete
        self._on_cancel = on_cancel

        self.add_item(DeleteButton(
            label=f"Delete {item_name}",
            callback=self._handle_delete
        ))
        self.add_item(CancelButton(callback=self._handle_cancel))

    async def _handle_delete(self, interaction: discord.Interaction):
        """Handle delete button."""
        self.deleted = True
        if self._on_delete:
            await self._on_delete(interaction)
        self.stop()

    async def _handle_cancel(self, interaction: discord.Interaction):
        """Handle cancel button."""
        if self._on_cancel:
            await self._on_cancel(interaction)
        self.stop()


class EventOptionsView(discord.ui.View):
    """
    View for selecting event options (category, timezone).

    Used when adding/editing events through the control panel.
    """

    def __init__(
        self,
        profile: str,
        title: str,
        start: str,
        end: str,
        image: Optional[str] = None,
        current_category: Optional[str] = None,
        is_edit: bool = False,
        event_id: Optional[int] = None,
        on_submit: Optional[Callable] = None,
        timeout: float = 180.0
    ):
        """
        Initialize the event options view.

        Args:
            profile: Game profile
            title: Event title
            start: Start date string
            end: End date string
            image: Image URL (optional)
            current_category: Current category selection
            is_edit: Whether this is an edit operation
            event_id: Event ID if editing
            on_submit: Async callback(interaction, data) when submitted
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)

        self.profile = profile
        self.title = title
        self.start = start
        self.end = end
        self.image = image
        self.is_edit = is_edit
        self.event_id = event_id
        self._on_submit = on_submit

        # State
        self.selected_category = current_category
        self.selected_timezone = "UTC"

        # Add components
        self.add_item(CategorySelect(
            profile=profile,
            current_category=current_category,
            callback=self._on_category_select
        ))
        self.add_item(TimezoneSelect(callback=self._on_timezone_select))
        self.add_item(ConfirmButton(
            label="Confirm Event" if not is_edit else "Update Event",
            callback=self._on_confirm
        ))

    async def _on_category_select(self, interaction: discord.Interaction, value: str):
        """Handle category selection."""
        self.selected_category = value
        await interaction.response.defer()

    async def _on_timezone_select(self, interaction: discord.Interaction, value: str):
        """Handle timezone selection."""
        self.selected_timezone = value
        await interaction.response.defer()

    async def _on_confirm(self, interaction: discord.Interaction):
        """Handle confirm button."""
        data = {
            "profile": self.profile,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "image": self.image,
            "category": self.selected_category,
            "timezone": self.selected_timezone,
            "is_edit": self.is_edit,
            "event_id": self.event_id,
        }

        if self._on_submit:
            await self._on_submit(interaction, data)
        else:
            await interaction.response.send_message(
                f"Event submitted: {data}",
                ephemeral=True
            )
        self.stop()


class PaginatedView(discord.ui.View):
    """
    View for paginated content with navigation buttons.
    """

    def __init__(
        self,
        pages: List[discord.Embed],
        on_page_change: Optional[Callable] = None,
        timeout: float = 120.0
    ):
        """
        Initialize the paginated view.

        Args:
            pages: List of embeds to paginate
            on_page_change: Async callback(interaction, page_num) on page change
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)

        self.pages = pages
        self.current_page = 0
        self._on_page_change = on_page_change

        self._update_buttons()

    def _update_buttons(self):
        """Update button states based on current page."""
        self.clear_items()

        # First page button
        self.add_item(PaginationButton(
            "first",
            callback=self._go_first,
            disabled=(self.current_page == 0)
        ))

        # Previous button
        self.add_item(PaginationButton(
            "prev",
            callback=self._go_prev,
            disabled=(self.current_page == 0)
        ))

        # Next button
        self.add_item(PaginationButton(
            "next",
            callback=self._go_next,
            disabled=(self.current_page >= len(self.pages) - 1)
        ))

        # Last page button
        self.add_item(PaginationButton(
            "last",
            callback=self._go_last,
            disabled=(self.current_page >= len(self.pages) - 1)
        ))

    async def _go_first(self, interaction: discord.Interaction, _: str):
        """Go to first page."""
        self.current_page = 0
        await self._update_view(interaction)

    async def _go_prev(self, interaction: discord.Interaction, _: str):
        """Go to previous page."""
        self.current_page = max(0, self.current_page - 1)
        await self._update_view(interaction)

    async def _go_next(self, interaction: discord.Interaction, _: str):
        """Go to next page."""
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        await self._update_view(interaction)

    async def _go_last(self, interaction: discord.Interaction, _: str):
        """Go to last page."""
        self.current_page = len(self.pages) - 1
        await self._update_view(interaction)

    async def _update_view(self, interaction: discord.Interaction):
        """Update the view after page change."""
        self._update_buttons()

        if self._on_page_change:
            await self._on_page_change(interaction, self.current_page)
        else:
            await interaction.response.edit_message(
                embed=self.pages[self.current_page],
                view=self
            )

    def get_current_embed(self) -> discord.Embed:
        """Get the current page's embed."""
        if self.pages:
            return self.pages[self.current_page]
        return discord.Embed(description="No content available.")


class EventListView(discord.ui.View):
    """
    View for selecting and managing events from a list.
    """

    def __init__(
        self,
        events: List[Dict[str, Any]],
        on_select: Optional[Callable] = None,
        on_edit: Optional[Callable] = None,
        on_delete: Optional[Callable] = None,
        timeout: float = 120.0
    ):
        """
        Initialize the event list view.

        Args:
            events: List of event dicts
            on_select: Async callback when event selected
            on_edit: Async callback when edit clicked
            on_delete: Async callback when delete clicked
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)

        self.events = events
        self.selected_event_id: Optional[str] = None
        self._on_select = on_select
        self._on_edit = on_edit
        self._on_delete = on_delete

        # Add event select
        self.add_item(EventSelect(
            events=events,
            callback=self._handle_select
        ))

        # Add action buttons (initially disabled)
        self._edit_button = EditButton(callback=self._handle_edit)
        self._edit_button.disabled = True
        self.add_item(self._edit_button)

        self._delete_button = DeleteButton(callback=self._handle_delete)
        self._delete_button.disabled = True
        self.add_item(self._delete_button)

    async def _handle_select(self, interaction: discord.Interaction, value: str):
        """Handle event selection."""
        self.selected_event_id = value

        # Enable action buttons
        self._edit_button.disabled = False
        self._delete_button.disabled = False

        if self._on_select:
            await self._on_select(interaction, value)
        else:
            await interaction.response.edit_message(view=self)

    async def _handle_edit(self, interaction: discord.Interaction):
        """Handle edit button."""
        if self._on_edit and self.selected_event_id:
            await self._on_edit(interaction, self.selected_event_id)
        else:
            await interaction.response.defer()

    async def _handle_delete(self, interaction: discord.Interaction):
        """Handle delete button."""
        if self._on_delete and self.selected_event_id:
            await self._on_delete(interaction, self.selected_event_id)
        else:
            await interaction.response.defer()
