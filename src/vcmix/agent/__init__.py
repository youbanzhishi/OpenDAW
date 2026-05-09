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

from vcmix.agent.modelbus import ModelBus, ModelConfig, Message
from vcmix.agent.toolbox import ToolExecutor, AGENT_TOOLS
from vcmix.agent.runtime import AgentRuntime, AgentResponse, AgentAction
from vcmix.agent.memory import ShortTermMemory
from vcmix.agent.persona import Persona, BUILTIN_PERSONAS
from vcmix.agent.mcp_server import VCMixMCPServer, MCPTool, MCPResult

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
