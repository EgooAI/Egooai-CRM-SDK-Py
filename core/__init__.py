from pathlib import Path
from typing import Dict, Optional

from sqlmodel import SQLModel, create_engine


def _resolve_config_path(config_path: Optional[Path | str] = None) -> Path:
    """解析数据库配置文件路径；未传入时默认使用项目根目录下的 sql.yml。"""
    if config_path is not None:
        return Path(config_path).resolve()
    return Path(__file__).resolve().parent.parent / "sql.yml"


def _read_sql_config(config_path: Path) -> Dict[str, str]:
    """解析 sql.yml 中简单的 key:value 配置。"""
    if not config_path.exists():
        raise FileNotFoundError(f"sql config not found: {config_path}")

    config: Dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        config[key.strip()] = value.strip().strip('"\'')

    return config


def _load_database_path(config_path: Path) -> Path:
    """从 sql.yml 中读取 sqlite 路径并转换成绝对路径。"""
    config = _read_sql_config(config_path)
    db_type = config.get("type")
    db_path = config.get("path")

    if db_type != "sqlite":
        raise ValueError(f"Unsupported database type: {db_type}")
    if not db_path:
        raise ValueError("Missing 'path' in sql.yml")

    resolved_path = (config_path.parent / db_path).resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    return resolved_path


def bootstrap_engine(config_path: Optional[Path | str] = None):
    """统一完成配置路径解析、数据库路径读取、engine 创建与自动建表。"""
    resolved_config_path = _resolve_config_path(config_path)
    database_path = _load_database_path(resolved_config_path)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    SQLModel.metadata.create_all(engine)
    return resolved_config_path, database_path, engine


from .Account import AccountManager
from .Customer import CustomerManager
from .Platform import PlatformManager

__all__ = ["CustomerManager", "AccountManager", "PlatformManager", "bootstrap_engine"]
