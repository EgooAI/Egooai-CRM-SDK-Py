from pathlib import Path
from typing import Optional

from sqlalchemy import inspect
from sqlmodel import Session, select

from models.account_mapping import AccountMapping
from utils.common import bootstrap_engine, get_database_lock


class AccountMappingManager:
    """负责 AccountMapping 表的连接初始化与增删改查操作。"""

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、获取共享 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    @staticmethod
    def _payload_tuple(account_mapping: AccountMapping) -> tuple[object, ...]:
        return (account_mapping.aid, account_mapping.type, account_mapping.key)

    @staticmethod
    def _sync_account_mapping_state(target: AccountMapping, source: AccountMapping) -> None:
        target.amid = source.amid

    @staticmethod
    def _apply_account_mapping_updates(current_account_mapping: AccountMapping, account_mapping: AccountMapping) -> None:
        current_account_mapping.aid = account_mapping.aid
        current_account_mapping.type = account_mapping.type
        current_account_mapping.key = account_mapping.key

    def _find_matching_account_mapping(self, session: Session, account_mapping: AccountMapping) -> Optional[AccountMapping]:
        statement = select(AccountMapping)
        for existing_account_mapping in session.exec(statement).all():
            if self._payload_tuple(existing_account_mapping) == self._payload_tuple(account_mapping):
                return existing_account_mapping
        return None

    def add_account_mapping(self, account_mapping: AccountMapping) -> None:
        """向 AccountMapping 表新增一条映射记录，并回填数据库生成的字段。"""
        with self._lock:
            with Session(self.engine) as session:
                session.add(account_mapping)
                session.commit()
                session.refresh(account_mapping)

    def upsert_account_mapping(self, account_mapping: AccountMapping) -> None:
        """按主键或业务字段执行 UPSERT；完全重复的数据不会重复插入。"""
        with self._lock:
            with Session(self.engine) as session:
                if account_mapping.amid is not None:
                    current_account_mapping = session.get(AccountMapping, account_mapping.amid)
                    if current_account_mapping is None:
                        raise ValueError(f"AccountMapping {account_mapping.amid} not found")

                    if self._payload_tuple(current_account_mapping) == self._payload_tuple(account_mapping):
                        self._sync_account_mapping_state(account_mapping, current_account_mapping)
                        return

                    self._apply_account_mapping_updates(current_account_mapping, account_mapping)
                    session.add(current_account_mapping)
                    session.commit()
                    session.refresh(current_account_mapping)
                    self._sync_account_mapping_state(account_mapping, current_account_mapping)
                    return

                existing_account_mapping = self._find_matching_account_mapping(session, account_mapping)
                if existing_account_mapping is not None:
                    self._sync_account_mapping_state(account_mapping, existing_account_mapping)
                    return

                session.add(account_mapping)
                session.commit()
                session.refresh(account_mapping)

    def delete_account_mapping(self, amid: int) -> None:
        """按主键删除映射；如果记录不存在则直接返回。"""
        with self._lock:
            with Session(self.engine) as session:
                account_mapping = session.get(AccountMapping, amid)
                if account_mapping is None:
                    return

                session.delete(account_mapping)
                session.commit()

    def edit_account_mapping(self, amid: int, account_mapping: AccountMapping) -> None:
        """按主键更新已有映射的可编辑字段。"""
        with self._lock:
            with Session(self.engine) as session:
                current_account_mapping = session.get(AccountMapping, amid)
                if current_account_mapping is None:
                    raise ValueError(f"AccountMapping {amid} not found")

                self._apply_account_mapping_updates(current_account_mapping, account_mapping)

                session.add(current_account_mapping)
                session.commit()
                session.refresh(current_account_mapping)

    def get_account_mapping(self, amid: int) -> Optional[AccountMapping]:
        """按主键查询单条映射，不存在时返回 None。"""
        with Session(self.engine) as session:
            return session.get(AccountMapping, amid)

    def list_account_mapping(self) -> list[AccountMapping]:
        """查询并返回全部映射记录，结果按 amid 升序排列。"""
        with Session(self.engine) as session:
            amid_column = inspect(AccountMapping).columns.amid
            statement = select(AccountMapping).order_by(amid_column)
            return list(session.exec(statement).all())


__all__ = ["AccountMappingManager"]
