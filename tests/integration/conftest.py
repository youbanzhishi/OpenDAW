from __future__ import annotations

"""conftest.py — Shared fixtures for VCMix integration tests.

Generates synthetic test audio (sine waves) and project YAML files
for end-to-end CLI testing via subprocess.

Dependencies: pytest, numpy, soundfile
"""

import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

# ── Constants ──────────────────────────────────────────────────────────────

SAMPLE_RATE = 44100
DURATION_S = 1.0
FREQ_VOCAL = 440.0    # A4
FREQ_ACCOMP = 261.6   # C4


# ── Helpers ────────────────────────────────────────────────────────────────

def _generate_sine(
    freq: float, sr: int = SAMPLE_RATE, duration: float = DURATION_S,
) -> tuple[np.ndarray, int]:
    """Generate a sine wave audio buffer."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    audio = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return audio, sr


def _write_wav(path: Path, audio: np.ndarray, sr: int) -> Path:
    """Write audio to WAV file, ensuring 2D shape for soundfile."""
    if audio.ndim == 1:
        audio = audio.reshape(1, -1)
    sf.write(str(path), audio.T, sr)
    return path


def run_cli(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run vcmix CLI via "python -m vcmix" and return CompletedProcess."""
    cmd = ["python", "-m", "vcmix"] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
    )


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def vocal_audio():
    """Generate 1-second 440 Hz sine wave."""
    return _generate_sine(FREQ_VOCAL)


@pytest.fixture
def accomp_audio():
    """Generate 1-second 261.6 Hz sine wave."""
    return _generate_sine(FREQ_ACCOMP)


@pytest.fixture
def vocal_wav(tmp_path, vocal_audio):
    """Write vocal sine wave to temp WAV file."""
    audio, sr = vocal_audio
    return _write_wav(tmp_path / "vocal.wav", audio, sr)


@pytest.fixture
def accomp_wav(tmp_path, accomp_audio):
    """Write accompaniment sine wave to temp WAV file."""
    audio, sr = accomp_audio
    return _write_wav(tmp_path / "accomp.wav", audio, sr)


@pytest.fixture
def project_yaml(tmp_path, vocal_wav, accomp_wav):
    """Create a 2-track VCMix project YAML file.

    Tracks:
        vocal   — 440 Hz sine with vc-gain +3 dB
        accomp  — 261.6 Hz sine with vc-gain +1 dB

    Both tracks feed into a simple master with balanced levels.
    """
    yaml_content = f"""name: "Integration Test Project"
bpm: 120
sample_rate: {SAMPLE_RATE}

tracks:
  - name: vocal
    file: "{vocal_wav.name}"
    volume: 0.9
    effects:
      - name: vc-gain
        params:
          gain: 3

  - name: accomp
    file: "{accomp_wav.name}"
    volume: 0.7
    effects:
      - name: vc-gain
        params:
          gain: 1

master:
  levels:
    vocal: 1.0
    accomp: 0.8
  effects: []
  output: "mix_output.wav"
"""
    yaml_path = tmp_path / "project.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    return yaml_path


@pytest.fixture
def project_yaml_with_sends(tmp_path, vocal_wav, accomp_wav):
    """Create a project YAML with send/return buses for A/B testing."""
    yaml_content = f"""name: "AB Test Project"
bpm: 120
sample_rate: {SAMPLE_RATE}

tracks:
  - name: vocal
    file: "{vocal_wav.name}"
    volume: 0.9
    effects:
      - name: vc-gain
        params:
          gain: 3
    effects_a:
      - name: vc-gain
        params:
          gain: 3
    effects_b:
      - name: vc-gain
        params:
          gain: -3

  - name: accomp
    file: "{accomp_wav.name}"
    volume: 0.7
    effects:
      - name: vc-gain
        params:
          gain: 1
    effects_a:
      - name: vc-gain
        params:
          gain: 1
    effects_b:
      - name: vc-gain
        params:
          gain: -1

sends:
  - name: reverb_bus
    type: post_fader
    effects:
      - name: vc-reverb
        params:
          room: 30
          mix: 20

master:
  levels:
    vocal: 1.0
    accomp: 0.8
  effects: []
  output: "mix_output.wav"
"""
    yaml_path = tmp_path / "project_ab.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    return yaml_path
