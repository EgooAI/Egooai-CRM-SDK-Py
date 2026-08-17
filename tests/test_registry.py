import unittest

from agent_pipeline.registry import (
    LLMConfig,
    LLMRegistry,
    ToolRegistry,
    llm_registry,
    register_llm,
    register_tool,
    tool_registry,
)


class RegistryTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        tool_registry.clear()
        llm_registry.clear()

    def test_tool_registry_registers_and_retrieves_callable(self) -> None:
        registry = ToolRegistry()

        def echo(value: str) -> str:
            return value

        registry.register("echo", echo)

        self.assertIs(registry.get("echo"), echo)
        self.assertEqual(registry.require("echo")("ok"), "ok")
        self.assertEqual(registry.list(), {"echo": echo})

    def test_tool_registry_replaces_existing_name(self) -> None:
        registry = ToolRegistry()

        def first() -> str:
            return "first"

        def second() -> str:
            return "second"

        registry.register("tool", first)
        registry.register("tool", second)

        self.assertIs(registry.require("tool"), second)

    def test_tool_registry_rejects_invalid_registration(self) -> None:
        registry = ToolRegistry()

        with self.assertRaises(ValueError):
            registry.register("", lambda: None)

        with self.assertRaises(TypeError):
            registry.register("bad", object())

        with self.assertRaises(KeyError):
            registry.require("missing")

    def test_llm_registry_registers_and_retrieves_config(self) -> None:
        registry = LLMRegistry()
        config = LLMConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            model_name="example-model",
        )

        registry.register(2, config)

        self.assertEqual(registry.get(2), config)
        self.assertEqual(registry.require(2).model_name, "example-model")
        self.assertEqual(registry.list(), {2: config})

    def test_llm_registry_replaces_existing_level(self) -> None:
        registry = LLMRegistry()
        first = LLMConfig(base_url="https://first.example.com", api_key="first", model_name="first")
        second = LLMConfig(base_url="https://second.example.com", api_key="second", model_name="second")

        registry.register(1, first)
        registry.register(1, second)

        self.assertEqual(registry.require(1), second)

    def test_llm_registry_rejects_invalid_registration(self) -> None:
        registry = LLMRegistry()

        with self.assertRaises(ValueError):
            registry.register(5, LLMConfig(base_url="", api_key="", model_name=""))

        with self.assertRaises(TypeError):
            registry.register(1, object())

        with self.assertRaises(KeyError):
            registry.require(1)

    def test_global_register_helpers_use_shared_registries(self) -> None:
        def add_one(value: int) -> int:
            return value + 1

        config = LLMConfig(base_url="https://api.example.com", api_key="key", model_name="model")

        register_tool("add_one", add_one)
        register_llm(3, config)

        self.assertEqual(tool_registry.require("add_one")(1), 2)
        self.assertEqual(llm_registry.require(3), config)


if __name__ == "__main__":
    unittest.main()
