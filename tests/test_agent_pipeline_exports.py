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
    run_agent_preset,
)


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


if __name__ == "__main__":
    unittest.main()
