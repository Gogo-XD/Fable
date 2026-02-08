"""
Database connection and initialization.
"""

import aiosqlite
from pathlib import Path
from app.config import settings
from app.logging import get_logger

logger = get_logger('database')

DATABASE_PATH = Path(settings.DATABASE_PATH)


async def _table_columns(db: aiosqlite.Connection, table_name: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def _table_create_sql(db: aiosqlite.Connection, table_name: str) -> str | None:
    cursor = await db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    sql = row[0]
    return str(sql) if sql else None


def _supports_guardian_delete_action_types(create_sql: str | None) -> bool:
    if not create_sql:
        return False
    normalized = " ".join(create_sql.lower().split())
    return "'entity_delete'" in normalized and "'relation_delete'" in normalized


async def _migrate_guardian_runs_drop_note_id(db: aiosqlite.Connection) -> None:
    guardian_columns = await _table_columns(db, "guardian_runs")
    if "note_id" not in guardian_columns:
        return

    logger.info("Applying migration: remove guardian_runs.note_id")
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute("SAVEPOINT guardian_runs_note_id_migration")
        await db.execute(
            """CREATE TABLE guardian_runs_new (
                id TEXT PRIMARY KEY,
                world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
                trigger_kind TEXT NOT NULL CHECK(trigger_kind IN ('note_scan', 'manual', 'api')),
                status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'failed', 'applied', 'partial')),
                request_json TEXT NOT NULL DEFAULT '{}',
                summary_json TEXT,
                error TEXT,
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        await db.execute(
            """INSERT INTO guardian_runs_new
               (id, world_id, trigger_kind, status, request_json, summary_json, error, started_at, completed_at, created_at, updated_at)
               SELECT id, world_id, trigger_kind, status, request_json, summary_json, error, started_at, completed_at, created_at, updated_at
               FROM guardian_runs"""
        )
        await db.execute("DROP TABLE guardian_runs")
        await db.execute("ALTER TABLE guardian_runs_new RENAME TO guardian_runs")
        await db.execute("DROP INDEX IF EXISTS idx_guardian_runs_note")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_guardian_runs_world_created ON guardian_runs(world_id, created_at DESC)"
        )
        await db.execute("RELEASE SAVEPOINT guardian_runs_note_id_migration")
    except Exception:
        await db.execute("ROLLBACK TO SAVEPOINT guardian_runs_note_id_migration")
        await db.execute("RELEASE SAVEPOINT guardian_runs_note_id_migration")
        raise
    finally:
        await db.execute("PRAGMA foreign_keys = ON")


async def _migrate_guardian_action_type_constraints(db: aiosqlite.Connection) -> None:
    actions_sql = await _table_create_sql(db, "guardian_actions")
    options_sql = await _table_create_sql(db, "guardian_mechanic_options")
    if not actions_sql or not options_sql:
        return

    actions_ok = _supports_guardian_delete_action_types(actions_sql)
    options_ok = _supports_guardian_delete_action_types(options_sql)
    if actions_ok and options_ok:
        return

    logger.info("Applying migration: expand guardian action_type constraints")
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute("SAVEPOINT guardian_action_type_migration")
        if not actions_ok:
            await db.execute(
                """CREATE TABLE guardian_actions_new (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES guardian_runs(id) ON DELETE CASCADE,
                    finding_id TEXT REFERENCES guardian_findings(id) ON DELETE SET NULL,
                    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
                    action_type TEXT NOT NULL
                        CHECK(action_type IN ('timeline_operation', 'entity_patch', 'relation_patch', 'entity_delete', 'relation_delete', 'world_patch', 'noop')),
                    op_type TEXT,
                    target_kind TEXT CHECK(target_kind IN ('entity', 'relation', 'world')),
                    target_id TEXT,
                    payload TEXT NOT NULL DEFAULT '{}',
                    rationale TEXT,
                    status TEXT NOT NULL DEFAULT 'proposed'
                        CHECK(status IN ('proposed', 'accepted', 'applied', 'rejected', 'failed')),
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            await db.execute(
                """INSERT INTO guardian_actions_new
                   (id, run_id, finding_id, world_id, action_type, op_type, target_kind, target_id, payload, rationale, status, error, created_at, updated_at)
                   SELECT id, run_id, finding_id, world_id, action_type, op_type, target_kind, target_id, payload, rationale, status, error, created_at, updated_at
                   FROM guardian_actions"""
            )
            await db.execute("DROP TABLE guardian_actions")
            await db.execute("ALTER TABLE guardian_actions_new RENAME TO guardian_actions")
            await db.execute("DROP INDEX IF EXISTS idx_guardian_actions_run_status")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guardian_actions_run_status ON guardian_actions(run_id, status, created_at)"
            )

        if not options_ok:
            await db.execute(
                """CREATE TABLE guardian_mechanic_options_new (
                    id TEXT PRIMARY KEY,
                    mechanic_run_id TEXT NOT NULL REFERENCES guardian_mechanic_runs(id) ON DELETE CASCADE,
                    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
                    run_id TEXT NOT NULL REFERENCES guardian_runs(id) ON DELETE CASCADE,
                    finding_id TEXT REFERENCES guardian_findings(id) ON DELETE SET NULL,
                    option_index INTEGER NOT NULL DEFAULT 0,
                    action_type TEXT NOT NULL
                        CHECK(action_type IN ('timeline_operation', 'entity_patch', 'relation_patch', 'entity_delete', 'relation_delete', 'world_patch', 'noop')),
                    op_type TEXT,
                    target_kind TEXT CHECK(target_kind IN ('entity', 'relation', 'world')),
                    target_id TEXT,
                    payload TEXT NOT NULL DEFAULT '{}',
                    rationale TEXT,
                    expected_outcome TEXT,
                    risk_level TEXT NOT NULL DEFAULT 'medium' CHECK(risk_level IN ('low', 'medium', 'high')),
                    confidence REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'proposed'
                        CHECK(status IN ('proposed', 'accepted', 'rejected', 'applied', 'failed')),
                    mapped_action_id TEXT REFERENCES guardian_actions(id) ON DELETE SET NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            await db.execute(
                """INSERT INTO guardian_mechanic_options_new
                   (id, mechanic_run_id, world_id, run_id, finding_id, option_index, action_type, op_type, target_kind, target_id, payload, rationale, expected_outcome, risk_level, confidence, status, mapped_action_id, error, created_at, updated_at)
                   SELECT id, mechanic_run_id, world_id, run_id, finding_id, option_index, action_type, op_type, target_kind, target_id, payload, rationale, expected_outcome, risk_level, confidence, status, mapped_action_id, error, created_at, updated_at
                   FROM guardian_mechanic_options"""
            )
            await db.execute("DROP TABLE guardian_mechanic_options")
            await db.execute("ALTER TABLE guardian_mechanic_options_new RENAME TO guardian_mechanic_options")
            await db.execute("DROP INDEX IF EXISTS idx_guardian_mechanic_options_run_status")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guardian_mechanic_options_run_status ON guardian_mechanic_options(mechanic_run_id, status, created_at)"
            )
            await db.execute("DROP INDEX IF EXISTS idx_guardian_mechanic_options_finding")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guardian_mechanic_options_finding ON guardian_mechanic_options(finding_id)"
            )

        await db.execute("RELEASE SAVEPOINT guardian_action_type_migration")
    except Exception:
        await db.execute("ROLLBACK TO SAVEPOINT guardian_action_type_migration")
        await db.execute("RELEASE SAVEPOINT guardian_action_type_migration")
        raise
    finally:
        await db.execute("PRAGMA foreign_keys = ON")


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
        entity_columns = await _table_columns(db, "entities")
        if "status" not in entity_columns:
            await db.execute(
                "ALTER TABLE entities ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )
        await db.commit()
        await _migrate_guardian_runs_drop_note_id(db)
        await _migrate_guardian_action_type_constraints(db)
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
