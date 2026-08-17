import unittest

from agent_pipeline.registry import tool_registry
from agent_tools import calculate, register_builtin_tools


class AgentPipelineExportsTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        tool_registry.clear()

    def test_importing_package_does_not_register_builtin_tools(self) -> None:
        self.assertIsNone(tool_registry.get("calculate"))

    def test_register_builtin_tools_registers_calculate(self) -> None:
        register_builtin_tools()

        self.assertIs(tool_registry.require("calculate"), calculate)


if __name__ == "__main__":
    unittest.main()