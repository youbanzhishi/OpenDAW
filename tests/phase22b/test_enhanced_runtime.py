"""
test_enhanced_runtime.py — Tests for Enhanced Runtime (Phase 22b).
"""

import os
import sys
import tempfile

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enhanced_modelbus import ProviderConfig
from enhanced_runtime import (
    AgentAction,
    AgentResponse,
    EnhancedAgentRuntime,
    create_runtime,
)
from persona_manager import PersonaManager


class TestAgentResponse:
    """Test AgentResponse dataclass."""

    def test_create_empty_response(self):
        """Should create empty response."""
        response = AgentResponse()
        assert response.message == ""
        assert response.actions == []
        assert response.thinking == ""
        assert response.requires_confirmation is False
        assert response.model_used == ""

    def test_create_with_data(self):
        """Should create with data."""
        action = AgentAction(
            tool="test_tool",
            arguments={"arg": "value"},
            result={"success": True},
        )
        response = AgentResponse(
            message="Test response",
            actions=[action],
            thinking="I am thinking",
            requires_confirmation=True,
            model_used="openai/gpt-4o",
        )
        assert response.message == "Test response"
        assert len(response.actions) == 1
        assert response.actions[0].tool == "test_tool"
        assert response.requires_confirmation is True


class TestEnhancedAgentRuntime:
    """Test EnhancedAgentRuntime class."""

    @pytest.fixture
    def runtime(self):
        """Create a runtime instance."""
        config = ProviderConfig(
            provider_type="openai",
            model_id="gpt-4o",
            api_key="test-key",
        )
        runtime = EnhancedAgentRuntime(provider_config=config)
        yield runtime

    @pytest.fixture
    def runtime_with_persona_manager(self):
        """Create a runtime with temp persona manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PersonaManager(storage_dir=tmpdir)
            config = ProviderConfig(provider_type="openai", model_id="gpt-4o")
            runtime = EnhancedAgentRuntime(
                provider_config=config,
                persona_manager=manager,
            )
            yield runtime

    def test_initialization(self, runtime):
        """Should initialize with config."""
        assert runtime.get_current_model() == "openai/gpt-4o"
        assert runtime._project_id is None

    def test_set_project(self, runtime):
        """Should bind to project."""
        runtime.set_project("test-project")
        assert runtime._project_id == "test-project"

        status = runtime.get_status()
        assert status["project_id"] == "test-project"

    def test_set_persona(self, runtime_with_persona_manager):
        """Should switch persona."""
        runtime = runtime_with_persona_manager

        success = runtime.set_persona("mix-engineer")
        assert success is True

        persona = runtime.get_persona()
        assert persona is not None
        assert persona.id == "mix-engineer"

        status = runtime.get_status()
        assert status["persona"] == "mix-engineer"
        assert status["persona_name"] == "混音工程师"

    def test_set_nonexistent_persona(self, runtime_with_persona_manager):
        """Should return False for nonexistent persona."""
        runtime = runtime_with_persona_manager
        success = runtime.set_persona("nonexistent")
        assert success is False

    def test_switch_model(self, runtime):
        """Should switch model."""
        runtime.switch_model(
            provider_type="anthropic",
            model_id="claude-3.5-sonnet",
            api_key="sk-ant-test",
        )
        assert runtime.get_current_model() == "anthropic/claude-3.5-sonnet"

    def test_context_preserved_after_persona_switch(self, runtime_with_persona_manager):
        """Should preserve context when switching persona."""
        runtime = runtime_with_persona_manager

        # Set initial persona and add context
        runtime.set_persona("mix-engineer")
        runtime._model_bus.context.messages.append({"role": "user", "content": "Hello"})

        # Switch persona
        runtime.set_persona("vocal-expert")

        # Context should be preserved
        assert len(runtime._model_bus.context.messages) == 1
        assert runtime._model_bus.context.messages[0]["content"] == "Hello"

    def test_set_custom_prompt(self, runtime):
        """Should set custom prompt."""
        runtime.set_custom_prompt("You are a custom assistant.")
        assert runtime._custom_prompt == "You are a custom assistant."

        status = runtime.get_status()
        assert status["persona"] == "custom"

    def test_get_status(self, runtime):
        """Should return status dict."""
        status = runtime.get_status()
        assert "model" in status
        assert "persona" in status
        assert "execution_mode" in status
        assert "memory_messages" in status
        assert "context_messages" in status

    def test_clear_conversation(self, runtime):
        """Should clear conversation."""
        runtime._memory.add_message("user", "Test")
        runtime._model_bus.context.messages.append({"role": "user", "content": "Test"})

        runtime.clear_conversation()

        assert len(runtime._memory) == 0
        assert len(runtime._model_bus.context.messages) == 0

    def test_get_available_personas(self, runtime_with_persona_manager):
        """Should list all personas."""
        runtime = runtime_with_persona_manager
        personas = runtime.get_available_personas()
        assert len(personas) > 0

        # Should have built-in personas
        assert any(p["id"] == "mix-engineer" for p in personas)
        assert any(p["id"] == "beginner-coach" for p in personas)

    def test_configure_model_compatibility(self, runtime):
        """Should support Phase 22a compatibility method."""
        runtime.configure_model({
            "provider": "anthropic",
            "model": "claude-3.5-sonnet",
            "api_key": "test",
        })
        assert runtime.get_current_model() == "anthropic/claude-3.5-sonnet"


class TestCreateRuntime:
    """Test the create_runtime convenience function."""

    def test_create_with_defaults(self):
        """Should create with defaults."""
        runtime = create_runtime()
        assert runtime.get_current_model() == "openai/gpt-4o"

    def test_create_with_custom_config(self):
        """Should create with custom config."""
        runtime = create_runtime(
            provider="anthropic",
            model="claude-3.5-sonnet",
            api_key="test-key",
        )
        assert runtime.get_current_model() == "anthropic/claude-3.5-sonnet"

    def test_create_with_persona(self):
        """Should create with persona."""
        with tempfile.TemporaryDirectory() as tmpdir:
            PersonaManager(storage_dir=tmpdir)
            create_runtime(persona="mix-engineer")
            # Note: Persona won't load without proper manager
            # This tests the parameter is accepted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
