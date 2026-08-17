import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_pipeline import (
    AgentPipeline,
    AgentPipelineInput,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    OpenAICompatibleLLMClient,
    ToolExecutionResult,
)
from agent_pipeline.llm import StaticLLMClient
from agent_pipeline.llm_api import load_default_llm_levels, register_default_llms
from agent_pipeline.registry import LLMConfig, llm_registry, tool_registry
from agent_pipeline.resolver import resolve_agent_preset
from agent_pipeline.types import LLMToolSchema
from core import AgentPresetManager, LLMApiConfigManager
from models import AgentPreset, LLMApiConfig


class LLMApiTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        llm_registry.clear()
        tool_registry.clear()

    @staticmethod
    def _dispose_shared_engine(db_path: Path) -> None:
        from utils.common import bootstrap_engine

        bootstrap_engine(db_path)[1].dispose()

    @staticmethod
    def _config(level: int, model_name: str = "claude-opus-4-8", **overrides) -> LLMApiConfig:
        payload = {
            "level": level,
            "base_url": "https://api.example.com/v1",
            "api_key": "replace-me",
            "model_name": model_name,
        }
        payload.update(overrides)
        return LLMApiConfig(**payload)

    def _write_configs(self, db_path: Path, configs: list[LLMApiConfig]) -> None:
        manager = LLMApiConfigManager(database_path=db_path)
        try:
            manager.replace_configs(configs)
        finally:
            manager.engine.dispose()

    def test_load_default_llm_levels_registers_levels_zero_through_four(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "llm_api.sqlite"
            self._write_configs(db_path, [self._config(level) for level in range(5)])

            levels = load_default_llm_levels(db_path)

            self.assertEqual(sorted(levels.keys()), [0, 1, 2, 3, 4])
            self.assertEqual(levels[2].model_name, "claude-opus-4-8")
            self.assertIsNone(levels[2].system_prompt)
            self.assertEqual(levels[2].context, 12000)
            self._dispose_shared_engine(db_path)

    def test_load_default_llm_levels_uses_only_configured_levels(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "llm_api.sqlite"
            self._write_configs(
                db_path,
                [
                    self._config(0),
                    self._config(4, model_name="claude-sonnet-5"),
                ],
            )

            levels = load_default_llm_levels(db_path)

            self.assertEqual(sorted(levels.keys()), [0, 4])
            self.assertEqual(levels[0].model_name, "claude-opus-4-8")
            self.assertEqual(levels[4].model_name, "claude-sonnet-5")
            self._dispose_shared_engine(db_path)

    def test_load_default_llm_levels_maps_optional_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "llm_api.sqlite"
            self._write_configs(
                db_path,
                [
                    self._config(
                        2,
                        system_prompt="You are a careful assistant.",
                        context=4096,
                        max_tool_rounds=5,
                    )
                ],
            )

            levels = load_default_llm_levels(db_path)

            self.assertEqual(levels[2].system_prompt, "You are a careful assistant.")
            self.assertEqual(levels[2].context, 4096)
            self.assertEqual(levels[2].max_tool_rounds, 5)
            self._dispose_shared_engine(db_path)

    def test_register_default_llms_is_idempotent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "llm_api.sqlite"
            self._write_configs(
                db_path,
                [self._config(0, system_prompt="You are a careful assistant.", context=4096)],
            )

            first = register_default_llms(db_path)
            second = register_default_llms(db_path)

            self.assertEqual(llm_registry.list(), second)
            self.assertEqual(first, second)
            self.assertEqual(first[0].system_prompt, "You are a careful assistant.")
            self.assertEqual(first[0].context, 4096)
            self._dispose_shared_engine(db_path)

    def test_register_default_llms_returns_empty_when_config_table_is_empty(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "llm_api.sqlite"
            LLMApiConfigManager(database_path=db_path).engine.dispose()

            levels = register_default_llms(db_path)

            self.assertEqual(levels, {})
            self.assertEqual(llm_registry.list(), {})
            self._dispose_shared_engine(db_path)

    def test_agent_preset_resolver_can_use_database_registrations(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "llm_api.sqlite"
            self._write_configs(db_path, [self._config(2)])
            register_default_llms(db_path)
            agent_preset = AgentPreset(
                apid="default-assistant",
                name="default assistant",
                description="General customer service preset",
                prompt="Help the customer politely",
                llm_level=2,
                tools=[],
            )

            runtime = resolve_agent_preset(agent_preset)

            self.assertEqual(runtime.llm.model_name, "claude-opus-4-8")
            self._dispose_shared_engine(db_path)

    def test_agent_pipeline_can_use_database_registrations(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "llm_api.sqlite"
            self._write_configs(db_path, [self._config(2)])
            register_default_llms(db_path)
            manager = AgentPresetManager(database_path=Path(temp_dir) / "agent_pipeline.sqlite")
            try:
                preset = AgentPreset(
                    apid="default-assistant",
                    name="default assistant",
                    description="General customer service preset",
                    prompt="Help the customer politely",
                    llm_level=2,
                    tools=[],
                )
                manager.add_agent_preset(preset)
                client = StaticLLMClient([
                    LLMResponse(text="registered by llm_api", needs_tool=False),
                ])

                result = AgentPipeline(llm_client=client, manager=manager).run(
                    AgentPipelineInput(user_input="hello", apid="default-assistant")
                )

                self.assertEqual(result.output_text, "registered by llm_api")
                self.assertEqual(result.runtime.llm.model_name, "claude-opus-4-8")
            finally:
                manager.engine.dispose()
            self._dispose_shared_engine(db_path)

    def test_openai_client_replays_tool_history_with_tool_messages(self) -> None:
        client = OpenAICompatibleLLMClient(
            LLMConfig(
                base_url="https://api.example.com/v1",
                api_key="replace-me",
                model_name="example-model",
            )
        )
        payload = client._build_payload(
            LLMRequest(
                system_prompt="You are helpful.",
                user_input="What is 7*8?",
                tool_prompt="Available tools:\n- calculate",
                tool_schemas=[
                    LLMToolSchema(
                        name="calculate",
                        description="Perform arithmetic.",
                        parameters={"type": "object"},
                    )
                ],
                tool_calls=[
                    LLMToolCall(
                        name="calculate",
                        tool_input={"operation": "multiply", "a": 7, "b": 8},
                        call_id="call_abc",
                    )
                ],
                tool_results=[
                    ToolExecutionResult(
                        name="calculate",
                        ok=True,
                        content=56,
                    )
                ],
            )
        )

        messages = payload["messages"]
        self.assertEqual([message["role"] for message in messages], ["system", "user", "assistant", "tool"])
        self.assertEqual(messages[2]["tool_calls"][0]["id"], "call_abc")
        self.assertEqual(messages[2]["tool_calls"][0]["function"]["name"], "calculate")
        self.assertEqual(messages[3]["tool_call_id"], "call_abc")
        self.assertEqual(messages[3]["content"], "56")


if __name__ == "__main__":
    unittest.main()
