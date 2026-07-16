from __future__ import annotations

import json
import re
from typing import Any

from core.system_agents import (
    CHAT_CUSTOMER_INTENT_AGENT_APID,
    CHAT_CUSTOMER_STAGE_AGENT_APID,
    CHAT_REPLY_SUGGESTION_AGENT_APID,
    CHAT_TRANSLATION_AGENT_APID,
)
from utils.chat_result_tools import (
    process_chat_suggestion_result,
    process_chat_translation_result,
    process_customer_intent_analysis_result,
    process_customer_stage_analysis_result,
)


def _strip_json_fence(text: str) -> str:
    value = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else value


def _load_json_object(raw_text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(_strip_json_fence(raw_text))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_translation(raw_text: str) -> dict[str, Any]:
    payload = _load_json_object(raw_text)
    if payload is None:
        return process_chat_translation_result({})
    return process_chat_translation_result(payload)


def _normalize_suggestion(raw_text: str) -> dict[str, Any]:
    payload = _load_json_object(raw_text) or {}
    buyer_language = str(payload.get("buyer_language") or payload.get("language") or "mixed")
    items = payload.get("items")
    if items is None:
        for fallback_key in ("suggestions", "replies", "reply_suggestions"):
            fallback_value = payload.get(fallback_key)
            if isinstance(fallback_value, list):
                items = fallback_value
                break
    if items is None:
        items = []
    return process_chat_suggestion_result(buyer_language, items)


def _normalize_intent(raw_text: str) -> dict[str, Any]:
    payload = _load_json_object(raw_text) or {}
    return process_customer_intent_analysis_result(
        intent=str(payload.get("intent") or raw_text).strip(),
        evidence=payload.get("evidence") or payload.get("evidences") or [],
        concerns=payload.get("concerns") or payload.get("pain_points") or "",
        next_actions=payload.get("next_actions") or payload.get("actions") or "",
    )


def _normalize_stage(raw_text: str) -> dict[str, Any]:
    payload = _load_json_object(raw_text) or {}
    return process_customer_stage_analysis_result(
        stage=str(payload.get("stage") or raw_text).strip(),
        evidence=payload.get("evidence") or payload.get("evidences") or [],
        next_actions=payload.get("next_actions") or payload.get("actions") or [],
        confidence=str(payload.get("confidence") or "").strip(),
    )


def normalize_system_agent_output(apid: str, raw_text: str) -> str:
    if apid == CHAT_TRANSLATION_AGENT_APID:
        payload = _normalize_translation(raw_text)
    elif apid == CHAT_REPLY_SUGGESTION_AGENT_APID:
        payload = _normalize_suggestion(raw_text)
    elif apid == CHAT_CUSTOMER_INTENT_AGENT_APID:
        payload = _normalize_intent(raw_text)
    elif apid == CHAT_CUSTOMER_STAGE_AGENT_APID:
        payload = _normalize_stage(raw_text)
    else:
        return raw_text
    return json.dumps(payload, ensure_ascii=False)


__all__ = ["normalize_system_agent_output"]
