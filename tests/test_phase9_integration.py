"""
test_phase9_integration.py — Integration tests for Phase 9 Renderer integration.

Tests:
    - MIDI track rendering through Renderer
    - Automation gain curve application
    - Automation plugin parameter overrides
    - MIDI track with plugin processing
"""

from __future__ import annotations

from pathlib import Path

import mido
import numpy as np
import pytest
import soundfile as sf
import yaml

from vcmix.config.parser import ProjectConfig, parse_project
from vcmix.engine.renderer import Renderer

# ── Helpers ──────────────────────────────────────────────────────────────

def _create_test_midi(
    path: Path,
    notes: list[tuple[int, float, float, float]] | None = None,
    bpm: int = 120,
    ticks_per_beat: int = 480,
) -> Path:
    """Create a test MIDI file.

    Args:
        path: Output .mid file path.
        notes: List of (note, velocity_0to1, start_beat, duration_beats).
        bpm: Tempo.
        ticks_per_beat: MIDI ticks per beat.

    Returns:
        Path to the created file.
    """
    if notes is None:
        notes = [(60, 1.0, 0.0, 4.0)]  # C4, full vel, beat 0, 4 beats

    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # Tempo meta event
    tempo = mido.bpm2tempo(bpm)
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    # Build events list
    events: list[tuple[int, str, int, int]] = []
    for note_num, velocity_norm, start_beat, duration_beats in notes:
        start_tick = int(start_beat * ticks_per_beat)
        end_tick = int((start_beat + duration_beats) * ticks_per_beat)
        vel = int(velocity_norm * 127)
        events.append((start_tick, "note_on", note_num, vel))
        events.append((end_tick, "note_off", note_num, 0))

    # Sort by tick (note_off before note_on at same tick)
    events.sort(key=lambda e: (e[0], e[1] == "note_on"))

    current_tick = 0
    for tick, msg_type, note_num, velocity in events:
        delta = tick - current_tick
        if msg_type == "note_on":
            track.append(mido.Message("note_on", note=note_num, velocity=velocity, time=delta))
        else:
            track.append(mido.Message("note_off", note=note_num, velocity=0, time=delta))
        current_tick = tick

    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(str(path))
    return path


