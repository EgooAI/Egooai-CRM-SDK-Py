from __future__ import annotations

from pathlib import Path
from typing import Generic, Optional, TypeVar

from sqlmodel import Session, select, SQLModel

from utils.common import bootstrap_engine, get_database_lock, utc_now

M = TypeVar("M", bound=SQLModel)


class BaseManager(Generic[M]):
    """SQLModel 单表的通用 CRUD 基类。

    子类通过类属性声明表元数据，通用增删改查在基类实现；子类保留具名方法
    （一行委托）以维持稳定的公共 API。

    - ``pk_field``：主键字段名。
    - ``editable_fields``：更新时写入的字段，同时参与 upsert 的 payload 比较。
    - ``state_fields``：upsert 相等/命中路径回填到入参对象的字段（如时间戳）。
    - ``touch_updated_time``：更新时是否刷新 ``updated_time``。
    - ``match_fields``：主键为空时的查重方式；``None`` 表示直接插入，
      ``()`` 表示全表扫描 payload 比对，非空元组表示按这些字段查询后 payload 比对。
    - ``adopt_on_key_match``：按 ``match_fields`` 命中第一条即采纳，不比较 payload。
    - ``pk_is_auto``：自增主键为 True（主键缺失时抛错）；业务主键为 False
      （记录不存在时直接插入）。
    """

    model: type[M]
    pk_field: str
    editable_fields: tuple[str, ...]
    state_fields: tuple[str, ...] = ()
    touch_updated_time: bool = False
    match_fields: Optional[tuple[str, ...]] = None
    adopt_on_key_match: bool = False
    pk_is_auto: bool = True

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、获取共享 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    def _payload_tuple(self, obj: M) -> tuple[object, ...]:
        return tuple(getattr(obj, field) for field in self.editable_fields)

    def _sync_state(self, target: M, source: M) -> None:
        setattr(target, self.pk_field, getattr(source, self.pk_field))
        for field in self.state_fields:
            setattr(target, field, getattr(source, field))

    def _apply_updates(self, current: M, obj: M) -> None:
        for field in self.editable_fields:
            setattr(current, field, getattr(obj, field))
        if self.touch_updated_time:
            current.updated_time = utc_now()

    def _find_matching(self, session: Session, obj: M) -> Optional[M]:
        if self.match_fields is None:
            return None
        if self.adopt_on_key_match and not getattr(obj, self.match_fields[0]):
            return None
        statement = select(self.model)
        for field in self.match_fields:
            statement = statement.where(getattr(self.model, field) == getattr(obj, field))
        rows = list(session.exec(statement).all())
        if self.adopt_on_key_match:
            return rows[0] if rows else None
        payload = self._payload_tuple(obj)
        for row in rows:
            if self._payload_tuple(row) == payload:
                return row
        return None

    def _add(self, obj: M) -> None:
        """向表中新增一条记录，并回填数据库生成的字段。"""
        with self._lock:
            with Session(self.engine) as session:
                session.add(obj)
                session.commit()
                session.refresh(obj)

    def _upsert(self, obj: M) -> None:
        """按主键或业务字段执行 UPSERT；完全重复的数据不会重复插入。"""
        with self._lock:
            with Session(self.engine) as session:
                pk_value = getattr(obj, self.pk_field)
                if self.pk_is_auto:
                    if pk_value is None:
                        existing = self._find_matching(session, obj)
                        if existing is not None:
                            self._sync_state(obj, existing)
                            return
                        session.add(obj)
                        session.commit()
                        session.refresh(obj)
                        return
                    current = session.get(self.model, pk_value)
                    if current is None:
                        raise ValueError(f"{self.model.__name__} {pk_value} not found")
                else:
                    current = session.get(self.model, pk_value)
                    if current is None:
                        session.add(obj)
                        session.commit()
                        session.refresh(obj)
                        return

                if self._payload_tuple(current) == self._payload_tuple(obj):
                    self._sync_state(obj, current)
                    return

                self._apply_updates(current, obj)
                session.add(current)
                session.commit()
                session.refresh(current)
                self._sync_state(obj, current)

    def _delete(self, pk_value) -> None:
        """按主键删除记录；如果记录不存在则直接返回。"""
        with self._lock:
            with Session(self.engine) as session:
                current = session.get(self.model, pk_value)
                if current is None:
                    return

                session.delete(current)
                session.commit()

    def _edit(self, pk_value, obj: M) -> None:
        """按主键更新已有记录的可编辑字段，并按需刷新更新时间。"""
        with self._lock:
            with Session(self.engine) as session:
                current = session.get(self.model, pk_value)
                if current is None:
                    raise ValueError(f"{self.model.__name__} {pk_value} not found")

                self._apply_updates(current, obj)

                session.add(current)
                session.commit()
                session.refresh(current)

    def _get(self, pk_value) -> Optional[M]:
        """按主键查询单条记录，不存在时返回 None。"""
        with Session(self.engine) as session:
            return session.get(self.model, pk_value)

    def _list(self) -> list[M]:
        """查询并返回全部记录，结果按主键升序排列。"""
        with Session(self.engine) as session:
            statement = select(self.model).order_by(getattr(self.model, self.pk_field))
            return list(session.exec(statement).all())


__all__ = ["BaseManager"]
