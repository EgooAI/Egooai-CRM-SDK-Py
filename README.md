# EgooAI CRM SDK Py

基于 **SQLModel + SQLite** 的本地 CRM 数据层 SDK。本文主要面向调用方，快速说明可导入对象、模型字段、Manager 方法、UPSERT 行为、内存注册表和调度接口。

## 安装与运行

要求：Python `>=3.10,<4`

```bash
uv sync
```

不使用 `uv` 时，安装 `pyproject.toml` 中声明的依赖即可。

## 公开导入

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

### Registries

```python
from core import (
    LLMConfig,
    register_tool,
    register_llm,
    tool_registry,
    llm_registry,
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
from config.scheduler import ThreadPoolScheduler
```

## 快速示例

```python
from pathlib import Path

from core import AccountManager, CustomerManager, MessageManager, PlatformManager, SessionMetaManager
from models import Account, Customer, Message, Platform, SessionMeta

db_path = Path("demo.sqlite")

platform_manager = PlatformManager(database_path=db_path)
customer_manager = CustomerManager(database_path=db_path)
account_manager = AccountManager(database_path=db_path)
session_meta_manager = SessionMetaManager(database_path=db_path)
message_manager = MessageManager(database_path=db_path)

platform = Platform(pid="alibaba", name="Alibaba")
platform_manager.upsert_platform(platform)

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
    external_mid="msg-001",
    sid=session_meta.sid,
    sender=account.aid,
    read=False,
    content={"text": "hello"},
    type="text",
)
message_manager.upsert_message(message)
```

## 数据模型

### Customer

```python
Customer(
    cid: int | None = None,        # PK, DB generated
    name: str | None = None,
    sex: str | None = None,
    birthdate: date | None = None,
    region: str | None = None,
    extra: dict | None = None,
    image: dict | None = None,
    created_time: datetime = utc_now(),
    updated_time: datetime = utc_now(),
)
```

### Account

```python
Account(
    aid: int | None = None,        # PK, DB generated
    cid: int,                      # required FK -> Customer.cid
    pid: str | None = None,        # FK -> Platform.pid
    account: str | None = None,
    nickname: str | None = None,
    avatar: str | None = None,
    sids: list[int] | None = None,
    extra: dict | None = None,
    created_time: datetime = utc_now(),
    updated_time: datetime = utc_now(),
)
```

### Platform

```python
Platform(
    pid: str,                      # PK
    name: str,
    extra: dict | None = None,
    created_time: datetime = utc_now(),
    updated_time: datetime = utc_now(),
)
```

### AccountMapping

```python
AccountMapping(
    amid: int | None = None,       # PK, DB generated
    aid: int,                      # required FK -> Account.aid
    type: str | None = None,
    key: str | None = None,
)
```

### SessionMeta

```python
SessionMeta(
    sid: int | None = None,        # PK, DB generated
    name: str | None = None,
    participants: list[int] = [],  # aid list, stored as JSON
)
```

### Message

```python
Message(
    external_mid: str,             # PK, external message id
    sid: int,                      # FK -> SessionMeta.sid
    sender: int,                   # FK -> Account.aid
    read: bool | None = None,
    content: Any,                  # JSON
    type: str,
)
```

### Translate

```python
Translate(
    text_hash: str,                # PK
    translation: str,
)
```

### Meta

```python
Meta(
    key: str | None = "version",  # PK
    value: str = "1.0.0",
)
```

### AgentPreset

```python
AgentPreset(
    apid: str,                     # PK, external meaningful id
    name: str,
    description: str,
    prompt: str,
    intelevel: int,                # 0..4
    tools: list[str] = [],         # tool names from tool_registry
)
```

## Manager 接口

大多数 Manager 保持以下方法风格：

```python
add_*(model) -> None
upsert_*(model) -> None
edit_*(primary_key, model) -> None
delete_*(primary_key) -> None
get_*(primary_key) -> Model | None
list_*() -> list[Model]
```

### CustomerManager

