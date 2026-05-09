"""
test_model_provider.py — Tests for Model Provider system (Phase 22b).
"""

import os
import sys

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model_provider import (
    MODEL_REGISTRY,
    AnthropicProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderType,
    create_provider,
    get_available_models,
)


class TestModelRegistry:
    """Test the model registry."""

    def test_registry_has_models(self):
        """Registry should have models."""
        assert len(MODEL_REGISTRY) > 0

    def test_registry_has_openai_models(self):
        """Registry should have OpenAI models."""
        openai_models = [m for m in MODEL_REGISTRY.values() if m.provider == ProviderType.OPENAI]
        assert len(openai_models) > 0
        assert any("gpt-4o" in m.id for m in openai_models)

    def test_registry_has_anthropic_models(self):
        """Registry should have Anthropic models."""
        anthropic_models = [m for m in MODEL_REGISTRY.values() if m.provider == ProviderType.ANTHROPIC]
        assert len(anthropic_models) > 0
        assert any("claude" in m.id for m in anthropic_models)

    def test_registry_has_ollama_models(self):
        """Registry should have Ollama models."""
        ollama_models = [m for m in MODEL_REGISTRY.values() if m.provider == ProviderType.OLLAMA]
        assert len(ollama_models) > 0

    def test_model_info_attributes(self):
        """ModelInfo should have required attributes."""
        model = MODEL_REGISTRY["gpt-4o"]
        assert model.id == "gpt-4o"
        assert model.name == "GPT-4o"
        assert model.provider == ProviderType.OPENAI
        assert model.context_window > 0
        assert model.supports_tools is True
        assert model.supports_vision is True


class TestProviderFactory:
    """Test the provider factory function."""

    def test_create_openai_provider(self):
        """Should create OpenAI provider."""
        provider = create_provider("openai", "gpt-4o", api_key="test-key")
        assert isinstance(provider, OpenAIProvider)
        assert provider.model_id == "gpt-4o"

    def test_create_anthropic_provider(self):
        """Should create Anthropic provider."""
        provider = create_provider("anthropic", "claude-3.5-sonnet", api_key="test-key")
        assert isinstance(provider, AnthropicProvider)
        assert provider.model_id == "claude-3.5-sonnet"

    def test_create_ollama_provider(self):
        """Should create Ollama provider."""
        provider = create_provider("ollama", "llama3.3:70b")
        assert isinstance(provider, OllamaProvider)
        assert provider.model_id == "llama3.3:70b"

    def test_create_with_provider_type_enum(self):
        """Should accept ProviderType enum."""
        provider = create_provider(ProviderType.OPENAI, "gpt-4o-mini", api_key="test")
        assert isinstance(provider, OpenAIProvider)

    def test_auto_detect_claude(self):
        """Should auto-detect Claude provider from model name."""
        provider = create_provider("custom", "claude-3.5-sonnet", api_key="test")
        assert isinstance(provider, AnthropicProvider)


class TestGetAvailableModels:
    """Test the get_available_models function."""

    def test_get_all_models(self):
        """Should return all models."""
        models = get_available_models()
        assert len(models) == len(MODEL_REGISTRY)

    def test_filter_by_provider(self):
        """Should filter by provider type."""
        openai_models = get_available_models(ProviderType.OPENAI)
        assert all(m.provider == ProviderType.OPENAI for m in openai_models)

        anthropic_models = get_available_models(ProviderType.ANTHROPIC)
        assert all(m.provider == ProviderType.ANTHROPIC for m in anthropic_models)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
