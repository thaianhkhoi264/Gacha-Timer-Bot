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

__all__ = [
    'GameConfig',
    'GameModule',
    'HoyoverseGameModule',
]
