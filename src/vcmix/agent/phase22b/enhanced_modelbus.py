"""
enhanced_modelbus.py — Enhanced ModelBus with multi-provider support (Phase 22b).

Features:
- Dynamic provider switching without losing conversation context
- Automatic message format conversion between providers
- Provider health checking and fallback
- Connection pooling and resource management
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from vcmix.agent.phase22b.model_provider import (
    LLMResponse,
    ModelInfo,
    ModelProvider,
    ProviderType,
    create_provider,
    get_available_models,
)

logger = logging.getLogger("vcmix.agent.enhanced_modelbus")


@dataclass
class ProviderConfig:
    """Configuration for a model provider.

    Attributes:
        provider_type: The type of LLM provider.
        model_id: The specific model to use.
        api_key: API key (optional for local providers).
        base_url: Base URL for the API endpoint.
        temperature: Default sampling temperature.
        max_tokens: Default max output tokens.
        priority: Provider priority (lower = higher priority, for fallback).
        enabled: Whether this provider is currently enabled.
    """
    provider_type: ProviderType | str = "openai"
    model_id: str = "gpt-4o"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096
    priority: int = 100
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage."""
        return {
            "provider_type": self.provider_type.value if isinstance(self.provider_type, ProviderType) else self.provider_type,
            "model_id": self.model_id,
            "api_key": "***" if self.api_key else "",
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "priority": self.priority,
            "enabled": self.enabled,
        }


@dataclass
class MessageContext:
    """Conversation context that survives provider switches.

    Attributes:
        messages: The conversation history.
        system_prompt: Current system prompt.
        metadata: Additional metadata (persona, project, etc.).
    """
    messages: list[dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "messages": self.messages,
            "system_prompt": self.system_prompt,
            "metadata": self.metadata,
        }


