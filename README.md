# EgooAI CRM SDK Py

一个基于 **SQLModel + SQLite** 的本地 Python CRM / Session 数据层原型库。

当前代码以 **manager + model** 的形式提供客户、账号、平台、账号映射、会话元数据、会话聊天、版本元信息与翻译映射的 CRUD 能力。其中会话聊天采用“**每个会话一张物理表**”的动态建表方案，这是当前仓库最关键的实现特征。

## 项目简介

这个仓库不是 Web 服务、CLI 或已发布到 PyPI 的 SDK，而是一个面向本地 SQLite 数据库的轻量数据层原型。使用者通过 `core/` 中导出的 manager 类完成建库、建表和数据读写，通过 `models/` 中的 SQLModel 模型组织输入输出数据。

默认情况下，数据库文件会落在项目根目录的 `db.sqlite`。也可以在初始化 manager 时显式传入 `database_path`，将数据写入其他 SQLite 文件。

## 当前能力概览

### CRM 基础实体
- `Customer`：客户基础信息
- `Account`：客户账号信息
- `Platform`：平台信息
- `AccountMapping`：账号与外部标识的映射关系

### Session / Chat
- `SessionMeta`：会话元数据，包含唯一 `chatid` 与参与者列表 `participants`
- `SessionChat`：聊天消息模型，用于写入对应会话的动态聊天表
- 创建 `SessionMeta` 时自动创建 `sessionchat_<chatid>` 表
- 删除 `SessionMeta` 时自动删除对应聊天表
- `SessionChatManager` 同时支持按 `chatid` 和按 `sid` 访问聊天记录

### 元数据与辅助能力
- `Meta`：单例版本信息读写
- `Translate`：文本哈希到译文的映射
- `bootstrap_engine()`：统一处理 SQLite 路径解析、建表与外键约束开启
- `utc_now()`：返回带时区的 UTC 时间

## 安装与环境

### 运行要求
- Python `>= 3.10`
- 依赖：`sqlalchemy`、`sqlmodel`

### 安装依赖

仓库当前使用 `uv` 管理依赖，且 `pyproject.toml` 中配置为 `package = false`，因此更接近“本地项目”而不是可发布包。

```bash
uv sync
```

如果你不使用 `uv`，也可以自行安装 `pyproject.toml` 中声明的依赖。

## 快速开始

下面的示例演示一条完整链路：创建平台、客户、账号、会话元数据，然后按 `sid` 写入一条聊天消息。

```python
from pathlib import Path

from core import (
    AccountManager,
    PlatformManager,
    CustomerManager,
    SessionMetaManager,
    SessionChatManager,
)
from models import Account, Customer, Platform, SessionMeta, SessionChat


db_path = Path("demo.sqlite")

platform_manager = PlatformManager(database_path=db_path)
customer_manager = CustomerManager(database_path=db_path)
account_manager = AccountManager(database_path=db_path)
session_meta_manager = SessionMetaManager(database_path=db_path)
session_chat_manager = SessionChatManager(database_path=db_path)

platform = Platform(
    pid="wechat",
    name="WeChat",
)
platform_manager.add_platform(platform)

customer = Customer(
    name="Alice",
    sex="F",
    region="Shanghai",
    extra={"level": 1},
    image={"avatar": "alice.png"},
)
customer_manager.add_customer(customer)

account = Account(
    cid=customer.cid,
    pid=platform.pid,
    account="alice@example.com",
    nickname="Alice",
)
account_manager.add_account(account)

session_meta = SessionMeta(
    name="session-a",
    participants=[account.aid],
)
session_meta_manager.add_session_meta(session_meta)

chat = SessionChat(
    sender=account.aid,
    type="text",
    content={"text": "hello"},
    read=False,
)
session_chat_manager.add_session_chat_by_sid(session_meta.sid, chat)

saved_chat = session_chat_manager.get_session_chat_by_sid(session_meta.sid, chat.id)
print(session_meta.chatid)
print(saved_chat.content)
```

执行以上代码后会发生这些事情：
- `demo.sqlite` 会在首次初始化时自动创建
- 静态表会通过 `SQLModel.metadata.create_all(...)` 自动建表
- `SessionMeta` 插入时会自动生成 32 位小写十六进制 `chatid`
- 对应的动态聊天表 `sessionchat_<chatid>` 会自动创建
- 聊天消息会写入这张会话专属表，而不是共享单表

## 数据模型与管理器

