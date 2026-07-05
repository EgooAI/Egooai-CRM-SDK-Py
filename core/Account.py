from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from models import Account
from models.Customer import utc_now

from . import bootstrap_engine


class AccountManager:
    """负责 Account 表的连接初始化与增删改查操作。"""

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        """读取数据库配置、创建 engine，并在表缺失时自动建表。"""
        self.config_path, self.database_path, self.engine = bootstrap_engine(config_path)

    def add_account(self, account: Account) -> None:
        """向 Account 表新增一条账号记录，并回填数据库生成的字段。"""
        with Session(self.engine) as session:
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

            current_account.cid = account.cid
            current_account.pid = account.pid
            current_account.account = account.account
            current_account.nickname = account.nickname
            current_account.avatar = account.avatar
            current_account.extra = account.extra
            current_account.updated_time = utc_now()

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
            statement = select(Account).order_by(Account.aid)
            return list(session.exec(statement).all())


__all__ = ["AccountManager"]
