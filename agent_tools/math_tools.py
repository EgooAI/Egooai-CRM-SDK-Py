from __future__ import annotations

from agent_pipeline.registry import register_tool


def calculate(operation: str, a: float, b: float) -> float:
    """Perform basic arithmetic with operation: add, subtract, multiply, or divide."""
    normalized = operation.strip().lower()
    if normalized in {"add", "plus", "+"}:
        return a + b
    if normalized in {"subtract", "minus", "-"}:
        return a - b
    if normalized in {"multiply", "times", "*", "x"}:
        return a * b
    if normalized in {"divide", "/"}:
        if b == 0:
            raise ValueError("Division by zero is not allowed")
        return a / b
    raise ValueError("operation must be one of: add, subtract, multiply, divide")


def register_math_tools() -> list[str]:
    register_tool("calculate", calculate)
    return ["calculate"]


__all__ = [
    "calculate",
    "register_math_tools",
]
