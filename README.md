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
- `AgentPresetRevisionManager`

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
- `AgentPresetRevision`

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
6. 直到 LLM 直接返回最终回答，或触发上下文/工具预限制

当前已支持 **多轮工具调用** 与 **同一轮多个工具调用**。有两个上限：

- `max_tool_rounds`：按 LLM 调用轮次计算（不是按工具结果数）；默认 10；
- 单次运行的调用总数上限：`AgentPipeline(max_tool_calls=...)`，默认 20，防止并行调用放大数量。

达到轮次上限时，pipeline 会用 `tool_choice: none` 再请求一次收尾；收尾成功则状态仍是
`completed`，收尾仍要求调用工具或调用总数触顶时状态为 `tool_rounds_limited`，
但已有的文本、调用记录和意图都会保留，不会返回空结果。

工具失败（未知工具名、参数 JSON 非法、工具抛异常、工具超时）都会作为失败结果回传给模型，
运行不中断；只有"preset 里声明了但注册表中不存在"这类配置错误才会在运行前报错。
如果供应商不支持强制的 `tool_choice`（例如部分 reasoning 模型），pipeline 会自动降级为
`auto` 并重试一次。

读取类工具（`category="read"`）的单次结果默认按 8000 字符截断
（`ToolExecutor(max_result_chars=...)` 或调用时的 `max_result_chars` 可调整）：
文本保留前缀并追加原始长度提示；结构化结果超过上限时替换为
`{"truncated": true, "original_chars": N, "notice": ...}`，避免模型收到半截 JSON。
截断发生在执行层，因此回传给模型的内容、`ToolCallRecord.content` 与上下文估算
看到的是同一份结果，被截断时记录里的 `original_chars` 非空。
效果类工具（`category="effect"`）不截断：意图已在截断前写入收集器，返回值只是确认。

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

- `output_text`：最终输出文本
- `iterations`：实际进行了多少次 LLM 调用（含收尾调用）
- `tool_call` / `tool_result`：最后一次工具调用的请求与结果（兼容旧调用方）
- `tool_call_records`：**完整**调用记录（`call_id`、工具名、参数、成功/失败、结果或错误、耗时、轮次）
- `tool_exchanges`：按轮次分组的 assistant 调用与 tool 结果，供 LLM 客户端回放
- `intents`：效果类工具产生的意图（SDK 只承载，不解释含义）
- `usage`：累计 token 用量（供应商未返回时为空）
- `duration_ms`：本次运行耗时
- `status`：`completed` / `context_limited` / `tool_rounds_limited`
- `raw_responses`：底层 LLM 返回的原始响应列表，便于调试

## 工具元数据与上下文

工具注册可以附带元数据（可选，旧用法不变）：

```python
from agent_pipeline import ToolContext, ToolSpec, register_tool

def reply_customer(ctx: ToolContext, reply: str) -> str:
    ctx.emit("reply_customer", {"reply": reply})
    return "recorded"

register_tool("reply_customer", reply_customer, spec=ToolSpec(
    name="reply_customer",
    title="回复客户",
    category="effect",       # read / effect
    repeatable=True,
    max_calls=3,
    timeout_seconds=10,
))
```

- `category="effect"` 表示调用即代表一个对外动作意图；工具自己写入 `ToolContext`，
  运行结果通过 `intents` 带出，SDK 不执行任何对外动作；
- 参数说明可以用 `Annotated[str, "说明"]` 写在函数签名上，会进入 JSON schema；
- 声明了 `ctx: ToolContext` 的参数在执行时自动注入，**不会**进入 schema，模型无法伪造；
- `AgentPreset.requires_tool` 为真时，pipeline 会强制 `tool_choice="required"`；
- `ToolRegistry.list()`、`get()` 等旧接口保持不变；`list_specs()` 返回元数据。

**输出归一化注册表**（`output_normalizer_registry`）是旧机制：它只在模型输出纯文本、
需要解析成结构化结果时使用。新 Agent 应通过效果类工具表达动作，不要依赖解析文本。

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
- `context` 的估算会计入 system prompt、user input、tool prompt、tool schema、工具名与调用参数，以及累计的 tool result；因此不只是用户输入过长会触发超限，工具结果文本过长也会触发
- `max_tool_rounds` 用于限制最多执行多少轮工具调用（按 LLM 调用轮次计）；超过后会用 `tool_choice: none` 收尾一次，状态为 `tool_rounds_limited`，由调用方决定提示文案
- 若未设置 `max_tool_rounds`，SDK 使用默认上限 10，避免无限循环
- 若等级或工具未注册，运行期解析会抛错
- 当前配置适合本地开发，不建议把真实密钥提交到仓库

## AgentPreset 与版本历史

`AgentPreset` 保存 Agent 的名称、描述、提示词、LLM level、工具、`enabled` 启用状态与
`requires_tool`（是否必须至少调用一次工具）。`requires_tool` 通过追加式迁移增加，
旧数据库升级后默认关闭；`AgentPresetRevision` 快照也包含该字段。
`llm_level` 会映射到对应的 LLM 配置。

`AgentPresetRevisionManager` 提供追加式历史快照：`add_revision` / `get_revision` /
`list_revisions(apid, limit)` / `prune_revisions(apid, keep)`。快照中的 `source`
与 `note` 由宿主定义，SDK 不解释其取值；删除 `AgentPreset` 会级联删除其历史。

SDK 表结构的追加列迁移在 `utils/migrations.py` 中声明，并在建表后幂等执行，
以保证旧数据库升级后仍可读写。

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
