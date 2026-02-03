"""
Discord UI components for the Gacha Timer Bot.

This package provides:
- buttons: Reusable button components
- selects: Select menu components
- modals: Modal dialog components
- views: Complete interactive views
"""

from .buttons import (
    ConfirmButton,
    CancelButton,
    DeleteButton,
    EditButton,
    RefreshButton,
    PaginationButton,
    LinkButton,
)

from .selects import (
    CategorySelect,
    TimezoneSelect,
    ProfileSelect,
    RegionSelect,
    EventSelect,
)

from .modals import (
    AddEventModal,
    EditEventModal,
    QuickAddModal,
    ConfirmationModal,
)

from .views import (
    ConfirmationView,
    DeleteConfirmationView,
    EventOptionsView,
    PaginatedView,
    EventListView,
)


__all__ = [
    # Buttons
    'ConfirmButton',
    'CancelButton',
    'DeleteButton',
    'EditButton',
    'RefreshButton',
    'PaginationButton',
    'LinkButton',
    # Selects
    'CategorySelect',
    'TimezoneSelect',
    'ProfileSelect',
    'RegionSelect',
    'EventSelect',
    # Modals
    'AddEventModal',
    'EditEventModal',
    'QuickAddModal',
    'ConfirmationModal',
    # Views
    'ConfirmationView',
    'DeleteConfirmationView',
    'EventOptionsView',
    'PaginatedView',
    'EventListView',
]
