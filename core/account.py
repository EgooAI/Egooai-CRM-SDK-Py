from pathlib import Path
from typing import Optional

from sqlalchemy import inspect
from sqlmodel import Session, select

from models import Account
from utils.common import bootstrap_engine, utc_now


class AccountManager:
    """负责 Account 表的连接初始化与增删改查操作。"""

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、创建 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)

    @staticmethod
    def _payload_tuple(account: Account) -> tuple[object, ...]:
        return (
            account.cid,
            account.pid,
            account.account,
            account.nickname,
            account.avatar,
            account.sids,
            account.extra,
        )

    @staticmethod
    def _sync_account_state(target: Account, source: Account) -> None:
        target.aid = source.aid
        target.created_time = source.created_time
        target.updated_time = source.updated_time

    @staticmethod
    def _apply_account_updates(current_account: Account, account: Account) -> None:
        current_account.cid = account.cid
        current_account.pid = account.pid
        current_account.account = account.account
        current_account.nickname = account.nickname
        current_account.avatar = account.avatar
        current_account.sids = account.sids
        current_account.extra = account.extra
        current_account.updated_time = utc_now()

    def _find_matching_account(self, session: Session, account: Account) -> Optional[Account]:
        statement = select(Account)
        for existing_account in session.exec(statement).all():
            if self._payload_tuple(existing_account) == self._payload_tuple(account):
                return existing_account
        return None

    def add_account(self, account: Account) -> None:
        """向 Account 表新增一条账号记录，并回填数据库生成的字段。"""
        with Session(self.engine) as session:
            session.add(account)
            session.commit()
            session.refresh(account)

    def upsert_account(self, account: Account) -> None:
        """按主键或业务字段执行 UPSERT；完全重复的数据不会重复插入。"""
        with Session(self.engine) as session:
            if account.aid is not None:
                current_account = session.get(Account, account.aid)
                if current_account is None:
                    raise ValueError(f"Account {account.aid} not found")

                if self._payload_tuple(current_account) == self._payload_tuple(account):
                    self._sync_account_state(account, current_account)
                    return

                self._apply_account_updates(current_account, account)
                session.add(current_account)
                session.commit()
                session.refresh(current_account)
                self._sync_account_state(account, current_account)
                return

            existing_account = self._find_matching_account(session, account)
            if existing_account is not None:
                self._sync_account_state(account, existing_account)
                return

            session.add(account)
            session.commit()
            session.refresh(account)

    def delete_account(self, aid: int) -> None:
        """按主键删除账号；如果记录不存在则直接返回。"""
        with Session(self.engine) as session:
            account = session.get(Account, aid)
            if account is None:
                return

            session.delete(account)
            session.commit()

    def edit_account(self, aid: int, account: Account) -> None:
        """按主键更新已有账号的可编辑字段，并刷新更新时间。"""
        with Session(self.engine) as session:
            current_account = session.get(Account, aid)
            if current_account is None:
                raise ValueError(f"Account {aid} not found")

            self._apply_account_updates(current_account, account)

            session.add(current_account)
            session.commit()
            session.refresh(current_account)

    def get_account(self, aid: int) -> Optional[Account]:
        """按主键查询单个账号，不存在时返回 None。"""
        with Session(self.engine) as session:
            return session.get(Account, aid)

    def list_account(self) -> list[Account]:
        """查询并返回全部账号记录，结果按 aid 升序排列。"""
        with Session(self.engine) as session:
            aid_column = inspect(Account).columns.aid
            statement = select(Account).order_by(aid_column)
            return list(session.exec(statement).all())


__all__ = ["AccountManager"]
