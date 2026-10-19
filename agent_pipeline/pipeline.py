from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from typing import Any, Optional

from agent_pipeline.errors import AgentPresetResolutionError, LLMInvocationError
from agent_pipeline.llm import LLMClient
from agent_pipeline.resolver import (
    REQUIRED_TOOL_CHOICES,
    AgentPresetRuntimeConfig,
    require_agent_preset_by_apid,
    resolve_agent_preset,
)
from agent_pipeline.tools import (
    ToolContext,
    ToolExecutor,
    build_tool_schema,
    tool_use_instruction,
)
from agent_pipeline.types import (
    AgentPipelineInput,
    AgentPipelineResult,
    AgentPipelineResultStatus,
    EffectIntent,
    LLMRequest,
    LLMToolCall,
    LLMToolSchema,
    LLMUsage,
    ToolCallRecord,
    ToolExchange,
    ToolExecutionResult,
)
from core.agent_preset import AgentPresetManager

DEFAULT_MAX_TOOL_ROUNDS = 10
DEFAULT_MAX_TOOL_CALLS = 20
_CLOSING_INPUT_SUFFIX = (
    "\n\n[系统提示] 工具调用预算已用尽（或达到轮次上限）。"
    "不要再调用任何工具，请立即根据已经获得的信息给出最终回答。"
)


@dataclass
class _Execution:
    results: list[ToolExecutionResult]
    intents: list[EffectIntent]


