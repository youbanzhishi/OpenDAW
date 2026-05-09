"""
model_provider.py — Unified Model Provider interface (Phase 22b).

Defines the ModelProvider trait/class hierarchy for multiple LLM backends:
- OpenAIProvider: GPT-4o, GPT-4o-mini, GPT-4-turbo
- AnthropicProvider: Claude-3.5-Sonnet, Claude-3-Opus (native API)
- OllamaProvider: Local models (llama3.3, qwen2.5, deepseek-r1)
- vLLMProvider: Custom vLLM clusters
- AzureProvider: Azure OpenAI

Each provider implements a common interface, enabling runtime switching
without losing conversation context.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger("vcmix.agent.model_provider")


class ProviderType(Enum):
    """Supported LLM provider types."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    VLLM = "vllm"
    AZURE = "azure"
    CUSTOM = "custom"


@dataclass
class ModelInfo:
    """Information about a specific model."""
    id: str  # Provider-specific model ID (e.g., "gpt-4o", "claude-3.5-sonnet")
    name: str  # Display name
    provider: ProviderType
    context_window: int = 128_000  # Token context window
    supports_tools: bool = True  # Whether it supports function calling
    supports_vision: bool = False
    max_output_tokens: int = 4096
    description: str = ""


# ── Model Registry ────────────────────────────────────────────────────────

MODEL_REGISTRY: dict[str, ModelInfo] = {
    # OpenAI models
    "gpt-4o": ModelInfo("gpt-4o", "GPT-4o", ProviderType.OPENAI,
                        context_window=128_000, supports_tools=True, supports_vision=True,
                        max_output_tokens=4096, description="Most capable, multimodal"),
    "gpt-4o-mini": ModelInfo("gpt-4o-mini", "GPT-4o Mini", ProviderType.OPENAI,
                              context_window=128_000, supports_tools=True, supports_vision=True,
                              max_output_tokens=16_384, description="Fast, affordable"),
    "gpt-4-turbo": ModelInfo("gpt-4-turbo", "GPT-4 Turbo", ProviderType.OPENAI,
                             context_window=128_000, supports_tools=True,
                             max_output_tokens=4096, description="Previous generation flagship"),

    # Anthropic models
    "claude-3.5-sonnet": ModelInfo("claude-3.5-sonnet-latest", "Claude 3.5 Sonnet", ProviderType.ANTHROPIC,
                                    context_window=200_000, supports_tools=True, supports_vision=True,
                                    max_output_tokens=8192, description="Best balance of capability and speed"),
    "claude-3-opus": ModelInfo("claude-3-opus-latest", "Claude 3 Opus", ProviderType.ANTHROPIC,
                                context_window=200_000, supports_tools=True, supports_vision=True,
                                max_output_tokens=4096, description="Highest capability, slower"),
    "claude-3-sonnet": ModelInfo("claude-3-sonnet-latest", "Claude 3 Sonnet", ProviderType.ANTHROPIC,
                                  context_window=200_000, supports_tools=True, supports_vision=True,
                                  max_output_tokens=4096, description="Balanced capability"),

    # Ollama models (local)
    "llama3.3:70b": ModelInfo("llama3.3:70b", "Llama 3.3 70B", ProviderType.OLLAMA,
                              context_window=128_000, supports_tools=True,
                              max_output_tokens=4096, description="Meta's latest open model"),
    "qwen2.5:72b": ModelInfo("qwen2.5:72b", "Qwen 2.5 72B", ProviderType.OLLAMA,
                             context_window=128_000, supports_tools=True,
                             max_output_tokens=4096, description="Alibaba's capable open model"),
    "deepseek-r1:70b": ModelInfo("deepseek-r1:70b", "DeepSeek R1 70B", ProviderType.OLLAMA,
                                  context_window=128_000, supports_tools=True,
                                  max_output_tokens=8192, description="DeepSeek's reasoning model"),

    # vLLM models
    "custom-mix-v1": ModelInfo("custom-mix-v1", "Custom Mix v1", ProviderType.VLLM,
                              context_window=128_000, supports_tools=True,
                              max_output_tokens=4096, description="Custom vLLM deployment"),
}


