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

Managers that point to the same resolved SQLite path share one underlying engine. The engine lifecycle is managed centrally by `bootstrap_engine()` in `utils.common`.

Concurrency policy:

- The engine is safe to share across threads.
- Managers that point to the same resolved database path also share one process-local database lock for write methods.
- Sessions are **not** shared across threads; each manager method opens its own short-lived `Session`.
- Read methods can still run concurrently, but write methods are serialized inside the current Python process.
- `MetaManager.get_version()` is treated as a read-write method because it may create the default singleton row.
- SQLite supports concurrent reads, but writes still contend on the database lock and may wait up to the configured timeout.
- The locking strategy only guarantees serialization inside the current Python process; cross-process coordination still relies on SQLite itself.
- `manager.engine.dispose()` releases the shared engine for that database path. It is safe to call more than once, but application code should avoid calling it frequently during normal operation or while other threads are actively using managers.

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

- `utils.bootstrap_engine`
- `utils.utc_now`
- `utils.ThreadPoolScheduler`

Compatibility aliases:

- `config.bootstrap_engine`
- `config.scheduler.ThreadPoolScheduler`
- `scheduler.ThreadPoolScheduler`

## Queued thread-pool scheduling

Use `ThreadPoolScheduler` when you want same-database tasks to execute strictly in submission order while different databases can still run in parallel.

```python
from utils import ThreadPoolScheduler

with ThreadPoolScheduler(max_workers=4) as scheduler:
    future = scheduler.submit_manager_call(customer_manager, customer_manager.add_customer, customer)
    future.result()
```

Scheduling guarantees:

- Tasks targeting the same resolved `database_path` run and finish strictly in submission order.
- Tasks targeting different resolved database paths may run in parallel.
- Exceptions are re-raised from `future.result()`.
- Shutdown prevents new task submission.
- Wait for `future.result()` before reading model fields that are backfilled by manager methods.

## Tests

Run the test suite with:

```bash
python -m unittest discover tests
```