class AgentPipeline:
    """Run an agent preset through repeated LLM and tool rounds."""

    def __init__(
        self,
        llm_client: LLMClient,
        manager: Optional[AgentPresetManager] = None,
        tool_executor: Optional[ToolExecutor] = None,
        max_tool_rounds: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
    ) -> None:
        self.llm_client = llm_client
        self.manager = manager
        self.tool_executor = tool_executor or ToolExecutor()
        self.max_tool_rounds = max_tool_rounds
        self.max_tool_calls = max_tool_calls if max_tool_calls is not None else DEFAULT_MAX_TOOL_CALLS

    @staticmethod
    def _build_tool_prompt(runtime: AgentPresetRuntimeConfig) -> str:
        if not runtime.tool_names:
            return "There are no tools available. If the prompt is enough, answer directly."
        lines = ["Available tools:"]
        for name, spec in zip(runtime.tool_names, runtime.tool_specs):
            lines.append(tool_use_instruction(spec, name))
        lines.append("Call a tool only when it is necessary to answer the user accurately.")
        return "\n".join(lines)

    @staticmethod
    def _build_tool_schemas(runtime: AgentPresetRuntimeConfig) -> list[LLMToolSchema]:
        schemas: list[LLMToolSchema] = []
        for name, tool, spec in zip(runtime.tool_names, runtime.tools, runtime.tool_specs):
            description = (spec.description or "").strip() if spec is not None else ""
            if not description:
                from inspect import getdoc

                description = (getdoc(tool) or f"Call the {name} tool.").strip()
            schemas.append(
                LLMToolSchema(
                    name=name,
                    description=description,
                    parameters=build_tool_schema(tool, spec),
                )
            )
        return schemas

    @staticmethod
    def _estimate_request_context_length(request_payload: LLMRequest) -> int:
        def serialized_length(value: Any) -> int:
            try:
                return len(json.dumps(value, ensure_ascii=False))
            except (TypeError, ValueError):
                return len(str(value))

        total = len(request_payload.system_prompt) + len(request_payload.user_input) + len(request_payload.tool_prompt)
        for tool_schema in request_payload.tool_schemas:
            total += len(tool_schema.name)
            total += len(tool_schema.description)
            total += serialized_length(tool_schema.parameters)
        for call in request_payload.tool_calls:
            total += len(call.name)
            total += serialized_length(call.tool_input)
        for tool_result in request_payload.tool_results:
            total += len(tool_result.name)
            total += serialized_length(tool_result.content)
            if tool_result.error:
                total += len(tool_result.error)
        return total

    @staticmethod
    def _compose_system_prompt(runtime: AgentPresetRuntimeConfig) -> str:
        if runtime.llm.system_prompt:
            return f"{runtime.llm.system_prompt}\n\n{runtime.preset.prompt}"
        return runtime.preset.prompt

    def _resolve_runtime(self, pipeline_input: AgentPipelineInput) -> AgentPresetRuntimeConfig:
        if pipeline_input.agent_preset is not None:
            try:
                return resolve_agent_preset(pipeline_input.agent_preset)
            except KeyError as exc:
                raise AgentPresetResolutionError(str(exc)) from exc

        if pipeline_input.apid is None:
            raise AgentPresetResolutionError("Either apid or agent_preset must be provided")

        if self.manager is None:
            raise AgentPresetResolutionError("AgentPresetManager is required when resolving by apid")

        try:
            return require_agent_preset_by_apid(self.manager, pipeline_input.apid)
        except (ValueError, KeyError) as exc:
            raise AgentPresetResolutionError(str(exc)) from exc

    def _build_request(
        self,
        runtime: AgentPresetRuntimeConfig,
        pipeline_input: AgentPipelineInput,
        exchanges: list[ToolExchange],
        tool_prompt: str,
        tool_schemas: list[LLMToolSchema],
        *,
        user_input: Optional[str] = None,
        tool_choice: str = "auto",
    ) -> LLMRequest:
        calls = [call for exchange in exchanges for call in exchange.calls]
        results = [result for exchange in exchanges for result in exchange.results]
        return LLMRequest(
            system_prompt=self._compose_system_prompt(runtime),
            user_input=pipeline_input.user_input if user_input is None else user_input,
            tool_prompt=tool_prompt if tool_choice != "none" else "",
            tool_schemas=tool_schemas if tool_choice != "none" else [],
            tool_results=results,
            tool_calls=calls,
            tool_exchanges=list(exchanges),
            tool_choice=tool_choice,
        )

    @staticmethod
    def _round_limit(runtime: AgentPresetRuntimeConfig, override: Optional[int]) -> int:
        if override is not None:
            return override
        if runtime.llm.max_tool_rounds is not None:
            return runtime.llm.max_tool_rounds
        return DEFAULT_MAX_TOOL_ROUNDS

    def run(self, pipeline_input: AgentPipelineInput) -> AgentPipelineResult:
        started = time.perf_counter()
        runtime = self._resolve_runtime(pipeline_input)
        if pipeline_input.tool_choice not in REQUIRED_TOOL_CHOICES:
            raise AgentPresetResolutionError(
                f"tool_choice must be one of {sorted(REQUIRED_TOOL_CHOICES)}"
            )
        if runtime.requires_tool and pipeline_input.tool_choice == "none":
            raise AgentPresetResolutionError(
                f"AgentPreset {runtime.preset.apid} requires a tool call but tool_choice is none"
            )
        if runtime.requires_tool and not runtime.tool_names:
            raise AgentPresetResolutionError(
                f"AgentPreset {runtime.preset.apid} requires a tool call but mounts no tools"
            )

        context = pipeline_input.tool_context
        if not isinstance(context, ToolContext):
            context = ToolContext()
        intents: list[EffectIntent] = []
        records: list[ToolCallRecord] = []
        exchanges: list[ToolExchange] = []
        raw_responses: list[object] = []
        total_calls = 0
        context_limit = runtime.llm.context
        max_rounds = self._round_limit(runtime, self.max_tool_rounds)
        max_calls = int(self.max_tool_calls)
        if max_rounds < 1 or max_calls < 1:
            raise AgentPresetResolutionError("tool round and call limits must be positive")
        per_tool_counts: dict[str, int] = {}
        tool_prompt = self._build_tool_prompt(runtime)
        tool_schemas = self._build_tool_schemas(runtime)
        base_choice = pipeline_input.tool_choice
        if base_choice == "auto" and runtime.requires_tool:
            base_choice = "required"
        # Some providers reject a forced ``tool_choice`` (reasoning models, older
        # gateways). The first such rejection downgrades to ``auto`` plus the
        # embedded prompt reminder; the run continues instead of failing.
        state_choice = {"value": base_choice}
        state = {"iterations": 0, "usage": LLMUsage(), "tool_rounds": 0}

        def _finish(status: AgentPipelineResultStatus, output_text: str) -> AgentPipelineResult:
            return AgentPipelineResult(
                status=status,
                runtime=runtime,
                output_text=output_text,
                iterations=state["iterations"],
                tool_call=(
                    exchanges[-1].calls[-1] if exchanges and exchanges[-1].calls else None
                ),
                tool_result=(
                    exchanges[-1].results[-1]
                    if exchanges and exchanges[-1].results else None
                ),
                raw_responses=raw_responses,
                tool_call_records=records,
                tool_exchanges=exchanges,
                intents=intents,
                usage=state["usage"],
                duration_ms=(time.perf_counter() - started) * 1000,
            )

        while True:
            if state["tool_rounds"] >= max_rounds:
                return self._close_out(
                    pipeline_input, runtime, exchanges, tool_prompt, tool_schemas,
                    context_limit, state, raw_responses, _finish, state_choice,
                    exhausted_status=AgentPipelineResultStatus.COMPLETED,
                )

            request_payload = self._build_request(
                runtime, pipeline_input, exchanges, tool_prompt, tool_schemas,
                tool_choice=state_choice["value"],
            )
            if context_limit is not None:
                current_context_length = self._estimate_request_context_length(request_payload)
                if current_context_length > context_limit:
                    return _finish(AgentPipelineResultStatus.CONTEXT_LIMITED, "")

            response = self._invoke(request_payload, state_choice)
            state["iterations"] += 1
            raw_responses.append(response.raw)
            state["usage"] = state["usage"].merged(response.usage)

            calls = response.calls
            if not calls:
                output_text = response.text
                normalizer = runtime.output_normalizer
                if normalizer is not None:
                    output_text = normalizer(response.text)
                return _finish(AgentPipelineResultStatus.COMPLETED, output_text)

            if state_choice["value"] == "none":
                return _finish(AgentPipelineResultStatus.TOOL_ROUNDS_LIMITED, response.text)

            if total_calls >= max_calls:
                # The executed-call budget is spent: stop executing and force a
                # closing answer so the caller still gets text and full records.
                return self._close_out(
                    pipeline_input, runtime, exchanges, tool_prompt, tool_schemas,
                    context_limit, state, raw_responses, _finish, state_choice,
                    exhausted_status=AgentPipelineResultStatus.TOOL_ROUNDS_LIMITED,
                )

            state["tool_rounds"] += 1
            execution = self._execute_calls(
                runtime, calls, context, records, round_index=state["tool_rounds"],
                remaining=max_calls - total_calls, per_tool_counts=per_tool_counts,
            )
            total_calls += len(execution.results)
            exchanges.append(ToolExchange(calls=list(calls), results=list(execution.results)))
            intents.extend(execution.intents)

    def _invoke(
        self,
        request_payload: LLMRequest,
        state_choice: dict[str, str],
        *,
        system_prompt: Optional[str] = None,
    ):
        """Send one request; a rejected forced tool_choice degrades to ``auto`` once."""
        payload = request_payload
        if system_prompt is not None:
            payload = replace(request_payload, system_prompt=system_prompt)
        try:
            return self.llm_client.invoke(payload)
        except LLMInvocationError as exc:
            if "tool_choice" not in str(exc):
                raise
            # This provider rejects the explicit choice. A ``required`` run keeps
            # its prompt-level instruction ("you must call a tool"); a closing
            # request already says not to call tools, so ``auto`` is harmless.
            state_choice["value"] = "auto"
            fallback = dict(payload.__dict__)
            fallback["tool_choice"] = "auto"
            fallback["system_prompt"] = (
                f"{payload.system_prompt}\n\n"
                "This provider does not accept a forced tool choice; follow the "
                "tool instructions in the prompt instead."
            )
            return self.llm_client.invoke(LLMRequest(**fallback))

    def _execute_calls(
        self,
        runtime: AgentPresetRuntimeConfig,
        calls: list[LLMToolCall],
        context: ToolContext,
        records: list[ToolCallRecord],
        *,
        round_index: int,
        remaining: int,
        per_tool_counts: dict[str, int],
    ) -> _Execution:
        results: list[ToolExecutionResult] = []
        intents: list[EffectIntent] = []
        specs = {
            name: spec
            for name, spec in zip(runtime.tool_names, runtime.tool_specs)
        }
        for index, call in enumerate(calls):
            if call.input_error:
                results.append(ToolExecutionResult(
                    name=call.name, ok=False, error=call.input_error, call_id=call.call_id,
                ))
                records.append(ToolCallRecord(
                    call_id=call.call_id, name=call.name, arguments=dict(call.tool_input or {}),
                    ok=False, error=call.input_error, duration_ms=0.0, round=round_index,
                ))
                continue
            if index >= remaining:
                error = "本次运行的工具调用总数已达上限，未执行该调用。"
                results.append(ToolExecutionResult(
                    name=call.name, ok=False, error=error, call_id=call.call_id,
                ))
                records.append(ToolCallRecord(
                    call_id=call.call_id, name=call.name, arguments=dict(call.tool_input or {}),
                    ok=False, error=error, duration_ms=0.0, round=round_index,
                ))
                continue
            spec = specs.get(call.name)
            count = per_tool_counts.get(call.name, 0)
            limit_error = self._repeat_limit_error(spec, call.name, count)
            if limit_error is not None:
                results.append(ToolExecutionResult(
                    name=call.name, ok=False, error=limit_error, call_id=call.call_id,
                ))
                records.append(ToolCallRecord(
                    call_id=call.call_id, name=call.name, arguments=dict(call.tool_input or {}),
                    ok=False, error=limit_error, duration_ms=0.0, round=round_index,
                ))
                continue

            per_tool_counts[call.name] = count + 1
            collector = context.child(call_id=call.call_id)
            result, record = self.tool_executor.execute(
                runtime, call.name, call.tool_input, context=collector,
                call_id=call.call_id, round_index=round_index,
            )
            if result.ok:
                # Only a successful effect call contributes intents; the tool has
                # already recorded its own payload and sequence for later rounds.
                intents.extend(collector.intents)
                context.recorded = collector.recorded
                context.recorded_sequence = collector.recorded_sequence
            results.append(result)
            records.append(record)
        return _Execution(results=results, intents=intents)

    @staticmethod
    def _repeat_limit_error(spec, name: str, issued: int) -> Optional[str]:
        if spec is None:
            return None
        if not spec.repeatable and issued >= 1:
            return f"工具 {name} 每次运行最多调用一次，请不要再调用它。"
        if spec.max_calls is not None and issued >= spec.max_calls:
            return f"工具 {name} 每次运行最多调用 {spec.max_calls} 次，请不要再调用它。"
        return None

    def _close_out(
        self,
        pipeline_input: AgentPipelineInput,
        runtime: AgentPresetRuntimeConfig,
        exchanges: list[ToolExchange],
        tool_prompt: str,
        tool_schemas: list[LLMToolSchema],
        context_limit: Optional[int],
        state: dict[str, Any],
        raw_responses: list[object],
        finish,
        state_choice: dict[str, str],
        *,
        exhausted_status: AgentPipelineResultStatus,
    ) -> AgentPipelineResult:
        """One last request with tools disabled so a limited run still ends with text."""
        state_choice["value"] = "none"
        request_payload = self._build_request(
            runtime, pipeline_input, exchanges, tool_prompt, tool_schemas,
            user_input=f"{pipeline_input.user_input}{_CLOSING_INPUT_SUFFIX}",
            tool_choice="none",
        )
        if context_limit is not None and self._estimate_request_context_length(request_payload) > context_limit:
            return finish(AgentPipelineResultStatus.CONTEXT_LIMITED, "")
        response = self._invoke(request_payload, state_choice)
        state["iterations"] += 1
        raw_responses.append(response.raw)
        state["usage"] = state["usage"].merged(response.usage)
        # The closing call cannot add calls: a further tool request leaves the
        # run restricted, and the collected records stay visible either way.
        text = response.text
        tool_calls_ignored = bool(response.calls)
        if not tool_calls_ignored:
            normalizer = runtime.output_normalizer
            if normalizer is not None and text.strip():
                text = normalizer(text)
        status = (
            AgentPipelineResultStatus.TOOL_ROUNDS_LIMITED
            if tool_calls_ignored or exhausted_status is AgentPipelineResultStatus.TOOL_ROUNDS_LIMITED
            else AgentPipelineResultStatus.COMPLETED
        )
        return finish(status, text)


__all__ = ["AgentPipeline", "DEFAULT_MAX_TOOL_CALLS", "DEFAULT_MAX_TOOL_ROUNDS"]
