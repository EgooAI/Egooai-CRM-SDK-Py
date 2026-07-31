from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

_SYSTEM_AGENT_SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "system_agents.sql"


def _default_agentpreset_schema_sql() -> str:
    return """
    CREATE TABLE agentpreset (
        apid TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        prompt TEXT NOT NULL,
        intelevel INTEGER NOT NULL,
        tools TEXT NOT NULL
    )
    """


@lru_cache(maxsize=1)
def _load_system_agent_apids() -> tuple[str, ...]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(_default_agentpreset_schema_sql())
        connection.executescript(_SYSTEM_AGENT_SQL_PATH.read_text(encoding="utf-8"))
        rows = connection.execute(
            """
            SELECT apid
            FROM agentpreset
            ORDER BY rowid
            """
        ).fetchall()
        return tuple(str(row[0]) for row in rows)
    finally:
        connection.close()


(
    CHAT_TRANSLATION_AGENT_APID,
    CHAT_REPLY_SUGGESTION_AGENT_APID,
    CHAT_CUSTOMER_INTENT_AGENT_APID,
    CHAT_CUSTOMER_STAGE_AGENT_APID,
) = _load_system_agent_apids()

SYSTEM_AGENT_APID_ORDER = _load_system_agent_apids()
SYSTEM_AGENT_APIDS = frozenset(_load_system_agent_apids())


__all__ = [
    "CHAT_CUSTOMER_INTENT_AGENT_APID",
    "CHAT_CUSTOMER_STAGE_AGENT_APID",
    "CHAT_REPLY_SUGGESTION_AGENT_APID",
    "CHAT_TRANSLATION_AGENT_APID",
    "SYSTEM_AGENT_APID_ORDER",
    "SYSTEM_AGENT_APIDS",
]
