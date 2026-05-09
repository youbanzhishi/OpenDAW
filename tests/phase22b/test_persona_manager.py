"""
test_persona_manager.py — Tests for Persona Manager (Phase 22b).
"""

import tempfile
from pathlib import Path

import pytest

# Add parent directory to path
from vcmix.agent.phase22b.persona_manager import (
    Persona,
    PersonaManager,
    get_persona_manager,
)


class TestPersona:
    """Test the Persona class."""

    def test_create_persona(self):
        """Should create a persona."""
        persona = Persona(
            id="test",
            name="Test Persona",
            description="A test persona",
            system_prompt="You are a test.",
        )
        assert persona.id == "test"
        assert persona.name == "Test Persona"
        assert persona.is_builtin is False

    def test_get_system_prompt(self):
        """Should return system prompt."""
        persona = Persona(
            id="test",
            name="Test",
            description="Test",
            system_prompt="You are a test assistant.",
        )
        assert persona.get_system_prompt() == "You are a test assistant."

    def test_get_system_prompt_with_context(self):
        """Should include context in system prompt."""
        persona = Persona(
            id="test",
            name="Test",
            description="Test",
            system_prompt="You are a test assistant.",
        )
        prompt = persona.get_system_prompt({"project_id": "my-project"})
        assert "my-project" in prompt
        assert "You are a test assistant." in prompt

    def test_serialize_to_dict(self):
        """Should serialize to dict."""
        persona = Persona(
            id="test",
            name="Test",
            description="Test",
            system_prompt="Test prompt",
            execution_mode="confirm",
        )
        data = persona.to_dict()
        assert data["id"] == "test"
        assert data["name"] == "Test"
        assert data["execution_mode"] == "confirm"
        assert data["is_builtin"] is False

    def test_deserialize_from_dict(self):
        """Should deserialize from dict."""
        data = {
            "id": "test",
            "name": "Test",
            "description": "Test",
            "system_prompt": "Test prompt",
            "execution_mode": "auto",
            "is_builtin": False,
        }
        persona = Persona.from_dict(data)
        assert persona.id == "test"
        assert persona.name == "Test"
        assert persona.execution_mode == "auto"


class TestPersonaManager:
    """Test the PersonaManager class."""

    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_storage):
        """Create a PersonaManager with temp storage."""
        return PersonaManager(storage_dir=str(temp_storage))

    def test_load_builtin_personas(self, manager):
        """Should load built-in personas."""
        personas = manager.list_builtin_personas()
        assert len(personas) > 0
        assert any(p.id == "mix-engineer" for p in personas)
        assert any(p.id == "beginner-coach" for p in personas)

    def test_list_all_personas(self, manager):
        """Should list all personas."""
        personas = manager.list_personas()
        assert len(personas) > 0
        # All should have unique IDs
        ids = [p.id for p in personas]
        assert len(ids) == len(set(ids))

    def test_get_persona(self, manager):
        """Should get a persona by ID."""
        persona = manager.get_persona("mix-engineer")
        assert persona is not None
        assert persona.name == "混音工程师"

    def test_get_nonexistent_persona(self, manager):
        """Should return None for nonexistent persona."""
        persona = manager.get_persona("nonexistent")
        assert persona is None

    def test_persona_exists(self, manager):
        """Should check persona existence."""
        assert manager.persona_exists("mix-engineer") is True
        assert manager.persona_exists("nonexistent") is False

    def test_save_custom_persona(self, manager, temp_storage):
        """Should save a custom persona."""
        custom = Persona(
            id="my-custom",
            name="My Custom",
            description="A custom persona",
            system_prompt="You are custom.",
            is_builtin=False,
        )
        manager.save_persona(custom)

        # Should be retrievable
        retrieved = manager.get_persona("my-custom")
        assert retrieved is not None
        assert retrieved.name == "My Custom"

        # Should be in custom list
        custom_personas = manager.list_custom_personas()
        assert any(p.id == "my-custom" for p in custom_personas)

        # Should persist to disk
        file_path = temp_storage / "my-custom.json"
        assert file_path.exists()

    def test_cannot_save_builtin_persona(self, manager):
        """Should not allow saving built-in personas."""
        builtin = manager.get_persona("mix-engineer")
        assert builtin.is_builtin is True

        with pytest.raises(ValueError):
            manager.save_persona(builtin)

    def test_delete_custom_persona(self, manager):
        """Should delete a custom persona."""
        # Create and save
        custom = Persona(
            id="to-delete",
            name="To Delete",
            description="Will be deleted",
            system_prompt="Delete me.",
        )
        manager.save_persona(custom)

        # Should exist
        assert manager.persona_exists("to-delete")

        # Delete
        result = manager.delete_persona("to-delete")
        assert result is True

        # Should not exist
        assert manager.persona_exists("to-delete") is False

    def test_cannot_delete_builtin(self, manager):
        """Should not allow deleting built-in personas."""
        result = manager.delete_persona("mix-engineer")
        assert result is False

    def test_duplicate_persona(self, manager):
        """Should duplicate a persona."""
        new = manager.duplicate_persona("mix-engineer", "my-copy", "My Copy")
        assert new is not None
        assert new.id == "my-copy"
        assert new.name == "My Copy"
        assert new.is_builtin is False
        assert "混音工程师" in new.description

    def test_export_import_persona(self, manager):
        """Should export and import personas."""
        # Create custom persona
        custom = Persona(
            id="export-test",
            name="Export Test",
            description="For export/import",
            system_prompt="Export test prompt.",
        )
        manager.save_persona(custom)

        # Export
        json_str = manager.export_persona("export-test")
        assert json_str is not None
        assert "export-test" in json_str

        # Delete original
        manager.delete_persona("export-test")

        # Import
        imported = manager.import_persona(json_str)
        assert imported is not None
        assert imported.id == "export-test"
        assert imported.name == "Export Test"


class TestGlobalPersonaManager:
    """Test the global persona manager instance."""

    def test_get_persona_manager(self):
        """Should get or create the global manager."""
        manager1 = get_persona_manager()
        manager2 = get_persona_manager()
        # Should return the same instance
        assert manager1 is manager2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
