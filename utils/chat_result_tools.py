from __future__ import annotations

import json
from typing import Any

"""四个 Chat 系统 Agent 的返回结果规范化工具。

这些函数会作为 AgentPipeline 工具暴露给 LLM。LLM 可以在执行末尾调用它们，
把自由文本或中间推理结果转换成稳定的类 JSON 数据，方便 Web 层解析和展示。
"""


def _load_json_value(value: Any) -> Any:
    """兼容工具调用传入的 Python 原生值或 JSON 字符串。"""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def process_chat_translation_result(translations: dict | str) -> dict[str, Any]:
    """规范化按消息文本 hash 索引的翻译结果。

    翻译 Agent 可以传入以下任一形式：
    - {"hash": "译文"} / {"hash": null}
    - {"translations": {"hash": "译文"}}
    - 上述任一结构的 JSON 字符串
    """
    payload = _load_json_value(translations)
    if isinstance(payload, dict) and isinstance(payload.get("translations"), dict):
        payload = payload["translations"]
    if not isinstance(payload, dict):
        raise ValueError("translations must be a dict or JSON object string")

    normalized: dict[str, str | None] = {}
    for key, value in payload.items():
        if value is None:
            normalized[str(key)] = None
        elif isinstance(value, str):
            normalized[str(key)] = value.strip()
        else:
            normalized[str(key)] = str(value).strip()
    return {"translations": normalized}


def process_chat_suggestion_result(buyer_language: str, items: list | str) -> dict[str, Any]:
    """把回复建议规范化为 AI 建议弹窗可直接消费的结构。"""
    raw_items = _load_json_value(items)
    if not isinstance(raw_items, list):
        raise ValueError("items must be a list or JSON array string")

    normalized_items: list[dict[str, str]] = []
    for item in raw_items[:3]:
        if not isinstance(item, dict):
            continue
        normalized_items.append(
            {
                "zh": str(item.get("zh") or item.get("cn") or item.get("chinese") or "").strip(),
                "reply": str(
                    item.get("reply")
                    or item.get("buyer_reply")
                    or item.get("message")
                    or item.get("text")
                    or ""
                ).strip(),
            }
        )
    return {"buyer_language": buyer_language.strip() or "mixed", "items": normalized_items}


def process_customer_intent_analysis_result(
    intent: str,
    evidence: list | str,
    concerns: list | str = "",
    next_actions: list | str = "",
) -> dict[str, Any]:
    """规范化客户意图分析结果，用于 Chat 工具弹窗展示。"""
    return {
        "intent": intent.strip(),
        "evidence": _normalize_text_list(evidence),
        "concerns": _normalize_text_list(concerns),
        "next_actions": _normalize_text_list(next_actions),
    }


def process_customer_stage_analysis_result(
    stage: str,
    evidence: list | str,
    next_actions: list | str,
    confidence: str = "",
) -> dict[str, Any]:
    """规范化客户阶段分析结果，用于 Chat 工具弹窗展示。"""
    return {
        "stage": stage.strip(),
        "evidence": _normalize_text_list(evidence),
        "next_actions": _normalize_text_list(next_actions),
        "confidence": confidence.strip(),
    }


def _normalize_text_list(value: list | str) -> list[str]:
    """把列表、JSON 数组字符串或换行文本统一转换为干净的字符串列表。"""
    payload = _load_json_value(value)
    if payload is None or payload == "":
        return []
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    return [line.strip() for line in str(payload).splitlines() if line.strip()]


def register_chat_result_tools() -> list[str]:
    """把这些工具注册到全局 AgentPipeline 工具注册表。"""
    # 延迟导入，避免 SDK 启动时出现 core <-> utils 循环导入。
    from core import register_tool

    register_tool("process_chat_translation_result", process_chat_translation_result)
    register_tool("process_chat_suggestion_result", process_chat_suggestion_result)
    register_tool("process_customer_intent_analysis_result", process_customer_intent_analysis_result)
    register_tool("process_customer_stage_analysis_result", process_customer_stage_analysis_result)
    return [
        "process_chat_translation_result",
        "process_chat_suggestion_result",
        "process_customer_intent_analysis_result",
        "process_customer_stage_analysis_result",
    ]


__all__ = [
    "process_chat_translation_result",
    "process_chat_suggestion_result",
    "process_customer_intent_analysis_result",
    "process_customer_stage_analysis_result",
    "register_chat_result_tools",
]
