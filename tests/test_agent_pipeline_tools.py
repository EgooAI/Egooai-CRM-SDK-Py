import unittest
from typing import Annotated

from agent_pipeline import (
    AgentPipeline,
    AgentPipelineInput,
    LLMConfig,
    LLMResponse,
    LLMToolCall,
    LLMUsage,
    OpenAICompatibleLLMClient,
    ToolContext,
    ToolExecutionResult,
    ToolExecutor,
    ToolSpec,
    build_tool_schema,
    register_llm,
    register_tool,
    tool_registry,
)
from agent_pipeline.llm import StaticLLMClient
from agent_pipeline.resolver import AgentPresetRuntimeConfig
from models import AgentPreset


class ToolExecutorTestCase(unittest.TestCase):
    @staticmethod
    def _build_runtime(tool_names, tools, specs=None) -> AgentPresetRuntimeConfig:
        preset = AgentPreset(
            apid="default-assistant",
            name="default assistant",
            description="General customer service preset",
            prompt="Help the customer politely",
            llm_level=2,
            tools=tool_names,
        )
        return AgentPresetRuntimeConfig(
            preset=preset,
            llm=LLMConfig(base_url="https://api.example.com", api_key="secret", model_name="model"),
            tools=tools,
            tool_names=tool_names,
            tool_specs=tuple(specs or [None] * len(tool_names)),
        )

    def test_execute_tool_with_keyword_arguments(self) -> None:
        def search_customer(keyword: str) -> dict[str, str]:
            return {"keyword": keyword}

        runtime = self._build_runtime(["search_customer"], [search_customer])
        result, record = ToolExecutor().execute(runtime, "search_customer", {"keyword": "Alice"})

        self.assertTrue(result.ok)
        self.assertEqual(result.content, {"keyword": "Alice"})
        self.assertTrue(record.ok)
        self.assertEqual(record.arguments, {"keyword": "Alice"})

    def test_execute_tool_with_empty_input(self) -> None:
        def ping() -> str:
            return "pong"

        runtime = self._build_runtime(["ping"], [ping])
        result, _ = ToolExecutor().execute(runtime, "ping", None)

        self.assertEqual(result.content, "pong")

    def test_execute_tool_coerces_numeric_strings_using_annotations(self) -> None:
        def multiply_numbers(a: float, b: float) -> float:
            return a * b

        runtime = self._build_runtime(["multiply_numbers"], [multiply_numbers])
        result, _ = ToolExecutor().execute(runtime, "multiply_numbers", {"a": "7", "b": "8"})

        self.assertEqual(result.content, 56.0)

    def test_execute_unknown_tool_is_a_failure_result_not_an_exception(self) -> None:
        def ping() -> str:
            return "pong"

        runtime = self._build_runtime(["ping"], [ping])
        result, record = ToolExecutor().execute(runtime, "missing", {})

        self.assertFalse(result.ok)
        self.assertIn("missing", result.error or "")
        self.assertFalse(record.ok)

    def test_execute_tool_returns_error_result_on_callable_failure(self) -> None:
        def broken() -> None:
            raise RuntimeError("boom")

        runtime = self._build_runtime(["broken"], [broken])
        result, _ = ToolExecutor().execute(runtime, "broken", {})

        self.assertFalse(result.ok)
        self.assertIn("boom", result.error or "")

    def test_execute_tool_times_out(self) -> None:
        import time

        def slow() -> str:
            time.sleep(0.2)
            return "late"

        runtime = self._build_runtime(["slow"], [slow], [ToolSpec(name="slow", timeout_seconds=0.01)])
        result, _ = ToolExecutor().execute(runtime, "slow", {})

        self.assertFalse(result.ok)
        self.assertIn("超时", result.error or "")

    def test_context_parameter_is_injected_and_hidden_from_schema(self) -> None:
        def request_reply(ctx: ToolContext, reply: str) -> str:
            ctx.emit("reply", {"reply": reply})
            return "ok"

        spec = ToolSpec(name="request_reply", category="effect")
        runtime = self._build_runtime(["request_reply"], [request_reply], [spec])
        context = ToolContext(mode="simulated", scope={"sid": 1})
        result, _ = ToolExecutor().execute(runtime, "request_reply", {"reply": "hi"}, context=context)

        self.assertTrue(result.ok)
        self.assertEqual([intent.kind for intent in context.intents], ["reply"])
        self.assertEqual(context.intents[0].mode, "simulated")
        schema = build_tool_schema(request_reply, spec)
        self.assertEqual(list(schema["properties"]), ["reply"])

    def test_annotated_parameter_description_reaches_schema(self) -> None:
        def say(
            reply: Annotated[str, "买家语言回复"],
            tone: Annotated[str, "语气：formal / friendly / urgent"] = "formal",
        ) -> str:
            return reply

        schema = build_tool_schema(say)
        self.assertEqual(schema["properties"]["reply"]["description"], "买家语言回复")
        self.assertEqual(schema["properties"]["tone"]["description"], "语气：formal / friendly / urgent")
        self.assertEqual(schema["required"], ["reply"])

    def test_spec_parameter_description_is_used_when_annotation_has_none(self) -> None:
        def say(reply: str) -> str:
            return reply

        schema = build_tool_schema(say, ToolSpec(name="say", parameter_descriptions={"reply": "回复正文"}))
        self.assertEqual(schema["properties"]["reply"]["description"], "回复正文")


