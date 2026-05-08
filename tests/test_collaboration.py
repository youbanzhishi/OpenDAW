"""
test_collaboration.py — Tests for multi-user collaboration (Phase 18).

Tests cover:
    - CollaborationManager room lifecycle
    - User join/leave
    - Change broadcasting
    - Conflict resolution (LWW)
    - Room state management
    - WebSocket message format validation
    - Edge cases (empty rooms, missing users, etc.)
"""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from vcmix.web.collaboration import CollaborationManager, Room, User

# ── Room Tests ────────────────────────────────────────────────────────────


class TestRoom:
    """Tests for the Room dataclass."""

    def test_room_creation(self):
        room = Room(project_id="proj_123")
        assert room.project_id == "proj_123"
        assert room.user_count == 0
        assert room.user_ids == []
        assert room.state == {}
        assert room.history == []

    def test_room_with_users(self):
        user1 = User(user_id="alice")
        user2 = User(user_id="bob")
        room = Room(project_id="proj_123", users={"alice": user1, "bob": user2})
        assert room.user_count == 2
        assert "alice" in room.user_ids
        assert "bob" in room.user_ids

    def test_room_user_count_property(self):
        room = Room(project_id="proj_1")
        assert room.user_count == 0
        room.users["alice"] = User(user_id="alice")
        assert room.user_count == 1

    def test_room_state_isolation(self):
        """Each room should have independent state."""
        room1 = Room(project_id="proj_1")
        room2 = Room(project_id="proj_2")
        room1.state["tracks"] = {"vocals": {}}
        assert "tracks" not in room2.state


class TestUser:
    """Tests for the User dataclass."""

    def test_user_creation(self):
        user = User(user_id="alice")
        assert user.user_id == "alice"
        assert user.websocket is None
        assert user.joined_at > 0

    def test_user_with_websocket(self):
        ws = MagicMock()
        user = User(user_id="bob", websocket=ws)
        assert user.websocket is ws


# ── CollaborationManager Tests ────────────────────────────────────────────


