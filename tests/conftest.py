"""
Pytest configuration and shared fixtures for testing.

This file contains shared fixtures that can be used across all test files.
"""

import pytest
import aiosqlite
from pathlib import Path


@pytest.fixture
async def test_db():
    """
    Create an in-memory SQLite database for testing.

    Yields:
        aiosqlite.Connection: Test database connection
    """
    db = await aiosqlite.connect(":memory:")
    yield db
    await db.close()


@pytest.fixture
def mock_discord_ctx():
    """
    Create a mock Discord context for command testing.

    Returns:
        Mock: Mocked discord.ext.commands.Context
    """
    # Placeholder for Discord context mock
    # Will be implemented when we write actual tests
    pass


@pytest.fixture
def temp_db_path(tmp_path):
    """
    Provide a temporary file path for database testing.

    Args:
        tmp_path: pytest's built-in temporary directory fixture

    Returns:
        Path: Temporary database file path
    """
    return tmp_path / "test.db"
