"""
mcp_server.py — MCP Server for VCMix Agent (Phase 22a).

Implements a Model Context Protocol (MCP) server that exposes VCMix's
55+ API endpoints as MCP Tools, allowing external Agents (OpenClaw,
Hermes, etc.) to control the DAW through a standard protocol.

Flow:
  External Agent → MCP (JSON-RPC) → VCMixMCPServer → ToolExecutor → Local API
                                                                      ↓
                                                              WebSocket broadcast
                                                                      ↓
                                                              Frontend real-time refresh

Phase 22a: SSE transport only (stdio deferred to later phase).

MCP Protocol reference: https://spec.modelcontextprotocol.io/specification/
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from vcmix.agent.toolbox import AGENT_TOOLS, ToolExecutor

logger = logging.getLogger("vcmix.agent.mcp_server")


# ── MCP Data Types ───────────────────────────────────────────────────────

@dataclass
class MCPTool:
    """MCP Tool definition — mirrors the MCP specification Tool type.

    Attributes:
        name: Unique tool identifier.
        description: Human-readable description.
        inputSchema: JSON Schema for the tool's input parameters.
    """

    name: str
    description: str
    inputSchema: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to MCP specification format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }


@dataclass
class MCPResult:
    """MCP Tool call result — mirrors the MCP specification CallToolResult.

    Attributes:
        content: List of content items (text, image, etc.).
        isError: Whether the tool call resulted in an error.
    """

    content: list[dict[str, Any]] = field(default_factory=list)
    isError: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to MCP specification format."""
        return {
            "content": self.content,
            "isError": self.isError,
        }

    @classmethod
    def text(cls, text: str, is_error: bool = False) -> "MCPResult":
        """Create a text result."""
        return cls(
            content=[{"type": "text", "text": text}],
            isError=is_error,
        )


@dataclass
class MCPSession:
    """An active MCP SSE session from an external Agent.

    Attributes:
        session_id: Unique session identifier.
        agent_name: Name of the connected external Agent.
        connected_at: Connection timestamp.
        last_activity: Last activity timestamp.
    """

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    agent_name: str = "unknown"
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


