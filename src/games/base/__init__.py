"""
Base classes for game modules.

This package provides abstract base classes that all game modules inherit from,
following the Open/Closed Principle for extensibility.
"""

from .game_module import (
    GameConfig,
    GameModule,
    HoyoverseGameModule,
)
from .special_event_module import (
    SpecialEventGameModule,
)

__all__ = [
    'GameConfig',
    'GameModule',
    'HoyoverseGameModule',
    'SpecialEventGameModule',
]