class _PipelineCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client: StaticLLMClient | None = None

    def tearDown(self) -> None:
        from agent_pipeline import llm_registry, output_normalizer_registry

        tool_registry.clear()
        llm_registry.clear()
        output_normalizer_registry.clear()

    @staticmethod
    def _preset(*, tools: list[str], requires_tool: bool = False, apid: str = "p") -> AgentPreset:
        return AgentPreset(
            apid=apid, name="p", description="d", prompt="Answer politely",
            llm_level=2, tools=tools, requires_tool=requires_tool,
        )

    @staticmethod
    def _llm(**kwargs) -> None:
        register_llm(2, LLMConfig(
            base_url="https://api.example.com/v1", api_key="k", model_name="m", **kwargs,
        ))

    def test_one_response_with_two_calls_executes_both_in_order(self) -> None:
        self._llm()
        register_tool("a", lambda x: f"a:{x}")
        register_tool("b", lambda x: f"b:{x}")
        client = StaticLLMClient([
            LLMResponse(
                text="", needs_tool=True,
                tool_calls=[LLMToolCall(name="a", tool_input={"x": 1}, call_id="c1"),
                            LLMToolCall(name="b", tool_input={"x": 2}, call_id="c2")],
            ),
            LLMResponse(text="done"),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["a", "b"]))
        )

        self.assertEqual([record.name for record in result.tool_call_records], ["a", "b"])
        self.assertEqual([record.ok for record in result.tool_call_records], [True, True])
        self.assertEqual([record.call_id for record in result.tool_call_records], ["c1", "c2"])
        self.assertEqual([len(exchange.results) for exchange in result.tool_exchanges], [2])
        self.assertEqual(result.output_text, "done")
        # The second request replays one assistant message with both calls.
        second = client.requests[1]
        self.assertEqual([call.call_id for call in second.tool_calls], ["c1", "c2"])
        self.assertEqual([item.call_id for item in second.tool_results], ["c1", "c2"])

    def test_model_client_replays_multiple_calls_in_one_assistant_message(self) -> None:
        client = OpenAICompatibleLLMClient(LLMConfig(base_url="https://e/v1", api_key="k", model_name="m"))
        from agent_pipeline.types import LLMRequest, LLMToolSchema, ToolExchange

        payload = client._build_payload(LLMRequest(
            system_prompt="s", user_input="u", tool_prompt="t",
            tool_schemas=[LLMToolSchema(name="a", description="A")],
            tool_exchanges=[ToolExchange(
                calls=[LLMToolCall(name="a", tool_input={"x": 1}, call_id="c1"),
                       LLMToolCall(name="a", tool_input={"x": 2}, call_id="c2")],
                results=[ToolExecutionResult(name="a", ok=True, content=1, call_id="c1"),
                         ToolExecutionResult(name="a", ok=True, content=2, call_id="c2")],
            )],
        ))
        roles = [message["role"] for message in payload["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "tool"])
        self.assertEqual([call["id"] for call in payload["messages"][2]["tool_calls"]], ["c1", "c2"])
        self.assertEqual(payload["tool_choice"], "auto")

    def test_unknown_tool_keeps_running_and_model_sees_the_error(self) -> None:
        self._llm()
        register_tool("known", lambda: "ok")
        client = StaticLLMClient([
            LLMResponse(text="", needs_tool=True, tool_call=LLMToolCall(name="nope", tool_input={})),
            LLMResponse(text="recovered"),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["known"]))
        )

        self.assertEqual(result.status.value, "completed")
        self.assertEqual(result.output_text, "recovered")
        self.assertFalse(result.tool_call_records[0].ok)
        self.assertIn("nope", client.requests[1].tool_results[0].error or "")

    def test_invalid_arguments_json_is_reported_and_run_continues(self) -> None:
        self._llm()
        register_tool("a", lambda x: x)
        client = StaticLLMClient([
            LLMResponse(
                text="", needs_tool=True,
                tool_call=LLMToolCall(name="a", tool_input={}, input_error="工具参数不是合法 JSON"),
            ),
            LLMResponse(text="fixed"),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["a"]))
        )

        self.assertEqual(result.output_text, "fixed")
        self.assertEqual(len(result.tool_call_records), 1)
        self.assertFalse(result.tool_call_records[0].ok)

    def test_exactly_max_rounds_still_returns_text_and_records(self) -> None:
        self._llm()
        register_tool("search", lambda keyword: {"keyword": keyword})
        client = StaticLLMClient([
            LLMResponse(text="", needs_tool=True, tool_call=LLMToolCall(name="search", tool_input={"keyword": str(i)}))
            for i in range(3)
        ] + [LLMResponse(text="final answer")])

        result = AgentPipeline(llm_client=client, max_tool_rounds=3).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["search"]))
        )

        # Three tool rounds exhaust the budget; the forced closing request then
        # supplies text, so a run that used exactly its rounds is not restricted.
        self.assertEqual(result.status.value, "completed")
        self.assertEqual(result.output_text, "final answer")
        self.assertEqual(result.iterations, 4)
        self.assertEqual(len(result.tool_call_records), 3)

    def test_hitting_the_round_limit_forces_a_closing_answer(self) -> None:
        self._llm()
        register_tool("search", lambda keyword: {"keyword": keyword})
        tool_responses = [
            LLMResponse(text="", needs_tool=True, tool_call=LLMToolCall(name="search", tool_input={"keyword": "x"}))
            for _ in range(2)
        ]
        client = StaticLLMClient(tool_responses + [LLMResponse(text="已收集到的信息")])

        result = AgentPipeline(llm_client=client, max_tool_rounds=2).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["search"]))
        )

        self.assertEqual(result.status.value, "completed")
        self.assertFalse(result.restricted)
        self.assertEqual(result.output_text, "已收集到的信息")
        self.assertEqual(len(result.tool_call_records), 2)
        self.assertEqual(result.iterations, 3)
        # The closing request disables tools entirely.
        self.assertEqual(client.requests[-1].tool_choice, "none")
        self.assertEqual(client.requests[-1].tool_schemas, [])

    def test_total_call_cap_bounds_parallel_calls(self) -> None:
        self._llm()
        register_tool("a", lambda x: x)
        calls = [LLMToolCall(name="a", tool_input={"x": i}, call_id=f"c{i}") for i in range(4)]
        client = StaticLLMClient([
            LLMResponse(text="", needs_tool=True, tool_calls=calls),
            LLMResponse(text="", needs_tool=True, tool_calls=calls),
            LLMResponse(text="limited"),
        ])

        result = AgentPipeline(llm_client=client, max_tool_calls=2).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["a"]))
        )

        self.assertEqual(result.status.value, "tool_rounds_limited")
        self.assertEqual(result.output_text, "limited")
        self.assertEqual(len(result.tool_call_records), 4)
        self.assertEqual(
            [record.ok for record in result.tool_call_records], [True, True, False, False],
        )
        self.assertIn("上限", result.tool_call_records[2].error or "")
        self.assertEqual(len(client.requests), 3)

    def test_non_repeatable_tool_rejects_second_call(self) -> None:
        self._llm()
        register_tool("once", lambda: "v", spec=ToolSpec(name="once", repeatable=False))
        client = StaticLLMClient([
            LLMResponse(text="", needs_tool=True, tool_call=LLMToolCall(name="once", tool_input={})),
            LLMResponse(text="", needs_tool=True, tool_call=LLMToolCall(name="once", tool_input={})),
            LLMResponse(text="done"),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["once"]))
        )

        self.assertEqual([record.ok for record in result.tool_call_records], [True, False])
        self.assertIn("最多调用一次", result.tool_call_records[1].error or "")

    def test_requires_tool_forces_tool_choice(self) -> None:
        self._llm()
        register_tool("reply", lambda text: text)
        client = StaticLLMClient([LLMResponse(text="hi")])

        AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["reply"], requires_tool=True))
        )

        self.assertEqual(client.requests[0].tool_choice, "required")

    def test_requires_tool_without_tools_is_a_configuration_error(self) -> None:
        from agent_pipeline import AgentPresetResolutionError

        self._llm()
        with self.assertRaises(AgentPresetResolutionError):
            AgentPipeline(llm_client=StaticLLMClient([])).run(
                AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=[], requires_tool=True))
            )

    def test_effect_intents_are_collected_only_for_successful_calls(self) -> None:
        self._llm()

        def reply_customer(ctx: ToolContext, text: str) -> str:
            if text == "bad":
                ctx.emit("reply", {"text": "discarded"})
                raise ValueError("rejected")
            ctx.emit("reply", {"text": text})
            return "recorded"

        register_tool("reply_customer", reply_customer, spec=ToolSpec(name="reply_customer", category="effect"))
        client = StaticLLMClient([
            LLMResponse(text="", needs_tool=True, tool_call=LLMToolCall(name="reply_customer", tool_input={"text": "bad"})),
            LLMResponse(text="", needs_tool=True, tool_call=LLMToolCall(name="reply_customer", tool_input={"text": "hi"})),
            LLMResponse(text="done"),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(
                user_input="go", agent_preset=self._preset(tools=["reply_customer"]),
                tool_context=ToolContext(mode="simulated"),
            )
        )

        self.assertEqual([intent.content["text"] for intent in result.intents], ["hi"])
        self.assertEqual(result.intents[0].mode, "simulated")
        self.assertEqual(result.intents[0].sequence, 1)

    def test_usage_is_accumulated_across_rounds(self) -> None:

        self._llm()
        register_tool("a", lambda: "v")
        client = StaticLLMClient([
            LLMResponse(text="", needs_tool=True, tool_call=LLMToolCall(name="a", tool_input={}),
                        usage=LLMUsage(prompt_tokens=10, completion_tokens=2, total_tokens=12)),
            LLMResponse(text="done", usage=LLMUsage(prompt_tokens=20, completion_tokens=3, total_tokens=23)),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["a"]))
        )

        self.assertEqual(result.usage.prompt_tokens, 30)
        self.assertEqual(result.usage.total_tokens, 35)

    def test_rejected_forced_tool_choice_degrades_to_auto_once(self) -> None:
        from agent_pipeline import LLMInvocationError

        self._llm()
        register_tool("reply", lambda text: text)
        seen: list[str] = []

        class _Client:
            def __init__(self, responses):
                self.responses = list(responses)

            def invoke(self, request):
                seen.append(request.tool_choice)
                if request.tool_choice == "required":
                    raise LLMInvocationError(
                        "LLM API HTTP 400: Thinking mode does not support this tool_choice"
                    )
                return self.responses.pop(0)

        client = _Client([
            LLMResponse(text="", needs_tool=True, tool_call=LLMToolCall(name="reply", tool_input={"text": "hi"})),
            LLMResponse(text="done"),
        ])

        result = AgentPipeline(llm_client=client).run(
            AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["reply"], requires_tool=True))
        )

        self.assertEqual(seen, ["required", "auto", "auto"])
        self.assertEqual(result.output_text, "done")
        self.assertEqual(len(result.tool_call_records), 1)

    def test_a_rejected_choice_is_not_retried_forever(self) -> None:
        from agent_pipeline import LLMInvocationError

        self._llm()
        register_tool("reply", lambda text: text)

        class _Rejecting:
            def __init__(self):
                self.calls = 0

            def invoke(self, request):
                self.calls += 1
                raise LLMInvocationError("LLM API HTTP 400: tool_choice is not supported")

        client = _Rejecting()
        with self.assertRaises(LLMInvocationError):
            AgentPipeline(llm_client=client).run(
                AgentPipelineInput(user_input="go", agent_preset=self._preset(tools=["reply"], requires_tool=True))
            )
        self.assertEqual(client.calls, 2)


if __name__ == "__main__":
    unittest.main()
