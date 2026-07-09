from pathlib import Path
from typing import Optional

from sqlalchemy import inspect
from sqlmodel import Session, select

from models import Customer
from utils.common import bootstrap_engine, get_database_lock, utc_now


class CustomerManager:
    """负责 Customer 表的连接初始化与增删改查操作。"""

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、获取共享 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)
        self._lock = get_database_lock(self.database_path)

    @staticmethod
    def _payload_tuple(customer: Customer) -> tuple[object, ...]:
        return (
            customer.name,
            customer.sex,
            customer.birthdate,
            customer.region,
            customer.extra,
            customer.image,
        )

    @staticmethod
    def _sync_customer_state(target: Customer, source: Customer) -> None:
        target.cid = source.cid
        target.created_time = source.created_time
        target.updated_time = source.updated_time

    @staticmethod
    def _apply_customer_updates(current_customer: Customer, customer: Customer) -> None:
        current_customer.name = customer.name
        current_customer.sex = customer.sex
        current_customer.birthdate = customer.birthdate
        current_customer.region = customer.region
        current_customer.extra = customer.extra
        current_customer.image = customer.image
        current_customer.updated_time = utc_now()

    def _find_matching_customer(self, session: Session, customer: Customer) -> Optional[Customer]:
        statement = select(Customer)
        for existing_customer in session.exec(statement).all():
            if self._payload_tuple(existing_customer) == self._payload_tuple(customer):
                return existing_customer
        return None

    def add_customer(self, customer: Customer) -> None:
        """向 Customer 表新增一条客户记录，并回填数据库生成的字段。"""
        with self._lock:
            with Session(self.engine) as session:
                session.add(customer)
                session.commit()
                session.refresh(customer)

    def upsert_customer(self, customer: Customer) -> None:
        """按主键或业务字段执行 UPSERT；完全重复的数据不会重复插入。"""
        with self._lock:
            with Session(self.engine) as session:
                if customer.cid is not None:
                    current_customer = session.get(Customer, customer.cid)
                    if current_customer is None:
                        raise ValueError(f"Customer {customer.cid} not found")

                    if self._payload_tuple(current_customer) == self._payload_tuple(customer):
                        self._sync_customer_state(customer, current_customer)
                        return

                    self._apply_customer_updates(current_customer, customer)
                    session.add(current_customer)
                    session.commit()
                    session.refresh(current_customer)
                    self._sync_customer_state(customer, current_customer)
                    return

                existing_customer = self._find_matching_customer(session, customer)
                if existing_customer is not None:
                    self._sync_customer_state(customer, existing_customer)
                    return

                session.add(customer)
                session.commit()
                session.refresh(customer)

    def delete_customer(self, cid: int) -> None:
        """按主键删除客户；如果记录不存在则直接返回。"""
        with self._lock:
            with Session(self.engine) as session:
                customer = session.get(Customer, cid)
                if customer is None:
                    return

                session.delete(customer)
                session.commit()

    def edit_customer(self, cid: int, customer: Customer) -> None:
        """按主键更新已有客户的可编辑字段，并刷新更新时间。"""
        with self._lock:
            with Session(self.engine) as session:
                current_customer = session.get(Customer, cid)
                if current_customer is None:
                    raise ValueError(f"Customer {cid} not found")

                self._apply_customer_updates(current_customer, customer)

                session.add(current_customer)
                session.commit()
                session.refresh(current_customer)

    def get_customer(self, cid: int) -> Optional[Customer]:
        """按主键查询单个客户，不存在时返回 None。"""
        with Session(self.engine) as session:
            return session.get(Customer, cid)

    def list_customer(self) -> list[Customer]:
        """查询并返回全部客户记录，结果按 cid 升序排列。"""
        with Session(self.engine) as session:
            cid_column = inspect(Customer).columns.cid
            statement = select(Customer).order_by(cid_column)
            return list(session.exec(statement).all())


__all__ = ["CustomerManager"]