```python
CustomerManager(database_path: Path | str | None = None)

add_customer(customer: Customer) -> None
upsert_customer(customer: Customer) -> None
edit_customer(cid: int, customer: Customer) -> None
delete_customer(cid: int) -> None
get_customer(cid: int) -> Customer | None
list_customer() -> list[Customer]
```

### AccountManager

```python
AccountManager(database_path: Path | str | None = None)

add_account(account: Account) -> None
upsert_account(account: Account) -> None
edit_account(aid: int, account: Account) -> None
delete_account(aid: int) -> None
get_account(aid: int) -> Account | None
list_account() -> list[Account]
```

### AccountMappingManager

```python
AccountMappingManager(database_path: Path | str | None = None)

add_account_mapping(account_mapping: AccountMapping) -> None
upsert_account_mapping(account_mapping: AccountMapping) -> None
edit_account_mapping(amid: int, account_mapping: AccountMapping) -> None
delete_account_mapping(amid: int) -> None
get_account_mapping(amid: int) -> AccountMapping | None
list_account_mapping() -> list[AccountMapping]
```

### PlatformManager

```python
PlatformManager(database_path: Path | str | None = None)

add_platform(platform: Platform) -> None
upsert_platform(platform: Platform) -> None
edit_platform(pid: str, platform: Platform) -> None
delete_platform(pid: str) -> None
get_platform(pid: str) -> Platform | None
list_platform() -> list[Platform]
```

### SessionMetaManager

```python
SessionMetaManager(database_path: Path | str | None = None)

add_session_meta(session_meta: SessionMeta) -> None
upsert_session_meta(session_meta: SessionMeta) -> None
edit_session_meta(sid: int, session_meta: SessionMeta) -> None
delete_session_meta(sid: int) -> None
get_session_meta(sid: int) -> SessionMeta | None
list_session_meta() -> list[SessionMeta]
```

### MessageManager

```python
MessageManager(database_path: Path | str | None = None)

add_message(message: Message) -> None
upsert_message(message: Message) -> None
edit_message(external_mid: str, message: Message) -> None
delete_message(external_mid: str) -> None
get_message(external_mid: str) -> Message | None
list_message() -> list[Message]
```

### TranslateManager

```python
TranslateManager(database_path: Path | str | None = None)

add_translate(translate: Translate) -> None
upsert_translate(translate: Translate) -> None
edit_translate(text_hash: str, translate: Translate) -> None
delete_translate(text_hash: str) -> None
get_translate(text_hash: str) -> Translate | None
list_translate() -> list[Translate]
```

### MetaManager

```python
MetaManager(database_path: Path | str | None = None)

get_version() -> str
update_version(value: str) -> None
upsert_meta(meta: Meta) -> None
```

### AgentPresetManager

```python
AgentPresetManager(database_path: Path | str | None = None)

add_agent_preset(agent_preset: AgentPreset) -> None
upsert_agent_preset(agent_preset: AgentPreset) -> None
edit_agent_preset(apid: str, agent_preset: AgentPreset) -> None
delete_agent_preset(apid: str) -> None
get_agent_preset(apid: str) -> AgentPreset | None
list_agent_preset() -> list[AgentPreset]
```

## UPSERT 判定规则

| Manager | 定位规则 | 不存在时 | 存在且 payload 相同时 | 存在且 payload 不同时 |
| --- | --- | --- | --- | --- |
| `PlatformManager.upsert_platform` | `pid` | 插入 | 跳过并同步状态 | 更新 `name/extra/updated_time` |
| `TranslateManager.upsert_translate` | `text_hash` | 插入 | 跳过 | 更新 `translation` |
| `MetaManager.upsert_meta` | `key`，空 key 归一化为 `version` | 插入 | 跳过并同步状态 | 更新 `value` |
| `MessageManager.upsert_message` | `external_mid` | 插入 | 跳过 | 更新 `sid/sender/read/content/type` |
| `AgentPresetManager.upsert_agent_preset` | `apid` | 插入 | 跳过并同步状态 | 更新 `name/description/prompt/intelevel/tools` |
| `CustomerManager.upsert_customer` | 有 `cid` 时按 `cid`；无 `cid` 时按完整 payload 扫描 | 插入；显式 `cid` 缺失时报错 | 跳过并同步状态 | 更新字段 |
| `AccountManager.upsert_account` | 有 `aid` 时按 `aid`；无 `aid` 时按完整 payload 扫描 | 插入；显式 `aid` 缺失时报错 | 跳过并同步状态 | 更新字段 |
| `AccountMappingManager.upsert_account_mapping` | 有 `amid` 时按 `amid`；无 `amid` 时按完整 payload 扫描 | 插入；显式 `amid` 缺失时报错 | 跳过并同步状态 | 更新字段 |
| `SessionMetaManager.upsert_session_meta` | 有 `sid` 时按 `sid`；无 `sid` 时按完整 payload 扫描 | 插入；显式 `sid` 缺失时报错 | 跳过并同步状态 | 更新字段 |

