import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_pipeline import (
    AgentPipeline,
    AgentPipelineInput,
    AgentPresetResolutionError,
    LLMInvocationError,
    LLMResponse,
    LLMToolCall,
    StaticLLMClient,
    ToolExecutionError,
    run_agent_preset,
)
from core import AgentPresetManager, LLMConfig, llm_registry, register_llm, register_tool, tool_registry
from models import AgentPreset


class AgentPipelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "agent_pipeline.sqlite"
        self.manager = AgentPresetManager(database_path=self.db_path)

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        tool_registry.clear()
        llm_registry.clear()
        self.temp_dir.cleanup()

    @staticmethod
    def _build_llm_config(model_name: str = "example-model") -> LLMConfig:
        return LLMConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            model_name=model_name,
        )

    def _build_agent_preset(
        self,
        apid: str = "default-assistant",
        tools: list[str] | None = None,
    ) -> AgentPreset:
        payload = {
            "apid": apid,
            "name": "default assistant",
            "description": "General customer service preset",
            "prompt": "Help the customer politely",
            "intelevel": 2,
        }
        if tools is not None:
            payload["tools"] = tools
        return AgentPreset(**payload)

    def test_run_returns_direct_output_when_no_tool_is_needed(self) -> None:
        register_llm(2, self._build_llm_config())
        preset = self._build_agent_preset(tools=[])
        client = StaticLLMClient([
            LLMResponse(text="direct answer", needs_tool=False, raw={"turn": 1}),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="hello", agent_preset=preset)
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output_text, "direct answer")
        self.assertEqual(result.iterations, 1)
        self.assertIsNone(result.tool_call)
        self.assertIsNone(result.tool_result)
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(client.requests[0].system_prompt, "Help the customer politely")
        self.assertEqual(client.requests[0].tool_names, [])

    def test_run_executes_one_tool_round_and_returns_final_output(self) -> None:
        register_llm(2, self._build_llm_config())
        register_tool("search_customer", lambda keyword: {"keyword": keyword, "match": "Alice"})
        preset = self._build_agent_preset(tools=["search_customer"])
        client = StaticLLMClient([
            LLMResponse(
                text="need tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Alice"}),
                raw={"turn": 1},
            ),
            LLMResponse(text="final answer", needs_tool=False, raw={"turn": 2}),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="find alice", agent_preset=preset)
        )

        self.assertEqual(result.output_text, "final answer")
        self.assertEqual(result.iterations, 2)
        self.assertIsNotNone(result.tool_call)
        assert result.tool_call is not None
        self.assertEqual(result.tool_call.name, "search_customer")
        self.assertIsNotNone(result.tool_result)
        assert result.tool_result is not None
        self.assertEqual(result.tool_result.content, {"keyword": "Alice", "match": "Alice"})
        self.assertEqual(len(client.requests), 2)
        self.assertIsNotNone(client.requests[1].tool_result)
        assert client.requests[1].tool_result is not None
        self.assertEqual(client.requests[1].tool_result.content, {"keyword": "Alice", "match": "Alice"})

    def test_run_by_apid_uses_manager_resolution_path(self) -> None:
        register_llm(2, self._build_llm_config())
        preset = self._build_agent_preset(apid="saved", tools=[])
        self.manager.add_agent_preset(preset)
        client = StaticLLMClient([
            LLMResponse(text="resolved by apid", needs_tool=False),
        ])

        result = run_agent_preset(
            llm_client=client,
            user_input="hello",
            manager=self.manager,
            apid="saved",
        )

        self.assertEqual(result.runtime.preset.apid, "saved")
        self.assertEqual(result.output_text, "resolved by apid")

    def test_run_raises_for_missing_apid_and_missing_agent_preset(self) -> None:
        client = StaticLLMClient([])
        pipeline = AgentPipeline(llm_client=client)

        with self.assertRaises(AgentPresetResolutionError):
            pipeline.run(AgentPipelineInput(user_input="hello"))

    def test_run_raises_when_manager_is_missing_for_apid_lookup(self) -> None:
        client = StaticLLMClient([])
        pipeline = AgentPipeline(llm_client=client)

        with self.assertRaises(AgentPresetResolutionError):
            pipeline.run(AgentPipelineInput(user_input="hello", apid="saved"))

    def test_run_wraps_missing_registry_entries_as_resolution_error(self) -> None:
        client = StaticLLMClient([])
        pipeline = AgentPipeline(llm_client=client)
        preset = self._build_agent_preset(tools=[])

        with self.assertRaises(AgentPresetResolutionError):
            pipeline.run(AgentPipelineInput(user_input="hello", agent_preset=preset))

    def test_run_raises_when_llm_requests_tool_without_tool_call_payload(self) -> None:
        register_llm(2, self._build_llm_config())
        preset = self._build_agent_preset(tools=[])
        client = StaticLLMClient([
            LLMResponse(text="missing tool payload", needs_tool=True, tool_call=None),
        ])

        with self.assertRaises(LLMInvocationError):
            AgentPipeline(llm_client=client).run(AgentPipelineInput(user_input="hello", agent_preset=preset))

    def test_run_raises_when_second_response_requests_more_tools(self) -> None:
        register_llm(2, self._build_llm_config())
        register_tool("search_customer", lambda keyword: {"keyword": keyword})
        preset = self._build_agent_preset(tools=["search_customer"])
        client = StaticLLMClient([
            LLMResponse(
                text="need tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Alice"}),
            ),
            LLMResponse(
                text="still wants tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Bob"}),
            ),
        ])

        with self.assertRaises(LLMInvocationError):
            AgentPipeline(llm_client=client).run(AgentPipelineInput(user_input="hello", agent_preset=preset))

    def test_run_raises_tool_execution_error_when_callable_fails(self) -> None:
        register_llm(2, self._build_llm_config())

        def broken_tool(**kwargs):
            raise RuntimeError("boom")

        register_tool("broken_tool", broken_tool)
        preset = self._build_agent_preset(tools=["broken_tool"])
        client = StaticLLMClient([
            LLMResponse(
                text="need tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="broken_tool", tool_input={"keyword": "Alice"}),
            ),
        ])

        with self.assertRaises(ToolExecutionError):
            AgentPipeline(llm_client=client).run(AgentPipelineInput(user_input="hello", agent_preset=preset))


if __name__ == "__main__":
    unittest.main()