# ── Provider Interface ────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)  # prompt_tokens, completion_tokens, total_tokens

    @property
    def has_tool_calls(self) -> bool:
        return self.tool_calls is not None and len(self.tool_calls) > 0


class ModelProvider(ABC):
    """Abstract base class for all LLM providers.

    Each provider implements chat completion for its specific API.
    All providers return standardized LLMResponse objects.
    """

    def __init__(self, model_id: str, **kwargs: Any) -> None:
        self.model_id = model_id
        self.model_info = MODEL_REGISTRY.get(model_id, ModelInfo(
            id=model_id, name=model_id, provider=ProviderType.CUSTOM
        ))

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with role/content.
            tools: Optional tool definitions.
            temperature: Sampling temperature.
            max_tokens: Max output tokens (None = model default).

        Returns:
            LLMResponse with standardized structure.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close underlying HTTP client."""
        ...

    def supports_tools(self) -> bool:
        """Check if this provider/model supports function calling."""
        return self.model_info.supports_tools


# ── OpenAI Provider ──────────────────────────────────────────────────────

class OpenAIProvider(ModelProvider):
    """OpenAI API provider (also compatible with OpenAI-compatible APIs)."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        model_id: str = "gpt-4o",
        api_key: str = "",
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_id)
        self.api_key = api_key or "dummy"
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self.model_info.max_output_tokens,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        try:
            resp = await self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data)
        except httpx.HTTPStatusError as e:
            logger.error("OpenAI API error: %s %s", e.response.status_code, e.response.text[:500])
            raise RuntimeError(f"OpenAI API error {e.response.status_code}: {e.response.text[:200]}") from e
        except httpx.RequestError as e:
            logger.error("OpenAI request failed: %s", e)
            raise RuntimeError(f"OpenAI request failed: {e}") from e

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""

        tool_calls = None
        raw_tcs = msg.get("tool_calls")
        if raw_tcs:
            tool_calls = []
            for tc in raw_tcs:
                fn = tc.get("function", {})
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", "{}"),
                })

        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw_response=data,
            model=data.get("model", self.model_id),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        )

    async def close(self) -> None:
        await self._client.aclose()


# ── Anthropic Provider ────────────────────────────────────────────────────

class AnthropicProvider(ModelProvider):
    """Anthropic Claude API provider (native API, not OpenAI-compatible)."""

    ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(
        self,
        model_id: str = "claude-3.5-sonnet",
        api_key: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(model_id)
        self.api_key = api_key or "dummy"
        self._client = httpx.AsyncClient(
            base_url="https://api.anthropic.com/v1",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=60.0,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        # Convert OpenAI message format to Anthropic format
        system_msg = ""
        chat_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                system_msg = content
            elif role == "user":
                chat_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                chat_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                # Tool results become user messages with tool_use_id
                tool_call_id = msg.get("tool_call_id", "")
                chat_messages.append({
                    "role": "user",
                    "content": f"<tool_result id=\"{tool_call_id}\">{content}</tool_result>",
                })

        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self.model_info.max_output_tokens,
        }
        if system_msg:
            payload["system"] = system_msg

        # Convert tools to Anthropic format
        if tools:
            payload["tools"] = [
                {
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]

        try:
            resp = await self._client.post("/messages", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data)
        except httpx.HTTPStatusError as e:
            logger.error("Anthropic API error: %s %s", e.response.status_code, e.response.text[:500])
            raise RuntimeError(f"Anthropic API error {e.response.status_code}: {e.response.text[:200]}") from e
        except httpx.RequestError as e:
            logger.error("Anthropic request failed: %s", e)
            raise RuntimeError(f"Anthropic request failed: {e}") from e

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        content_blocks = data.get("content", [])

        # Find text content
        text_content = ""
        tool_calls = None

        for block in content_blocks:
            if block.get("type") == "text":
                text_content = block.get("text", "")
            elif block.get("type") == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                })

        usage = data.get("usage", {})
        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls,
            raw_response=data,
            model=data.get("model", self.model_id),
            usage={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
        )

    async def close(self) -> None:
        await self._client.aclose()


