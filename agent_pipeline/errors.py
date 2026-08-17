class AgentPipelineError(Exception):
    """Agent pipeline 基础异常。"""


class AgentPresetResolutionError(AgentPipelineError):
    """AgentPreset 解析失败。"""


class LLMInvocationError(AgentPipelineError):
    """LLM 调用或响应协议不符合预期。"""


class ToolSelectionError(AgentPipelineError):
    """LLM 选择了未注册或未授权的工具。"""
