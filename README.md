# EgooAI CRM SDK Py

一个基于 **SQLModel + SQLite** 的本地 CRM SDK，包含两部分能力：

- CRM 数据模型与 CRUD Manager
- 面向 Agent 场景的 `tool_registry`、`llm_registry` 和 `agent_pipeline`

适合本地原型、轻量数据落库，以及工具调用型 Agent 实验。

## 环境要求

- Python `>=3.10,<4`

## 安装

```bash
uv sync
```

不使用 `uv` 时，按 `pyproject.toml` 安装依赖即可。

## 主要模块

### 数据层

`core/` 提供以下 Manager：

- `CustomerManager`
- `AccountManager`
- `AccountMappingManager`
- `PlatformManager`
- `SessionMetaManager`
- `MessageManager`
- `TranslateManager`
- `MetaManager`
- `AgentPresetManager`

`models/` 提供对应模型：

- `Customer`
- `Account`
- `AccountMapping`
- `Platform`
- `SessionMeta`
- `Message`
- `Translate`
- `Meta`
- `AgentPreset`

### Registry

`core` 提供两个进程内注册表：

- `tool_registry`：注册工具函数
- `llm_registry`：按 `intelevel` 注册 LLM 配置

常用入口：

```python
from core import register_tool, register_llm, tool_registry, llm_registry, resolve_agent_preset
```

### Agent Pipeline

`agent_pipeline` 提供一个最小执行链路：

1. 读取 `AgentPreset`
2. 解析出 LLM 配置和工具列表
3. 调用 LLM
4. 如需工具，则执行一轮 tool call
5. 再调用一次 LLM，生成最终回答

当前只支持 **单轮工具调用**。

## 快速开始

### 1) 数据层示例

```python
from pathlib import Path

from core import AccountManager, CustomerManager, PlatformManager
from models import Account, Customer, Platform

db_path = Path("demo.sqlite")

platform_manager = PlatformManager(database_path=db_path)
customer_manager = CustomerManager(database_path=db_path)
account_manager = AccountManager(database_path=db_path)

platform_manager.upsert_platform(Platform(pid="wechat", name="WeChat"))

customer = Customer(name="Alice", region="Shanghai")
customer_manager.add_customer(customer)

account_manager.add_account(
    Account(
        cid=customer.cid,
        pid="wechat",
        account="alice@example.com",
        nickname="Alice",
    )
)
```

### 2) Agent Pipeline 示例

先注册 LLM 和工具，再保存一个 `AgentPreset`：

```python
from agent_pipeline import OpenAICompatibleLLMClient, register_math_tools
from agent_pipeline.llm_api import register_default_llms
from core import AgentPresetManager, llm_registry
from models import AgentPreset

register_default_llms()  # 默认读取项目根目录 llm_api.yaml
register_math_tools()

manager = AgentPresetManager(database_path="demo.sqlite")
manager.upsert_agent_preset(
    AgentPreset(
        apid="math-assistant",
        name="Math Assistant",
        description="Use math tools when needed",
        prompt="You are a precise math assistant.",
        intelevel=2,
        tools=["add_numbers", "subtract_numbers", "multiply_numbers", "divide_numbers"],
    )
)

client = OpenAICompatibleLLMClient(llm_registry.require(2))
```

执行 pipeline：

```python
from agent_pipeline import AgentPipeline, AgentPipelineInput

result = AgentPipeline(llm_client=client, manager=manager).run(
    AgentPipelineInput(
        user_input="Use a tool to calculate 7 multiplied by 8.",
        apid="math-assistant",
    )
)

print(result.output_text)
```

## LLM 配置

项目内提供示例文件：

- `llm_api.example.yaml`

先复制为 `llm_api.yaml`，再填写真实配置：

```yaml
default:
  base_url: "https://api.example.com/v1"
  api_key: "replace-me"
  model_name: "claude-opus-4-8"

levels:
  0: {}
  1: {}
  2: {}
  3: {}
  4: {}
```

加载方式：

```python
from agent_pipeline.llm_api import register_default_llms

register_default_llms()
```

说明：

- `AgentPreset.intelevel` 会映射到对应的 LLM 配置
- 若等级或工具未注册，运行期解析会抛错
- 当前配置适合本地开发，不建议把真实密钥提交到仓库

## 并发与 SQLite

- 相同数据库路径共享同一个 engine
- 相同数据库路径的任务按顺序串行执行
- 不同数据库路径的任务可以并行
- Manager 内部使用短生命周期 `Session`
- SQLite 已启用 `foreign_keys=ON`

如需调度，可使用：

```python
from utils import ThreadPoolScheduler
```

## 测试

```bash
python -m pytest tests
```

例如：

```bash
python -m pytest tests/test_agent_pipeline.py
python -m pytest tests/test_llm_api.py
```

## 注意事项

- 这是本地 SQLite 数据层，不适合高并发服务场景
- 当前没有 schema migration 机制
- 当前导入方式以仓库内直接使用为主，例如 `from core import ...`
