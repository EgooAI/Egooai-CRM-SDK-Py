from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Optional, Protocol
from urllib import error, request

from agent_pipeline.errors import LLMInvocationError
from agent_pipeline.registry import LLMConfig
from agent_pipeline.types import LLMRequest, LLMResponse, LLMToolCall, LLMToolSchema, LLMUsage, ToolExchange


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


def _tool_result_content(content: Any, ok: bool, error_text: Optional[str]) -> str:
    payload = content if ok else {"error": error_text}
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"error": "tool result is not JSON serializable", "detail": str(payload)}, ensure_ascii=False)


def _exchanges_of(request_payload: LLMRequest) -> list[ToolExchange]:
    """Prefer ordered exchanges; fall back to pairing the flat call/result lists."""
    if request_payload.tool_exchanges:
        return list(request_payload.tool_exchanges)
    if not request_payload.tool_results:
        return []
    return [ToolExchange(
        calls=list(request_payload.tool_calls), results=list(request_payload.tool_results),
    )]


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
    def _parse_tool_arguments(raw_arguments: Any) -> tuple[dict[str, Any], Optional[str]]:
        """Return ``(arguments, error)``; a bad payload becomes a model-visible failure."""
        if raw_arguments in (None, ""):
            return {}, None
        if isinstance(raw_arguments, dict):
            return raw_arguments, None
        if isinstance(raw_arguments, str):
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                return {}, f"工具参数不是合法 JSON：{exc.msg}（原始值：{raw_arguments[:400]}）"
            if not isinstance(parsed, dict):
                return {}, "工具参数必须是一个 JSON 对象。"
            return parsed, None
        return {}, "不支持的工具参数载荷类型。"

    def _build_messages(self, request_payload: LLMRequest) -> list[dict[str, Any]]:
        system_content = (
            f"{request_payload.system_prompt}\n\n"
            f"{request_payload.tool_prompt}\n"
            "When a tool is needed, use the provided function call interface. "
            "After a tool result answers the user's request, answer directly without calling the same tool again."
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": request_payload.user_input},
        ]
        counter = 0
        for exchange in _exchanges_of(request_payload):
            counter += 1
            results = list(exchange.results)
            calls = list(exchange.calls)
            if len(calls) != len(results):
                # Defensive pairing: emit one assistant message per result so the
                # protocol stays valid even if a caller filled partial lists.
                calls = calls[: len(results)] + [None] * max(0, len(results) - len(calls))
            tool_calls_payload: list[dict[str, Any]] = []
            ids: list[str] = []
            for index, (call, result) in enumerate(zip(calls, results)):
                tool_name = call.name if call is not None else result.name
                tool_arguments = call.tool_input if call is not None else {}
                tool_call_id = (
                    call.call_id if call is not None and call.call_id
                    else f"call_{counter}_{index + 1}_{tool_name}"
                )
                ids.append(tool_call_id)
                tool_calls_payload.append({
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_arguments, ensure_ascii=False),
                    },
                })
            if tool_calls_payload:
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": tool_calls_payload,
                })
            for tool_call_id, result in zip(ids, results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": result.name,
                    "content": _tool_result_content(result.content, result.ok, result.error),
                })
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
            choice = request_payload.tool_choice or "auto"
            if choice in ("auto", "required", "none"):
                payload["tool_choice"] = choice
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

    @staticmethod
    def _usage_of(raw_response: dict[str, Any]) -> LLMUsage:
        usage = raw_response.get("usage")
        if not isinstance(usage, dict):
            return LLMUsage()

        def _int(name: str) -> Optional[int]:
            value = usage.get(name)
            return value if type(value) is int and value >= 0 else None

        return LLMUsage(
            prompt_tokens=_int("prompt_tokens"),
            completion_tokens=_int("completion_tokens"),
            total_tokens=_int("total_tokens"),
        )

    def _parse_tool_calls(self, tool_calls: list) -> list[LLMToolCall]:
        parsed: list[LLMToolCall] = []
        for raw_call in tool_calls:
            if not isinstance(raw_call, dict):
                raise LLMInvocationError("LLM API tool call must be an object")
            function_payload = raw_call.get("function")
            if not isinstance(function_payload, dict):
                raise LLMInvocationError("LLM API tool call missing function payload")
            tool_name = function_payload.get("name")
            if not isinstance(tool_name, str) or not tool_name:
                raise LLMInvocationError("LLM API tool call missing tool name")
            tool_arguments, input_error = self._parse_tool_arguments(function_payload.get("arguments"))
            call_id = raw_call.get("id")
            parsed.append(LLMToolCall(
                name=tool_name,
                tool_input=tool_arguments,
                call_id=call_id if isinstance(call_id, str) and call_id else None,
                input_error=input_error,
            ))
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

        usage = self._usage_of(raw_response)
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            parsed_calls = self._parse_tool_calls(tool_calls)
            return LLMResponse(
                text=self._stringify_content(message.get("content")),
                needs_tool=True,
                tool_call=parsed_calls[0],
                raw=raw_response,
                tool_calls=parsed_calls,
                usage=usage,
            )

        return LLMResponse(
            text=self._stringify_content(message.get("content")),
            needs_tool=False,
            raw=raw_response,
            usage=usage,
        )


__all__ = ["LLMClient", "OpenAICompatibleLLMClient", "StaticLLMClient"]
