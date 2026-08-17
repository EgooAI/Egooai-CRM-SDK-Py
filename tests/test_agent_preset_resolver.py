import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_pipeline.registry import LLMConfig, llm_registry, register_llm, register_tool, tool_registry
from agent_pipeline.resolver import (
    require_agent_preset_by_apid,
    resolve_agent_preset,
    resolve_agent_preset_by_apid,
)
from core import AgentPresetManager
from models import AgentPreset


class AgentPresetResolverTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "agent_preset_resolver.sqlite"
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

    @staticmethod
    def _search_tool(keyword: str) -> dict[str, str]:
        return {"keyword": keyword}

    @staticmethod
    def _calendar_tool(date_text: str) -> dict[str, str]:
        return {"date": date_text}

    def _build_agent_preset(
        self,
        apid: str = "default-assistant",
        llm_level: int = 2,
        tools: list[str] | None = None,
    ) -> AgentPreset:
        payload = {
            "apid": apid,
            "name": "default assistant",
            "description": "General customer service preset",
            "prompt": "Help the customer politely",
            "llm_level": llm_level,
        }
        if tools is not None:
            payload["tools"] = tools
        return AgentPreset(**payload)

    def test_resolve_agent_preset_maps_llm_level_and_tools(self) -> None:
        register_llm(2, self._build_llm_config(model_name="resolved-model"))
        register_tool("search_customer", self._search_tool)
        register_tool("calendar", self._calendar_tool)
        agent_preset = self._build_agent_preset(tools=["search_customer", "calendar"])

        runtime = resolve_agent_preset(agent_preset)

        self.assertEqual(runtime.preset, agent_preset)
        self.assertEqual(runtime.llm.model_name, "resolved-model")
        self.assertEqual(runtime.tool_names, ["search_customer", "calendar"])
        self.assertIs(runtime.tools[0], self._search_tool)
        self.assertIs(runtime.tools[1], self._calendar_tool)

    def test_resolve_agent_preset_requires_registered_llm_level(self) -> None:
        register_tool("search_customer", self._search_tool)
        agent_preset = self._build_agent_preset(tools=["search_customer"], llm_level=2)

        with self.assertRaises(KeyError):
            resolve_agent_preset(agent_preset)

    def test_resolve_agent_preset_requires_registered_tool_name(self) -> None:
        register_llm(2, self._build_llm_config())
        agent_preset = self._build_agent_preset(tools=["missing_tool"], llm_level=2)

        with self.assertRaises(KeyError):
            resolve_agent_preset(agent_preset)

    def test_resolve_agent_preset_accepts_empty_tool_list(self) -> None:
        register_llm(2, self._build_llm_config())
        agent_preset = self._build_agent_preset(tools=[])

        runtime = resolve_agent_preset(agent_preset)

        self.assertEqual(runtime.tools, [])
        self.assertEqual(runtime.tool_names, [])

    def test_resolve_agent_preset_by_apid_returns_none_when_missing(self) -> None:
        register_llm(2, self._build_llm_config())

        self.assertIsNone(resolve_agent_preset_by_apid(self.manager, "missing"))

    def test_require_agent_preset_by_apid_resolves_saved_preset(self) -> None:
        register_llm(2, self._build_llm_config(model_name="resolved-model"))
        register_tool("search_customer", self._search_tool)
        agent_preset = self._build_agent_preset(apid="saved", tools=["search_customer"])
        self.manager.add_agent_preset(agent_preset)

        runtime = require_agent_preset_by_apid(self.manager, "saved")

        self.assertEqual(runtime.preset.apid, "saved")
        self.assertEqual(runtime.llm.model_name, "resolved-model")
        self.assertEqual(runtime.tool_names, ["search_customer"])
        self.assertIs(runtime.tools[0], self._search_tool)

    def test_require_agent_preset_by_apid_raises_when_missing(self) -> None:
        with self.assertRaises(ValueError):
            require_agent_preset_by_apid(self.manager, "missing")

    def test_agent_preset_manager_does_not_require_registries_for_crud(self) -> None:
        agent_preset = self._build_agent_preset(apid="unregistered", llm_level=2, tools=["unknown_tool"])

        self.manager.add_agent_preset(agent_preset)
        saved_agent_preset = self.manager.get_agent_preset("unregistered")

        self.assertIsNotNone(saved_agent_preset)
        assert saved_agent_preset is not None
        self.assertEqual(saved_agent_preset.tools, ["unknown_tool"])
        self.assertEqual(saved_agent_preset.llm_level, 2)


if __name__ == "__main__":
    unittest.main()
