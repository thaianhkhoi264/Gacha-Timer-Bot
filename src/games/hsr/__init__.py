"""
HSR (Honkai: Star Rail) game module.

This package provides all HSR-specific functionality:
- HSRModule: Main module implementing GameModule interface
- HSREventRepository: Database operations
- setup_hsr_commands: Discord command registration
"""

from .module import HSRModule
from .database import HSREventRepository
from .commands import setup_hsr_commands

__all__ = [
    'HSRModule',
    'HSREventRepository',
    'setup_hsr_commands',
]
