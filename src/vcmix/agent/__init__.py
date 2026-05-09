"""
VCMix AgentPlugin — AI Agent for VCMix DAW (Phase 22a).

Embedded domain-expert Agent that lives inside the DAW project,
understands audio terminology, and directly operates VCMix APIs.

Modules:
    modelbus    — Unified LLM client (OpenAI SDK compatible)
    toolbox     — 20 VCMix API tool definitions + executor
    runtime     — AgentRuntime with ReAct loop
    memory      — Short-term conversation memory (sliding window)
    persona     — Persona framework with builtin presets
    mcp_server  — MCP Server for external Agent integration
"""

from vcmix.agent.mcp_server import MCPResult, MCPTool, VCMixMCPServer
from vcmix.agent.memory import ShortTermMemory
from vcmix.agent.modelbus import Message, ModelBus, ModelConfig
from vcmix.agent.persona import BUILTIN_PERSONAS, Persona
from vcmix.agent.runtime import AgentAction, AgentResponse, AgentRuntime
from vcmix.agent.toolbox import AGENT_TOOLS, ToolExecutor

__all__ = [
    "ModelBus",
    "ModelConfig",
    "Message",
    "ToolExecutor",
    "AGENT_TOOLS",
    "AgentRuntime",
    "AgentResponse",
    "AgentAction",
    "ShortTermMemory",
    "Persona",
    "BUILTIN_PERSONAS",
    "VCMixMCPServer",
    "MCPTool",
    "MCPResult",
]