class EnhancedModelBus:
    """Enhanced ModelBus with multi-provider support and context preservation.

    Key features:
    1. **Multi-Provider**: Support for OpenAI, Anthropic, Ollama, vLLM, etc.
    2. **Dynamic Switching**: Change providers at runtime without losing context.
    3. **Message Normalization**: Convert messages to provider-specific formats.
    4. **Health Checking**: Monitor provider availability.
    5. **Fallback Support**: Automatic fallback to backup providers.

    Usage:
        # Initialize with default provider
        bus = EnhancedModelBus(config=ProviderConfig(
            provider_type="openai",
            model_id="gpt-4o",
            api_key="sk-..."
        ))

        # Chat with context preservation
        response = await bus.chat([{"role": "user", "content": "Hello"}])

        # Switch provider at runtime
        bus.switch_provider(ProviderConfig(
            provider_type="anthropic",
            model_id="claude-3.5-sonnet",
            api_key="sk-ant-..."
        ))

        # Continue conversation with same context
        response = await bus.chat([{"role": "user", "content": "Continue..."}])
    """

    def __init__(self, config: ProviderConfig | None = None) -> None:
        self._current_config = config or ProviderConfig()
        self._provider: ModelProvider | None = None
        self._context = MessageContext()
        self._fallback_providers: list[ProviderConfig] = []

        # Initialize the provider
        self._init_provider()

    def _init_provider(self) -> None:
        """Initialize the current provider from config."""
        self._provider = create_provider(
            provider_type=self._current_config.provider_type,
            model_id=self._current_config.model_id,
            api_key=self._current_config.api_key,
            base_url=self._current_config.base_url or None,
        )
        logger.info("ModelBus initialized with %s/%s",
                   self._current_config.provider_type, self._current_config.model_id)

    @property
    def current_provider(self) -> str:
        """Get current provider info string."""
        return f"{self._current_config.provider_type}/{self._current_config.model_id}"

    @property
    def model_info(self) -> ModelInfo | None:
        """Get current model information."""
        if self._provider:
            return self._provider.model_info
        return None

    @property
    def context(self) -> MessageContext:
        """Get current conversation context."""
        return self._context

    def switch_provider(self, config: ProviderConfig) -> None:
        """Switch to a new provider at runtime.

        The conversation context is preserved. Messages are automatically
        converted to the new provider's format.

        Args:
            config: New provider configuration.
        """
        # Preserve context
        old_system_prompt = self._context.system_prompt
        old_messages = self._context.messages.copy()

        # Close old provider
        if self._provider:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._provider.close())
                else:
                    loop.run_until_complete(self._provider.close())
            except Exception as e:
                logger.warning("Error closing old provider: %s", e)

        # Update config and reinitialize
        self._current_config = config
        self._init_provider()

        # Restore context (system prompt will be updated on next call)
        self._context.system_prompt = old_system_prompt
        self._context.messages = old_messages

        logger.info("Provider switched to %s/%s", config.provider_type, config.model_id)

    def set_system_prompt(self, prompt: str) -> None:
        """Set the system prompt for the conversation.

        Args:
            prompt: The system prompt to use.
        """
        self._context.system_prompt = prompt
        logger.debug("System prompt updated: %s chars", len(prompt))

    def add_fallback(self, config: ProviderConfig) -> None:
        """Add a fallback provider for automatic failover.

        Fallback providers are tried in priority order when the primary fails.

        Args:
            config: Fallback provider configuration.
        """
        self._fallback_providers.append(config)
        self._fallback_providers.sort(key=lambda p: p.priority)

    def clear_fallbacks(self) -> None:
        """Clear all fallback providers."""
        self._fallback_providers.clear()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Send a chat completion request.

        This method:
        1. Updates conversation context
        2. Converts messages to provider-specific format
        3. Sends request to current provider (with fallback on failure)
        4. Updates context with response

        Args:
            messages: List of message dicts (role/content/tool_calls).
            tools: Optional tool definitions.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            system_prompt: Optional system prompt override.

        Returns:
            LLMResponse from the provider.
        """
        if not self._provider:
            raise RuntimeError("No provider initialized")

        # Update system prompt if provided
        if system_prompt:
            self._context.system_prompt = system_prompt

        # Build messages with system prompt
        full_messages = self._prepare_messages(messages)

        # Use config defaults if not overridden
        temp = temperature if temperature is not None else self._current_config.temperature
        tokens = max_tokens if max_tokens is not None else self._current_config.max_tokens

        # Try current provider first
        try:
            response = await self._provider.chat(
                messages=full_messages,
                tools=tools,
                temperature=temp,
                max_tokens=tokens,
            )

            # Update context
            self._update_context(messages, response)

            return response

        except Exception as e:
            logger.warning("Primary provider failed: %s", e)

            # Try fallbacks
            for fallback_config in self._fallback_providers:
                try:
                    logger.info("Trying fallback provider: %s/%s",
                               fallback_config.provider_type, fallback_config.model_id)

                    fallback_provider = create_provider(
                        provider_type=fallback_config.provider_type,
                        model_id=fallback_config.model_id,
                        api_key=fallback_config.api_key,
                        base_url=fallback_config.base_url or None,
                    )

                    response = await fallback_provider.chat(
                        messages=full_messages,
                        tools=tools,
                        temperature=temp,
                        max_tokens=tokens,
                    )

                    await fallback_provider.close()
                    self._update_context(messages, response)

                    return response

                except Exception as fallback_error:
                    logger.warning("Fallback provider %s failed: %s",
                                  fallback_config.model_id, fallback_error)
                    continue

            # All providers failed
            raise RuntimeError(f"All providers failed. Last error: {e}") from e

    def _prepare_messages(self, new_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prepare messages with system prompt for the current provider.

        Args:
            new_messages: New messages from user.

        Returns:
            Full message list ready for API call.
        """
        provider_type = self._current_config.provider_type
        if isinstance(provider_type, str):
            try:
                provider_type = ProviderType(provider_type)
            except ValueError:
                provider_type = ProviderType.OPENAI

        formatted: list[dict[str, Any]] = []

        # System prompt handling varies by provider
        if provider_type == ProviderType.ANTHROPIC:
            # Anthropic: system message goes in dedicated field
            if self._context.system_prompt:
                pass  # System will be extracted in provider
        else:
            # OpenAI/Ollama: system message as first message
            if self._context.system_prompt:
                formatted.append({
                    "role": "system",
                    "content": self._context.system_prompt,
                })

        # Add conversation history from context
        formatted.extend(self._context.messages)

        # Add new messages
        formatted.extend(new_messages)

        return formatted

    def _update_context(self, new_messages: list[dict[str, Any]], response: LLMResponse) -> None:
        """Update conversation context with new exchange.

        Args:
            new_messages: Messages sent to the model.
            response: Response from the model.
        """
        # Add user messages
        for msg in new_messages:
            if msg.get("role") in ("user", "system"):
                self._context.messages.append(msg.copy())

        # Add assistant response
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content,
        }
        if response.tool_calls:
            assistant_msg["tool_calls"] = response.tool_calls
        self._context.messages.append(assistant_msg)

    def get_conversation_history(self) -> list[dict[str, Any]]:
        """Get the current conversation history.

        Returns:
            List of messages in the conversation.
        """
        return self._context.messages.copy()

    def clear_context(self) -> None:
        """Clear conversation context (but keep system prompt)."""
        self._context.messages.clear()
        logger.debug("Conversation context cleared")

    def get_status(self) -> dict[str, Any]:
        """Get current ModelBus status.

        Returns:
            Status dict with provider info, context size, etc.
        """
        return {
            "current_provider": self.current_provider,
            "model_info": {
                "id": self.model_info.id if self.model_info else None,
                "name": self.model_info.name if self.model_info else None,
                "supports_tools": self.model_info.supports_tools if self.model_info else False,
            } if self.model_info else None,
            "context_size": len(self._context.messages),
            "system_prompt_length": len(self._context.system_prompt),
            "fallback_count": len(self._fallback_providers),
            "config": self._current_config.to_dict(),
        }

    async def health_check(self) -> dict[str, Any]:
        """Check health of current provider.

        Returns:
            Health status dict.
        """
        if not self._provider:
            return {"healthy": False, "error": "No provider initialized"}

        try:
            # Simple test: send a minimal request
            await self._provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
            return {
                "healthy": True,
                "provider": self.current_provider,
                "response_time": "ok",
            }
        except Exception as e:
            return {
                "healthy": False,
                "provider": self.current_provider,
                "error": str(e),
            }

    async def close(self) -> None:
        """Close the underlying provider."""
        if self._provider:
            await self._provider.close()
        logger.info("ModelBus closed")

    # ── Static utilities ─────────────────────────────────────────────────

    @staticmethod
    def list_providers() -> list[dict[str, Any]]:
        """List all available providers.

        Returns:
            List of provider info dicts.
        """
        providers = {}
        for model in get_available_models():
            ptype = model.provider.value
            if ptype not in providers:
                providers[ptype] = {
                    "type": ptype,
                    "models": [],
                }
            providers[ptype]["models"].append({
                "id": model.id,
                "name": model.name,
                "context_window": model.context_window,
                "supports_tools": model.supports_tools,
                "supports_vision": model.supports_vision,
            })
        return list(providers.values())
