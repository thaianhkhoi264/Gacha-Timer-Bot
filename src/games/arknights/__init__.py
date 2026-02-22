"""
Arknights game module.

This package provides all Arknights-specific functionality:
- ArknightsModule: Main module implementing GameModule interface
- ArknightsEventRepository: Database operations
- setup_arknights_commands: Discord command registration
"""

from .module import ArknightsModule
from .database import ArknightsEventRepository
from .commands import setup_arknights_commands

__all__ = [
    'ArknightsModule',
    'ArknightsEventRepository',
    'setup_arknights_commands',
]
