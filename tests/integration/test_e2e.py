"""test_e2e.py — VCMix end-to-end integration tests.

Tests the full CLI workflow via subprocess, verifying:
    - Exit codes match documented values
    - Output files are created in correct format
    - CLI flags (--report, --auto-fix, --ab, etc.) work correctly
    - All major subcommands produce valid output

Each test is independent and uses tmp_path for isolation.

Run: pytest tests/integration/ -v

Dependencies: pytest, numpy, soundfile
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


# ── Helper ─────────────────────────────────────────────────────────────────

def run_cli(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run vcmix CLI via 'python -m vcmix' and return CompletedProcess."""
    cmd = ["python", "-m", "vcmix"] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
    )


def generate_sine_wav(path: Path, freq: float = 440.0, sr: int = 44100,
                      duration: float = 1.0, amplitude: float = 0.5) -> Path:
    """Generate a sine wave WAV file and return its path."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    audio = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    audio_2d = audio.reshape(1, -1)
    sf.write(str(path), audio_2d.T, sr)
    return path


def make_project_yaml(
    tmp_path: Path,
    vocal_name: str = "vocal.wav",
    accomp_name: str = "accomp.wav",
    extra_tracks: str = "",
    extra_master: str = "",
    output_name: str = "mix_output.wav",
    with_ab: bool = False,
    with_sends: bool = False,
) -> Path:
    """Create a 2-track project YAML and return its path."""
    ab_section = ""
    if with_ab:
        ab_section = """
    effects_a:
      - name: vc-gain
        params:
          gain: 3
    effects_b:
      - name: vc-gain
        params:
          gain: -3"""

    sends_section = ""
    if with_sends:
        sends_section = """
sends:
  - name: reverb_bus
    type: post_fader
    effects:
      - name: vc-reverb
        params:
          room: 30
          mix: 20
"""

    yaml_content = f"""name: "E2E Test Project"
bpm: 120
sample_rate: 44100

tracks:
  - name: vocal
    file: "{vocal_name}"
    volume: 0.9
    effects:
      - name: vc-gain
        params:
          gain: 3{ab_section}

  - name: accomp
    file: "{accomp_name}"
    volume: 0.7
    effects:
      - name: vc-gain
        params:
          gain: 1{extra_tracks}
{sends_section}
master:
  levels:
    vocal: 1.0
    accomp: 0.8{extra_master}
  output: "{output_name}"
