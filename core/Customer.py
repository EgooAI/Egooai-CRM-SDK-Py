from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from models import Customer
from utils.common import bootstrap_engine, utc_now


class CustomerManager:
    """负责 Customer 表的连接初始化与增删改查操作。"""

    def __init__(self, database_path: Optional[Path | str] = None) -> None:
        """读取数据库路径、创建 engine，并在表缺失时自动建表。"""
        self.database_path, self.engine = bootstrap_engine(database_path)

    def add_customer(self, customer: Customer) -> None:
        """向 Customer 表新增一条客户记录，并回填数据库生成的字段。"""
        with Session(self.engine) as session:
            session.add(customer)
            session.commit()
            session.refresh(customer)

    def delete_customer(self, cid: int) -> None:
        """按主键删除客户；如果记录不存在则直接返回。"""
        with Session(self.engine) as session:
            customer = session.get(Customer, cid)
            if customer is None:
                return

            session.delete(customer)
            session.commit()

    def edit_customer(self, cid: int, customer: Customer) -> None:
        """按主键更新已有客户的可编辑字段，并刷新更新时间。"""
        with Session(self.engine) as session:
            current_customer = session.get(Customer, cid)
            if current_customer is None:
                raise ValueError(f"Customer {cid} not found")

            current_customer.name = customer.name
            current_customer.sex = customer.sex
            current_customer.birthdate = customer.birthdate
            current_customer.region = customer.region
            current_customer.extra = customer.extra
            current_customer.image = customer.image
            current_customer.updated_time = utc_now()

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
            statement = select(Customer).order_by(Customer.cid)
            return list(session.exec(statement).all())


__all__ = ["CustomerManager"]
