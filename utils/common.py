from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from types import MethodType
from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

_ENGINE_LOCK = RLock()
_SHARED_ENGINES: dict[Path, Engine] = {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_database_path(database_path: Optional[Path | str] = None) -> Path:
    """解析 sqlite 数据库文件路径；未传入时默认使用项目根目录下的 db.sqlite。"""
    if database_path is not None:
        resolved_path = Path(database_path).resolve()
    else:
        resolved_path = (Path(__file__).resolve().parent.parent / "db.sqlite").resolve()

    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    return resolved_path


def _attach_shared_dispose(engine: Engine, database_path: Path) -> Engine:
    original_dispose = engine.dispose

    def _shared_dispose(self) -> None:
        with _ENGINE_LOCK:
            if _SHARED_ENGINES.get(database_path) is self:
                _SHARED_ENGINES.pop(database_path, None)
        original_dispose()

    engine.dispose = MethodType(_shared_dispose, engine)
    return engine


def _create_shared_engine(database_path: Path) -> Engine:
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    return _attach_shared_dispose(engine, database_path)


def bootstrap_engine(database_path: Optional[Path | str] = None):
    """统一完成数据库路径解析、共享 engine 获取与自动建表。"""
    resolved_database_path = _resolve_database_path(database_path)

    with _ENGINE_LOCK:
        engine = _SHARED_ENGINES.get(resolved_database_path)
        if engine is None:
            engine = _create_shared_engine(resolved_database_path)
            _SHARED_ENGINES[resolved_database_path] = engine

    return resolved_database_path, engine


__all__ = ["utc_now", "bootstrap_engine"]
