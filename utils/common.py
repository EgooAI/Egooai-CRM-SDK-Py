from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import event
from sqlmodel import SQLModel, create_engine


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


def bootstrap_engine(database_path: Optional[Path | str] = None):
    """统一完成数据库路径解析、engine 创建与自动建表。"""
    resolved_database_path = _resolve_database_path(database_path)
    engine = create_engine(f"sqlite:///{resolved_database_path.as_posix()}")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    return resolved_database_path, engine


__all__ = ["utc_now", "bootstrap_engine"]
