from __future__ import annotations

import inspect
import json
from typing import Optional, get_type_hints

from agent_pipeline.errors import AgentPresetResolutionError, LLMInvocationError
from agent_pipeline.llm import LLMClient
from agent_pipeline.tools import ToolExecutor
from agent_pipeline.types import (
    AgentPipelineInput,
    AgentPipelineResult,
    LLMRequest,
    LLMToolCall,
    LLMToolSchema,
    ToolExecutionResult,
)
from core.agent_preset import AgentPresetManager
from core.agent_preset_resolver import AgentPresetRuntimeConfig, require_agent_preset_by_apid, resolve_agent_preset


class AgentPipeline:
    """Run an agent preset through repeated LLM and tool rounds."""

    def __init__(
        self,
        llm_client: LLMClient,
        manager: Optional[AgentPresetManager] = None,
        tool_executor: Optional[ToolExecutor] = None,
        max_tool_rounds: Optional[int] = None,
    ) -> None:
        self.llm_client = llm_client
        self.manager = manager
        self.tool_executor = tool_executor or ToolExecutor()
        self.max_tool_rounds = max_tool_rounds

    @staticmethod
    def _build_tool_prompt(tool_names: list[str]) -> str:
        if not tool_names:
            return "There are no tools available. If the prompt is enough, answer directly."
        bullet_list = "\n".join(f"- {name}" for name in tool_names)
        return (
            "Available tools:\n"
            f"{bullet_list}\n"
            "Call a tool only when it is necessary to answer the user accurately."
        )

    @staticmethod
    def _annotation_to_json_type(annotation: object) -> str:
        if annotation in (int, float):
            return "number"
        if annotation is bool:
            return "boolean"
        if annotation is dict:
            return "object"
        if annotation is list:
            return "array"
        return "string"

    def _build_tool_schemas(self, runtime: AgentPresetRuntimeConfig) -> list[LLMToolSchema]:
        schemas: list[LLMToolSchema] = []
        for tool_name, tool in zip(runtime.tool_names, runtime.tools, strict=False):
            signature = inspect.signature(tool)
            type_hints = get_type_hints(tool)
            properties: dict[str, object] = {}
            required: list[str] = []
            for parameter in signature.parameters.values():
                if parameter.kind not in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                ):
                    continue
                properties[parameter.name] = {
                    "type": self._annotation_to_json_type(type_hints.get(parameter.name, parameter.annotation)),
                }
                if parameter.default is inspect._empty:
                    required.append(parameter.name)
            schemas.append(
                LLMToolSchema(
                    name=tool_name,
                    description=(inspect.getdoc(tool) or f"Call the {tool_name} tool.").strip(),
                    parameters={
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                )
            )
        return schemas

    @staticmethod
    def _estimate_request_context_length(request_payload: LLMRequest) -> int:
        total = len(request_payload.system_prompt) + len(request_payload.user_input) + len(request_payload.tool_prompt)
        for tool_schema in request_payload.tool_schemas:
            total += len(tool_schema.name)
            total += len(tool_schema.description)
            total += len(json.dumps(tool_schema.parameters, ensure_ascii=False))
        for tool_result in request_payload.tool_results:
            total += len(tool_result.name)
            total += len(json.dumps(tool_result.content, ensure_ascii=False))
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
        except ValueError as exc:
            raise AgentPresetResolutionError(str(exc)) from exc
        except KeyError as exc:
            raise AgentPresetResolutionError(str(exc)) from exc

    def _build_request(
        self,
        runtime: AgentPresetRuntimeConfig,
        pipeline_input: AgentPipelineInput,
        tool_calls: list[LLMToolCall],
        tool_results: list[ToolExecutionResult],
    ) -> LLMRequest:
        return LLMRequest(
            system_prompt=self._compose_system_prompt(runtime),
            user_input=pipeline_input.user_input,
            tool_names=runtime.tool_names,
            tool_prompt=self._build_tool_prompt(runtime.tool_names),
            tool_schemas=self._build_tool_schemas(runtime),
            tool_result=tool_results[-1] if tool_results else None,
            tool_results=list(tool_results),
            tool_calls=list(tool_calls),
        )

    def run(self, pipeline_input: AgentPipelineInput) -> AgentPipelineResult:
        runtime = self._resolve_runtime(pipeline_input)
        tool_calls: list[LLMToolCall] = []
        tool_results: list[ToolExecutionResult] = []
        raw_responses: list[object] = []
        last_tool_call = None
        iterations = 0
        context_limit = runtime.llm.context
        max_tool_rounds = self.max_tool_rounds
        if max_tool_rounds is None:
            max_tool_rounds = runtime.llm.max_tool_rounds

        while True:
            request_payload = self._build_request(runtime, pipeline_input, tool_calls, tool_results)
            if context_limit is not None:
                current_context_length = self._estimate_request_context_length(request_payload)
                if current_context_length > context_limit:
                    return AgentPipelineResult(
                        status="completed",
                        runtime=runtime,
                        output_text=(
                            runtime.llm.context_limit_output_text
                            or (
                                f"Context length exceeded limit: {current_context_length}>{context_limit}. "
                                "Please handle this workflow on the business side."
                            )
                        ),
                        iterations=iterations,
                        tool_call=last_tool_call,
                        tool_result=tool_results[-1] if tool_results else None,
                        raw_responses=raw_responses,
                    )
            response = self.llm_client.invoke(request_payload)
            iterations += 1
            raw_responses.append(response.raw)

            if not response.needs_tool:
                return AgentPipelineResult(
                    status="completed",
                    runtime=runtime,
                    output_text=response.text,
                    iterations=iterations,
                    tool_call=last_tool_call,
                    tool_result=tool_results[-1] if tool_results else None,
                    raw_responses=raw_responses,
                )

            if response.tool_call is None:
                raise LLMInvocationError("LLMResponse indicates tool usage but no tool_call was provided")

            if max_tool_rounds is not None and len(tool_results) >= max_tool_rounds:
                return AgentPipelineResult(
                    status="completed",
                    runtime=runtime,
                    output_text=runtime.llm.tool_round_limit_output_text or "调用超过次数限制",
                    iterations=iterations,
                    tool_call=last_tool_call,
                    tool_result=tool_results[-1] if tool_results else None,
                    raw_responses=raw_responses,
                )

            last_tool_call = response.tool_call
            tool_result = self.tool_executor.execute(
                runtime,
                response.tool_call.name,
                response.tool_call.tool_input,
            )
            tool_calls.append(response.tool_call)
            tool_results.append(tool_result)


def run_agent_preset(
    llm_client: LLMClient,
    user_input: str,
    manager: Optional[AgentPresetManager] = None,
    apid: Optional[str] = None,
    agent_preset=None,
    max_tool_rounds: Optional[int] = None,
) -> AgentPipelineResult:
    pipeline = AgentPipeline(llm_client=llm_client, manager=manager, max_tool_rounds=max_tool_rounds)
    return pipeline.run(AgentPipelineInput(user_input=user_input, apid=apid, agent_preset=agent_preset))
