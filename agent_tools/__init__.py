from .chat_result_tools import (
    process_chat_suggestion_result,
    process_chat_translation_result,
    process_customer_intent_analysis_result,
    process_customer_stage_analysis_result,
    register_chat_result_tools,
)
from .math_tools import (
    calculate,
    register_math_tools,
)


def register_builtin_tools() -> list[str]:
    """Register all built-in tools shipped with the SDK."""
    registered: list[str] = []
    registered.extend(register_math_tools())
    registered.extend(register_chat_result_tools())
    return registered


__all__ = [
    "calculate",
    "process_chat_suggestion_result",
    "process_chat_translation_result",
    "process_customer_intent_analysis_result",
    "process_customer_stage_analysis_result",
    "register_builtin_tools",
    "register_chat_result_tools",
    "register_math_tools",
]
