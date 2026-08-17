import unittest

from agent_pipeline import (
    AgentPipeline,
    AgentPipelineError,
    AgentPipelineInput,
    AgentPipelineResult,
    AgentPipelineResultStatus,
    AgentPresetResolutionError,
    LLMClient,
    LLMInvocationError,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolSchema,
    ToolExecutionResult,
    ToolExecutor,
    ToolSelectionError,
)
from agent_pipeline.registry import tool_registry
from agent_tools import calculate, register_builtin_tools


class AgentPipelineExportsTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        tool_registry.clear()

    def test_public_exports_are_importable(self) -> None:
        self.assertTrue(callable(AgentPipeline))
        self.assertTrue(callable(AgentPipelineInput))
        self.assertTrue(callable(AgentPipelineResult))
        self.assertTrue(callable(AgentPipelineResultStatus))
        self.assertTrue(callable(LLMRequest))
        self.assertTrue(callable(LLMResponse))
        self.assertTrue(callable(LLMToolCall))
        self.assertTrue(callable(LLMToolSchema))
        self.assertTrue(callable(ToolExecutionResult))
        self.assertTrue(callable(ToolExecutor))
        self.assertTrue(callable(AgentPipelineError))
        self.assertTrue(callable(AgentPresetResolutionError))
        self.assertTrue(callable(LLMInvocationError))
        self.assertTrue(callable(ToolSelectionError))
        self.assertTrue(hasattr(LLMClient, "invoke"))
        self.assertTrue(callable(calculate))
        self.assertTrue(callable(register_builtin_tools))

    def test_importing_package_does_not_register_builtin_tools(self) -> None:
        self.assertIsNone(tool_registry.get("calculate"))

    def test_register_builtin_tools_registers_calculate(self) -> None:
        register_builtin_tools()

        self.assertIs(tool_registry.require("calculate"), calculate)


if __name__ == "__main__":
    unittest.main()