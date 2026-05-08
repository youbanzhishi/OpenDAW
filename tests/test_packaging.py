"""
test_packaging.py — Phase 16: Cross-platform packaging, Docker, CI, and desktop build tests.

Validates:
    - pyproject.toml metadata completeness
    - Entry point (vcmix CLI) availability
    - Docker configuration (Dockerfile, docker-compose.yml, .dockerignore)
    - GitHub Actions CI workflow correctness
    - Release workflow correctness
    - Desktop (Tauri) build configuration
    - Python package buildability
    - Optional dependencies groups
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Project root directory
ROOT = Path(__file__).resolve().parent.parent


# ── pyproject.toml validation ───────────────────────────────────────────


class TestPyprojectToml:
    """Validate pyproject.toml metadata completeness."""

    def _read_pyproject(self) -> str:
        return (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    def test_pyproject_exists(self):
        assert (ROOT / "pyproject.toml").is_file(), "pyproject.toml must exist"

    def test_project_name(self):
        content = self._read_pyproject()
        assert 'name = "vcmix"' in content

    def test_project_version(self):
        content = self._read_pyproject()
        assert "version =" in content
        # version should be a valid semver-like string
        import re
        match = re.search(r'version\s*=\s*"(\d+\.\d+\.\d+)"', content)
        assert match, "Version must be in semver format (X.Y.Z)"

    def test_project_description(self):
        content = self._read_pyproject()
        assert "description =" in content
        assert len(content.split('description = "')[1].split('"')[0]) > 10

    def test_project_authors(self):
        content = self._read_pyproject()
        assert "authors =" in content

    def test_project_license(self):
        content = self._read_pyproject()
        assert "license =" in content

    def test_requires_python(self):
        content = self._read_pyproject()
        assert "requires-python" in content
        assert "3.9" in content

    def test_core_dependencies(self):
        content = self._read_pyproject()
        for dep in ["numpy", "soundfile", "scipy", "pyyaml"]:
            assert dep in content, f"Core dependency '{dep}' missing from pyproject.toml"

    def test_web_optional_dependencies(self):
        content = self._read_pyproject()
        for dep in ["fastapi", "uvicorn", "websockets"]:
            assert dep in content, f"Web dependency '{dep}' missing"

    def test_optional_ai_dependencies(self):
        content = self._read_pyproject()
        # demucs should be in optional deps
        assert "demucs" in content, "Optional AI dependency 'demucs' missing"

    def test_optional_audio_dependencies(self):
        content = self._read_pyproject()
        for dep in ["sounddevice", "mido"]:
            assert dep in content, f"Optional audio dependency '{dep}' missing"

    def test_dev_dependencies(self):
        content = self._read_pyproject()
        for dep in ["pytest", "ruff"]:
            assert dep in content, f"Dev dependency '{dep}' missing"

    def test_entry_point(self):
        content = self._read_pyproject()
        assert 'vcmix = "vcmix.cli:main"' in content, "Console script entry point missing"

    def test_setuptools_packages_find(self):
        content = self._read_pyproject()
        assert "[tool.setuptools.packages.find]" in content

    def test_package_data_includes_static_and_presets(self):
        content = self._read_pyproject()
        assert "[tool.setuptools.package-data]" in content
        assert "static" in content
        assert "presets" in content


# ── Entry point test ─────────────────────────────────────────────────────


class TestEntryPoint:
    """Validate CLI entry point works."""

    def test_vcmix_help(self):
        """vcmix --help should succeed."""
        result = subprocess.run(
            [sys.executable, "-m", "vcmix", "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode == 0, f"vcmix --help failed: {result.stderr}"

    def test_vcmix_version(self):
        """vcmix --version should succeed and show version."""
        result = subprocess.run(
            [sys.executable, "-m", "vcmix", "--version"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode == 0
        assert "0.13" in result.stdout or "0.13" in result.stderr

    def test_serve_command_registered(self):
        """'serve' subcommand should be registered."""
        result = subprocess.run(
            [sys.executable, "-m", "vcmix", "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert "serve" in result.stdout, "'serve' command not found in CLI help"

    def test_serve_help(self):
        """vcmix serve --help should succeed."""
        result = subprocess.run(
            [sys.executable, "-m", "vcmix", "serve", "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode == 0
        assert "--host" in result.stdout
        assert "--port" in result.stdout
        assert "--reload" in result.stdout


# ── Docker configuration tests ───────────────────────────────────────────


class TestDockerConfig:
    """Validate Docker build and compose configuration."""

    def test_dockerfile_exists(self):
        assert (ROOT / "Dockerfile").is_file(), "Dockerfile must exist"

    def test_dockerfile_base_image(self):
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "python:3.11-slim" in content, "Should use python:3.11-slim base image"

    def test_dockerfile_expose_port(self):
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "EXPOSE 8000" in content or "expose 8000" in content.lower()

    def test_dockerfile_install_web_deps(self):
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "[web]" in content, "Should install web optional dependencies"

    def test_dockerfile_cmd(self):
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "vcmix" in content
        assert "serve" in content

    def test_dockerfile_healthcheck(self):
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "HEALTHCHECK" in content, "Dockerfile should include HEALTHCHECK"

    def test_docker_compose_exists(self):
        assert (ROOT / "docker-compose.yml").is_file(), "docker-compose.yml must exist"

    def test_docker_compose_port_mapping(self):
        content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        assert "8000" in content, "Port 8000 should be mapped"

    def test_docker_compose_volumes(self):
        content = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        assert "projects" in content
        assert "output" in content

    def test_dockerignore_exists(self):
        assert (ROOT / ".dockerignore").is_file(), ".dockerignore must exist"

    def test_dockerignore_excludes_git(self):
        content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert ".git" in content

    def test_dockerignore_excludes_tests(self):
        content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert "tests/" in content or "tests" in content


# ── GitHub Actions CI tests ──────────────────────────────────────────────


class TestCIWorkflows:
    """Validate GitHub Actions workflow configuration."""

    def test_test_workflow_exists(self):
        assert (ROOT / ".github" / "workflows" / "test.yml").is_file()

    def test_test_workflow_matrix_os(self):
        content = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        for os_name in ["ubuntu-latest", "macos-latest", "windows-latest"]:
            assert os_name in content, f"OS '{os_name}' missing from test matrix"

    def test_test_workflow_matrix_python(self):
        content = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        for py_ver in ["3.9", "3.10", "3.11", "3.12"]:
            assert py_ver in content, f"Python '{py_ver}' missing from test matrix"

    def test_test_workflow_uses_setup_python_v5(self):
        content = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        assert "actions/setup-python@v5" in content

    def test_test_workflow_ruff_step(self):
        content = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        assert "ruff" in content

    def test_test_workflow_pytest_step(self):
        content = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        assert "pytest" in content

    def test_test_workflow_fail_fast_false(self):
        content = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        assert "fail-fast: false" in content

    def test_release_workflow_exists(self):
        assert (ROOT / ".github" / "workflows" / "release.yml").is_file()

    def test_release_workflow_tag_trigger(self):
        content = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        assert "v*" in content or "tags" in content

    def test_release_workflow_pypi_publish(self):
        content = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        assert "pypi" in content.lower() or "PyPI" in content

    def test_release_workflow_docker_push(self):
        content = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        assert "docker" in content.lower() or "ghcr" in content.lower()

    def test_release_workflow_uses_twine(self):
        content = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        assert "twine" in content

    def test_desktop_workflow_exists(self):
        assert (ROOT / ".github" / "workflows" / "desktop.yml").is_file()

    def test_desktop_workflow_multi_platform(self):
        content = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
        for platform in ["ubuntu-latest", "macos-latest", "windows-latest"]:
            assert platform in content, f"Platform '{platform}' missing from desktop workflow"

    def test_desktop_workflow_tauri_action(self):
        content = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
        assert "tauri" in content.lower()


# ── Tauri desktop build tests ────────────────────────────────────────────


class TestTauriConfig:
    """Validate Tauri desktop build configuration."""

    def test_tauri_conf_exists(self):
        assert (ROOT / "desktop" / "src-tauri" / "tauri.conf.json").is_file()

    def test_tauri_product_name(self):
        import json
        conf = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text())
        assert conf["productName"] == "VCMix"

    def test_tauri_identifier(self):
        import json
        conf = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text())
        assert conf["identifier"] == "com.opendaw.vcmix"

    def test_tauri_version(self):
        import json
        conf = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text())
        assert "version" in conf
        import re
        assert re.match(r"\d+\.\d+\.\d+", conf["version"])

    def test_tauri_bundle_active(self):
        import json
        conf = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text())
        assert conf["bundle"]["active"] is True

    def test_tauri_windows_nsis_config(self):
        import json
        conf = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text())
        assert "windows" in conf["bundle"]
        assert "nsis" in conf["bundle"]["windows"]

    def test_tauri_macos_dmg_config(self):
        import json
        conf = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text())
        assert "macOS" in conf["bundle"]
        assert "dmg" in conf["bundle"]["macOS"]

    def test_tauri_linux_deb_config(self):
        import json
        conf = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text())
        assert "linux" in conf["bundle"]
        assert "deb" in conf["bundle"]["linux"]

    def test_tauri_updater_disabled(self):
        import json
        conf = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text())
        assert "updater" in conf.get("plugins", {})
        assert conf["plugins"]["updater"]["active"] is False

    def test_tauri_cargo_toml_exists(self):
        assert (ROOT / "desktop" / "src-tauri" / "Cargo.toml").is_file()

    def test_tauri_package_json_exists(self):
        assert (ROOT / "desktop" / "package.json").is_file()


# ── Package buildability test ────────────────────────────────────────────


class TestPackageBuild:
    """Validate that the package can be built."""

    def test_src_layout_vcmix_package(self):
        """vcmix package must exist under src/."""
        assert (ROOT / "src" / "vcmix" / "__init__.py").is_file()

    def test_src_layout_cli_module(self):
        """CLI module must exist."""
        assert (ROOT / "src" / "vcmix" / "cli.py").is_file()

    def test_src_layout_main_module(self):
        """__main__.py must exist for `python -m vcmix`."""
        assert (ROOT / "src" / "vcmix" / "__main__.py").is_file()

    def test_web_app_module(self):
        """Web app module must exist for serve command."""
        assert (ROOT / "src" / "vcmix" / "web" / "app.py").is_file()

    def test_create_app_function(self):
        """create_app() must be importable from vcmix.web.app."""
        from vcmix.web.app import create_app
        assert callable(create_app)

    def test_license_file_exists(self):
        """LICENSE file must exist for packaging."""
        assert (ROOT / "LICENSE").is_file()