| Model | Manager | 主键 | 说明 |
| --- | --- | --- | --- |
| `Customer` | `CustomerManager` | `cid` | 客户基础信息 |
| `Account` | `AccountManager` | `aid` | 账号信息，关联客户和平台 |
| `Platform` | `PlatformManager` | `pid` | 平台定义 |
| `AccountMapping` | `AccountMappingManager` | `amid` | 账号与外部 key 的映射 |
| `SessionMeta` | `SessionMetaManager` | `sid` | 会话元数据与 `chatid` |
| `SessionChat` | `SessionChatManager` | 动态表 `id` | 会话聊天记录 |
| `Meta` | `MetaManager` | `key` | 版本等单例元信息 |
| `Translate` | `TranslateManager` | `text_hash` | 文本翻译映射 |

### 当前导出的 manager

`core/__init__.py` 当前导出以下公共入口：
- `CustomerManager`
- `AccountManager`
- `AccountMappingManager`
- `PlatformManager`
- `SessionMetaManager`
- `SessionChatManager`
- `TranslateManager`
- `MetaManager`
- `bootstrap_engine`

## Session / Chat 机制

### 1. `chatid` 格式

`SessionMeta.chatid` 必须是 **32 位小写十六进制字符串**。代码中会通过正则校验，不合法的值会抛出 `ValueError`。

### 2. 动态聊天表命名

每个会话拥有独立的物理聊天表，命名规则为：

```text
sessionchat_<chatid>
```

例如：

```text
sessionchat_0123456789abcdef0123456789abcdef
```

### 3. 建表与删表行为

- `SessionMetaManager.add_session_meta(...)` 会先确保对应聊天表存在，再写入 `sessionmeta`
- `SessionMetaManager.delete_session_meta(...)` 会删除该会话元数据，并同步删除对应聊天表
- 如果聊天表删除失败，会话元数据不会被静默删除

### 4. `SessionChat` 的真实存储方式

`SessionChat` 本身不是一张固定的 SQLModel 表，而是一个消息行模型。真正落库时，消息会写入与 `chatid` 对应的动态物理表。

这意味着当前实现不是单表 `sessionchat` 方案，而是“每个 session 一张表”的分表方案。

### 5. 按 `chatid` / `sid` 两种访问方式

`SessionChatManager` 提供两组接口：
- 按 `chatid`：`add_session_chat`、`get_session_chat`、`list_session_chat`、`edit_session_chat`、`delete_session_chat`
- 按 `sid`：`add_session_chat_by_sid`、`get_session_chat_by_sid`、`list_session_chat_by_sid`、`edit_session_chat_by_sid`、`delete_session_chat_by_sid`

按 `sid` 操作时，代码会先从 `SessionMeta` 查到真实 `chatid`，再路由到对应动态表。

### 6. 外键与约束

- `SessionChat.sender` 外键指向 `account.aid`
- `Account.cid` 外键指向 `customer.cid`
- `Account.pid` 外键指向 `platform.pid`
- `AccountMapping.aid` 外键指向 `account.aid`
- SQLite 连接建立时会执行 `PRAGMA foreign_keys=ON`

如果 `sender` 指向不存在的账号，插入聊天消息会触发外键错误。

### 7. 非法或孤立 `chatid`

以下情况会抛出 `ValueError`：
- `chatid` 格式不合法
- `chatid` 虽然格式合法，但对应的 `SessionMeta` 已不存在
- 通过不存在的 `sid` 访问聊天消息

## 数据库初始化行为

`bootstrap_engine(database_path=None)` 会统一完成以下工作：
- 解析数据库路径；未传入时默认使用项目根目录 `db.sqlite`
- 自动创建数据库文件所在目录
- 创建 SQLAlchemy / SQLModel engine
- 开启 SQLite 外键约束
- 对当前 `SQLModel.metadata` 中的静态表执行 `create_all`

因此绝大多数场景下，只要初始化任意 manager，就已经完成了静态表初始化。

## 测试覆盖

当前 `tests/` 目录已覆盖以下 manager / 行为：
- `CustomerManager`
- `AccountManager`
- `AccountMappingManager`
- `PlatformManager`
- `SessionMetaManager`
- `SessionChatManager`
- `MetaManager`
- `TranslateManager`

重点测试点包括：
- SQLite 数据库文件自动创建
- 各实体 CRUD 行为
- 时间字段更新行为
- JSON 字段存取
- 动态聊天表自动创建与删除
- 按 `sid` 路由到聊天表
- 非法 `chatid` / 孤立 `chatid` 的错误处理
- 外键约束生效
- `Meta` 的单例版本记录行为

运行测试：

```bash
python -m unittest discover tests
```

## 已知边界

当前代码范围比较明确，README 也只描述已经实现的能力：
- 当前仅看到 SQLite 存储实现
- 没有 migration 系统说明
- 没有 HTTP API / RPC 封装
- 没有异步接口
- 没有声明为可直接发布到 PyPI 的完整打包流程
- 会话聊天采用“每个会话一张物理表”的设计，适合当前原型场景，但会影响后续统一查询、迁移和统计分析方式
