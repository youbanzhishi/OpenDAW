"""
modelbus.py — Unified LLM client for VCMix AgentPlugin (Phase 22a).

All LLM backends are accessed through the OpenAI SDK-compatible interface,
which is the de-facto standard supported by virtually every provider:
OpenAI, Anthropic (via compatibility layer), Ollama, vLLM, etc.

Usage:
    config = ModelConfig(provider="openai", model="gpt-4o", api_key="sk-...")
    bus = ModelBus(config)
    response = await bus.chat([{"role": "user", "content": "Hello"}])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("vcmix.agent.modelbus")


@dataclass
class ModelConfig:
    """Configuration for a single LLM backend."""

    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    temperature: float = 0.3
    max_tokens: int = 2048

    # Well-known provider defaults
    PROVIDER_DEFAULTS: dict[str, dict[str, str]] = field(default_factory=lambda: {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "models": "gpt-4o,gpt-4o-mini,gpt-4-turbo",
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "models": "claude-3.5-sonnet,claude-3-opus",
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "models": "llama3.3:70b,qwen2.5:72b,deepseek-r1",
        },
        "vllm": {
            "base_url": "http://localhost:8000/v1",
            "models": "custom-mix-engine-v1",
        },
    }, repr=False)

    def apply_provider_defaults(self) -> "ModelConfig":
        """Fill in default base_url if not explicitly set."""
        defaults = self.PROVIDER_DEFAULTS.get(self.provider)
        if defaults and self.base_url == "https://api.openai.com/v1" and self.provider != "openai":
            self.base_url = defaults["base_url"]
        return self


@dataclass
class Message:
    """A single chat message."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible message dict."""
        d: dict[str, Any] = {"role": self.role}
        if self.content:
            d["content"] = self.content
        if self.tool_calls is not None:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        # Tool role must have tool_call_id
        if self.role == "tool" and self.tool_call_id:
            d["content"] = self.content or ""
        return d


class ModelBus:
    """Unified LLM client using OpenAI SDK-compatible chat completions API.

    Uses httpx to call the /chat/completions endpoint directly,
    supporting both cloud LLMs and local models (Ollama, vLLM).
    """

    def __init__(self, config: ModelConfig) -> None:
        self.config = config.apply_provider_defaults()
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request.

        Args:
            messages: List of message dicts (role/content/tool_calls/tool_call_id).
            tools: Optional list of tool definitions in OpenAI function-calling format.
            temperature: Override config temperature.
            max_tokens: Override config max_tokens.

        Returns:
            Raw response dict from the API, with at least:
              - choices[0].message.content
              - choices[0].message.tool_calls (if the model wants to call tools)
        """
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]

        logger.debug("ModelBus.chat: model=%s, msgs=%d, tools=%d",
                     self.config.model, len(messages), len(tools or []))

        try:
            resp = await self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data
        except httpx.HTTPStatusError as e:
            logger.error("LLM API error: %s %s", e.response.status_code, e.response.text[:500])
            raise RuntimeError(
                f"LLM API error {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.RequestError as e:
            logger.error("LLM request failed: %s", e)
            raise RuntimeError(f"LLM request failed: {e}") from e

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    def extract_assistant_message(self, response: dict[str, Any]) -> Message:
        """Extract the assistant message from a chat completion response.

        Returns a Message with content and optional tool_calls.
        """
        choice = response.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""
        raw_tool_calls = msg.get("tool_calls")

        parsed_tool_calls = None
        if raw_tool_calls:
            parsed_tool_calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                parsed_tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", "{}"),
                })

        return Message(
            role="assistant",
            content=content,
            tool_calls=parsed_tool_calls,
        )
