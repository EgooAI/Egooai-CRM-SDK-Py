from pathlib import Path
from typing import Optional

from sqlalchemy import inspect
from sqlmodel import Session, select

from models.account_mapping import AccountMapping
from utils.common import bootstrap_engine


class AccountMappingManager:
    """负责 AccountMapping 表的连接初始化与增删改查操作。"""

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、创建 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)

    def add_account_mapping(self, account_mapping: AccountMapping) -> None:
        """向 AccountMapping 表新增一条映射记录，并回填数据库生成的字段。"""
        with Session(self.engine) as session:
            session.add(account_mapping)
            session.commit()
            session.refresh(account_mapping)

    def delete_account_mapping(self, amid: int) -> None:
        """按主键删除映射；如果记录不存在则直接返回。"""
        with Session(self.engine) as session:
            account_mapping = session.get(AccountMapping, amid)
            if account_mapping is None:
                return

            session.delete(account_mapping)
            session.commit()

    def edit_account_mapping(self, amid: int, account_mapping: AccountMapping) -> None:
        """按主键更新已有映射的可编辑字段。"""
        with Session(self.engine) as session:
            current_account_mapping = session.get(AccountMapping, amid)
            if current_account_mapping is None:
                raise ValueError(f"AccountMapping {amid} not found")

            current_account_mapping.aid = account_mapping.aid
            current_account_mapping.type = account_mapping.type
            current_account_mapping.key = account_mapping.key

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