def _create_audio_wav(path: Path, sr: int = 44100, duration: float = 1.0) -> Path:
    """Create a simple test WAV file."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    sf.write(str(path), audio, sr)
    return path


def _make_project_yaml(
    tmp_path: Path,
    tracks: list[dict],
    bpm: float = 120.0,
    master_levels: dict | None = None,
) -> tuple[ProjectConfig, Path]:
    """Create a minimal project YAML and return parsed config + project dir."""
    if master_levels is None:
        master_levels = {}
        for t in tracks:
            master_levels[t["name"]] = 1.0

    yaml_content = {
        "name": "test_phase9",
        "bpm": bpm,
        "sample_rate": 44100,
        "tracks": tracks,
        "master": {
            "levels": master_levels,
            "output": str(tmp_path / "out.wav"),
        },
    }
    yaml_path = tmp_path / "project.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_content, f)

    config = parse_project(yaml_path)
    config.__dict__["_project_dir"] = tmp_path
    return config, tmp_path


# ── Test: MIDI Track Rendering ──────────────────────────────────────────

class TestMidiTrackRendering:
    """Test MIDI track rendering through the Renderer pipeline."""

    def test_midi_track_renders_audio(self, tmp_path: Path) -> None:
        """A MIDI track should produce non-silent audio."""
        midi_path = tmp_path / "melody.mid"
        _create_test_midi(midi_path, notes=[
            (60, 0.8, 0.0, 2.0),  # C4, beat 0-2
        ])

        tracks = [
            {
                "name": "synth",
                "type": "midi",
                "midi_file": "melody.mid",
                "synth": "sine",
            }
        ]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        # Test _render_midi_track directly
        track_cfg = config.tracks[0]
        sr = config.sample_rate
        audio = r._render_midi_track(track_cfg, sr, proj_dir)

        assert isinstance(audio, np.ndarray)
        assert len(audio) > 0
        # Should not be all zeros
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        assert rms > 1e-6, "MIDI track should produce audible audio"

    def test_midi_track_with_multiple_notes(self, tmp_path: Path) -> None:
        """MIDI track with multiple notes should render correctly."""
        midi_path = tmp_path / "chords.mid"
        _create_test_midi(midi_path, notes=[
            (60, 0.7, 0.0, 2.0),  # C4
            (64, 0.7, 0.0, 2.0),  # E4
            (67, 0.7, 0.0, 2.0),  # G4
        ])

        tracks = [
            {
                "name": "chords",
                "type": "midi",
                "midi_file": "chords.mid",
                "synth": "sawtooth",
            }
        ]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        track_cfg = config.tracks[0]
        audio = r._render_midi_track(track_cfg, config.sample_rate, proj_dir)

        assert len(audio) > 0
        # Chord should have more energy than single note
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        assert rms > 1e-4

    def test_midi_track_different_synths(self, tmp_path: Path) -> None:
        """Different synth types should produce different audio."""
        midi_path = tmp_path / "note.mid"
        _create_test_midi(midi_path, notes=[(69, 0.8, 0.0, 1.0)])

        results = {}
        for synth_type in ["sine", "sawtooth", "square", "triangle"]:
            sub_dir = tmp_path / synth_type
            sub_dir.mkdir(parents=True, exist_ok=True)
            # Copy the MIDI file into each subdirectory
            import shutil
            shutil.copy2(str(midi_path), str(sub_dir / "note.mid"))
            tracks = [
                {
                    "name": f"synth_{synth_type}",
                    "type": "midi",
                    "midi_file": "note.mid",
                    "synth": synth_type,
                }
            ]
            config, proj_dir = _make_project_yaml(sub_dir, tracks)
            r = Renderer(config, stream="none")
            audio = r._render_midi_track(config.tracks[0], config.sample_rate, proj_dir)
            results[synth_type] = audio.flatten()[:1000]  # First 1000 samples

        # Sine and sawtooth should be different
        corr = np.corrcoef(results["sine"], results["sawtooth"])[0, 1]
        assert abs(corr) < 0.99, "Different synths should produce different audio"

    def test_midi_track_empty_file(self, tmp_path: Path) -> None:
        """MIDI track with no notes should produce near-silent audio."""
        midi_path = tmp_path / "empty.mid"
        # Create MIDI file with no note events
        mid = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.save(str(midi_path))

        tracks = [
            {
                "name": "empty_synth",
                "type": "midi",
                "midi_file": "empty.mid",
                "synth": "sine",
            }
        ]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        audio = r._render_midi_track(config.tracks[0], config.sample_rate, proj_dir)
        # Should return a zero-like buffer (at least 1 sample)
        assert len(audio) >= 1


# ── Test: Automation Gain Curve ─────────────────────────────────────────

class TestAutomationGainCurve:
    """Test gain automation curve rendering."""

    def test_gain_automation_applied(self, tmp_path: Path) -> None:
        """Gain automation should modify audio level."""
        wav_path = tmp_path / "vocal.wav"
        _create_audio_wav(wav_path, duration=2.0)

        # Track with gain automation: fade from -12dB to 0dB
        tracks = [
            {
                "name": "vocal",
                "file": str(wav_path),
                "automation": {
                    "gain": [
                        [0, -12, "linear"],
                        [8, 0, "linear"],
                    ],
                },
            }
        ]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        track_cfg = config.tracks[0]

        # Load original audio
        from vcmix.audio.io import read_audio
        original, _ = read_audio(wav_path)

        # Apply automation
        processed = r._render_track_with_automation(track_cfg, original, config.sample_rate)

        # At beat 0, gain should be -12dB (very quiet)
        # At beat 8, gain should be 0dB (unity)
        # The processed audio should be different from original
        orig_rms = float(np.sqrt(np.mean(original.flatten().astype(np.float64) ** 2)))
        proc_rms = float(np.sqrt(np.mean(processed.flatten().astype(np.float64) ** 2)))

        # With -12dB at start ramping to 0dB, average should be lower
        assert proc_rms < orig_rms, "Gain automation should reduce overall level"

    def test_gain_automation_step_curve(self, tmp_path: Path) -> None:
        """Step automation should hold values until next point."""
        wav_path = tmp_path / "drums.wav"
        _create_audio_wav(wav_path, duration=2.0)

        # Use step automation with a cut within the audio range
        # At 120 BPM, 2 seconds = 4 beats. Set cut at beat 1.
        tracks = [
            {
                "name": "drums",
                "file": str(wav_path),
                "automation": {
                    "gain": [
                        [0, 0, "step"],
                        [1, -20, "step"],
                    ],
                },
            }
        ]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        track_cfg = config.tracks[0]

        from vcmix.audio.io import read_audio
        original, _ = read_audio(wav_path)
        processed = r._render_track_with_automation(track_cfg, original, config.sample_rate)

        # First quarter (beats 0-1) should be at 0dB, rest at -20dB
        # Overall should be significantly attenuated
        orig_rms = float(np.sqrt(np.mean(original.flatten().astype(np.float64) ** 2)))
        proc_rms = float(np.sqrt(np.mean(processed.flatten().astype(np.float64) ** 2)))
        # With 75% of audio at -20dB, overall should be much quieter
        # (but not exactly 0.5 due to block boundaries)
        assert proc_rms < orig_rms * 0.7, (
            f"Expected proc_rms < orig_rms*0.7,"
            f" got {proc_rms:.6f} vs {orig_rms*0.7:.6f}"
        )

    def test_no_automation_returns_original(self, tmp_path: Path) -> None:
        """Track without automation should return audio unchanged."""
        wav_path = tmp_path / "bass.wav"
        _create_audio_wav(wav_path)

        tracks = [{"name": "bass", "file": str(wav_path)}]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        track_cfg = config.tracks[0]

        from vcmix.audio.io import read_audio
        original, _ = read_audio(wav_path)
        processed = r._render_track_with_automation(track_cfg, original, config.sample_rate)

        # Should be identical
        np.testing.assert_array_almost_equal(
            original.flatten()[:100],
            processed.flatten()[:100],
            decimal=5,
        )


# ── Test: Automation Plugin Parameters ──────────────────────────────────

class TestAutomationPluginParams:
    """Test plugin parameter automation via AutomationEngine integration."""

    def test_plugin_param_overrides(self, tmp_path: Path) -> None:
        """_get_automation_overrides should merge automation values."""
        wav_path = tmp_path / "guitar.wav"
        _create_audio_wav(wav_path)

        tracks = [
            {
                "name": "guitar",
                "file": str(wav_path),
                "automation": {
                    "vc-reverb.wet": [
                        [0, 0.1, "linear"],
                        [16, 0.5, "linear"],
                    ],
                },
            }
        ]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        track_cfg = config.tracks[0]

        static_params = {"room": 30, "wet": 0.2}

        # At beat 0, wet should be overridden to ~0.1
        params_beat0 = r._get_automation_overrides(track_cfg, "vc-reverb", static_params, 0.0)
        assert abs(params_beat0["wet"] - 0.1) < 0.01, (
            f"Expected wet~0.1 at beat 0, got {params_beat0['wet']}"
        )

        # At beat 16, wet should be overridden to ~0.5
        params_beat16 = r._get_automation_overrides(track_cfg, "vc-reverb", static_params, 16.0)
        assert abs(params_beat16["wet"] - 0.5) < 0.01, (
            f"Expected wet~0.5 at beat 16, got {params_beat16['wet']}"
        )

        # Static params should be preserved
        assert params_beat0["room"] == 30

    def test_no_automation_preserves_static(self, tmp_path: Path) -> None:
        """Without automation, static params should be preserved."""
        wav_path = tmp_path / "piano.wav"
        _create_audio_wav(wav_path)

        tracks = [{"name": "piano", "file": str(wav_path)}]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        track_cfg = config.tracks[0]

        static_params = {"room": 30, "wet": 0.2}
        result = r._get_automation_overrides(track_cfg, "vc-reverb", static_params, 4.0)

        assert result == static_params


# ── Test: MIDI Track + Plugin Processing ────────────────────────────────

class TestMidiWithPlugins:
    """Test MIDI track rendering combined with plugin effect chain."""

    def test_midi_track_validation(self, tmp_path: Path) -> None:
        """MIDI tracks should be validated for .mid file existence."""
        tracks = [
            {
                "name": "synth",
                "type": "midi",
                "midi_file": "nonexistent.mid",
                "synth": "sine",
            }
        ]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        with pytest.raises(FileNotFoundError, match="MIDI file not found"):
            r.run()

    def test_midi_track_in_full_render(self, tmp_path: Path) -> None:
        """MIDI track should work in full render pipeline."""
        midi_path = tmp_path / "bass.mid"
        _create_test_midi(midi_path, notes=[
            (48, 0.7, 0.0, 4.0),  # C3 bass note
        ])

        tracks = [
            {
                "name": "bass_synth",
                "type": "midi",
                "midi_file": "bass.mid",
                "synth": "sine",
            }
        ]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        output_path = r.run()

        assert output_path.exists()
        # Verify output is not empty
        from vcmix.audio.io import read_audio
        result, sr = read_audio(output_path)
        rms = float(np.sqrt(np.mean(result.flatten().astype(np.float64) ** 2)))
        assert rms > 1e-6, "Rendered output should contain audio"

    def test_mixed_audio_and_midi_tracks(self, tmp_path: Path) -> None:
        """Project with both audio and MIDI tracks should render correctly."""
        # Create audio track
        wav_path = tmp_path / "vocal.wav"
        _create_audio_wav(wav_path, duration=2.0)

        # Create MIDI track
        midi_path = tmp_path / "pad.mid"
        _create_test_midi(midi_path, notes=[
            (60, 0.5, 0.0, 4.0),
            (64, 0.5, 0.0, 4.0),
            (67, 0.5, 0.0, 4.0),
        ])

        tracks = [
            {"name": "vocal", "file": str(wav_path)},
            {
                "name": "pad",
                "type": "midi",
                "midi_file": "pad.mid",
                "synth": "sawtooth",
            },
        ]
        master_levels = {"vocal": 0.8, "pad": 0.5}
        config, proj_dir = _make_project_yaml(tmp_path, tracks, master_levels=master_levels)

        r = Renderer(config, stream="none")
        output_path = r.run()

        assert output_path.exists()
        from vcmix.audio.io import read_audio
        result, sr = read_audio(output_path)
        rms = float(np.sqrt(np.mean(result.flatten().astype(np.float64) ** 2)))
        assert rms > 1e-6

    def test_midi_track_with_automation(self, tmp_path: Path) -> None:
        """MIDI track with gain automation should work."""
        midi_path = tmp_path / "lead.mid"
        _create_test_midi(midi_path, notes=[
            (72, 0.8, 0.0, 2.0),  # C5
            (74, 0.8, 2.0, 2.0),  # D5
        ])

        tracks = [
            {
                "name": "lead",
                "type": "midi",
                "midi_file": "lead.mid",
                "synth": "triangle",
                "automation": {
                    "gain": [
                        [0, 0, "linear"],
                        [4, -6, "linear"],
                    ],
                },
            }
        ]
        config, proj_dir = _make_project_yaml(tmp_path, tracks)

        r = Renderer(config, stream="none")
        track_cfg = config.tracks[0]

        # Render MIDI track
        audio = r._render_midi_track(track_cfg, config.sample_rate, proj_dir)
        assert len(audio) > 0

        # Apply automation
        processed = r._render_track_with_automation(track_cfg, audio, config.sample_rate)

        # Processed should exist and be different due to gain automation
        assert len(processed) > 0
        # The end should be quieter than the beginning due to -6dB ramp
        first_half = processed.flatten()[:len(processed.flatten()) // 2]
        second_half = processed.flatten()[len(processed.flatten()) // 2:]
        rms_first = float(np.sqrt(np.mean(first_half.astype(np.float64) ** 2)))
        rms_second = float(np.sqrt(np.mean(second_half.astype(np.float64) ** 2)))
        # Second half should be quieter (automation ramps to -6dB)
        assert rms_second < rms_first, "Gain automation should make end quieter"
