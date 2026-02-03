"""
Base repository class with common database utilities.

This module provides a base class for SQLite repositories with
connection management, WAL mode, and common utilities.
"""

import aiosqlite
import os
from typing import Optional, Any, List
from contextlib import asynccontextmanager


class BaseRepository:
    """
    Base class for SQLite repositories.

    Provides common database utilities and connection management.
    All concrete repositories should inherit from this class.
    """

    def __init__(self, db_path: str):
        """
        Initialize the repository.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._ensure_directory()

    def _ensure_directory(self):
        """Ensure the directory for the database file exists."""
        directory = os.path.dirname(self.db_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    @asynccontextmanager
    async def get_connection(self):
        """
        Get an async database connection with optimal settings.

        Usage:
            async with self.get_connection() as conn:
                await conn.execute(...)

        Yields:
            aiosqlite.Connection: Database connection
        """
        conn = await aiosqlite.connect(self.db_path)
        try:
            # Enable WAL mode for better concurrency
            await conn.execute("PRAGMA journal_mode=WAL")
            # Enable foreign key constraints
            await conn.execute("PRAGMA foreign_keys=ON")
            # Balance between safety and performance
            await conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
        finally:
            await conn.close()

    async def execute(self, query: str, params: tuple = ()) -> int:
        """
        Execute a query and return the last row ID.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Last row ID (for INSERT) or rows affected (for UPDATE/DELETE)
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()
            return cursor.lastrowid

    async def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """
        Execute a query with multiple parameter sets.

        Args:
            query: SQL query string
            params_list: List of parameter tuples

        Returns:
            Number of rows affected
        """
        async with self.get_connection() as conn:
            await conn.executemany(query, params_list)
            await conn.commit()
            return len(params_list)

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[tuple]:
        """
        Fetch a single row.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Single row tuple or None
        """
        async with self.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                return await cursor.fetchone()

    async def fetch_all(self, query: str, params: tuple = ()) -> List[tuple]:
        """
        Fetch all rows.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of row tuples
        """
        async with self.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                return await cursor.fetchall()

    async def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.

        Args:
            table_name: Name of the table

        Returns:
            True if table exists, False otherwise
        """
        row = await self.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return row is not None

    async def column_exists(self, table_name: str, column_name: str) -> bool:
        """
        Check if a column exists in a table.

        Args:
            table_name: Name of the table
            column_name: Name of the column

        Returns:
            True if column exists, False otherwise
        """
        async with self.get_connection() as conn:
            async with conn.execute(f"PRAGMA table_info({table_name})") as cursor:
                columns = await cursor.fetchall()
                return any(col[1] == column_name for col in columns)

    async def add_column_if_not_exists(
        self,
        table_name: str,
        column_name: str,
        column_type: str,
        default: Optional[str] = None
    ):
        """
        Add a column to a table if it doesn't exist.

        Args:
            table_name: Name of the table
            column_name: Name of the column to add
            column_type: SQLite column type (e.g., "TEXT", "INTEGER")
            default: Default value (optional)
        """
        if not await self.column_exists(table_name, column_name):
            default_clause = f" DEFAULT {default}" if default else ""
            await self.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}{default_clause}"
            )

    async def create_index_if_not_exists(
        self,
        index_name: str,
        table_name: str,
        columns: List[str],
        unique: bool = False
    ):
        """
        Create an index if it doesn't exist.

        Args:
            index_name: Name for the index
            table_name: Table to index
            columns: List of column names
            unique: Whether the index should be unique
        """
        unique_clause = "UNIQUE " if unique else ""
        columns_str = ", ".join(columns)
        await self.execute(
            f"CREATE {unique_clause}INDEX IF NOT EXISTS {index_name} "
            f"ON {table_name} ({columns_str})"
        )


def safe_int(value: Any, fallback: int = 0) -> int:
    """
    Safely convert a value to integer.

    Args:
        value: Value to convert
        fallback: Fallback value if conversion fails

    Returns:
        Integer value
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
