# EgooAI CRM SDK Py

本项目使用 **uv** 管理 Python 依赖。

## 环境准备

1. 安装 uv
2. 在项目根目录执行：

```bash
uv sync
```

这会根据 [pyproject.toml](pyproject.toml) 和 [uv.lock](uv.lock) 创建并同步依赖环境。

## 运行测试

在项目根目录执行：

```bash
uv run -m unittest discover -s tests
```

当前测试覆盖了 `CustomerManager` 和 `AccountManager` 的建表与增删改查流程，并包含 `Account` 测试数据插入用例。

## 相关文件

- [pyproject.toml](pyproject.toml) — 项目依赖声明
- [uv.lock](uv.lock) — uv 生成的依赖锁文件
- [sql.yml](sql.yml) — SQLite 数据库配置
- [db.sqlite](db.sqlite) — 本地 SQLite 数据库文件
