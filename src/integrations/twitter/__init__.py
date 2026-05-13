"""
Twitter Integration - Event extraction from tweets.

This module provides Twitter integration for extracting game events from
official announcement tweets using LLM-based parsing.
"""

from .handler import TwitterHandler
from .extractors.base import BaseTweetExtractor

__all__ = ['TwitterHandler', 'BaseTweetExtractor']
