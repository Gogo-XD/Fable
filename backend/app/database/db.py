"""
Database connection and initialization.
"""

import aiosqlite
from pathlib import Path
from app.config import settings
from app.logging import get_logger

logger = get_logger('database')

DATABASE_PATH = Path(settings.DATABASE_PATH)


async def get_db():
    """
    Get database connection as async context manager.

    :return: Async database connection
    :rtype: AsyncGenerator[aiosqlite.Connection, None]
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    """
    Initialize database with schema.

    :return: None
    :rtype: None
    """
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        schema_path = Path(__file__).parent / "init_db.sql"
        with open(schema_path) as f:
            await db.executescript(f.read())
        await db.commit()
        logger.info(f"Database initialized at {DATABASE_PATH}")


async def execute_query(query: str, params: tuple = ()):
    """
    Execute a query and return results.

    :param query: The SQL query to execute
    :type query: str
    :param params: Query parameters
    :type params: tuple
    :return: List of row dictionaries from query results
    :rtype: list[dict]
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        await db.commit()
        return [dict(row) for row in rows]


async def execute_insert(query: str, params: tuple = ()) -> str | None:
    """
    Execute an insert and return last row id.

    :param query: The SQL insert query to execute
    :type query: str
    :param params: Query parameters
    :type params: tuple
    :return: The last inserted row ID
    :rtype: str | None
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(query, params)
        await db.commit()
        return cursor.lastrowid
