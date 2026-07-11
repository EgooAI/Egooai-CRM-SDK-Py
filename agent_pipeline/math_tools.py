from __future__ import annotations

from core import register_tool


def add_numbers(a: float, b: float) -> float:
    """Add two numbers and return the sum."""
    return a + b


def subtract_numbers(a: float, b: float) -> float:
    """Subtract the second number from the first number."""
    return a - b


def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers and return the product."""
    return a * b


def divide_numbers(a: float, b: float) -> float:
    """Divide the first number by the second number."""
    if b == 0:
        raise ValueError("Division by zero is not allowed")
    return a / b


def register_math_tools() -> list[str]:
    register_tool("add_numbers", add_numbers)
    register_tool("subtract_numbers", subtract_numbers)
    register_tool("multiply_numbers", multiply_numbers)
    register_tool("divide_numbers", divide_numbers)
    return ["add_numbers", "subtract_numbers", "multiply_numbers", "divide_numbers"]


__all__ = [
    "add_numbers",
    "subtract_numbers",
    "multiply_numbers",
    "divide_numbers",
    "register_math_tools",
]