说明：`Customer`、`Account`、`AccountMapping`、`SessionMeta` 当前仍包含 payload 去重逻辑。外部系统同步场景建议优先使用稳定外部键后再扩展对应业务级接口。

## 注册表接口

注册表是进程内内存映射，不写入 SQLite。

### Tool Registry

```python
from core import register_tool, tool_registry

def search_customer(keyword: str) -> dict:
    return {"keyword": keyword}

register_tool("search_customer", search_customer)

tool = tool_registry.require("search_customer")
result = tool("Alice")
```

接口：

```python
register_tool(name: str, func: Callable[..., Any]) -> None
tool_registry.register(name: str, func: Callable[..., Any]) -> None
tool_registry.get(name: str) -> Callable[..., Any] | None
tool_registry.require(name: str) -> Callable[..., Any]
tool_registry.list() -> dict[str, Callable[..., Any]]
tool_registry.clear() -> None
```

### LLM Registry

```python
from core import LLMConfig, register_llm, llm_registry

register_llm(
    2,
    LLMConfig(
        base_url="https://api.example.com/v1",
        api_key="secret",
        model_name="example-model",
    ),
)

config = llm_registry.require(2)
```

接口：

```python
LLMConfig(base_url: str, api_key: str, model_name: str)

register_llm(level: int, config: LLMConfig) -> None
llm_registry.register(level: int, config: LLMConfig) -> None
llm_registry.get(level: int) -> LLMConfig | None
llm_registry.require(level: int) -> LLMConfig
llm_registry.list() -> dict[int, LLMConfig]
llm_registry.clear() -> None
```

`level` 范围为 `0..4`，与 `AgentPreset.intelevel` 保持一致。

## 线程池调度器

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

接口：

```python
ThreadPoolScheduler(max_workers: int = 4)

submit(database_path: Path | str, func, *args, **kwargs) -> Future
submit_manager_call(manager, func, *args, **kwargs) -> Future
shutdown(wait: bool = True) -> None
```

语义：

- 同一 `database_path` 的任务按提交顺序串行执行。
- 不同 `database_path` 的任务可并行。
- 任务异常会在 `future.result()` 时重新抛出。
- `shutdown()` 后不能提交新任务。

## Engine 与线程安全

- 同一进程内，相同 `resolved database_path` 共享同一个 SQLAlchemy engine。
- 同一数据库路径共享同一把进程内写锁。
- Manager 方法内部创建短生命周期 `Session`，不要跨线程共享 `Session`。
- SQLite 连接参数：`check_same_thread=False`、`timeout=30`。
- 每个连接开启 `PRAGMA foreign_keys=ON`。
- `manager.engine.dispose()` 后，再次 `bootstrap_engine()` 会按路径重建共享 engine。

## 测试

```bash
python -m pytest tests
```

单测示例：

```bash
python -m pytest tests/test_message_manager.py
python -m pytest tests/test_registry.py
```

## 注意事项

- 这是本地 SQLite 数据层，不是高并发数据库服务。
- 当前没有 schema migration 机制；模型变更后，旧 SQLite 文件不会自动迁移。
- 当前导入风格是本地项目入口：`core`、`models`、`utils`。如作为正式包发布，应改为包命名空间导入。
