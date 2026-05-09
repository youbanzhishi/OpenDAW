"""
agent_api.py — FastAPI endpoints for VCMix Agent (Phase 22b).

Endpoints for:
- Model management (list, switch, health check)
- Persona management (list, get, create, update, delete)
- Agent chat (single turn and streaming)
- Runtime status

All endpoints preserve conversation context across model/persona switches.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from vcmix.agent.enhanced_modelbus import EnhancedModelBus, ProviderConfig
from vcmix.agent.enhanced_runtime import AgentResponse, EnhancedAgentRuntime
from vcmix.agent.persona_manager import Persona, PersonaManager

logger = logging.getLogger("vcmix.agent.api")

# ── Request/Response Models ────────────────────────────────────────────────

class ModelSwitchRequest(BaseModel):
    """Request to switch LLM model."""
    provider_type: str = Field(..., description="Provider: openai, anthropic, ollama, vllm")
    model_id: str = Field(..., description="Model ID")
    api_key: str | None = Field(None, description="API key (optional for local)")
    base_url: str | None = Field(None, description="Custom base URL")

class FallbackProviderRequest(BaseModel):
    """Request to add fallback provider."""
    provider_type: str
    model_id: str
    api_key: str | None = None
    base_url: str | None = None
    priority: int = 100

class PersonaSwitchRequest(BaseModel):
    """Request to switch persona."""
    persona_id: str = Field(..., description="Persona ID")

class CustomPromptRequest(BaseModel):
    """Request to set custom system prompt."""
    prompt: str = Field(..., description="Custom system prompt")
    name: str | None = Field(None, description="Optional name for saving")

class PersonaCreateRequest(BaseModel):
    """Request to create custom persona."""
    id: str = Field(..., description="Unique persona ID")
    name: str = Field(..., description="Display name")
    description: str = Field("", description="Description")
    system_prompt: str = Field(..., description="System prompt")
    execution_mode: str = Field("confirm", description="auto, confirm, suggest")
    tool_preferences: dict[str, float] = Field(default_factory=dict)

class PersonaUpdateRequest(BaseModel):
    """Request to update persona."""
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    execution_mode: str | None = None
    tool_preferences: dict[str, float] | None = None

class ChatRequest(BaseModel):
    """Request to chat with the agent."""
    message: str = Field(..., description="User message")
    project_id: str | None = Field(None, description="Project ID")
    execution_mode: str | None = Field(None, description="Override execution mode")
    stream: bool = Field(False, description="Enable streaming response")

class ChatStreamResponse(BaseModel):
    """Streaming chat response chunk."""
    type: str  # thinking, tool_call, tool_result, message, done
    content: str
    data: dict[str, Any] | None = None

class AgentStatusResponse(BaseModel):
    """Agent runtime status."""
    model: str
    model_info: dict[str, Any] | None
    project_id: str | None
    persona: str
    persona_name: str
    execution_mode: str
    memory_messages: int
    context_messages: int

class ModelListResponse(BaseModel):
    """List of available models."""
    providers: list[dict[str, Any]]

class PersonaListResponse(BaseModel):
    """List of personas."""
    personas: list[dict[str, Any]]

# ── Runtime State ───────────────────────────────────────────────────────────

# Global runtime instance (per worker process)
_runtime: EnhancedAgentRuntime | None = None
_persona_manager: PersonaManager | None = None


def get_runtime() -> EnhancedAgentRuntime:
    """Get or create the global runtime."""
    global _runtime
    if _runtime is None:
        _runtime = EnhancedAgentRuntime()
    return _runtime


def get_persona_manager() -> PersonaManager:
    """Get or create the global persona manager."""
    global _persona_manager
    if _persona_manager is None:
        _persona_manager = PersonaManager()
    return _persona_manager


# ── Router Setup ───────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


# ── Model Management Endpoints ─────────────────────────────────────────────

@router.get("/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """List all available models grouped by provider."""
    return ModelListResponse(providers=EnhancedModelBus.list_providers())


@router.post("/model/switch")
async def switch_model(request: ModelSwitchRequest) -> dict[str, Any]:
    """Switch to a different LLM model.

    The conversation context is preserved across the switch.
    """
    runtime = get_runtime()
    runtime.switch_model(
        provider_type=request.provider_type,
        model_id=request.model_id,
        api_key=request.api_key,
        base_url=request.base_url,
    )
    return {"success": True, "model": runtime.get_current_model()}


@router.post("/model/fallback")
async def add_fallback_provider(request: FallbackProviderRequest) -> dict[str, Any]:
    """Add a fallback provider for automatic failover."""
    runtime = get_runtime()
    config = ProviderConfig(
        provider_type=request.provider_type,
        model_id=request.model_id,
        api_key=request.api_key or "",
        base_url=request.base_url or "",
        priority=request.priority,
    )
    runtime.add_fallback_provider(config)
    return {"success": True, "fallback_count": len(runtime._model_bus._fallback_providers)}


@router.get("/model/status")
async def get_model_status() -> dict[str, Any]:
    """Get current model status."""
    runtime = get_runtime()
    return runtime._model_bus.get_status()


@router.get("/model/health")
async def health_check() -> dict[str, Any]:
    """Check if the current model is responsive."""
    runtime = get_runtime()
    return await runtime._model_bus.health_check()


# ── Persona Management Endpoints ──────────────────────────────────────────

@router.get("/personas", response_model=PersonaListResponse)
async def list_personas() -> PersonaListResponse:
    """List all available personas (built-in + custom)."""
    manager = get_persona_manager()
    personas = manager.list_personas()
    return PersonaListResponse(
        personas=[
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "execution_mode": p.execution_mode,
                "is_builtin": p.is_builtin,
            }
            for p in personas
        ]
    )


@router.get("/personas/{persona_id}")
async def get_persona(persona_id: str) -> dict[str, Any]:
    """Get a specific persona."""
    manager = get_persona_manager()
    persona = manager.get_persona(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona.to_dict()


@router.post("/personas/switch")
async def switch_persona(request: PersonaSwitchRequest) -> dict[str, Any]:
    """Switch to a different persona.

    The conversation context is preserved across the switch.
    """
    runtime = get_runtime()
    success = runtime.set_persona(request.persona_id)
    if not success:
        raise HTTPException(status_code=404, detail="Persona not found")
    return {"success": True, "persona": runtime.get_persona().to_dict() if runtime.get_persona() else None}


@router.post("/personas/custom")
async def create_custom_persona(request: PersonaCreateRequest) -> dict[str, Any]:
    """Create a custom persona."""
    manager = get_persona_manager()

    if manager.persona_exists(request.id):
        raise HTTPException(status_code=400, detail="Persona ID already exists")

    persona = Persona(
        id=request.id,
        name=request.name,
        description=request.description,
        system_prompt=request.system_prompt,
        execution_mode=request.execution_mode,
        tool_preferences=request.tool_preferences,
        is_builtin=False,
    )

    manager.save_persona(persona)
    return {"success": True, "persona": persona.to_dict()}


@router.put("/personas/{persona_id}")
async def update_persona(persona_id: str, request: PersonaUpdateRequest) -> dict[str, Any]:
    """Update a custom persona."""
    manager = get_persona_manager()
    persona = manager.get_persona(persona_id)

    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    if persona.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot modify built-in personas")

    # Update fields
    if request.name is not None:
        persona.name = request.name
    if request.description is not None:
        persona.description = request.description
    if request.system_prompt is not None:
        persona.system_prompt = request.system_prompt
    if request.execution_mode is not None:
        persona.execution_mode = request.execution_mode
    if request.tool_preferences is not None:
        persona.tool_preferences = request.tool_preferences

    manager.save_persona(persona)
    return {"success": True, "persona": persona.to_dict()}


@router.delete("/personas/{persona_id}")
async def delete_persona(persona_id: str) -> dict[str, Any]:
    """Delete a custom persona."""
    manager = get_persona_manager()
    success = manager.delete_persona(persona_id)
    if not success:
        raise HTTPException(status_code=404, detail="Persona not found or built-in")
    return {"success": True}


@router.post("/personas/{persona_id}/duplicate")
async def duplicate_persona(persona_id: str, new_id: str, new_name: str) -> dict[str, Any]:
    """Duplicate a persona as a new custom persona."""
    manager = get_persona_manager()
    persona = manager.duplicate_persona(persona_id, new_id, new_name)
    if not persona:
        raise HTTPException(status_code=404, detail="Source persona not found")
    return {"success": True, "persona": persona.to_dict()}


@router.get("/personas/{persona_id}/export")
async def export_persona(persona_id: str) -> dict[str, Any]:
    """Export a persona as JSON."""
    manager = get_persona_manager()
    json_str = manager.export_persona(persona_id)
    if json_str is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return {"success": True, "json": json_str}


@router.post("/personas/import")
async def import_persona(json_str: str) -> dict[str, Any]:
    """Import a persona from JSON."""
    manager = get_persona_manager()
    persona = manager.import_persona(json_str)
    if persona is None:
        raise HTTPException(status_code=400, detail="Failed to import persona")
    return {"success": True, "persona": persona.to_dict()}


# ── Chat Endpoints ─────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(request: ChatRequest) -> AgentResponse:
    """Send a message to the agent and get a response."""
    runtime = get_runtime()

    response = await runtime.chat(
        user_message=request.message,
        project_id=request.project_id,
        execution_mode=request.execution_mode,
    )

    return response


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> AsyncIterator[ChatStreamResponse]:
    """Stream agent response (thinking, tool calls, final message)."""
    runtime = get_runtime()

    async def generate() -> AsyncIterator[ChatStreamResponse]:
        # Add user message
        runtime._memory.add_message("user", request.message)
        messages = runtime._build_messages()
        tools = runtime._tool_executor._tools

        # First, send thinking status
        yield ChatStreamResponse(
            type="status",
            content="正在分析...",
            data={"project_id": request.project_id or runtime._project_id}
        )

        # Get LLM response
        try:
            response = await runtime._model_bus.chat(
                messages=messages,
                tools=tools,
            )
        except Exception as e:
            yield ChatStreamResponse(
                type="error",
                content=f"模型调用失败: {e}",
            )
            return

        # Send tool calls if any
        if response.has_tool_calls:
            for tc in response.tool_calls:
                yield ChatStreamResponse(
                    type="tool_call",
                    content=f"{tc['name']}({tc.get('arguments', '{}')})",
                    data=tc,
                )

        # Send final message
        yield ChatStreamResponse(
            type="done",
            content=response.content,
            data={"model": runtime.get_current_model()}
        )

    return generate()


@router.post("/chat/clear")
async def clear_conversation() -> dict[str, Any]:
    """Clear conversation history."""
    runtime = get_runtime()
    runtime.clear_conversation()
    return {"success": True}


# ── Status Endpoints ────────────────────────────────────────────────────────

@router.get("/status", response_model=AgentStatusResponse)
async def get_status() -> AgentStatusResponse:
    """Get agent runtime status."""
    runtime = get_runtime()
    return AgentStatusResponse(**runtime.get_status())


@router.post("/project/bind")
async def bind_project(project_id: str) -> dict[str, Any]:
    """Bind agent to a specific project."""
    runtime = get_runtime()
    runtime.set_project(project_id)
    return {"success": True, "project_id": project_id}


# ── Initialization ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: Any) -> AsyncIterator[None]:
    """Application lifespan handler."""
    # Startup
    logger.info("Agent API starting...")
    global _runtime, _persona_manager
    _runtime = EnhancedAgentRuntime()
    _persona_manager = PersonaManager()
    logger.info("Agent API ready")

    yield

    # Shutdown
    if _runtime:
        await _runtime.close()
    logger.info("Agent API shutdown complete")
