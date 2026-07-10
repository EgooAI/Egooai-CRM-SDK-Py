import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_pipeline import AgentPipeline, AgentPipelineInput, LLMResponse, StaticLLMClient
from core import AgentPresetManager, llm_registry, tool_registry
from agent_pipeline.llm_api import load_default_llm_levels, register_default_llms
from models import AgentPreset


class LLMApiTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        llm_registry.clear()
        tool_registry.clear()

    def _write_yaml(self, directory: Path, content: str) -> Path:
        path = directory / "llm_api.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_load_default_llm_levels_registers_levels_zero_through_four(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = self._write_yaml(
                Path(temp_dir),
                """
default:
  base_url: https://api.example.com/v1
  api_key: replace-me
  model_name: claude-opus-4-8

levels:
  0: {}
  1: {}
  2: {}
  3: {}
  4: {}
""".strip(),
            )

            levels = load_default_llm_levels(path)

            self.assertEqual(sorted(levels.keys()), [0, 1, 2, 3, 4])
            self.assertEqual(levels[2].model_name, "claude-opus-4-8")

    def test_load_default_llm_levels_supports_level_overrides(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = self._write_yaml(
                Path(temp_dir),
                """
default:
  base_url: https://api.example.com/v1
  api_key: replace-me
  model_name: claude-opus-4-8

levels:
  4:
    model_name: claude-sonnet-5
""".strip(),
            )

            levels = load_default_llm_levels(path)

            self.assertEqual(levels[0].model_name, "claude-opus-4-8")
            self.assertEqual(levels[4].model_name, "claude-sonnet-5")

    def test_register_default_llms_is_idempotent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = self._write_yaml(
                Path(temp_dir),
                """
default:
  base_url: https://api.example.com/v1
  api_key: replace-me
  model_name: claude-opus-4-8
""".strip(),
            )

            first = register_default_llms(path)
            second = register_default_llms(path)

            self.assertEqual(llm_registry.list(), second)
            self.assertEqual(first, second)

    def test_register_default_llms_raises_when_file_missing(self) -> None:
        missing_path = Path("definitely-missing-llm-api.yaml")

        with self.assertRaises(FileNotFoundError):
            register_default_llms(missing_path)

    def test_load_default_llm_levels_raises_for_missing_default_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = self._write_yaml(
                Path(temp_dir),
                """
default:
  base_url: https://api.example.com/v1
  api_key: replace-me
""".strip(),
            )

            with self.assertRaises(ValueError):
                load_default_llm_levels(path)

    def test_agent_preset_resolver_can_use_yaml_registrations(self) -> None:
        from core import resolve_agent_preset

        with TemporaryDirectory() as temp_dir:
            path = self._write_yaml(
                Path(temp_dir),
                """
default:
  base_url: https://api.example.com/v1
  api_key: replace-me
  model_name: claude-opus-4-8
""".strip(),
            )
            register_default_llms(path)
            agent_preset = AgentPreset(
                apid="default-assistant",
                name="default assistant",
                description="General customer service preset",
                prompt="Help the customer politely",
                intelevel=2,
                tools=[],
            )

            runtime = resolve_agent_preset(agent_preset)

            self.assertEqual(runtime.llm.model_name, "claude-opus-4-8")

    def test_agent_pipeline_can_use_yaml_registrations(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = self._write_yaml(
                Path(temp_dir),
                """
default:
  base_url: https://api.example.com/v1
  api_key: replace-me
  model_name: claude-opus-4-8
""".strip(),
            )
            register_default_llms(path)
            db_path = Path(temp_dir) / "agent_pipeline_llm_api.sqlite"
            manager = AgentPresetManager(database_path=db_path)
            try:
                preset = AgentPreset(
                    apid="default-assistant",
                    name="default assistant",
                    description="General customer service preset",
                    prompt="Help the customer politely",
                    intelevel=2,
                    tools=[],
                )
                manager.add_agent_preset(preset)
                client = StaticLLMClient([
                    LLMResponse(text="registered by llm_api", needs_tool=False),
                ])

                result = AgentPipeline(llm_client=client, manager=manager).run(
                    AgentPipelineInput(user_input="hello", apid="default-assistant")
                )

                self.assertEqual(result.output_text, "registered by llm_api")
                self.assertEqual(result.runtime.llm.model_name, "claude-opus-4-8")
            finally:
                manager.engine.dispose()


if __name__ == "__main__":
    unittest.main()
