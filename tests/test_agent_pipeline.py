import os
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
from core.system_agents import CHAT_REPLY_SUGGESTION_AGENT_APID
from models import AgentPreset


class AgentPipelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "agent_pipeline.sqlite"
        self.manager = AgentPresetManager(database_path=self.db_path)
        self.original_system_prompt = os.environ.get("SYSTEM_PROMPT")

    def tearDown(self) -> None:
        self.manager.engine.dispose()
        tool_registry.clear()
        llm_registry.clear()
        if self.original_system_prompt is None:
            os.environ.pop("SYSTEM_PROMPT", None)
        else:
            os.environ["SYSTEM_PROMPT"] = self.original_system_prompt
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

    def test_run_prepends_global_system_prompt_from_env(self) -> None:
        os.environ["SYSTEM_PROMPT"] = "Global compliance rules."
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
            "Global compliance rules.\n\nFollow company policy.\n\nHelp the customer politely",
        )

    def test_run_returns_business_prompt_when_context_limit_is_exceeded(self) -> None:
        register_llm(
            2,
            LLMConfig(
                base_url="https://api.example.com/v1",
                api_key="secret",
                model_name="example-model",
                context=10,
                context_limit_output_text="上下文超过限制",
            ),
        )
        preset = self._build_agent_preset(tools=[])
        client = StaticLLMClient([
            LLMResponse(text="should not be called", needs_tool=False, raw={"turn": 1}),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="hello", agent_preset=preset)
        )

        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.output_text, "上下文超过限制")
        self.assertEqual(len(client.requests), 0)

    def test_run_returns_business_prompt_when_user_input_text_exceeds_context_limit(self) -> None:
        register_llm(
            2,
            LLMConfig(
                base_url="https://api.example.com/v1",
                api_key="secret",
                model_name="example-model",
                context=120,
                context_limit_output_text="文本超过限制",
            ),
        )
        preset = self._build_agent_preset(tools=[])
        client = StaticLLMClient([
            LLMResponse(text="should not be called", needs_tool=False, raw={"turn": 1}),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="A" * 40, agent_preset=preset)
        )

        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.output_text, "文本超过限制")
        self.assertEqual(len(client.requests), 0)

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
        self.assertEqual(len(client.requests[1].tool_results), 1)
        self.assertEqual(client.requests[1].tool_results[0].content, {"keyword": "Alice", "match": "Alice"})

    def test_system_agent_normalizes_direct_json_output(self) -> None:
        register_llm(2, self._build_llm_config())
        preset = self._build_agent_preset(
            apid=CHAT_REPLY_SUGGESTION_AGENT_APID,
            tools=[],
        )
        client = StaticLLMClient([
            LLMResponse(
                text='{"buyer_language":"English","items":[{"zh":"您好","reply":"Hello"}]}',
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
            '{"buyer_language": "English", "items": [{"zh": "您好", "reply": "Hello"}]}',
        )
        self.assertEqual(client.requests[0].tool_names, [])

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

    def test_run_returns_unknown_after_more_than_five_tool_rounds(self) -> None:
        register_llm(
            2,
            LLMConfig(
                base_url="https://api.example.com/v1",
                api_key="secret",
                model_name="example-model",
                tool_round_limit_output_text="调用超过次数限制",
                max_tool_rounds=5,
            ),
        )
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
            LLMResponse(
                text="still wants tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Carol"}),
            ),
            LLMResponse(
                text="still wants tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Dave"}),
            ),
            LLMResponse(
                text="still wants tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Eve"}),
            ),
            LLMResponse(
                text="still wants tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Frank"}),
            ),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="hello", agent_preset=preset)
        )

        self.assertEqual(result.output_text, "调用超过次数限制")
        self.assertEqual(result.iterations, 6)
        self.assertIsNotNone(result.tool_call)
        assert result.tool_call is not None
        self.assertEqual(result.tool_call.name, "search_customer")
        self.assertIsNotNone(result.tool_result)
        assert result.tool_result is not None
        self.assertEqual(result.tool_result.content, {"keyword": "Eve"})

    def test_run_allows_more_than_five_tool_rounds_when_config_has_no_limit(self) -> None:
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
            LLMResponse(
                text="still wants tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Carol"}),
            ),
            LLMResponse(
                text="still wants tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Dave"}),
            ),
            LLMResponse(
                text="still wants tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Eve"}),
            ),
            LLMResponse(
                text="still wants tool",
                needs_tool=True,
                tool_call=LLMToolCall(name="search_customer", tool_input={"keyword": "Frank"}),
            ),
            LLMResponse(text="final answer", needs_tool=False),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="hello", agent_preset=preset)
        )

        self.assertEqual(result.output_text, "final answer")
        self.assertEqual(result.iterations, 7)
        self.assertIsNotNone(result.tool_call)
        assert result.tool_call is not None
        self.assertEqual(result.tool_call.name, "search_customer")
        self.assertIsNotNone(result.tool_result)
        assert result.tool_result is not None
        self.assertEqual(result.tool_result.content, {"keyword": "Frank"})

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
