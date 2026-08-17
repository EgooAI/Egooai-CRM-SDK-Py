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
- `ChatHistoryManager`
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
- `ChatHistory`
- `Translate`
- `Meta`
- `AgentPreset`

### Registry

`agent_pipeline.registry` 提供三个进程内注册表：

- `tool_registry`：注册工具函数
- `llm_registry`：按 `llm_level` 注册 LLM 配置
- `output_normalizer_registry`：按 Agent 的 `apid` 注册输出归一化函数

常用入口：

```python
from agent_pipeline.registry import register_tool, register_llm, tool_registry, llm_registry
from agent_pipeline.resolver import resolve_agent_preset
```

### Agent Pipeline

`agent_pipeline` 提供一个最小执行链路：

1. 读取 `AgentPreset`
2. 解析出 LLM 配置和工具列表
3. 调用 LLM
4. 如需工具，则执行对应的 tool call
5. 将工具结果回填给 LLM，继续下一轮
6. 直到 LLM 直接返回最终回答，或触发上下文/工具轮次限制

当前已支持 **多轮工具调用**；可通过 `max_tool_rounds` 控制上限。

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

register_default_llms()  # 默认读取 data/crm.sqlite 的 llm_api_config 表
register_math_tools()

manager = AgentPresetManager(database_path="demo.sqlite")
manager.upsert_agent_preset(
    AgentPreset(
        apid="math-assistant",
        name="Math Assistant",
        description="Use math tools when needed",
        prompt="You are a precise math assistant.",
        llm_level=2,
        tools=["calculate"],
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
print(result.iterations)
```

返回结果中常用字段包括：

- `output_text`：最终输出文本，或命中限制时的兜底文案
- `iterations`：实际进行了多少次 LLM 调用
- `tool_call`：最后一次工具调用的请求信息
- `tool_result`：最后一次工具调用的返回结果
- `raw_responses`：底层 LLM 返回的原始响应列表，便于调试

## LLM 配置

默认配置来源是 CRM SQLite 数据库中的 `llm_api_config` 表。该表一行对应一个 LLM level：

```text
llm_api_config
├── level                         # 主键，0~4
├── base_url
├── api_key
├── model_name
├── system_prompt
├── context
└── max_tool_rounds
```

可以通过 `LLMApiConfigManager` 直接写入：

```python
from core import LLMApiConfigManager
from models import LLMApiConfig

LLMApiConfigManager().replace_configs([
    LLMApiConfig(
        level=0,
        base_url="https://api.example.com/v1",
        api_key="replace-me",
        model_name="claude-opus-4-8",
        system_prompt="You are a careful and policy-compliant assistant.",
        context=12000,
        max_tool_rounds=5,
    ),
])
```

默认加载方式：

```python
from agent_pipeline.llm_api import register_default_llms

register_default_llms()
```

如果 `llm_api_config` 表没有数据，会抛出配置不存在错误。

说明：

- `AgentPreset.llm_level` 会映射到对应的 LLM 配置
- `context` 表示工作流允许的上下文长度上限；超限时不会继续请求 LLM，结果状态为 `context_limited`，由调用方决定提示文案
- `context` 的估算会计入 system prompt、user input、tool prompt、tool schema，以及累计的 tool result；因此不只是用户输入过长会触发超限，工具结果文本过长也会触发
- `max_tool_rounds` 用于限制最多可执行多少轮工具调用；超过后结果状态为 `tool_rounds_limited`，由调用方决定提示文案
- 若未设置 `max_tool_rounds`，SDK 使用默认上限 10，避免无限循环
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
python -m unittest discover tests
```

例如：

```bash
python -m unittest tests.test_agent_pipeline
python -m unittest tests.test_llm_api
```

## 注意事项

- 这是本地 SQLite 数据层，不适合高并发服务场景
- 当前导入方式以仓库内直接使用为主，例如 `from core import ...`
