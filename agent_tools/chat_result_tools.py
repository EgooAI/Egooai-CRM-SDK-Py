from __future__ import annotations

import json
from typing import Any

from core import register_tool


def _load_json_value(value: Any) -> Any:
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
    """Normalize the translation Agent result to {"translations": {"text_hash": "translation or null"}}."""
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
    """Normalize the suggestion Agent result to {"buyer_language": "...", "items": [{"zh": "...", "reply": "..."}]}."""
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
    """Normalize customer intent analysis into intent, evidence, concerns, and next_actions fields."""
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
    """Normalize customer stage analysis into stage, evidence, next_actions, and confidence fields."""
    return {
        "stage": stage.strip(),
        "evidence": _normalize_text_list(evidence),
        "next_actions": _normalize_text_list(next_actions),
        "confidence": confidence.strip(),
    }


def _normalize_text_list(value: list | str) -> list[str]:
    payload = _load_json_value(value)
    if payload is None or payload == "":
        return []
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    return [line.strip() for line in str(payload).splitlines() if line.strip()]


def register_chat_result_tools() -> list[str]:
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
