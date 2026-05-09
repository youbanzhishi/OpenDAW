"""
test_enhanced_modelbus.py — Tests for Enhanced ModelBus (Phase 22b).
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enhanced_modelbus import (
    EnhancedModelBus,
    ProviderConfig,
    MessageContext,
)
from model_provider import ProviderType


class TestProviderConfig:
    """Test ProviderConfig dataclass."""
    
    def test_create_config(self):
        """Should create a config."""
        config = ProviderConfig(
            provider_type="openai",
            model_id="gpt-4o",
            api_key="sk-test",
        )
        assert config.provider_type == "openai"
        assert config.model_id == "gpt-4o"
        assert config.api_key == "sk-test"
    
    def test_config_defaults(self):
        """Should have sensible defaults."""
        config = ProviderConfig()
        assert config.provider_type == "openai"
        assert config.model_id == "gpt-4o"
        assert config.temperature == 0.3
        assert config.max_tokens == 4096
        assert config.priority == 100
        assert config.enabled is True
    
    def test_to_dict(self):
        """Should serialize to dict."""
        config = ProviderConfig(
            provider_type="anthropic",
            model_id="claude-3.5-sonnet",
            api_key="sk-ant-secret",
        )
        data = config.to_dict()
        assert data["provider_type"] == "anthropic"
        assert data["model_id"] == "claude-3.5-sonnet"
        # API key should be masked
        assert data["api_key"] == "***"


class TestMessageContext:
    """Test MessageContext dataclass."""
    
    def test_create_empty_context(self):
        """Should create empty context."""
        ctx = MessageContext()
        assert ctx.messages == []
        assert ctx.system_prompt == ""
        assert ctx.metadata == {}
    
    def test_create_with_data(self):
        """Should create with data."""
        ctx = MessageContext(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="You are an assistant.",
            metadata={"project": "test"},
        )
        assert len(ctx.messages) == 1
        assert ctx.system_prompt == "You are an assistant."
        assert ctx.metadata["project"] == "test"
    
    def test_to_dict(self):
        """Should serialize to dict."""
        ctx = MessageContext(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="Test",
        )
        data = ctx.to_dict()
        assert len(data["messages"]) == 1
        assert data["system_prompt"] == "Test"


class TestEnhancedModelBus:
    """Test EnhancedModelBus class."""
    
    @pytest.fixture
    def modelbus(self):
        """Create a ModelBus instance."""
        config = ProviderConfig(
            provider_type="openai",
            model_id="gpt-4o",
            api_key="test-key",
        )
        bus = EnhancedModelBus(config)
        yield bus
    
    def test_initialization(self, modelbus):
        """Should initialize with config."""
        assert modelbus.current_provider == "openai/gpt-4o"
        assert modelbus.context is not None
    
    def test_set_system_prompt(self, modelbus):
        """Should set system prompt."""
        modelbus.set_system_prompt("You are a test assistant.")
        assert modelbus.context.system_prompt == "You are a test assistant."
    
    def test_switch_provider(self, modelbus):
        """Should switch provider."""
        modelbus.switch_provider(ProviderConfig(
            provider_type="anthropic",
            model_id="claude-3.5-sonnet",
            api_key="test-key-2",
        ))
        assert modelbus.current_provider == "anthropic/claude-3.5-sonnet"
    
    def test_context_preserved_on_switch(self, modelbus):
        """Should preserve context when switching."""
        # Add some context
        modelbus.set_system_prompt("Original prompt")
        modelbus.context.messages.append({"role": "user", "content": "Hello"})
        
        # Switch provider
        modelbus.switch_provider(ProviderConfig(
            provider_type="anthropic",
            model_id="claude-3.5-sonnet",
            api_key="test",
        ))
        
        # Context should be preserved
        assert len(modelbus.context.messages) == 1
        assert modelbus.context.messages[0]["content"] == "Hello"
    
    def test_get_conversation_history(self, modelbus):
        """Should get conversation history."""
        modelbus.context.messages.append({"role": "user", "content": "Test"})
        history = modelbus.get_conversation_history()
        assert len(history) == 1
        assert history[0]["content"] == "Test"
    
    def test_clear_context(self, modelbus):
        """Should clear context."""
        modelbus.context.messages.append({"role": "user", "content": "Test"})
        modelbus.set_system_prompt("Prompt")
        
        modelbus.clear_context()
        
        assert len(modelbus.context.messages) == 0
        assert modelbus.context.system_prompt == "Prompt"
    
    def test_get_status(self, modelbus):
        """Should return status dict."""
        status = modelbus.get_status()
        assert "current_provider" in status
        assert "model_info" in status
        assert "context_size" in status
        assert status["current_provider"] == "openai/gpt-4o"
    
    def test_add_fallback(self, modelbus):
        """Should add fallback provider."""
        modelbus.add_fallback(ProviderConfig(
            provider_type="anthropic",
            model_id="claude-3-sonnet",
            priority=50,
        ))
        assert len(modelbus._fallback_providers) == 1
    
    def test_list_providers(self):
        """Should list available providers."""
        providers = EnhancedModelBus.list_providers()
        assert len(providers) > 0
        # Should have provider types
        provider_types = [p["type"] for p in providers]
        assert "openai" in provider_types or "anthropic" in provider_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
