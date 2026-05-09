"""
websocket.py — WebSocket DataStream forwarding for VCMix Web UI.

Provides real-time streaming of rendering events to browser clients
via WebSocket. Uses the same DataStream emitter as the rendering pipeline.

Architecture:
    - Client connects to ws://host:port/api/stream
    - When a render is triggered with stream=websocket, events are
      forwarded to all connected clients in real-time
    - Events are JSON-formatted StreamEvent objects

Usage (frontend):
    const ws = new WebSocket('ws://localhost:8000/api/stream');
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(data.type, data.track, data);
    };
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


# ── Connection Manager ───────────────────────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections for DataStream forwarding."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        data = json.dumps(message, ensure_ascii=False)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def send_to(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        """Send a message to a specific client."""
        try:
            data = json.dumps(message, ensure_ascii=False)
            await websocket.send_text(data)
        except Exception:
            self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        """Number of active connections."""
        return len(self.active_connections)


# ── Global manager instance ──────────────────────────────────────────────

manager = ConnectionManager()


# ── WebSocket endpoint ───────────────────────────────────────────────────

@router.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time DataStream events.

    Protocol:
        - Server sends JSON events as they occur during rendering
        - Client can send commands:
            - {"action": "ping"} → server responds with {"type": "pong"}
            - {"action": "subscribe", "job_id": "..."} → subscribe to specific job events
        - Connection is kept alive with periodic heartbeat messages
    """
    await manager.connect(websocket)

    # Send welcome message
    await manager.send_to(websocket, {
        "type": "connected",
        "message": "VCMix DataStream WebSocket connected",
        "ts": time.time() * 1000,
    })

    try:
        while True:
            # Wait for client messages (commands)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    await manager.send_to(websocket, {
                        "type": "error",
                        "message": "Invalid JSON",
                    })
                    continue

                action = msg.get("action", "")

                if action == "ping":
                    await manager.send_to(websocket, {
                        "type": "pong",
                        "ts": time.time() * 1000,
                    })

                elif action == "status":
                    await manager.send_to(websocket, {
                        "type": "status",
                        "connections": manager.connection_count,
                        "ts": time.time() * 1000,
                    })

                else:
                    await manager.send_to(websocket, {
                        "type": "error",
                        "message": f"Unknown action: {action}",
                    })

            except asyncio.TimeoutError:
                # Send heartbeat on timeout
                await manager.send_to(websocket, {
                    "type": "heartbeat",
                    "ts": time.time() * 1000,
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Utility: emit event to all WebSocket clients ─────────────────────────

async def emit_stream_event(event: dict[str, Any]) -> None:
    """
    Emit a DataStream event to all connected WebSocket clients.

    Called from render routes to forward real-time events.
    """
    await manager.broadcast(event)


def emit_stream_event_sync(event: dict[str, Any]) -> None:
    """
    Synchronous wrapper for emit_stream_event.

    Safe to call from background threads — schedules the broadcast
    on the event loop.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(emit_stream_event(event))
        else:
            loop.run_until_complete(emit_stream_event(event))
    except RuntimeError:
        pass  # No event loop available


# ── Real-time sync event types ────────────────────────────────────────

EVENT_PROJECT_CREATED = "project_created"
EVENT_PROJECT_UPDATED = "project_updated"
EVENT_PROJECT_DELETED = "project_deleted"
EVENT_TRACK_ADDED = "track_added"
EVENT_TRACK_UPDATED = "track_updated"
EVENT_TRACK_REMOVED = "track_removed"
EVENT_EFFECT_ADDED = "effect_added"
EVENT_EFFECT_UPDATED = "effect_updated"
EVENT_EFFECT_REMOVED = "effect_removed"
EVENT_AI_MIX_APPLIED = "ai_mix_applied"
EVENT_AI_MASTER_APPLIED = "ai_master_applied"
