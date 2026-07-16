import unittest

from agent_pipeline import (
    AgentPipeline,
    AgentPipelineError,
    AgentPipelineInput,
    AgentPipelineResult,
    AgentPresetResolutionError,
    LLMClient,
    LLMInvocationError,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    StaticLLMClient,
    ToolExecutionError,
    ToolExecutionResult,
    ToolExecutor,
    ToolSelectionError,
    calculate,
    register_builtin_tools,
    run_agent_preset,
)
from core import tool_registry


class AgentPipelineExportsTestCase(unittest.TestCase):
    def test_public_exports_are_importable(self) -> None:
        self.assertTrue(callable(AgentPipeline))
        self.assertTrue(callable(AgentPipelineInput))
        self.assertTrue(callable(AgentPipelineResult))
        self.assertTrue(callable(LLMRequest))
        self.assertTrue(callable(LLMResponse))
        self.assertTrue(callable(LLMToolCall))
        self.assertTrue(callable(ToolExecutionResult))
        self.assertTrue(callable(StaticLLMClient))
        self.assertTrue(callable(ToolExecutor))
        self.assertTrue(callable(run_agent_preset))
        self.assertTrue(callable(AgentPipelineError))
        self.assertTrue(callable(AgentPresetResolutionError))
        self.assertTrue(callable(LLMInvocationError))
        self.assertTrue(callable(ToolSelectionError))
        self.assertTrue(callable(ToolExecutionError))
        self.assertTrue(hasattr(LLMClient, "invoke"))
        self.assertTrue(callable(calculate))
        self.assertTrue(callable(register_builtin_tools))

    def test_register_builtin_tools_registers_calculate(self) -> None:
        register_builtin_tools()

        self.assertIs(tool_registry.require("calculate"), calculate)


if __name__ == "__main__":
    unittest.main()
