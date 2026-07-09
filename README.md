# EgooAI CRM SDK Py

一个基于 **SQLModel + SQLite** 的轻量本地 CRM 数据层，提供统一的数据模型、Manager CRUD / UPSERT 能力，以及线程安全的本地调度支持。

---

## 安装

### 环境要求
- Python `>=3.10,<4`

### 安装依赖

```bash
uv sync
```

---

## 公开入口

### Managers

```python
from core import (
    CustomerManager,
    AccountManager,
    AccountMappingManager,
    AgentPresetManager,
    PlatformManager,
    SessionMetaManager,
    MessageManager,
    TranslateManager,
    MetaManager,
)
```

### Models

```python
from models import (
    Customer,
    Account,
    AccountMapping,
    AgentPreset,
    Platform,
    SessionMeta,
    Message,
    Meta,
    Translate,
)
```

### Utilities

```python
from utils import (
    utc_now,
    resolve_database_path,
    get_database_lock,
    bootstrap_engine,
    ThreadPoolScheduler,
)
```

兼容入口：

```python
from scheduler import ThreadPoolScheduler
```

---

## 快速开始

```python
from pathlib import Path

from core import (
    AccountManager,
    CustomerManager,
    MessageManager,
    PlatformManager,
    SessionMetaManager,
)
from models import Account, Customer, Message, Platform, SessionMeta

db_path = Path("demo.sqlite")

platform_manager = PlatformManager(database_path=db_path)
customer_manager = CustomerManager(database_path=db_path)
account_manager = AccountManager(database_path=db_path)
session_meta_manager = SessionMetaManager(database_path=db_path)
message_manager = MessageManager(database_path=db_path)

platform = Platform(pid="wechat", name="WeChat")
platform_manager.add_platform(platform)

customer = Customer(name="Alice", sex="F", region="Shanghai")
customer_manager.add_customer(customer)

account = Account(
    cid=customer.cid,
    pid=platform.pid,
    account="alice@example.com",
    nickname="Alice",
)
account_manager.add_account(account)

session_meta = SessionMeta(name="session-a", participants=[account.aid])
session_meta_manager.add_session_meta(session_meta)

message = Message(
    extrenal_mid="msg-001",
    sid=session_meta.sid,
    sender=account.aid,
    read=False,
    content={"text": "hello"},
    type="text",
)
message_manager.add_message(message)
```

---

## 模型概览

- `Customer`：客户
- `Account`：账号
- `Platform`：平台
- `AccountMapping`：账号映射
- `SessionMeta`：会话元信息
- `Message`：消息
- `Meta`：元数据
- `Translate`：翻译缓存
- `AgentPreset`：Agent 预设

注意：
- `Message` 当前主键字段名是 `extrenal_mid`
- `AgentPreset.intelevel` 范围为 `0..4`

---

## Manager 约定

大多数 Manager 提供统一风格的方法：

- `add_*`：新增并回填主键/数据库生成字段
- `upsert_*`：按主键或 payload 去重并插入/更新
- `edit_*`：按主键更新，不存在时抛 `ValueError`
- `delete_*`：按主键删除，不存在时 no-op
- `get_*`：按主键查询，不存在时返回 `None`
- `list_*`：按主键升序返回全部记录

特殊情况：
- `MetaManager.get_version()` 在缺失时会自动创建默认记录
- `AgentPresetManager` 会校验 `intelevel` 范围

---

## Engine 生命周期与线程安全

核心实现位于：
- [utils/common.py](utils/common.py)

当前策略：

- 同一个 `resolved database_path` 在同一进程内共享同一个 engine
- 同一个数据库路径共享同一把进程内写锁
- 每个 manager 方法内部创建短生命周期 `Session`
- `Session` 不跨线程共享
- 写方法串行化，读方法可并发
- SQLite 使用：
  - `check_same_thread=False`
  - `timeout=30`
  - `PRAGMA foreign_keys=ON`

说明：
- `manager.engine.dispose()` 可重复调用
- dispose 后再次 `bootstrap_engine()` 会重建 engine
- 当前锁只保证**同一 Python 进程内**的串行化

---

## 线程池调度器

使用方式：

```python
from utils import ThreadPoolScheduler

with ThreadPoolScheduler(max_workers=4) as scheduler:
    future = scheduler.submit_manager_call(
        customer_manager,
        customer_manager.add_customer,
        customer,
    )
    future.result()
```

调度语义：

- 同一 `database_path` 的任务按提交顺序执行和完成
- 不同 `database_path` 的任务可并行
- 异常会在 `future.result()` 时重新抛出
- shutdown 后不能继续提交新任务
- 读取回填字段前，先等待 `future.result()`

---

## 工具函数

- `utc_now()`：返回带 `timezone.utc` 的当前时间
- `resolve_database_path()`：统一解析数据库路径
- `get_database_lock()`：获取某个数据库路径对应的共享进程内锁
- `bootstrap_engine()`：获取共享 engine 并自动建表
- `ThreadPoolScheduler`：同库串行、跨库并行的调度器

---

## 测试

运行全量测试：

```bash
python -m unittest discover tests
```

也可以单独运行：

```bash
python -m unittest tests.test_customer_manager
python -m unittest tests.test_scheduler
```

---

## 注意事项

- 当前项目是本地 SQLite 数据层，不是高并发数据库服务
- 同库写操作会被串行化
- 跨进程访问同一个 SQLite 文件时，仍依赖 SQLite 自身锁机制
- 推荐统一通过：
  - `core` 导入 manager
  - `models` 导入模型
  - `utils` 导入 engine / 锁 / 调度器 / 时间工具
