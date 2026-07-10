from __future__ import annotations

import inspect
from typing import Optional

from agent_pipeline.errors import AgentPresetResolutionError, LLMInvocationError
from agent_pipeline.llm import LLMClient
from agent_pipeline.tools import ToolExecutor
from agent_pipeline.types import (
    AgentPipelineInput,
    AgentPipelineResult,
    LLMRequest,
    LLMToolSchema,
)
from core.agent_preset import AgentPresetManager
from core.agent_preset_resolver import AgentPresetRuntimeConfig, require_agent_preset_by_apid, resolve_agent_preset


class AgentPipeline:
    """Run an agent preset through one LLM step, one optional tool step, and a final LLM step."""

    def __init__(
        self,
        llm_client: LLMClient,
        manager: Optional[AgentPresetManager] = None,
        tool_executor: Optional[ToolExecutor] = None,
    ) -> None:
        self.llm_client = llm_client
        self.manager = manager
        self.tool_executor = tool_executor or ToolExecutor()

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
            properties: dict[str, object] = {}
            required: list[str] = []
            for parameter in signature.parameters.values():
                if parameter.kind not in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                ):
                    continue
                properties[parameter.name] = {
                    "type": self._annotation_to_json_type(parameter.annotation),
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

    def _build_initial_request(self, runtime: AgentPresetRuntimeConfig, pipeline_input: AgentPipelineInput) -> LLMRequest:
        return LLMRequest(
            system_prompt=runtime.preset.prompt,
            user_input=pipeline_input.user_input,
            tool_names=runtime.tool_names,
            tool_prompt=self._build_tool_prompt(runtime.tool_names),
            tool_schemas=self._build_tool_schemas(runtime),
        )

    def _build_followup_request(
        self,
        runtime: AgentPresetRuntimeConfig,
        pipeline_input: AgentPipelineInput,
        tool_result,
    ) -> LLMRequest:
        return LLMRequest(
            system_prompt=runtime.preset.prompt,
            user_input=pipeline_input.user_input,
            tool_names=runtime.tool_names,
            tool_prompt=self._build_tool_prompt(runtime.tool_names),
            tool_schemas=self._build_tool_schemas(runtime),
            tool_result=tool_result,
        )

    def run(self, pipeline_input: AgentPipelineInput) -> AgentPipelineResult:
        runtime = self._resolve_runtime(pipeline_input)
        initial_request = self._build_initial_request(runtime, pipeline_input)
        first_response = self.llm_client.invoke(initial_request)

        if not first_response.needs_tool:
            return AgentPipelineResult(
                status="completed",
                runtime=runtime,
                output_text=first_response.text,
                iterations=1,
                raw_responses=[first_response.raw],
            )

        if first_response.tool_call is None:
            raise LLMInvocationError("LLMResponse indicates tool usage but no tool_call was provided")

        tool_result = self.tool_executor.execute(
            runtime,
            first_response.tool_call.name,
            first_response.tool_call.tool_input,
        )

        followup_request = self._build_followup_request(runtime, pipeline_input, tool_result)
        second_response = self.llm_client.invoke(followup_request)

        if second_response.needs_tool:
            raise LLMInvocationError("Current AgentPipeline only supports a single tool round")

        return AgentPipelineResult(
            status="completed",
            runtime=runtime,
            output_text=second_response.text,
            iterations=2,
            tool_call=first_response.tool_call,
            tool_result=tool_result,
            raw_responses=[first_response.raw, second_response.raw],
        )


def run_agent_preset(
    llm_client: LLMClient,
    user_input: str,
    manager: Optional[AgentPresetManager] = None,
    apid: Optional[str] = None,
    agent_preset=None,
) -> AgentPipelineResult:
    pipeline = AgentPipeline(llm_client=llm_client, manager=manager)
    return pipeline.run(AgentPipelineInput(user_input=user_input, apid=apid, agent_preset=agent_preset))
