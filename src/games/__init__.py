"""
Game modules for the Gacha Timer Bot.

This package contains game-specific implementations following the
GameModule interface defined in the base package.

Available game modules:
- HSR (Honkai: Star Rail) - Hoyoverse regional game
- Arknights - Single-server game
- ZZZ (Zenless Zone Zero) - Hoyoverse regional game
- STRI (Strinova) - Standard event tracking
- WUWA (Wuthering Waves) - Standard event tracking
- Uma Musume - Japanese mobile game with special events (stub)
- Shadowverse - Card game with class-based events (stub)

Each module provides:
- Database operations specific to that game
- Event management and dashboard updates
- Notification scheduling with game-specific timings
- Discord commands for manual management
"""

from .base import GameConfig, GameModule, HoyoverseGameModule
from .hsr import HSRModule, HSREventRepository, setup_hsr_commands
from .arknights import ArknightsModule, ArknightsEventRepository, setup_arknights_commands
from .generic import (
    GenericEventRepository,
    GenericGameModule,
    GenericHoyoverseModule,
    create_zzz_module,
    create_stri_module,
    create_wuwa_module,
)

__all__ = [
    # Base classes
    'GameConfig',
    'GameModule',
    'HoyoverseGameModule',
    # HSR
    'HSRModule',
    'HSREventRepository',
    'setup_hsr_commands',
    # Arknights
    'ArknightsModule',
    'ArknightsEventRepository',
    'setup_arknights_commands',
    # Generic modules
    'GenericEventRepository',
    'GenericGameModule',
    'GenericHoyoverseModule',
    'create_zzz_module',
    'create_stri_module',
    'create_wuwa_module',
]
