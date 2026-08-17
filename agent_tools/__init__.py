from .math_tools import (
    calculate,
    register_math_tools,
)


def register_builtin_tools() -> list[str]:
    """Register all built-in tools shipped with the SDK."""
    return register_math_tools()


__all__ = [
    "calculate",
    "register_builtin_tools",
    "register_math_tools",
]
