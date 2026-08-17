from __future__ import annotations

from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
from threading import RLock
from types import MethodType
from typing import Any, Deque, Generic, Optional, TypeVar

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

K = TypeVar("K")
V = TypeVar("V")


class _ThreadSafeRegistry(Generic[K, V]):
    """一个最小线程安全注册表。

    用于按 key 复用进程内共享对象，例如：
    - SQLite engine
    - 按数据库路径共享的锁
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._items: dict[K, V] = {}

    def get_or_create(self, key: K, factory: Callable[[], V]) -> V:
        """线程安全地获取对象；若不存在则通过 factory 创建并缓存。"""
        with self._lock:
            value = self._items.get(key)
            if value is None:
                value = factory()
                self._items[key] = value
            return value

    def pop_if_identity(self, key: K, candidate: V) -> None:
        """仅当当前缓存值与 candidate 是同一对象时才移除。"""
        with self._lock:
            current = self._items.get(key)
            if current is candidate:
                self._items.pop(key, None)


@dataclass
class _QueuedTask:
    """调度器内部任务单元。"""

    future: Future
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


@dataclass
class _LaneState:
    """单个数据库路径对应的调度 lane 状态。"""

    lock: RLock = field(default_factory=RLock)
    queue: Deque[_QueuedTask] = field(default_factory=deque)
    running: bool = False


# 按数据库绝对路径共享的 engine 注册表。
_SHARED_ENGINES = _ThreadSafeRegistry[Path, Engine]()

# 按数据库绝对路径共享的进程内锁注册表。
_DATABASE_LOCKS = _ThreadSafeRegistry[Path, Any]()


def utc_now() -> datetime:
    """返回当前 UTC 时间，供模型默认值和更新时间使用。"""
    return datetime.now(timezone.utc)


def resolve_database_path(database_path: Optional[Path | str] = None) -> Path:
    """解析 sqlite 数据库文件路径；未传入时默认使用 data/crm.sqlite。"""
    if database_path is not None:
        resolved_path = Path(database_path).resolve()
    else:
        default_path = os.environ.get("MAA_CRM_DB_PATH", "data/crm.sqlite")
        resolved_path = Path(default_path).resolve()

    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    return resolved_path


def _attach_shared_dispose(engine: Engine, database_path: Path) -> Engine:
    """为共享 engine 打补丁，使 dispose 时同步清理共享注册表。"""
    original_dispose = engine.dispose

    def _shared_dispose(self) -> None:
        _SHARED_ENGINES.pop_if_identity(database_path, self)
        original_dispose()

    engine.dispose = MethodType(_shared_dispose, engine)
    return engine


def _create_shared_engine(database_path: Path) -> Engine:
    """Create a configured SQLite engine and build the schema."""
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


def get_database_lock(database_path: Path | str) -> Any:
    """获取某个数据库路径对应的共享进程内锁。"""
    resolved_database_path = resolve_database_path(database_path)
    return _DATABASE_LOCKS.get_or_create(resolved_database_path, RLock)


def bootstrap_engine(database_path: Optional[Path | str] = None):
    """统一完成数据库路径解析、共享 engine 获取与自动建表。"""
    resolved_database_path = resolve_database_path(database_path)
    engine = _SHARED_ENGINES.get_or_create(
        resolved_database_path,
        lambda: _create_shared_engine(resolved_database_path),
    )
    return resolved_database_path, engine


class ThreadPoolScheduler:
    """同库串行、跨库并行的线程池调度器。"""

    def __init__(self, max_workers: int = 4) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be greater than 0")
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lanes_lock = RLock()
        self._lanes: dict[Path, _LaneState] = {}
        self._shutdown = False

    def __enter__(self) -> ThreadPoolScheduler:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown(wait=True)

    def _get_lane(self, database_path: Path | str) -> tuple[Path, _LaneState]:
        resolved_database_path = resolve_database_path(database_path)
        with self._lanes_lock:
            lane = self._lanes.get(resolved_database_path)
            if lane is None:
                lane = _LaneState()
                self._lanes[resolved_database_path] = lane
        return resolved_database_path, lane

    def submit(self, database_path: Path | str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        resolved_database_path, lane = self._get_lane(database_path)
        future: Future = Future()
        task = _QueuedTask(future=future, func=func, args=args, kwargs=kwargs)

        with lane.lock:
            if self._shutdown:
                raise RuntimeError("ThreadPoolScheduler has been shut down")
            lane.queue.append(task)
            if not lane.running:
                lane.running = True
                self._executor.submit(self._run_lane, resolved_database_path, lane)

        return future

    def submit_manager_call(self, manager: Any, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        database_path = getattr(manager, "database_path", None)
        if database_path is None:
            raise ValueError("manager must expose database_path")
        return self.submit(database_path, func, *args, **kwargs)

    def _run_lane(self, database_path: Path, lane: _LaneState) -> None:
        while True:
            with lane.lock:
                if not lane.queue:
                    lane.running = False
                    return
                task = lane.queue.popleft()

            if task.future.cancelled():
                continue

            try:
                result = task.func(*task.args, **task.kwargs)
            except BaseException as exc:
                task.future.set_exception(exc)
            else:
                task.future.set_result(result)

    def shutdown(self, wait: bool = True) -> None:
        with self._lanes_lock:
            self._shutdown = True
        self._executor.shutdown(wait=wait)


__all__ = [
    "utc_now",
    "resolve_database_path",
    "get_database_lock",
    "bootstrap_engine",
    "ThreadPoolScheduler",
]
