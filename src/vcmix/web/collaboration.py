"""
collaboration.py — Multi-user collaboration manager for VCMix (Phase 18).

Provides real-time collaborative editing via WebSocket, enabling
multiple users to edit the same project simultaneously with
conflict resolution (last-write-wins strategy).

Architecture:
    - CollaborationManager: Singleton manager for all collaboration rooms
    - Room: Represents a collaborative editing session for one project
    - WebSocket protocol: join/leave/change/sync/conflict messages
    - Change types: track_add/track_remove/param_change/effect_add/effect_remove
    - Conflict resolution: Last-Write-Wins (LWW) with timestamp ordering

WebSocket Protocol:
    Client → Server:
        {"type": "join", "user_id": "alice", "project_id": "proj_123"}
        {"type": "change", "user_id": "alice", "project_id": "proj_123",
         "change": {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.8}}
        {"type": "leave", "user_id": "alice", "project_id": "proj_123"}
        {"type": "sync_request", "user_id": "alice", "project_id": "proj_123"}

    Server → Client:
        {"type": "user_joined", "user_id": "alice", "users": [...]}
        {"type": "user_left", "user_id": "alice", "users": [...]}
        {"type": "change", "user_id": "bob", "change": {...}}
        {"type": "sync", "state": {...}}
        {"type": "conflict", "description": "...", "resolution": "..."}

Usage:
    from vcmix.web.collaboration import CollaborationManager
    mgr = CollaborationManager()
    await mgr.join_room("proj_123", "alice", websocket)
    await mgr.broadcast_change("proj_123", "alice", change_dict)
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket


@dataclass
class User:
    """Represents a connected user in a collaboration room."""
    user_id: str
    websocket: Optional[WebSocket] = None
    joined_at: float = field(default_factory=time.time)


@dataclass
class Room:
    """Represents a collaborative editing session for a project.

    Attributes:
        project_id: The project being collaboratively edited.
        users: Mapping of user_id to User instance.
        state: Current project state (synced representation).
        history: List of all changes applied in order.
    """
    project_id: str
    users: dict[str, User] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def user_count(self) -> int:
        return len(self.users)

    @property
    def user_ids(self) -> list[str]:
        return list(self.users.keys())


class CollaborationManager:
    """Multi-user collaboration manager.

    Manages collaboration rooms where multiple users can
    edit the same project simultaneously via WebSocket.

    Thread-safe operations via asyncio locks when used
    within an async context.
    """

    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.users: dict[str, User] = {}  # session_id -> User
        self._lock = threading.Lock()

    # ── Room Management ────────────────────────────────────────────────────

    async def join_room(
        self,
        project_id: str,
        user_id: str,
        ws: WebSocket,
    ) -> dict[str, Any]:
        """Join a collaboration room.

        Creates the room if it doesn't exist, adds the user,
        and notifies other users.

        Args:
            project_id: Project to collaborate on.
            user_id: Identifier for the joining user.
            ws: WebSocket connection.

        Returns:
            Dict with room state and user list.
        """
        with self._lock:
            if project_id not in self.rooms:
                self.rooms[project_id] = Room(project_id=project_id)
            room = self.rooms[project_id]

            # Remove user from previous room if they were in one
            for pid, r in self.rooms.items():
                if user_id in r.users and pid != project_id:
                    r.users[user_id].websocket
                    del r.users[user_id]
                    # Schedule notification (don't await inside lock)
                    _notify_task = (pid, user_id, "user_left", r.user_ids)

            user = User(user_id=user_id, websocket=ws)
            room.users[user_id] = user
            self.users[user_id] = user

        # Notify other users
        await self._broadcast(
            project_id,
            {
                "type": "user_joined",
                "user_id": user_id,
                "users": room.user_ids,
                "timestamp": time.time(),
            },
            exclude_user=user_id,
        )

        # Send current state to joining user
        await self._send_to_user(user_id, {
            "type": "joined",
            "project_id": project_id,
            "users": room.user_ids,
            "state": room.state,
            "history_length": len(room.history),
            "timestamp": time.time(),
        })

        return {
            "project_id": project_id,
            "user_id": user_id,
            "users": room.user_ids,
            "history_length": len(room.history),
        }

    async def leave_room(
        self,
        project_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Leave a collaboration room.

        Removes the user from the room and notifies remaining users.
        Cleans up the room if empty.

        Args:
            project_id: Project room to leave.
            user_id: User leaving.

        Returns:
            Dict with leave status.
        """
        with self._lock:
            room = self.rooms.get(project_id)
            if room is None:
                return {"status": "not_in_room"}

            if user_id in room.users:
                del room.users[user_id]

            if user_id in self.users:
                del self.users[user_id]

            # Clean up empty rooms
            if room.user_count == 0:
                del self.rooms[project_id]
                return {"status": "left", "room_closed": True}

        # Notify remaining users
        await self._broadcast(
            project_id,
            {
                "type": "user_left",
                "user_id": user_id,
                "users": room.user_ids,
                "timestamp": time.time(),
            },
        )

        return {"status": "left", "users_remaining": room.user_count}

    # ── Change Broadcasting ────────────────────────────────────────────────

    async def broadcast_change(
        self,
        project_id: str,
        user_id: str,
        change: dict[str, Any],
    ) -> dict[str, Any]:
        """Broadcast a change to all other users in the room.

        Also records the change in the room history and updates
        the room state.

        Change types:
            - track_add: New track added
            - track_remove: Track removed
            - param_change: Parameter value changed
            - effect_add: Effect added to track
            - effect_remove: Effect removed from track

        Args:
            project_id: Project room.
            user_id: User making the change.
            change: Change description dict with 'kind' key.

        Returns:
            Dict with broadcast status.
        """
        with self._lock:
            room = self.rooms.get(project_id)
            if room is None:
                return {"status": "error", "message": "Room not found"}

            if user_id not in room.users:
                return {"status": "error", "message": "User not in room"}

        # Add metadata to change
        enriched_change = {
            **change,
            "user_id": user_id,
            "timestamp": time.time(),
        }

        # Record in history
        with self._lock:
            room.history.append(enriched_change)
            # Update room state
            self._apply_change_to_state(room.state, enriched_change)

        # Broadcast to other users
        await self._broadcast(
            project_id,
            {
                "type": "change",
                "change": enriched_change,
            },
            exclude_user=user_id,
        )

        return {
            "status": "broadcast",
            "change": enriched_change,
            "recipients": room.user_count - 1,
        }

    # ── Sync ───────────────────────────────────────────────────────────────

    async def sync_room(
        self,
        project_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Send current room state to a specific user.

        Args:
            project_id: Project room.
            user_id: User requesting sync.

        Returns:
            Dict with current state.
        """
        with self._lock:
            room = self.rooms.get(project_id)
            if room is None:
                return {"status": "error", "message": "Room not found"}

        await self._send_to_user(user_id, {
            "type": "sync",
            "state": room.state,
            "history": room.history[-50:],  # Last 50 changes
            "timestamp": time.time(),
        })

        return {
            "status": "synced",
            "state_keys": list(room.state.keys()),
            "history_length": len(room.history),
        }

    # ── Conflict Handling ──────────────────────────────────────────────────

    async def handle_conflict(
        self,
        project_id: str,
        changes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Handle conflicting changes using Last-Write-Wins (LWW).

        When multiple users modify the same parameter simultaneously,
        the change with the latest timestamp wins.

        Args:
            project_id: Project room.
            changes: List of conflicting change dicts.

        Returns:
            Dict with resolution details.
        """
        if not changes:
            return {"status": "no_conflict"}

        # Sort by timestamp, newest last
        sorted_changes = sorted(changes, key=lambda c: c.get("timestamp", 0))

        # Last write wins
        winning_change = sorted_changes[-1]

        with self._lock:
            room = self.rooms.get(project_id)
            if room is None:
                return {"status": "error", "message": "Room not found"}

            # Apply winning change
            self._apply_change_to_state(room.state, winning_change)
            room.history.append({
                **winning_change,
                "conflict_resolution": "lww",
                "competing_changes": len(changes),
            })

        # Notify all users of resolution
        await self._broadcast(
            project_id,
            {
                "type": "conflict",
                "resolution": "last_write_wins",
                "winning_change": winning_change,
                "competing_changes": len(changes),
                "timestamp": time.time(),
            },
        )

        return {
            "status": "resolved",
            "resolution": "last_write_wins",
            "winning_user": winning_change.get("user_id"),
            "winning_timestamp": winning_change.get("timestamp"),
            "competing_changes": len(changes),
        }

    # ── Query Methods ──────────────────────────────────────────────────────

    def get_room(self, project_id: str) -> Room | None:
        """Get a room by project ID."""
        return self.rooms.get(project_id)

    def get_room_users(self, project_id: str) -> list[str]:
        """Get user IDs in a room."""
        room = self.rooms.get(project_id)
        if room is None:
            return []
        return room.user_ids

    def get_room_history(
        self,
        project_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get recent change history for a room."""
        room = self.rooms.get(project_id)
        if room is None:
            return []
        return room.history[-limit:]

    @property
    def room_count(self) -> int:
        """Number of active rooms."""
        return len(self.rooms)

    @property
    def total_users(self) -> int:
        """Total number of connected users across all rooms."""
        return len(self.users)

    # ── Internal Helpers ───────────────────────────────────────────────────

    def _apply_change_to_state(
        self,
        state: dict[str, Any],
        change: dict[str, Any],
    ) -> None:
        """Apply a change to the room state.

        Updates the state dict based on change kind.
        """
        kind = change.get("kind", "")
        track_name = change.get("track", "")

        if kind == "track_add":
            tracks = state.setdefault("tracks", {})
            tracks[track_name] = change.get("track_data", {})
        elif kind == "track_remove":
            tracks = state.get("tracks", {})
            tracks.pop(track_name, None)
        elif kind == "param_change":
            tracks = state.setdefault("tracks", {})
            track_state = tracks.setdefault(track_name, {})
            track_state[change.get("param", "")] = change.get("value")
        elif kind == "effect_add":
            tracks = state.setdefault("tracks", {})
            track_state = tracks.setdefault(track_name, {})
            effects = track_state.setdefault("effects", [])
            effects.append(change.get("effect_data", {}))
        elif kind == "effect_remove":
            tracks = state.get("tracks", {})
            track_state = tracks.get(track_name, {})
            effects = track_state.get("effects", [])
            idx = change.get("effect_index", -1)
            if 0 <= idx < len(effects):
                effects.pop(idx)

    async def _broadcast(
        self,
        project_id: str,
        message: dict[str, Any],
        exclude_user: Optional[str] = None,
    ) -> None:
        """Broadcast a message to all users in a room.

        Args:
            project_id: Target room.
            message: Message to broadcast.
            exclude_user: User ID to exclude (sender).
        """
        room = self.rooms.get(project_id)
        if room is None:
            return

        data = json.dumps(message, ensure_ascii=False, default=str)
        dead_users = []

        for uid, user in room.users.items():
            if uid == exclude_user:
                continue
            if user.websocket is None:
                continue
            try:
                await user.websocket.send_text(data)
            except Exception:
                dead_users.append(uid)

        # Clean up dead connections
        for uid in dead_users:
            room.users.pop(uid, None)
            self.users.pop(uid, None)

    async def _send_to_user(
        self,
        user_id: str,
        message: dict[str, Any],
    ) -> None:
        """Send a message to a specific user."""
        user = self.users.get(user_id)
        if user is None or user.websocket is None:
            return

        data = json.dumps(message, ensure_ascii=False, default=str)
        try:
            await user.websocket.send_text(data)
        except Exception:
            # Clean up dead connection
            pass


# ── Global instance ────────────────────────────────────────────────────────

_collab_manager = CollaborationManager()


def get_collaboration_manager() -> CollaborationManager:
    """Get the global CollaborationManager instance."""
    return _collab_manager
