# EgooAI CRM SDK Py

A lightweight local CRM data layer built with `SQLModel` and `SQLite`.

## Current scope

The repository currently provides CRUD-style managers and models for:

- `Customer`
- `Account`
- `Platform`
- `AccountMapping`
- `SessionMeta`
- `Message`
- `Meta`
- `Translate`

All managers are exported from `core`, and all data models are exported from `models`.

## Engine lifecycle and thread safety

Managers that point to the same resolved SQLite path share one underlying engine. The engine lifecycle is managed centrally by `bootstrap_engine()` in `utils`.

Concurrency policy:

- The engine is safe to share across threads.
- Sessions are **not** shared across threads; each manager method opens its own short-lived `Session`.
- SQLite supports concurrent reads, but writes still contend on the database lock and may wait up to the configured timeout.
- `manager.engine.dispose()` releases the shared engine for that database path. It is safe to call more than once, but application code should avoid calling it frequently during normal operation.

## Installation

Requirements:

- Python `>=3.10`

Install dependencies with `uv`:

```bash
uv sync
```

## Quick start

```python
from pathlib import Path

from core import AccountManager, CustomerManager, PlatformManager, SessionMetaManager, MessageManager
from models import Account, Customer, Platform, SessionMeta, Message

db_path = Path("demo.sqlite")

platform_manager = PlatformManager(database_path=db_path)
customer_manager = CustomerManager(database_path=db_path)
account_manager = AccountManager(database_path=db_path)
session_meta_manager = SessionMetaManager(database_path=db_path)
message_manager = MessageManager(database_path=db_path)

platform = Platform(pid="wechat", name="WeChat")
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

session_meta = SessionMeta(name="session-a")
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

## Public managers

- `AccountManager`
- `AccountMappingManager`
- `CustomerManager`
- `MessageManager`
- `MetaManager`
- `PlatformManager`
- `SessionMetaManager`
- `TranslateManager`

## Public utilities

- `bootstrap_engine`
- `utc_now`

## Tests

Run the test suite with:

```bash
python -m unittest discover tests
```
