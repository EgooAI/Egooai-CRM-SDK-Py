import unittest

from agent_pipeline import ToolExecutionError, ToolExecutor, ToolSelectionError
from core import AgentPresetRuntimeConfig, LLMConfig
from models import AgentPreset


class ToolExecutorTestCase(unittest.TestCase):
    @staticmethod
    def _build_runtime(tool_names, tools) -> AgentPresetRuntimeConfig:
        preset = AgentPreset(
            apid="default-assistant",
            name="default assistant",
            description="General customer service preset",
            prompt="Help the customer politely",
            intelevel=2,
            tools=tool_names,
        )
        return AgentPresetRuntimeConfig(
            preset=preset,
            llm=LLMConfig(base_url="https://api.example.com", api_key="secret", model_name="model"),
            tools=tools,
            tool_names=tool_names,
        )

    def test_execute_tool_with_keyword_arguments(self) -> None:
        def search_customer(keyword: str) -> dict[str, str]:
            return {"keyword": keyword}

        runtime = self._build_runtime(["search_customer"], [search_customer])
        result = ToolExecutor().execute(runtime, "search_customer", {"keyword": "Alice"})

        self.assertTrue(result.ok)
        self.assertEqual(result.content, {"keyword": "Alice"})

    def test_execute_tool_with_empty_input(self) -> None:
        def ping() -> str:
            return "pong"

        runtime = self._build_runtime(["ping"], [ping])
        result = ToolExecutor().execute(runtime, "ping", None)

        self.assertEqual(result.content, "pong")

    def test_execute_tool_coerces_numeric_strings_using_annotations(self) -> None:
        def multiply_numbers(a: float, b: float) -> float:
            return a * b

        runtime = self._build_runtime(["multiply_numbers"], [multiply_numbers])
        result = ToolExecutor().execute(runtime, "multiply_numbers", {"a": "7", "b": "8"})

        self.assertEqual(result.content, 56.0)

    def test_execute_tool_raises_for_missing_tool_name(self) -> None:
        def ping() -> str:
            return "pong"

        runtime = self._build_runtime(["ping"], [ping])

        with self.assertRaises(ToolSelectionError):
            ToolExecutor().execute(runtime, "missing", {})

    def test_execute_tool_wraps_callable_errors(self) -> None:
        def broken() -> None:
            raise RuntimeError("boom")

        runtime = self._build_runtime(["broken"], [broken])

        with self.assertRaises(ToolExecutionError):
            ToolExecutor().execute(runtime, "broken", {})


if __name__ == "__main__":
    unittest.main()
