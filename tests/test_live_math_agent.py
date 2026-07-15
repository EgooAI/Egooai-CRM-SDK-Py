import os
import unittest

from agent_pipeline import AgentPipeline, AgentPipelineInput, OpenAICompatibleLLMClient, register_math_tools
from agent_pipeline.llm_api import register_default_llms
from core import AgentPresetManager, llm_registry, tool_registry
from models import AgentPreset

EXPECTED_MATH_TOOLS = [
    "calculate",
]


def find_live_math_agent(manager: AgentPresetManager) -> AgentPreset:
    for preset in manager.list_agent_preset():
        if preset.intelevel == 2 and preset.tools == EXPECTED_MATH_TOOLS:
            return preset
    raise AssertionError(
        "No math agent preset was found in the database. "
        "Please insert the preset into agentpreset before running the live test."
    )


def run_real_llm_math_agent_live_test() -> None:
    register_default_llms()
    register_math_tools()
    manager = AgentPresetManager()
    preset = find_live_math_agent(manager)
    client = OpenAICompatibleLLMClient(llm_registry.require(2))
    result = AgentPipeline(llm_client=client, manager=manager).run(
        AgentPipelineInput(
            user_input="Use the calculate tool to multiply 7 by 8 and return JSON only.",
            apid=preset.apid,
        )
    )
    assert result.tool_call is not None
    assert result.tool_call.name == "calculate"
    assert result.tool_result is not None
    assert result.tool_result.content == 56
    assert "56" in result.output_text


@unittest.skipUnless(os.environ.get("RUN_LIVE_LLM_TEST") == "1", "Set RUN_LIVE_LLM_TEST=1 to run the live LLM test.")
class LiveMathAgentTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        tool_registry.clear()
        llm_registry.clear()

    def test_real_llm_math_agent_live(self) -> None:
        run_real_llm_math_agent_live_test()


if __name__ == "__main__":
    os.environ.setdefault("RUN_LIVE_LLM_TEST", "1")
    unittest.main()
