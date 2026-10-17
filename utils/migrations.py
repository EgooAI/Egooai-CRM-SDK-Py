"""SDK-owned additive schema migrations.

``SQLModel.metadata.create_all`` only creates missing tables; it never adds a
new column to an existing table. Additive SDK column migrations live here and
run idempotently right after ``create_all`` when a shared engine is built.
Only nullable columns or columns with a literal default belong here.
"""

from __future__ import annotations

from sqlalchemy.engine import Engine

# (table, column, column definition) — append new additive columns here.
_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("agentpreset", "enabled", "BOOLEAN NOT NULL DEFAULT 1"),
)


def run_schema_migrations(engine: Engine) -> None:
    with engine.begin() as connection:
        for table, column, definition in _ADDITIVE_COLUMNS:
            existing = {
                row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if not existing or column in existing:
                continue
            connection.exec_driver_sql(
                f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}'
            )


__all__ = ["run_schema_migrations"]