class VCMixMCPServer:
    """MCP Server — lets external Agents (OpenClaw/Hermes etc.) control VCMix.

    Exposes all VCMix API endpoints as MCP Tools following the
    Model Context Protocol specification. External Agents discover
    available tools via tools/list and invoke them via tools/call.

    Reuses ToolExecutor from toolbox.py for actual API calls —
    no duplicate logic. All operations are broadcast via WebSocket
    to the frontend so users see real-time changes.

    Usage:
        server = VCMixMCPServer(api_base="http://localhost:8000/api/v1")
        tools = server.list_tools()
        result = await server.call_tool("get_project", {"project_id": "abc"})
    """

    def __init__(self, api_base: str = "http://localhost:8000/api/v1") -> None:
        self._tool_executor = ToolExecutor(api_base=api_base)
        self._sessions: dict[str, MCPSession] = {}
        self._mcp_tools: list[MCPTool] = self._build_mcp_tools()

    def _build_mcp_tools(self) -> list[MCPTool]:
        """Build MCP tool definitions from AGENT_TOOLS.

        Converts the internal tool format (OpenAI function-calling style)
        to MCP Tool format (name, description, inputSchema).
        """
        mcp_tools = []
        for tool_def in AGENT_TOOLS:
            mcp_tools.append(MCPTool(
                name=tool_def["name"],
                description=tool_def.get("description", ""),
                inputSchema=tool_def.get("parameters", {"type": "object", "properties": {}}),
            ))
        return mcp_tools

    def list_tools(self) -> list[MCPTool]:
        """Return the list of MCP Tools exposed by this server.

        Called when an external Agent sends tools/list.
        """
        return self._mcp_tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPResult:
        """Execute an MCP tool call.

        Called when an external Agent sends tools/call.
        Delegates to ToolExecutor which calls the local VCMix API.
        Results are automatically broadcast via WebSocket.

        Args:
            name: Tool name (must match one of list_tools()).
            arguments: Tool input arguments.

        Returns:
            MCPResult with the tool execution result.
        """
        # Validate tool name
        valid_names = [t.name for t in self._mcp_tools]
        if name not in valid_names:
            return MCPResult.text(f"Unknown tool: {name}. Available: {', '.join(valid_names[:5])}...", is_error=True)

        logger.info("MCP call_tool: %s(%s)", name, json.dumps(arguments, ensure_ascii=False)[:200])

        try:
            result = await self._tool_executor.execute(name, arguments)

            if "error" in result:
                return MCPResult.text(
                    f"Tool '{name}' failed: {result['error']}",
                    is_error=True,
                )

            # Convert result dict to MCP text content
            result_text = json.dumps(result, ensure_ascii=False, indent=2)
            # Truncate very large results
            if len(result_text) > 10000:
                result_text = result_text[:10000] + "\n... (truncated)"

            return MCPResult.text(result_text)

        except Exception as e:
            logger.error("MCP call_tool error: %s - %s", name, e)
            return MCPResult.text(f"Tool execution error: {e}", is_error=True)

    # ── Session Management ───────────────────────────────────────────────

    def create_session(self, agent_name: str = "unknown") -> MCPSession:
        """Create a new MCP session for an external Agent connection.

        Args:
            agent_name: Name/identifier of the connecting Agent.

        Returns:
            The new MCPSession.
        """
        session = MCPSession(agent_name=agent_name)
        self._sessions[session.session_id] = session
        logger.info("MCP session created: %s (agent: %s)", session.session_id, agent_name)
        return session

    def get_session(self, session_id: str) -> MCPSession | None:
        """Get an existing session by ID."""
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
        """Close and remove an MCP session."""
        session = self._sessions.pop(session_id, None)
        if session:
            logger.info("MCP session closed: %s (agent: %s)", session_id, session.agent_name)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all active MCP sessions."""
        return [
            {
                "session_id": s.session_id,
                "agent_name": s.agent_name,
                "connected_at": s.connected_at,
                "last_activity": s.last_activity,
            }
            for s in self._sessions.values()
        ]

    # ── JSON-RPC Message Handling ────────────────────────────────────────

    async def handle_jsonrpc(self, message: dict[str, Any], session: MCPSession | None = None) -> dict[str, Any]:
        """Handle a single JSON-RPC message from an MCP client.

        Supports the following MCP methods:
        - initialize: Server capability negotiation
        - tools/list: List available tools
        - tools/call: Invoke a tool
        - ping: Keep-alive

        Args:
            message: A JSON-RPC 2.0 message dict.
            session: Optional session for tracking.

        Returns:
            A JSON-RPC 2.0 response dict.
        """
        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params", {})

        # Update session activity
        if session:
            session.last_activity = time.time()

        try:
            if method == "initialize":
                return self._handle_initialize(msg_id, params)
            elif method == "ping":
                return self._make_response(msg_id, {})
            elif method == "tools/list":
                return self._handle_tools_list(msg_id, params)
            elif method == "tools/call":
                return await self._handle_tools_call(msg_id, params, session)
            else:
                return self._make_error(msg_id, -32601, f"Method not found: {method}")

        except Exception as e:
            logger.error("JSON-RPC handler error: %s", e)
            return self._make_error(msg_id, -32603, f"Internal error: {e}")

    def _handle_initialize(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP initialize request."""
        client_info = params.get("clientInfo", {})
        logger.info("MCP initialize from client: %s", client_info)

        return self._make_response(msg_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
            },
            "serverInfo": {
                "name": "VCMix MCP Server",
                "version": "0.22.0",
            },
        })

    def _handle_tools_list(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Handle MCP tools/list request."""
        tools = [t.to_dict() for t in self._mcp_tools]
        return self._make_response(msg_id, {"tools": tools})

    async def _handle_tools_call(self, msg_id: Any, params: dict[str, Any], session: MCPSession | None = None) -> dict[str, Any]:
        """Handle MCP tools/call request."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if not tool_name:
            return self._make_error(msg_id, -32602, "Missing tool name")

        result = await self.call_tool(tool_name, arguments)
        return self._make_response(msg_id, result.to_dict())

    # ── JSON-RPC Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _make_response(msg_id: Any, result: Any) -> dict[str, Any]:
        """Create a JSON-RPC success response."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }

    @staticmethod
    def _make_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
        """Create a JSON-RPC error response."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }

    # ── SSE Event Generation ─────────────────────────────────────────────

    def make_sse_event(self, data: dict[str, Any], event_type: str = "message") -> dict[str, str]:
        """Create an SSE event dict for streaming.

        Args:
            data: The data payload (will be JSON-serialized).
            event_type: SSE event type.

        Returns:
            Dict with "event" and "data" keys for SSE.
        """
        return {
            "event": event_type,
            "data": json.dumps(data, ensure_ascii=False),
        }

    async def close(self) -> None:
        """Clean up resources."""
        await self._tool_executor.close()
        self._sessions.clear()