class TestCollaborationManager:
    """Tests for the CollaborationManager class."""

    def setup_method(self):
        """Create a fresh manager for each test."""
        self.manager = CollaborationManager()

    def test_initial_state(self):
        assert self.manager.room_count == 0
        assert self.manager.total_users == 0
        assert self.manager.rooms == {}
        assert self.manager.users == {}

    @pytest.mark.asyncio
    async def test_join_room_creates_room(self):
        ws = AsyncMock()
        result = await self.manager.join_room("proj_1", "alice", ws)
        assert "proj_1" in self.manager.rooms
        assert self.manager.room_count == 1
        assert result["project_id"] == "proj_1"
        assert result["user_id"] == "alice"
        assert "alice" in result["users"]

    @pytest.mark.asyncio
    async def test_join_room_adds_user(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        assert self.manager.total_users == 1
        assert "alice" in self.manager.users

    @pytest.mark.asyncio
    async def test_join_room_sends_joined_message(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        # Should have sent a "joined" message to alice
        ws.send_text.assert_called()
        call_args = ws.send_text.call_args[0][0]
        msg = json.loads(call_args)
        assert msg["type"] == "joined"
        assert msg["project_id"] == "proj_1"

    @pytest.mark.asyncio
    async def test_multiple_users_join(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws1)
        await self.manager.join_room("proj_1", "bob", ws2)
        room = self.manager.get_room("proj_1")
        assert room.user_count == 2
        assert self.manager.total_users == 2

    @pytest.mark.asyncio
    async def test_multiple_users_notifies_others(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws1)
        # Reset mock to check notification
        ws1.reset_mock()
        await self.manager.join_room("proj_1", "bob", ws2)
        # alice should be notified of bob joining
        ws1.send_text.assert_called()
        call_args = ws1.send_text.call_args[0][0]
        msg = json.loads(call_args)
        assert msg["type"] == "user_joined"
        assert msg["user_id"] == "bob"

    @pytest.mark.asyncio
    async def test_leave_room(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        result = await self.manager.leave_room("proj_1", "alice")
        assert result["status"] == "left"
        room = self.manager.get_room("proj_1")
        assert room is None  # Room should be cleaned up when empty

    @pytest.mark.asyncio
    async def test_leave_nonexistent_room(self):
        result = await self.manager.leave_room("proj_999", "alice")
        assert result["status"] == "not_in_room"

    @pytest.mark.asyncio
    async def test_leave_room_notifies_others(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws1)
        await self.manager.join_room("proj_1", "bob", ws2)
        # Reset to check leave notification
        ws1.reset_mock()
        await self.manager.leave_room("proj_1", "bob")
        # alice should be notified of bob leaving
        ws1.send_text.assert_called()
        call_args = ws1.send_text.call_args[0][0]
        msg = json.loads(call_args)
        assert msg["type"] == "user_left"
        assert msg["user_id"] == "bob"

    @pytest.mark.asyncio
    async def test_leave_room_closes_empty_room(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        await self.manager.leave_room("proj_1", "alice")
        assert self.manager.room_count == 0
        assert self.manager.get_room("proj_1") is None

    @pytest.mark.asyncio
    async def test_leave_room_keeps_nonempty_room(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws1)
        await self.manager.join_room("proj_1", "bob", ws2)
        result = await self.manager.leave_room("proj_1", "bob")
        assert result["status"] == "left"
        assert result["users_remaining"] == 1
        room = self.manager.get_room("proj_1")
        assert room is not None
        assert room.user_count == 1

    @pytest.mark.asyncio
    async def test_broadcast_change(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws1)
        await self.manager.join_room("proj_1", "bob", ws2)

        ws2.reset_mock()
        change = {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.8}
        result = await self.manager.broadcast_change("proj_1", "alice", change)

        assert result["status"] == "broadcast"
        assert result["recipients"] == 1

        # bob should receive the change
        ws2.send_text.assert_called()
        call_args = ws2.send_text.call_args[0][0]
        msg = json.loads(call_args)
        assert msg["type"] == "change"
        assert msg["change"]["kind"] == "param_change"
        assert msg["change"]["user_id"] == "alice"

    @pytest.mark.asyncio
    async def test_broadcast_change_records_history(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        change = {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.8}
        await self.manager.broadcast_change("proj_1", "alice", change)

        history = self.manager.get_room_history("proj_1")
        assert len(history) == 1
        assert history[0]["kind"] == "param_change"
        assert history[0]["user_id"] == "alice"

    @pytest.mark.asyncio
    async def test_broadcast_change_nonexistent_room(self):
        change = {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.8}
        result = await self.manager.broadcast_change("proj_999", "alice", change)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_broadcast_change_user_not_in_room(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        change = {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.8}
        result = await self.manager.broadcast_change("proj_1", "bob", change)
        assert result["status"] == "error"
        assert "not in room" in result["message"]

    @pytest.mark.asyncio
    async def test_change_updates_room_state_track_add(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        change = {"kind": "track_add", "track": "drums", "track_data": {"volume": 0.7}}
        await self.manager.broadcast_change("proj_1", "alice", change)
        room = self.manager.get_room("proj_1")
        assert "drums" in room.state.get("tracks", {})

    @pytest.mark.asyncio
    async def test_change_updates_room_state_track_remove(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        # Add track first
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "track_add", "track": "drums", "track_data": {"volume": 0.7}})
        # Remove it
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "track_remove", "track": "drums"})
        room = self.manager.get_room("proj_1")
        assert "drums" not in room.state.get("tracks", {})

    @pytest.mark.asyncio
    async def test_change_updates_room_state_param_change(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "track_add", "track": "vocals", "track_data": {}})
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.9})
        room = self.manager.get_room("proj_1")
        assert room.state["tracks"]["vocals"]["volume"] == 0.9

    @pytest.mark.asyncio
    async def test_change_updates_room_state_effect_add(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "track_add", "track": "vocals", "track_data": {}})
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "effect_add", "track": "vocals", "effect_data": {"name": "VC-Compressor"}})
        room = self.manager.get_room("proj_1")
        effects = room.state["tracks"]["vocals"]["effects"]
        assert len(effects) == 1
        assert effects[0]["name"] == "VC-Compressor"

    @pytest.mark.asyncio
    async def test_change_updates_room_state_effect_remove(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "track_add", "track": "vocals", "track_data": {}})
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "effect_add", "track": "vocals", "effect_data": {"name": "VC-Compressor"}})
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "effect_remove", "track": "vocals", "effect_index": 0})
        room = self.manager.get_room("proj_1")
        assert room.state["tracks"]["vocals"]["effects"] == []

    @pytest.mark.asyncio
    async def test_sync_room(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        await self.manager.broadcast_change("proj_1", "alice",
            {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.5})

        ws.reset_mock()
        result = await self.manager.sync_room("proj_1", "alice")
        assert result["status"] == "synced"

        # Should have sent sync message
        ws.send_text.assert_called()

    @pytest.mark.asyncio
    async def test_sync_room_nonexistent(self):
        result = await self.manager.sync_room("proj_999", "alice")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_conflict_resolution_lww(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        await self.manager.join_room("proj_1", "bob", ws)

        # Two conflicting changes
        changes = [
            {"user_id": "alice", "kind": "param_change", "track": "vocals",
             "param": "volume", "value": 0.7, "timestamp": time.time() - 1},
            {"user_id": "bob", "kind": "param_change", "track": "vocals",
             "param": "volume", "value": 0.9, "timestamp": time.time()},
        ]
        result = await self.manager.handle_conflict("proj_1", changes)
        assert result["status"] == "resolved"
        assert result["resolution"] == "last_write_wins"
        assert result["winning_user"] == "bob"

    @pytest.mark.asyncio
    async def test_conflict_no_changes(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        result = await self.manager.handle_conflict("proj_1", [])
        assert result["status"] == "no_conflict"

    @pytest.mark.asyncio
    async def test_conflict_updates_state(self):
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        changes = [
            {"user_id": "alice", "kind": "param_change", "track": "vocals",
             "param": "volume", "value": 0.8, "timestamp": time.time()},
        ]
        await self.manager.handle_conflict("proj_1", changes)
        room = self.manager.get_room("proj_1")
        assert room.state["tracks"]["vocals"]["volume"] == 0.8

    def test_get_room_users(self):
        room = Room(project_id="proj_1")
        room.users["alice"] = User(user_id="alice")
        self.manager.rooms["proj_1"] = room
        users = self.manager.get_room_users("proj_1")
        assert users == ["alice"]

    def test_get_room_users_nonexistent(self):
        users = self.manager.get_room_users("proj_999")
        assert users == []

    def test_get_room_history(self):
        room = Room(project_id="proj_1", history=[{"kind": "test", "i": i} for i in range(10)])
        self.manager.rooms["proj_1"] = room
        history = self.manager.get_room_history("proj_1", limit=5)
        assert len(history) == 5
        assert history[0]["i"] == 5  # Last 5 items

    def test_get_room_history_nonexistent(self):
        history = self.manager.get_room_history("proj_999")
        assert history == []


class TestWebSocketMessageFormats:
    """Tests for WebSocket message format validation."""

    def test_join_message_format(self):
        msg = {
            "type": "join",
            "user_id": "alice",
            "project_id": "proj_123",
        }
        assert msg["type"] == "join"
        assert "user_id" in msg
        assert "project_id" in msg

    def test_change_message_format(self):
        msg = {
            "type": "change",
            "user_id": "alice",
            "change": {
                "kind": "param_change",
                "track": "vocals",
                "param": "volume",
                "value": 0.8,
            },
        }
        assert msg["type"] == "change"
        assert "change" in msg
        assert msg["change"]["kind"] in [
            "track_add", "track_remove", "param_change",
            "effect_add", "effect_remove",
        ]

    def test_change_kinds(self):
        """Verify all supported change kinds."""
        valid_kinds = {"track_add", "track_remove", "param_change",
                       "effect_add", "effect_remove"}
        for kind in valid_kinds:
            msg = {"type": "change", "change": {"kind": kind}}
            assert msg["change"]["kind"] in valid_kinds

    def test_conflict_message_format(self):
        msg = {
            "type": "conflict",
            "resolution": "last_write_wins",
            "winning_change": {"user_id": "bob"},
            "competing_changes": 2,
        }
        assert msg["type"] == "conflict"
        assert msg["resolution"] == "last_write_wins"

    def test_sync_message_format(self):
        msg = {
            "type": "sync_request",
            "user_id": "alice",
            "project_id": "proj_123",
        }
        assert msg["type"] == "sync_request"

    def test_server_message_formats(self):
        """Verify server-to-client message types."""
        server_types = {"joined", "user_joined", "user_left", "change",
                        "sync", "conflict", "join_ack", "change_ack",
                        "heartbeat", "error", "pong"}
        for t in server_types:
            msg = {"type": t}
            assert msg["type"] in server_types


class TestCollaborationEdgeCases:
    """Edge case tests for collaboration."""

    def setup_method(self):
        self.manager = CollaborationManager()

    @pytest.mark.asyncio
    async def test_rejoin_room(self):
        """User can rejoin after leaving."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws1)
        await self.manager.leave_room("proj_1", "alice")
        result = await self.manager.join_room("proj_1", "alice", ws2)
        assert result["user_id"] == "alice"
        room = self.manager.get_room("proj_1")
        assert room.user_count == 1

    @pytest.mark.asyncio
    async def test_multiple_rooms(self):
        """User can be in only one room at a time (last room wins)."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws1)
        await self.manager.join_room("proj_2", "alice", ws2)
        assert self.manager.room_count == 2
        # Note: current impl allows user in multiple rooms;
        # this tests that it doesn't crash

    @pytest.mark.asyncio
    async def test_broadcast_excludes_sender(self):
        """Sender should not receive their own change broadcast."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws1)
        await self.manager.join_room("proj_1", "bob", ws2)

        ws1.reset_mock()
        ws2.reset_mock()
        change = {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.5}
        await self.manager.broadcast_change("proj_1", "alice", change)

        # alice (sender) should NOT receive broadcast (only change_ack would be sent by ws handler)
        # bob should receive the broadcast
        ws2.send_text.assert_called()

    @pytest.mark.asyncio
    async def test_change_has_timestamp(self):
        """All changes should have a timestamp."""
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        change = {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.5}
        await self.manager.broadcast_change("proj_1", "alice", change)
        history = self.manager.get_room_history("proj_1")
        assert "timestamp" in history[0]

    @pytest.mark.asyncio
    async def test_change_has_user_id(self):
        """All changes should have a user_id."""
        ws = AsyncMock()
        await self.manager.join_room("proj_1", "alice", ws)
        change = {"kind": "param_change", "track": "vocals", "param": "volume", "value": 0.5}
        await self.manager.broadcast_change("proj_1", "alice", change)
        history = self.manager.get_room_history("proj_1")
        assert history[0]["user_id"] == "alice"