"""
    yaml_path = tmp_path / "project.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    return yaml_path


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def project_dir(tmp_path):
    """Create a temp project directory with 2 sine-wave audio files and a project.yaml."""
    generate_sine_wav(tmp_path / "vocal.wav", freq=440.0)
    generate_sine_wav(tmp_path / "accomp.wav", freq=261.6)
    make_project_yaml(tmp_path)
    return tmp_path


@pytest.fixture
def project_dir_ab(tmp_path):
    """Project directory with A/B comparison effect chains."""
    generate_sine_wav(tmp_path / "vocal.wav", freq=440.0)
    generate_sine_wav(tmp_path / "accomp.wav", freq=261.6)
    make_project_yaml(tmp_path, with_ab=True, output_name="mix_output.wav")
    return tmp_path


@pytest.fixture
def project_dir_sends(tmp_path):
    """Project directory with send/return buses."""
    generate_sine_wav(tmp_path / "vocal.wav", freq=440.0)
    generate_sine_wav(tmp_path / "accomp.wav", freq=261.6)
    make_project_yaml(tmp_path, with_sends=True, output_name="mix_output.wav")
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════════
# 1. RENDER COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRenderCommand:
    """Tests for 'vcmix render' subcommand."""

    def test_render_basic(self, project_dir):
        """vcmix render project.yaml — basic render should succeed (exit 0)."""
        result = run_cli("render", str(project_dir / "project.yaml"), cwd=str(project_dir))
        assert result.returncode == 0, f"render failed: {result.stderr}"
        output_file = project_dir / "mix_output.wav"
        assert output_file.exists(), "Output WAV file not created"

    def test_render_output_is_valid_wav(self, project_dir):
        """Rendered output should be a readable WAV file."""
        run_cli("render", str(project_dir / "project.yaml"), cwd=str(project_dir))
        output_file = project_dir / "mix_output.wav"
        assert output_file.exists()
        data, sr = sf.read(str(output_file))
        assert sr == 44100, f"Expected SR 44100, got {sr}"
        assert len(data) > 0, "Output audio is empty"

    def test_render_with_report(self, project_dir):
        """vcmix render project.yaml --report — should succeed and produce output."""
        result = run_cli("render", str(project_dir / "project.yaml"), "--report",
                         cwd=str(project_dir))
        assert result.returncode == 0, f"render --report failed: {result.stderr}"
        assert (project_dir / "mix_output.wav").exists()

    def test_render_with_auto_fix(self, project_dir):
        """vcmix render project.yaml --auto-fix — should succeed."""
        result = run_cli("render", str(project_dir / "project.yaml"), "--auto-fix",
                         cwd=str(project_dir))
        assert result.returncode == 0, f"render --auto-fix failed: {result.stderr}"
        assert (project_dir / "mix_output.wav").exists()

    def test_render_with_stream_json(self, project_dir):
        """vcmix render project.yaml --stream json — should emit JSON lines."""
        result = run_cli("render", str(project_dir / "project.yaml"), "--stream", "json",
                         cwd=str(project_dir))
        assert result.returncode == 0, f"render --stream json failed: {result.stderr}"
        # Verify JSON lines are present
        json_lines = [line for line in result.stdout.strip().split("\n") if line.startswith("{")]
        assert len(json_lines) > 0, "No JSON output lines found"
        # Each line should be valid JSON with 'step' or 'type' key
        for line in json_lines:
            parsed = json.loads(line)
            assert "step" in parsed or "type" in parsed, (
                f"JSON line missing 'step' or 'type' key: {line}"
            )

    def test_render_with_arrangement_aware(self, project_dir):
        """vcmix render project.yaml --arrangement-aware — should succeed (Phase 7)."""
        result = run_cli("render", str(project_dir / "project.yaml"), "--arrangement-aware",
                         cwd=str(project_dir))
        assert result.returncode == 0, f"render --arrangement-aware failed: {result.stderr}"
        assert (project_dir / "mix_output.wav").exists()

    def test_render_ab_mode(self, project_dir_ab):
        """vcmix render project.yaml --ab — should produce A and B versions (Phase 2)."""
        result = run_cli("render", str(project_dir_ab / "project.yaml"), "--ab",
                         cwd=str(project_dir_ab))
        assert result.returncode == 0, f"render --ab failed: {result.stderr}"
        output_a = project_dir_ab / "mix_output_a.wav"
        output_b = project_dir_ab / "mix_output_b.wav"
        assert output_a.exists(), f"A version not found: {output_a}"
        assert output_b.exists(), f"B version not found: {output_b}"

    def test_render_ab_with_diff(self, project_dir_ab):
        """vcmix render project.yaml --ab --diff — should include diff analysis."""
        result = run_cli("render", str(project_dir_ab / "project.yaml"), "--ab", "--diff",
                         cwd=str(project_dir_ab))
        assert result.returncode == 0, f"render --ab --diff failed: {result.stderr}"
        output_a = project_dir_ab / "mix_output_a.wav"
        output_b = project_dir_ab / "mix_output_b.wav"
        assert output_a.exists()
        assert output_b.exists()

    def test_render_nonexistent_project(self, tmp_path):
        """Render with non-existent YAML should fail with non-zero exit code."""
        result = run_cli("render", str(tmp_path / "nonexistent.yaml"))
        assert result.returncode != 0, "Should fail for non-existent project file"

    def test_render_with_sends(self, project_dir_sends):
        """Render a project with send/return buses should succeed."""
        result = run_cli("render", str(project_dir_sends / "project.yaml"),
                         cwd=str(project_dir_sends))
        assert result.returncode == 0, f"render with sends failed: {result.stderr}"
        assert (project_dir_sends / "mix_output.wav").exists()


# ═══════════════════════════════════════════════════════════════════════════
# 2. VALIDATE COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateCommand:
    """Tests for 'vcmix validate' subcommand."""

    def test_validate_valid_project(self, project_dir):
        """vcmix validate project.yaml — should report valid config."""
        result = run_cli("validate", str(project_dir / "project.yaml"))
        assert result.returncode == 0, f"validate failed: {result.stderr}"
        assert "valid" in result.stdout.lower() or "Valid" in result.stdout

    def test_validate_json_output(self, project_dir):
        """vcmix validate project.yaml --json — should produce valid JSON."""
        result = run_cli("validate", str(project_dir / "project.yaml"), "--json")
        assert result.returncode == 0, f"validate --json failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert "valid" in data
        assert data["valid"] is True
        assert "tracks" in data
        assert data["tracks"] == 2

    def test_validate_nonexistent_file(self, tmp_path):
        """Validate with non-existent file should fail."""
        result = run_cli("validate", str(tmp_path / "nonexistent.yaml"))
        assert result.returncode != 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. GRAPH COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestGraphCommand:
    """Tests for 'vcmix graph' subcommand."""

    def test_graph_text(self, project_dir):
        """vcmix graph project.yaml — should output text graph."""
        result = run_cli("graph", str(project_dir / "project.yaml"))
        assert result.returncode == 0, f"graph failed: {result.stderr}"
        assert "Project" in result.stdout or "vocal" in result.stdout

    def test_graph_mermaid(self, project_dir):
        """vcmix graph project.yaml -f mermaid — should output Mermaid syntax."""
        result = run_cli("graph", str(project_dir / "project.yaml"), "-f", "mermaid")
        assert result.returncode == 0, f"graph mermaid failed: {result.stderr}"
        assert "graph" in result.stdout.lower() or "flowchart" in result.stdout.lower() or "-->" in result.stdout


# ═══════════════════════════════════════════════════════════════════════════
# 4. ANALYZE COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalyzeCommand:
    """Tests for 'vcmix analyze' subcommand."""

    def test_analyze_wav(self, project_dir):
        """vcmix analyze vocal.wav — should produce analysis output."""
        vocal_path = project_dir / "vocal.wav"
        result = run_cli("analyze", str(vocal_path))
        assert result.returncode == 0, f"analyze failed: {result.stderr}"
        assert "RMS" in result.stdout or "rms" in result.stdout.lower()

    def test_analyze_json(self, project_dir):
        """vcmix analyze vocal.wav --json — should produce valid JSON output."""
        vocal_path = project_dir / "vocal.wav"
        result = run_cli("analyze", str(vocal_path), "--json")
        assert result.returncode == 0, f"analyze --json failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert "file" in data
        assert "rms_db" in data
        assert "peak_db" in data

    def test_analyze_nonexistent_file(self, tmp_path):
        """Analyze non-existent file should fail."""
        result = run_cli("analyze", str(tmp_path / "nonexistent.wav"))
        assert result.returncode != 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. AUTOMIX COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAutomixCommand:
    """Tests for 'vcmix automix' subcommand."""

    def test_automix_audio_file(self, project_dir):
        """vcmix automix vocal.wav — Phase 4: analyze dry vocal and generate YAML."""
        vocal_path = project_dir / "vocal.wav"
        result = run_cli("automix", str(vocal_path), cwd=str(project_dir))
        assert result.returncode == 0, f"automix audio failed: {result.stderr}"
        automix_yaml = project_dir / "vocal_automix.yaml"
        assert automix_yaml.exists(), f"AutoMix YAML not created: {result.stderr}"

    def test_automix_audio_with_bpm(self, project_dir):
        """vcmix automix vocal.wav --bpm 140 — should accept BPM override."""
        vocal_path = project_dir / "vocal.wav"
        result = run_cli("automix", str(vocal_path), "--bpm", "140", cwd=str(project_dir))
        assert result.returncode == 0, f"automix --bpm failed: {result.stderr}"

    def test_automix_audio_json_output(self, project_dir):
        """vcmix automix vocal.wav --json — should produce JSON analysis."""
        vocal_path = project_dir / "vocal.wav"
        result = run_cli("automix", str(vocal_path), "--json", cwd=str(project_dir))
        assert result.returncode == 0, f"automix --json failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert "file" in data or "analysis" in data

    def test_automix_project_yaml(self, project_dir):
        """vcmix automix project.yaml — Phase 6: closed-loop auto-mixing."""
        yaml_path = project_dir / "project.yaml"
        result = run_cli("automix", str(yaml_path), cwd=str(project_dir))
        assert result.returncode == 0, f"automix project failed: {result.stderr}"
        automix_output = project_dir / "project_automix.yaml"
        assert automix_output.exists(), f"AutoMix output not created: {result.stderr}"

    def test_automix_project_dry_run(self, project_dir):
        """vcmix automix project.yaml --dry-run=phase6 — should analyze without writing files."""
        yaml_path = project_dir / "project.yaml"
        result = run_cli("automix", str(yaml_path), "--dry-run=phase6", cwd=str(project_dir))
        assert result.returncode == 0, f"automix --dry-run failed: {result.stderr}"
        assert "dry-run" in result.stdout.lower() or "no files written" in result.stdout.lower()
        # Should NOT produce an _automix.yaml in dry-run mode
        automix_output = project_dir / "project_automix.yaml"
        assert not automix_output.exists(), "AutoMix should not write files in --dry-run mode"


# ═══════════════════════════════════════════════════════════════════════════
# 6. ARRANGEMENT COMMAND TESTS (Phase 7)
# ═══════════════════════════════════════════════════════════════════════════

class TestArrangementCommand:
    """Tests for 'vcmix arrangement' subcommand (Phase 7)."""

    def test_arrangement_analysis(self, project_dir):
        """vcmix arrangement project.yaml — should show section analysis."""
        result = run_cli("arrangement", str(project_dir / "project.yaml"))
        # Arrangement may warn about no audio if extraction fails,
        # but should not crash
        assert result.returncode == 0, f"arrangement failed: {result.stderr}"

    def test_arrangement_strategy(self, project_dir):
        """vcmix arrangement project.yaml --strategy — should show mixing strategy."""
        result = run_cli("arrangement", str(project_dir / "project.yaml"), "--strategy")
        assert result.returncode == 0, f"arrangement --strategy failed: {result.stderr}"

    def test_arrangement_json_output(self, project_dir):
        """vcmix arrangement project.yaml --json — should produce JSON output."""
        result = run_cli("arrangement", str(project_dir / "project.yaml"), "--json")
        assert result.returncode == 0, f"arrangement --json failed: {result.stderr}"


# ═══════════════════════════════════════════════════════════════════════════
# 7. PRESETS COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestPresetsCommand:
    """Tests for 'vcmix presets' subcommand."""

    def test_presets_list(self):
        """vcmix presets — should list built-in presets."""
        result = run_cli("presets")
        assert result.returncode == 0, f"presets failed: {result.stderr}"
        assert "preset" in result.stdout.lower() or "Built-in" in result.stdout

    def test_presets_json(self):
        """vcmix presets --json — should produce valid JSON."""
        result = run_cli("presets", "--json")
        assert result.returncode == 0, f"presets --json failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert "presets" in data
        assert isinstance(data["presets"], list)
        assert len(data["presets"]) > 0, "No built-in presets found"

    def test_presets_specific_name(self):
        """vcmix presets --name pop_vocal — should show details or report not found."""
        result = run_cli("presets", "--name", "pop_vocal")
        # pop_vocal may or may not exist — but the command should not crash
        assert result.returncode in (0, 1), f"presets --name crashed: {result.stderr}"


# ═══════════════════════════════════════════════════════════════════════════
# 8. VERSION & HELP TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCLIBasic:
    """Tests for basic CLI behavior."""

    def test_version(self):
        """vcmix --version — should print version string."""
        result = run_cli("--version")
        assert result.returncode == 0
        assert "0.8.0" in result.stdout

    def test_help(self):
        """vcmix --help — should list available subcommands."""
        result = run_cli("--help")
        assert result.returncode == 0
        assert "render" in result.stdout
        assert "validate" in result.stdout
        assert "graph" in result.stdout
        assert "analyze" in result.stdout
        assert "automix" in result.stdout
        assert "arrangement" in result.stdout
        assert "presets" in result.stdout

    def test_render_help(self):
        """vcmix render --help — should show render options."""
        result = run_cli("render", "--help")
        assert result.returncode == 0
        assert "--report" in result.stdout
        assert "--auto-fix" in result.stdout
        assert "--ab" in result.stdout
        assert "--arrangement-aware" in result.stdout

    def test_automix_help(self):
        """vcmix automix --help — should show automix options."""
        result = run_cli("automix", "--help")
        assert result.returncode == 0
        assert "--dry-run" in result.stdout
        assert "--reference" in result.stdout

    def test_arrangement_help(self):
        """vcmix arrangement --help — should show arrangement options."""
        result = run_cli("arrangement", "--help")
        assert result.returncode == 0
        assert "--strategy" in result.stdout
        assert "--json" in result.stdout


# ═══════════════════════════════════════════════════════════════════════════
# 9. EXIT CODE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestExitCodes:
    """Verify standardized exit codes for various error conditions."""

    def test_config_warning_exit_code(self, tmp_path):
        """YAML with missing tracks should report issues via validate (exit 0 with warnings)."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            'name: Bad\nbpm: 120\nsample_rate: 44100\ntracks: []\n'
            'master:\n  levels: {}\n  effects: []\n  output: out.wav\n',
            encoding="utf-8",
        )
        result = run_cli("validate", str(bad_yaml))
        # validate returns 0 even with warnings (they are advisory)
        assert result.returncode == 0
        assert "warning" in result.stdout.lower() or "No tracks" in result.stdout

    def test_invalid_yaml_parse_error(self, tmp_path):
        """Truly invalid YAML should fail with non-zero exit code."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("{{{{invalid yaml:::", encoding="utf-8")
        result = run_cli("validate", str(bad_yaml))
        assert result.returncode != 0, (
            f"Expected non-zero exit for invalid YAML, got {result.returncode}"
        )

    def test_io_error_exit_code(self, tmp_path):
        """Missing audio file should exit with code 3 (EXIT_IO_ERROR)."""
        yaml_content = (
            'name: "Missing Audio"\nbpm: 120\nsample_rate: 44100\n\n'
            'tracks:\n  - name: vocal\n    file: "nonexistent.wav"\n'
            '    volume: 0.9\n    effects: []\n\n'
            'master:\n  levels:\n    vocal: 1.0\n  effects: []\n'
            '  output: "output.wav"\n'
        )
        yaml_path = tmp_path / "missing_audio.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")
        result = run_cli("render", str(yaml_path), cwd=str(tmp_path))
        assert result.returncode == 3, (
            f"Expected exit code 3 (IO error), got {result.returncode}"
        )

    def test_success_exit_code(self, project_dir):
        """Successful render should exit with code 0."""
        result = run_cli("render", str(project_dir / "project.yaml"), cwd=str(project_dir))
        assert result.returncode == 0
