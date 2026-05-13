"""
Uma Musume Pretty Derby game module.

This module handles Uma Musume events with special support for:
- Champions Meeting (5 phases)
- Legend Race (character rotations)
"""

from .module import UmaMusumeModule
from .database import UmaEventRepository

__all__ = ['UmaMusumeModule', 'UmaEventRepository']
