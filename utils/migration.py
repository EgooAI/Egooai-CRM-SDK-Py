"""Versioned schema migrations for the SDK SQLite database.

Migrations run automatically after ``create_all`` inside ``bootstrap_engine``.
The current schema version is stored in the ``meta`` table under the
``schema_version`` key, so every migration is applied exactly once per database.
Only additive and idempotent DDL/DML is used so existing databases upgrade in
place while fresh databases converge to the same schema.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Callable

from sqlalchemy import Connection, Engine

logger = logging.getLogger(__name__)


def _table_exists(conn: Connection, table: str) -> bool:
    row = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: Connection, table: str, column: str) -> bool:
    for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall():
        if row[1] == column:
            return True
    return False


def _index_exists(conn: Connection, index: str) -> bool:
    row = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
        (index,),
    ).fetchone()
    return row is not None


def _ensure_version_table(conn: Connection) -> None:
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "id INTEGER NOT NULL PRIMARY KEY CHECK (id = 1), "
        "version INTEGER NOT NULL)"
    )


def _read_schema_version(conn: Connection) -> int:
    _ensure_version_table(conn)
    row = conn.exec_driver_sql(
        "SELECT version FROM schema_version WHERE id = 1",
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _write_schema_version(conn: Connection, version: int) -> None:
    _ensure_version_table(conn)
    conn.exec_driver_sql(
        "INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, ?)",
        (version,),
    )


def _coerce_epoch(value: object) -> float:
    """Best-effort normalization of heterogeneous timestamps to epoch seconds."""
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, (bytes, bytearray)):
        try:
            number = float(value.decode("utf-8", errors="ignore").strip())
        except ValueError:
            return 0.0
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return 0.0
        try:
            number = float(text)
        except ValueError:
            try:
                return datetime.datetime.fromisoformat(text).timestamp()
            except ValueError:
                return 0.0
    else:
        return 0.0
    return number / 1000.0 if number > 10**12 else number


# -- Pre-flight renames (must run before create_all) ---------------------------


def run_preflight_renames(engine: Engine) -> None:
    """Rename legacy tables before ``create_all`` so the models are authoritative."""
    with engine.begin() as conn:
        if _table_exists(conn, "message_test") and not _table_exists(conn, "chat_history"):
            conn.exec_driver_sql("ALTER TABLE message_test RENAME TO chat_history")
            logger.info("Renamed legacy table message_test -> chat_history")


# -- Versioned migrations -------------------------------------------------------

MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = []


def _migrate_0001_drop_llm_text_columns(conn: Connection) -> None:
    for column in ("context_limit_output_text", "tool_round_limit_output_text"):
        if _column_exists(conn, "llm_api_config", column):
            conn.exec_driver_sql(f"ALTER TABLE llm_api_config DROP COLUMN {column}")


def _migrate_0002_message_created_at(conn: Connection) -> None:
    if not _column_exists(conn, "message", "created_at"):
        conn.exec_driver_sql("ALTER TABLE message ADD COLUMN created_at DATETIME")

    rows = conn.exec_driver_sql("SELECT external_mid, content FROM message").fetchall()
    for external_mid, content in rows:
        if content is None:
            continue
        try:
            payload = json.loads(content)
        except (TypeError, ValueError):
            continue
        epoch = _coerce_epoch(payload.get("created_at"))
        if not epoch:
            continue
        created_at = datetime.datetime.fromtimestamp(epoch).isoformat()
        conn.exec_driver_sql(
            "UPDATE message SET created_at = ? WHERE external_mid = ?",
            (created_at, external_mid),
        )

    if not _index_exists(conn, "idx_message_sid"):
        conn.exec_driver_sql("CREATE INDEX idx_message_sid ON message(sid)")


def _migrate_0003_session_meta_key(conn: Connection) -> None:
    if not _column_exists(conn, "sessionmeta", "key"):
        conn.exec_driver_sql("ALTER TABLE sessionmeta ADD COLUMN key VARCHAR")

    conn.exec_driver_sql(
        "UPDATE sessionmeta SET key = name WHERE key IS NULL OR key = ''"
    )

    if not _index_exists(conn, "idx_session_meta_key"):
        conn.exec_driver_sql("CREATE INDEX idx_session_meta_key ON sessionmeta(key)")


def _migrate_0004_lookup_indexes(conn: Connection) -> None:
    if not _index_exists(conn, "idx_account_mapping_type_key"):
        conn.exec_driver_sql('CREATE INDEX idx_account_mapping_type_key ON accountmapping(type, "key")')
    if not _index_exists(conn, "idx_account_cid_pid_account"):
        conn.exec_driver_sql("CREATE INDEX idx_account_cid_pid_account ON account(cid, pid, account)")


MIGRATIONS.extend(
    [
        (1, "drop orphan llm_api_config text columns", _migrate_0001_drop_llm_text_columns),
        (2, "add message.created_at and index on message.sid", _migrate_0002_message_created_at),
        (3, "add session_meta.key with backfill and index", _migrate_0003_session_meta_key),
        (4, "add lookup indexes for account mapping and account", _migrate_0004_lookup_indexes),
    ]
)


def run_migrations(engine: Engine) -> None:
    """Apply all pending migrations in version order."""
    with engine.begin() as conn:
        current = _read_schema_version(conn)
    for version, description, migrate in MIGRATIONS:
        if version <= current:
            continue
        with engine.begin() as conn:
            migrate(conn)
            _write_schema_version(conn, version)
        logger.info("Applied schema migration %03d: %s", version, description)


__all__ = ["MIGRATIONS", "run_migrations", "run_preflight_renames"]