# ── Ollama Provider ───────────────────────────────────────────────────────

class OllamaProvider(ModelProvider):
    """Ollama local LLM provider (OpenAI-compatible API)."""

    def __init__(
        self,
        model_id: str = "llama3.3:70b",
        base_url: str = "http://localhost:11434/v1",
        **kwargs: Any,
    ) -> None:
        super().__init__(model_id)
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Content-Type": "application/json"},
            timeout=120.0,  # Local models need longer timeout
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        try:
            resp = await self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_response(data)
        except httpx.HTTPStatusError as e:
            logger.error("Ollama API error: %s %s", e.response.status_code, e.response.text[:500])
            raise RuntimeError(f"Ollama API error {e.response.status_code}: {e.response.text[:200]}") from e
        except httpx.RequestError as e:
            logger.error("Ollama request failed: %s", e)
            raise RuntimeError(f"Ollama request failed: {e}") from e

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        msg = data.get("message", {})
        content = msg.get("content", "") or ""

        tool_calls = None
        raw_tcs = msg.get("tool_calls")
        if raw_tcs:
            tool_calls = []
            for tc in raw_tcs:
                fn = tc.get("function", {})
                tool_calls.append({
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", "{}"),
                })

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw_response=data,
            model=data.get("model", self.model_id),
        )

    async def close(self) -> None:
        await self._client.aclose()


# ── Provider Factory ─────────────────────────────────────────────────────

def create_provider(provider_type: ProviderType | str, model_id: str, **kwargs: Any) -> ModelProvider:
    """Factory function to create a provider instance.

    Args:
        provider_type: Provider type (ProviderType enum or string).
        model_id: Model identifier (e.g., "gpt-4o", "claude-3.5-sonnet").
        **kwargs: Additional provider-specific arguments (api_key, base_url, etc.).

    Returns:
        ModelProvider instance.
    """
    if isinstance(provider_type, str):
        try:
            provider_type = ProviderType(provider_type)
        except ValueError:
            provider_type = ProviderType.CUSTOM

    # Auto-detect provider from model_id if not specified
    if provider_type == ProviderType.CUSTOM:
        if "claude" in model_id.lower():
            provider_type = ProviderType.ANTHROPIC
        elif model_id in MODEL_REGISTRY:
            provider_type = MODEL_REGISTRY[model_id].provider

    if provider_type in (ProviderType.OPENAI, ProviderType.AZURE, ProviderType.CUSTOM):
        return OpenAIProvider(model_id=model_id, **kwargs)
    elif provider_type == ProviderType.ANTHROPIC:
        return AnthropicProvider(model_id=model_id, **kwargs)
    elif provider_type == ProviderType.OLLAMA:
            return OllamaProvider(model_id=model_id, **kwargs)
    elif provider_type == ProviderType.VLLM:
            # vLLM uses OpenAI-compatible API
            return OpenAIProvider(model_id=model_id, **kwargs)
    else:
        raise ValueError(f"Unsupported provider type: {provider_type}")


def get_available_models(provider_type: ProviderType | None = None) -> list[ModelInfo]:
    """Get list of available models, optionally filtered by provider.

    Args:
        provider_type: Optional filter for specific provider.

    Returns:
        List of ModelInfo objects.
    """
    if provider_type:
        return [m for m in MODEL_REGISTRY.values() if m.provider == provider_type]
    return list(MODEL_REGISTRY.values())
