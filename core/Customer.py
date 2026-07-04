from pathlib import Path
from typing import Dict, Optional

from sqlmodel import SQLModel, Session, create_engine, select

from models import Customer
from models.Customer import utc_now


class CustomerManager:
    """负责 Customer 表的连接初始化与增删改查操作。"""

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        """读取数据库配置、创建 engine，并在表缺失时自动建表。"""
        self.config_path = (
            Path(config_path).resolve()
            if config_path is not None
            else Path(__file__).resolve().parent.parent / "sql.yml"
        )
        self.database_path = self._load_database_path()
        self.engine = create_engine(f"sqlite:///{self.database_path.as_posix()}")
        SQLModel.metadata.create_all(self.engine)

    def _load_database_path(self) -> Path:
        """从 sql.yml 中读取 sqlite 路径并转换成绝对路径。"""
        config = self._read_sql_config()
        db_type = config.get("type")
        db_path = config.get("path")

        if db_type != "sqlite":
            raise ValueError(f"Unsupported database type: {db_type}")
        if not db_path:
            raise ValueError("Missing 'path' in sql.yml")

        resolved_path = (self.config_path.parent / db_path).resolve()
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        return resolved_path

    def _read_sql_config(self) -> Dict[str, str]:
        """解析 sql.yml 中简单的 key:value 配置。"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"sql config not found: {self.config_path}")

        config: Dict[str, str] = {}
        for raw_line in self.config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            config[key.strip()] = value.strip().strip('"\'')

        return config

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
