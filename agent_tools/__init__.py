from .math_tools import (
    calculate,
    register_math_tools,
)


def register_builtin_tools() -> list[str]:
    """Register all built-in tools shipped with the SDK."""
    registered: list[str] = []
    registered.extend(register_math_tools())
    return registered


__all__ = [
    "calculate",
    "register_builtin_tools",
    "register_math_tools",
]
