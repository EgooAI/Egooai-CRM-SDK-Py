import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from agent_pipeline import (
    AgentPipeline,
    AgentPipelineInput,
    AgentPipelineResultStatus,
    AgentPresetResolutionError,
    LLMConfig,
    LLMInvocationError,
    LLMResponse,
    LLMToolCall,
    llm_registry,
    output_normalizer_registry,
    register_llm,
    register_output_normalizer,
    register_tool,
    tool_registry,
)
from agent_pipeline.llm import StaticLLMClient
from core import AgentPresetManager
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
        output_normalizer_registry.clear()
        self.temp_dir.cleanup()

    @staticmethod
    def _build_llm_config(model_name: str = "example-model") -> LLMConfig:
        return LLMConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            model_name=model_name,
        )

    @staticmethod
    def _build_llm_config_with_system_prompt(system_prompt: str) -> LLMConfig:
        return LLMConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            model_name="example-model",
            system_prompt=system_prompt,
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
            "llm_level": 2,
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

        self.assertEqual(result.status, AgentPipelineResultStatus.COMPLETED)
        self.assertEqual(result.output_text, "direct answer")
        self.assertEqual(result.iterations, 1)
        self.assertIsNone(result.tool_call)
        self.assertIsNone(result.tool_result)
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(client.requests[0].system_prompt, "Help the customer politely")

    def test_run_combines_llm_and_agent_system_prompts(self) -> None:
        register_llm(2, self._build_llm_config_with_system_prompt("Follow company policy."))
        preset = self._build_agent_preset(tools=[])
        client = StaticLLMClient([
            LLMResponse(text="direct answer", needs_tool=False, raw={"turn": 1}),
        ])

        AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="hello", agent_preset=preset)
        )

        self.assertEqual(
            client.requests[0].system_prompt,
            "Follow company policy.\n\nHelp the customer politely",
        )

    def test_run_rejects_oversized_context_before_invoking_llm(self) -> None:
        for context, user_input in ((10, "hello"), (120, "A" * 40)):
            with self.subTest(context=context, user_input=user_input):
                register_llm(2, LLMConfig(
                    base_url="https://api.example.com/v1",
                    api_key="secret",
                    model_name="example-model",
                    context=context,
                ))
                client = StaticLLMClient([])
                result = AgentPipeline(llm_client=client).run(
                    AgentPipelineInput(user_input=user_input, agent_preset=self._build_agent_preset(tools=[]))
                )

                self.assertEqual(result.status, AgentPipelineResultStatus.CONTEXT_LIMITED)
                self.assertEqual(result.iterations, 0)
                self.assertEqual(result.output_text, "")
                self.assertEqual(client.requests, [])

    def test_run_applies_registered_output_normalizer(self) -> None:
        register_llm(2, self._build_llm_config())
        register_output_normalizer(
            "normalized-agent",
            lambda raw_text: f"[normalized] {raw_text}",
        )
        preset = self._build_agent_preset(apid="normalized-agent", tools=[])
        client = StaticLLMClient([
            LLMResponse(
                text='{"buyer_language":"English","items":[]}',
                needs_tool=False,
                raw={"turn": 1},
            ),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="conversation", agent_preset=preset)
        )

        self.assertEqual(result.iterations, 1)
        self.assertEqual(
            result.output_text,
            '[normalized] {"buyer_language":"English","items":[]}',
        )

    def test_run_can_execute_multiple_tool_rounds(self) -> None:
        register_llm(2, self._build_llm_config())
        register_tool("first_tool", lambda keyword: {"keyword": keyword, "step": 1})
        register_tool("second_tool", lambda keyword: {"keyword": keyword, "step": 2})
        preset = self._build_agent_preset(tools=["first_tool", "second_tool"])
        client = StaticLLMClient([
            LLMResponse(
                text="need first tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="first_tool", tool_input={"keyword": "Alice"}),
                raw={"turn": 1},
            ),
            LLMResponse(
                text="need second tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="second_tool", tool_input={"keyword": "Bob"}),
                raw={"turn": 2},
            ),
            LLMResponse(text="final answer", needs_tool=False, raw={"turn": 3}),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="find alice", agent_preset=preset)
        )

        self.assertEqual(result.output_text, "final answer")
        self.assertEqual(result.iterations, 3)
        self.assertIsNotNone(result.tool_call)
        assert result.tool_call is not None
        self.assertEqual(result.tool_call.name, "second_tool")
        self.assertIsNotNone(result.tool_result)
        assert result.tool_result is not None
        self.assertEqual(result.tool_result.content, {"keyword": "Bob", "step": 2})
        self.assertEqual(len(client.requests), 3)
        self.assertEqual([len(request.tool_results) for request in client.requests], [0, 1, 2])
        self.assertEqual(
            [call.name for call in client.requests[2].tool_calls],
            ["first_tool", "second_tool"],
        )
        self.assertEqual(client.requests[2].tool_results[0].content, {"keyword": "Alice", "step": 1})
        self.assertEqual(
            [
                request.tool_results[-1].content if request.tool_results else None
                for request in client.requests
            ],
            [None, {"keyword": "Alice", "step": 1}, {"keyword": "Bob", "step": 2}],
        )

    def test_run_by_apid_uses_manager_resolution_path(self) -> None:
        register_llm(2, self._build_llm_config())
        preset = self._build_agent_preset(apid="saved", tools=[])
        self.manager.add_agent_preset(preset)
        client = StaticLLMClient([
            LLMResponse(text="resolved by apid", needs_tool=False),
        ])

        result = AgentPipeline(llm_client=client, manager=self.manager).run(
            AgentPipelineInput(user_input="hello", apid="saved")
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

    def test_run_honors_configured_tool_limit_and_default_budget(self) -> None:
        register_tool("search_customer", lambda keyword: {"keyword": keyword})
        preset = self._build_agent_preset(tools=["search_customer"])
        cases = (
            (5, AgentPipelineResultStatus.TOOL_ROUNDS_LIMITED, 5, "", "Eve"),
            (None, AgentPipelineResultStatus.COMPLETED, 7, "final answer", "Frank"),
        )
        for limit, status, iterations, output, last_keyword in cases:
            with self.subTest(max_tool_rounds=limit):
                register_llm(2, LLMConfig(
                    base_url="https://api.example.com/v1",
                    api_key="secret",
                    model_name="example-model",
                    max_tool_rounds=limit,
                ))
                responses = [
                    LLMResponse(
                        text="need tool",
                        needs_tool=True,
                        tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": keyword}),
                    )
                    for keyword in ("Alice", "Bob", "Carol", "Dave", "Eve", "Frank")
                ]
                client = StaticLLMClient(responses + [LLMResponse(text="final answer")])
                result = AgentPipeline(llm_client=client).run(
                    AgentPipelineInput(user_input="hello", agent_preset=preset)
                )

                self.assertEqual(result.status, status)
                self.assertEqual(result.output_text, output)
                self.assertEqual(result.iterations, iterations)
                self.assertEqual(len(client.requests), iterations)
                self.assertEqual(result.tool_call.name, "search_customer")
                self.assertEqual(result.tool_result.content, {"keyword": last_keyword})

    def test_run_feeds_tool_errors_back_to_llm_and_continues(self) -> None:
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
            LLMResponse(text="recovered answer", needs_tool=False),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="hello", agent_preset=preset)
        )

        self.assertEqual(result.output_text, "recovered answer")
        self.assertEqual(result.iterations, 2)
        self.assertIsNotNone(result.tool_result)
        assert result.tool_result is not None
        self.assertFalse(result.tool_result.ok)
        self.assertEqual(result.tool_result.error, "boom")
        self.assertEqual(client.requests[1].tool_results[0].error, "boom")


    def test_tool_schema_uses_parameterized_annotations(self) -> None:
        register_llm(2, self._build_llm_config())

        def lookup(
            count: int, price: float, enabled: bool, data: dict, items: list,
            text: str, params: dict[str, Any], ids: list[int], limit: int | None = None,
        ) -> str:
            return "ok"

        register_tool("lookup", lookup)
        preset = self._build_agent_preset(tools=["lookup"])
        client = StaticLLMClient([
            LLMResponse(text="answer", needs_tool=False),
        ])

        AgentPipeline(llm_client=client).run(AgentPipelineInput(user_input="hello", agent_preset=preset))

        schema = client.requests[0].tool_schemas[0]
        self.assertEqual(
            {name: spec["type"] for name, spec in schema.parameters["properties"].items()},
            {
                "count": "number", "price": "number", "enabled": "boolean",
                "data": "object", "items": "array", "text": "string",
                "params": "object", "ids": "array", "limit": "number",
            },
        )
        self.assertEqual(
            schema.parameters["required"],
            ["count", "price", "enabled", "data", "items", "text", "params", "ids"],
        )


if __name__ == "__main__":
    unittest.main()
