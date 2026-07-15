from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol
from urllib import error, request

from agent_pipeline.errors import LLMInvocationError
from agent_pipeline.types import LLMRequest, LLMResponse, LLMToolCall
from core import LLMConfig


class LLMClient(Protocol):
    def invoke(self, request: LLMRequest) -> LLMResponse:
        ...


class StaticLLMClient:
    """Test-only LLM client that returns responses in order."""

    def __init__(self, responses: Sequence[LLMResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []

    def invoke(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._responses:
            raise LLMInvocationError("No more mock LLM responses configured")
        return self._responses.pop(0)


class OpenAICompatibleLLMClient:
    """Minimal chat-completions client for OpenAI-compatible APIs."""

    def __init__(self, config: LLMConfig, timeout_seconds: float = 60.0) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.requests: list[LLMRequest] = []

    @property
    def _chat_completions_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/chat/completions"

    @staticmethod
    def _stringify_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            return "".join(parts)
        if content is None:
            return ""
        return str(content)

    @staticmethod
    def _load_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
        if raw_arguments in (None, ""):
            return {}
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str):
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise LLMInvocationError(f"Invalid tool arguments JSON: {raw_arguments}") from exc
            if not isinstance(parsed, dict):
                raise LLMInvocationError("Tool arguments must decode to an object")
            return parsed
        raise LLMInvocationError("Unsupported tool arguments payload")

    def _build_messages(self, request_payload: LLMRequest) -> list[dict[str, Any]]:
        system_content = (
            f"{request_payload.system_prompt}\n\n"
            f"{request_payload.tool_prompt}\n"
            "When a tool is needed, use the provided function call interface. "
            "After a tool result answers the user's request, answer directly without calling the same tool again."
        )
        if not request_payload.tool_results:
            return [
                {
                    "role": "system",
                    "content": system_content,
                },
                {"role": "user", "content": request_payload.user_input},
            ]

        messages = [
            {
                "role": "system",
                "content": system_content,
            },
            {"role": "user", "content": request_payload.user_input},
        ]
        for index, tool_result in enumerate(request_payload.tool_results):
            tool_call = request_payload.tool_calls[index] if index < len(request_payload.tool_calls) else None
            tool_name = tool_call.name if tool_call is not None else tool_result.name
            tool_arguments = tool_call.tool_input if tool_call is not None else {}
            tool_call_id = (
                tool_call.call_id
                if tool_call is not None and tool_call.call_id
                else f"call_{index + 1}_{tool_name}"
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_arguments, ensure_ascii=False),
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_result.name,
                    "content": json.dumps(
                        tool_result.content if tool_result.ok else {"error": tool_result.error},
                        ensure_ascii=False,
                    ),
                }
            )
        return messages

    def _build_payload(self, request_payload: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": self._build_messages(request_payload),
            "temperature": 0,
        }
        if request_payload.tool_schemas:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool_schema.name,
                        "description": tool_schema.description,
                        "parameters": tool_schema.parameters,
                    },
                }
                for tool_schema in request_payload.tool_schemas
            ]
            payload["tool_choice"] = "auto"
        return payload

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            self._chat_completions_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMInvocationError(f"LLM API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise LLMInvocationError(f"LLM API request failed: {exc.reason}") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMInvocationError(f"LLM API returned invalid JSON: {raw}") from exc
        if not isinstance(parsed, dict):
            raise LLMInvocationError("LLM API response root must be an object")
        return parsed

    def invoke(self, request_payload: LLMRequest) -> LLMResponse:
        self.requests.append(request_payload)
        payload = self._build_payload(request_payload)
        raw_response = self._post_json(payload)
        choices = raw_response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMInvocationError("LLM API response missing choices")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise LLMInvocationError("LLM API choice must be an object")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise LLMInvocationError("LLM API response missing message")

        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            first_tool_call = tool_calls[0]
            if not isinstance(first_tool_call, dict):
                raise LLMInvocationError("LLM API tool call must be an object")
            function_payload = first_tool_call.get("function")
            if not isinstance(function_payload, dict):
                raise LLMInvocationError("LLM API tool call missing function payload")
            tool_name = function_payload.get("name")
            if not isinstance(tool_name, str) or not tool_name:
                raise LLMInvocationError("LLM API tool call missing tool name")
            tool_arguments = self._load_tool_arguments(function_payload.get("arguments"))
            call_id = first_tool_call.get("id")
            return LLMResponse(
                text=self._stringify_content(message.get("content")),
                needs_tool=True,
                tool_call=LLMToolCall(
                    name=tool_name,
                    tool_input=tool_arguments,
                    call_id=call_id if isinstance(call_id, str) and call_id else None,
                ),
                raw=raw_response,
            )

        return LLMResponse(
            text=self._stringify_content(message.get("content")),
            needs_tool=False,
            raw=raw_response,
        )
