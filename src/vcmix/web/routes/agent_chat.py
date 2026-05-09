"""
agent_chat.py — Agent Chat + MCP API routes for VCMix (Phase 22a).

REST API endpoints for:
  - Agent conversation (chat with the embedded VCMix Agent)
  - Agent configuration (model, persona, execution mode)
  - Persona listing
  - Agent status
  - MCP Server SSE endpoint (for external Agent integration)
  - MCP tools listing (debug)

Phase 22a uses a global _agent instance for simplicity.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from vcmix.agent.mcp_server import MCPSession, VCMixMCPServer
from vcmix.agent.modelbus import ModelConfig
from vcmix.agent.persona import BUILTIN_PERSONAS
from vcmix.agent.runtime import AgentRuntime

logger = logging.getLogger("vcmix.web.routes.agent_chat")

router = APIRouter()

# ── Global Agent instance (Phase 22a simple implementation) ──────────────

_agent: AgentRuntime | None = None
_mcp_server: VCMixMCPServer | None = None
_mcp_sessions: dict[str, MCPSession] = {}


def _get_agent() -> AgentRuntime:
    """Get or create the global Agent instance."""
    global _agent
    if _agent is None:
        _agent = AgentRuntime()
    return _agent


def _get_mcp_server() -> VCMixMCPServer:
    """Get or create the global MCP server instance."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = VCMixMCPServer()
    return _mcp_server


# ── Pydantic Models ──────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Request body for agent chat."""
    message: str = Field(..., min_length=1, description="User message to the Agent")
    project_id: Optional[str] = Field(default=None, description="Project ID to bind")


class ChatResponse(BaseModel):
    """Response from agent chat."""
    message: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    thinking: str = ""
    requires_confirmation: bool = False


class AgentConfigRequest(BaseModel):
    """Request body for agent configuration."""
    provider: Optional[str] = Field(default=None, description="LLM provider (openai/anthropic/ollama/vllm)")
    model: Optional[str] = Field(default=None, description="Model name")
    api_key: Optional[str] = Field(default=None, description="API key")
    base_url: Optional[str] = Field(default=None, description="Custom base URL")
    persona: Optional[str] = Field(default=None, description="Persona ID (mix-engineer/vocal-expert/beginner-coach)")
    execution_mode: Optional[str] = Field(default=None, description="Execution mode (auto/confirm/suggest)")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=32768)


class MCPMessageRequest(BaseModel):
    """Request body for MCP JSON-RPC message."""
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


# ── Agent Chat Endpoints ─────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest):
    """Send a message to the VCMix Agent and get a response.

    The Agent uses a ReAct loop: it may call multiple tools
    before returning a final text response.
    """
    agent = _get_agent()
    try:
        response = await agent.chat(
            user_message=request.message,
            project_id=request.project_id,
        )
        return ChatResponse(
            message=response.message,
            actions=[
                {
                    "tool": a.tool,
                    "arguments": a.arguments,
                    "result": a.result,
                    "explanation": a.explanation,
                    "timestamp": a.timestamp,
                }
                for a in response.actions
            ],
            thinking=response.thinking,
            requires_confirmation=response.requires_confirmation,
        )
    except Exception as e:
        logger.error("Agent chat error: %s", e)
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")


@router.post("/config")
async def configure_agent(request: AgentConfigRequest):
    """Configure the Agent's LLM backend, persona, and execution mode."""
    agent = _get_agent()

    # Update model config if any model-related fields provided
    if any([request.provider, request.model, request.api_key, request.base_url,
            request.temperature is not None, request.max_tokens is not None]):
        current = agent.model_config
        new_config = ModelConfig(
            provider=request.provider or current.provider,
            model=request.model or current.model,
            api_key=request.api_key or current.api_key,
            base_url=request.base_url or current.base_url,
            temperature=request.temperature if request.temperature is not None else current.temperature,
            max_tokens=request.max_tokens if request.max_tokens is not None else current.max_tokens,
        )
        agent.configure_model(new_config)

    # Switch persona
    if request.persona:
        if request.persona not in BUILTIN_PERSONAS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown persona: {request.persona}. Available: {list(BUILTIN_PERSONAS.keys())}",
            )
        agent.set_persona(request.persona)

    # Set execution mode
    if request.execution_mode:
        if request.execution_mode not in ("auto", "confirm", "suggest"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid execution mode: {request.execution_mode}",
            )
        agent._execution_mode = request.execution_mode

    return {"status": "configured", "agent": agent.get_status()}


@router.get("/personas")
async def list_personas():
    """List all available Agent personas."""
    personas = []
    for pid, persona in BUILTIN_PERSONAS.items():
        personas.append({
            "id": persona.id,
            "name": persona.name,
            "description": persona.description,
            "execution_mode": persona.execution_mode,
        })
    return {"personas": personas, "count": len(personas)}


@router.get("/status")
async def agent_status():
    """Get the current Agent status."""
    agent = _get_agent()
    mcp = _get_mcp_server()
    return {
        "agent": agent.get_status(),
        "mcp": {
            "sessions": mcp.list_sessions(),
            "tools_count": len(mcp.list_tools()),
        },
    }


# ── MCP Server Endpoints ────────────────────────────────────────────────

@router.post("/mcp/message")
async def mcp_message(request: MCPMessageRequest):
    """Handle a single MCP JSON-RPC message.

    This is the POST endpoint for MCP clients that prefer
    request/response mode (rather than SSE streaming).
    Supports: initialize, tools/list, tools/call, ping.
    """
    mcp = _get_mcp_server()

    message = {
        "jsonrpc": request.jsonrpc,
        "id": request.id,
        "method": request.method,
        "params": request.params,
    }

    response = await mcp.handle_jsonrpc(message)
    return response


@router.get("/mcp/sse")
async def mcp_sse(request: Request):
    """SSE endpoint for MCP clients (OpenClaw, Hermes, etc.).

    Opens a Server-Sent Events stream. The client sends JSON-RPC
    messages via POST to /mcp/message, and receives responses
    and notifications via this SSE stream.

    MCP Protocol flow:
      1. Client connects to this SSE endpoint (GET)
      2. Server sends "endpoint" event with the POST URL
      3. Client sends initialize via POST
      4. Client sends tools/list via POST
      5. Client sends tools/call via POST
      6. Server streams results back via SSE

    External Agent operations are visible in the ChatPanel
    as "[外部Agent] 执行了xxx操作".
    """
    mcp = _get_mcp_server()
    session = mcp.create_session(agent_name="sse-client")

    async def event_generator():
        """Generate SSE events for the connected MCP client."""
        try:
            # Send endpoint event — tells the client where to POST messages
            endpoint_event = mcp.make_sse_event({
                "endpoint": "/api/v1/agent/mcp/message",
                "session_id": session.session_id,
            }, event_type="endpoint")
            yield f"event: {endpoint_event['event']}\ndata: {endpoint_event['data']}\n\n"

            # Keep connection alive with heartbeat
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                # Send heartbeat
                heartbeat = mcp.make_sse_event({"type": "ping"}, event_type="heartbeat")
                yield f"event: {heartbeat['event']}\ndata: {heartbeat['data']}\n\n"
                await asyncio.sleep(30)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("SSE error: %s", e)
        finally:
            mcp.close_session(session.session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/mcp/tools")
async def mcp_tools_list():
    """List MCP tools available (debug endpoint).

    Returns the full list of tools exposed via MCP
    in the MCP specification format.
    """
    mcp = _get_mcp_server()
    tools = mcp.list_tools()
    return {
        "tools": [t.to_dict() for t in tools],
        "count": len(tools),
    }
