"""
memory.py — Short-term conversation memory for VCMix Agent (Phase 22a).

Implements a sliding-window memory that keeps the most recent N messages
in full and can produce a text summary of older messages.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _MemoryEntry:
    """Internal representation of a conversation message."""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)


class ShortTermMemory:
    """Sliding-window short-term memory for Agent conversations.

    Keeps at most `max_messages` entries. When the window is full,
    the oldest message is dropped. A simple summary can be generated
    from the current window for context compression.

    Args:
        max_messages: Maximum number of messages to retain. Default 20.
    """

    def __init__(self, max_messages: int = 20) -> None:
        self.max_messages = max_messages
        self._messages: list[_MemoryEntry] = []

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the memory.

        Args:
            role: "system" | "user" | "assistant" | "tool"
            content: Message text content.
        """
        self._messages.append(_MemoryEntry(role=role, content=content))
        # Evict oldest messages beyond the window
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages:]

    def get_messages(self) -> list[dict[str, str]]:
        """Return all messages as a list of dicts for LLM context.

        Returns:
            List of {"role": ..., "content": ...} dicts.
        """
        return [{"role": m.role, "content": m.content} for m in self._messages]

    def clear(self) -> None:
        """Clear all messages from memory."""
        self._messages.clear()

    def get_summary(self) -> str:
        """Generate a brief text summary of the conversation.

        Produces a condensed description of what has been discussed,
        useful for system prompts or context compression.

        Returns:
            A summary string.
        """
        if not self._messages:
            return "No conversation history."

        user_msgs = [m for m in self._messages if m.role == "user"]
        assistant_msgs = [m for m in self._messages if m.role == "assistant"]
        tool_msgs = [m for m in self._messages if m.role == "tool"]

        parts: list[str] = []
        parts.append(f"Conversation: {len(self._messages)} messages")
        parts.append(f"  User turns: {len(user_msgs)}")
        parts.append(f"  Assistant turns: {len(assistant_msgs)}")
        parts.append(f"  Tool calls: {len(tool_msgs)}")

        # Include the last user message as recent context
        if user_msgs:
            last_user = user_msgs[-1].content[:100]
            parts.append(f"  Last user message: {last_user}")

        return "\n".join(parts)

    def __len__(self) -> int:
        return len(self._messages)
