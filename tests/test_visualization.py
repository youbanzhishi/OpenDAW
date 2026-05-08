"""
test_visualization.py — Phase 13 visualization tests for VCMix.

Tests:
    - Waveform data generation and processing
    - FFT spectrum data computation
    - MIDI note data format and generation
    - API endpoint integration
    - Edge cases and error handling

At least 30 tests.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest

# ═══════════════════════════════════════════════════════════════════════
# ── Waveform Data Tests ──────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════


class TestWaveformPeakGeneration:
    """Test waveform peak downsampling logic."""

    def test_generate_peaks_sine(self):
        """Sine wave should produce peaks between 0 and 1."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        sr = 44100
        duration = 2.0
        t = np.linspace(0, duration, int(sr * duration))
        audio = np.sin(2 * np.pi * 440 * t)
        peaks = _generate_waveform_peaks(audio, num_peaks=500)
        assert len(peaks) == 500
        assert all(0.0 <= p <= 1.0 for p in peaks)
        # Sine wave peaks should be close to 1.0
        assert max(peaks) > 0.9

    def test_generate_peaks_silence(self):
        """Silence should produce all-zero peaks."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        audio = np.zeros(44100)
        peaks = _generate_waveform_peaks(audio, num_peaks=100)
        assert len(peaks) == 100
        assert all(p == 0.0 for p in peaks)

    def test_generate_peaks_empty(self):
        """Empty audio should return empty peaks."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        audio = np.array([])
        peaks = _generate_waveform_peaks(audio, num_peaks=100)
        assert peaks == []

    def test_generate_peaks_stereo(self):
        """Stereo audio should be downmixed to mono."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        sr = 44100
        duration = 1.0
        t = np.linspace(0, duration, int(sr * duration))
        # Stereo: left=sine, right=-sine -> downmix ~ 0
        audio = np.stack([np.sin(2 * np.pi * 440 * t), -np.sin(2 * np.pi * 440 * t)])
        peaks = _generate_waveform_peaks(audio, num_peaks=200)
        assert len(peaks) == 200
        # Downmixed anti-phase should be near zero
        assert max(peaks) < 0.1

    def test_generate_peaks_short_audio(self):
        """Audio shorter than num_peaks should return one peak per sample."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        audio = np.array([0.1, 0.5, 0.8, 0.3])
        peaks = _generate_waveform_peaks(audio, num_peaks=10)
        assert len(peaks) == 4
        assert peaks[2] == pytest.approx(1.0)  # max normalized

    def test_generate_peaks_dc_offset(self):
        """DC offset should still normalize properly."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        audio = np.ones(44100) * 0.5  # DC at 0.5
        peaks = _generate_waveform_peaks(audio, num_peaks=100)
        assert all(p == pytest.approx(1.0) for p in peaks)

    def test_generate_peaks_noise(self):
        """White noise should produce roughly uniform peaks."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        rng = np.random.default_rng(42)
        audio = rng.standard_normal(44100) * 0.5
        peaks = _generate_waveform_peaks(audio, num_peaks=500)
        assert len(peaks) == 500
        nonzero_peaks = [p for p in peaks if p > 0]
        assert len(nonzero_peaks) > 400


# ═══════════════════════════════════════════════════════════════════════
# ── FFT Spectrum Tests ───────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════


class TestFFTSpectrum:
    """Test FFT spectrum computation."""

    def test_spectrum_sine_440(self):
        """440Hz sine should have peak at 440Hz bin."""
        from vcmix.web.routes.waveform import _compute_fft_spectrum
        sr = 44100
        duration = 1.0
        t = np.linspace(0, duration, int(sr * duration))
        audio = np.sin(2 * np.pi * 440 * t)
        result = _compute_fft_spectrum(audio, sr, fft_size=4096)

        assert len(result["frequencies"]) > 0
        assert len(result["magnitudes"]) > 0
        assert len(result["frequencies"]) == len(result["magnitudes"])

        peak_idx = np.argmax(result["magnitudes"])
        peak_freq = result["frequencies"][peak_idx]
        assert abs(peak_freq - 440) < 5  # Within 5Hz

    def test_spectrum_empty(self):
        """Empty audio should return empty spectrum."""
        from vcmix.web.routes.waveform import _compute_fft_spectrum
        audio = np.array([])
        result = _compute_fft_spectrum(audio, 44100, 2048)
        assert result["frequencies"] == []
        assert result["magnitudes"] == []
        assert result["rms_db"] == -120.0

    def test_spectrum_levels_sine(self):
        """Sine wave should have known RMS/Peak levels."""
        from vcmix.web.routes.waveform import _compute_fft_spectrum
        sr = 44100
        t = np.linspace(0, 1.0, sr)
        audio = np.sin(2 * np.pi * 1000 * t) * 0.5
        result = _compute_fft_spectrum(audio, sr, 2048)

        assert -12 < result["rms_db"] < -6
        assert -7 < result["peak_db"] < -5

    def test_spectrum_stereo_downmix(self):
        """Stereo audio should be downmixed for spectrum."""
        from vcmix.web.routes.waveform import _compute_fft_spectrum
        sr = 44100
        t = np.linspace(0, 1.0, sr)
        audio = np.stack([np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 880 * t)])
        result = _compute_fft_spectrum(audio, sr, 4096)
        assert len(result["frequencies"]) > 0

    def test_spectrum_full_scale_sine(self):
        """Full-scale sine (1.0) should have peak_db ~ 0dB."""
        from vcmix.web.routes.waveform import _compute_fft_spectrum
        sr = 44100
        t = np.linspace(0, 1.0, sr)
        audio = np.sin(2 * np.pi * 1000 * t)
        result = _compute_fft_spectrum(audio, sr, 2048)
        assert result["peak_db"] > -1.0

    def test_spectrum_lufs_value(self):
        """LUFS should be a reasonable value for known audio."""
        from vcmix.web.routes.waveform import _compute_fft_spectrum
        sr = 44100
        t = np.linspace(0, 2.0, int(2.0 * sr))
        audio = np.sin(2 * np.pi * 1000 * t) * 0.5
        result = _compute_fft_spectrum(audio, sr, 4096)
        assert -30 < result["lufs"] < 0


# ═══════════════════════════════════════════════════════════════════════
# ── MIDI Note Data Tests ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════


class TestMidiNoteData:
    """Test MIDI note data generation and format."""

    def test_demo_midi_generation(self):
        """Demo MIDI data should contain expected notes."""
        from vcmix.web.routes.piano_roll import _generate_demo_midi
        result = _generate_demo_midi(120)
        assert result["bpm"] == 120
        assert result["note_count"] > 0
        assert len(result["notes"]) == result["note_count"]
        assert result["total_beats"] > 0

    def test_demo_midi_note_ranges(self):
        """All demo notes should have valid MIDI values."""
        from vcmix.web.routes.piano_roll import _generate_demo_midi
        result = _generate_demo_midi()
        for note in result["notes"]:
            assert 0 <= note["note"] <= 127
            assert 0 <= note["velocity"] <= 127
            assert note["start_beat"] >= 0
            assert note["duration_beats"] > 0
            assert 0 <= note["channel"] <= 15

    def test_note_to_name_c4(self):
        """MIDI note 60 should be C4."""
        from vcmix.web.routes.piano_roll import _note_to_name
        assert _note_to_name(60) == "C4"

    def test_note_to_name_a4(self):
        """MIDI note 69 should be A4."""
        from vcmix.web.routes.piano_roll import _note_to_name
        assert _note_to_name(69) == "A4"

    def test_note_to_name_c0(self):
        """MIDI note 12 should be C0."""
        from vcmix.web.routes.piano_roll import _note_to_name
        assert _note_to_name(12) == "C0"

    def test_note_to_name_sharp(self):
        """MIDI note 61 should be C#4."""
        from vcmix.web.routes.piano_roll import _note_to_name
        assert _note_to_name(61) == "C#4"

    def test_note_to_name_low(self):
        """MIDI note 0 should be C-1."""
        from vcmix.web.routes.piano_roll import _note_to_name
        assert _note_to_name(0) == "C-1"

    def test_demo_midi_has_chord(self):
        """Demo MIDI should include a chord (multiple notes at same beat)."""
        from collections import Counter

        from vcmix.web.routes.piano_roll import _generate_demo_midi
        result = _generate_demo_midi()
        beat_counts = Counter(n["start_beat"] for n in result["notes"])
        assert any(c >= 3 for c in beat_counts.values())

    def test_demo_midi_has_bass(self):
        """Demo MIDI should include bass notes (low note numbers)."""
        from vcmix.web.routes.piano_roll import _generate_demo_midi
        result = _generate_demo_midi()
        bass_notes = [n for n in result["notes"] if n["note"] < 55]
        assert len(bass_notes) > 0

    def test_demo_midi_total_beats(self):
        """Total beats should equal the last note's end."""
        from vcmix.web.routes.piano_roll import _generate_demo_midi
        result = _generate_demo_midi()
        max_end = max(n["start_beat"] + n["duration_beats"] for n in result["notes"])
        assert abs(result["total_beats"] - max_end) < 0.01


# ═══════════════════════════════════════════════════════════════════════
# ── API Endpoint Tests ───────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════


def _unique_project_name(prefix: str) -> str:
    """Generate a unique project name to avoid collisions."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestVisualizationAPI:
    """Test visualization API endpoints via FastAPI test client."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient

        from vcmix.web.app import create_app
        app = create_app()
        return TestClient(app)

    def test_health_check(self, client):
        """Health endpoint should return ok."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_waveform_project_not_found(self, client):
        """Waveform endpoint should 404 for nonexistent project."""
        resp = client.get("/api/v1/waveform/nonexistent/vocal")
        assert resp.status_code == 404

    def test_spectrum_project_not_found(self, client):
        """Spectrum endpoint should 404 for nonexistent project."""
        resp = client.get("/api/v1/spectrum/nonexistent/vocal")
        assert resp.status_code == 404

    def test_midi_project_not_found(self, client):
        """MIDI endpoint should 404 for nonexistent project."""
        resp = client.get("/api/v1/midi/nonexistent/lead")
        assert resp.status_code == 404

    def test_waveform_track_not_found(self, client):
        """Waveform endpoint should 404 for nonexistent track in valid project."""
        pname = _unique_project_name("viz_tnf")
        resp = client.post("/api/v1/projects", json={
            "name": pname,
            "json_data": {
                "name": "VizTest",
                "bpm": 120,
                "sample_rate": 44100,
                "tracks": [{"name": "vocal", "file": "vocal.wav"}],
                "master": {"levels": {}, "effects": [], "output": "out.wav"},
            },
        })
        assert resp.status_code == 201
        data = resp.json()
        project_id = data["id"]

        resp2 = client.get(f"/api/v1/waveform/{project_id}/nonexistent_track")
        assert resp2.status_code == 404

    def test_waveform_valid_project(self, client):
        """Waveform endpoint should return peak data for valid project/track."""
        pname = _unique_project_name("viz_wf")
        resp = client.post("/api/v1/projects", json={
            "name": pname,
            "json_data": {
                "name": "VizWfTest",
                "bpm": 120,
                "sample_rate": 44100,
                "tracks": [{"name": "vocal", "file": "nonexistent_audio.wav"}],
                "master": {"levels": {}, "effects": [], "output": "out.wav"},
            },
        })
        data = resp.json()
        project_id = data["id"]

        resp2 = client.get(f"/api/v1/waveform/{project_id}/vocal")
        assert resp2.status_code == 200
        result = resp2.json()
        assert "peaks" in result
        assert len(result["peaks"]) > 0
        assert result["sample_rate"] == 44100
        assert result["channels"] >= 1

    def test_spectrum_valid_project(self, client):
        """Spectrum endpoint should return frequency data for valid project/track."""
        pname = _unique_project_name("viz_sp")
        resp = client.post("/api/v1/projects", json={
            "name": pname,
            "json_data": {
                "name": "VizSpTest",
                "bpm": 120,
                "sample_rate": 44100,
                "tracks": [{"name": "vocal", "file": "nonexistent.wav"}],
                "master": {"levels": {}, "effects": [], "output": "out.wav"},
            },
        })
        data = resp.json()
        project_id = data["id"]

        resp2 = client.get(f"/api/v1/spectrum/{project_id}/vocal")
        assert resp2.status_code == 200
        result = resp2.json()
        assert "frequencies" in result
        assert "magnitudes" in result
        assert len(result["frequencies"]) == len(result["magnitudes"])
        assert result["fft_size"] == 2048

    def test_spectrum_custom_fft_size(self, client):
        """Spectrum endpoint should accept custom FFT size."""
        pname = _unique_project_name("viz_fft")
        resp = client.post("/api/v1/projects", json={
            "name": pname,
            "json_data": {
                "name": "VizFFTTest",
                "bpm": 120,
                "sample_rate": 44100,
                "tracks": [{"name": "drums", "file": "nonexistent.wav"}],
                "master": {"levels": {}, "effects": [], "output": "out.wav"},
            },
        })
        data = resp.json()
        project_id = data["id"]

        resp2 = client.get(f"/api/v1/spectrum/{project_id}/drums?fft_size=4096")
        assert resp2.status_code == 200
        result = resp2.json()
        assert result["fft_size"] == 4096

    def test_midi_valid_project(self, client):
        """MIDI endpoint should return note data for valid project/track."""
        pname = _unique_project_name("viz_midi")
        resp = client.post("/api/v1/projects", json={
            "name": pname,
            "json_data": {
                "name": "VizMidiTest",
                "bpm": 120,
                "sample_rate": 44100,
                "tracks": [{"name": "lead", "file": "lead.wav", "type": "audio"}],
                "master": {"levels": {}, "effects": [], "output": "out.wav"},
            },
        })
        data = resp.json()
        project_id = data["id"]

        resp2 = client.get(f"/api/v1/midi/{project_id}/lead")
        assert resp2.status_code == 200
        result = resp2.json()
        assert "notes" in result
        assert result["bpm"] == 120
        assert result["note_count"] > 0

    def test_waveform_num_peaks_param(self, client):
        """Waveform endpoint should respect num_peaks parameter."""
        pname = _unique_project_name("viz_np")
        resp = client.post("/api/v1/projects", json={
            "name": pname,
            "json_data": {
                "name": "VizPeaksTest",
                "bpm": 120,
                "sample_rate": 44100,
                "tracks": [{"name": "vocal", "file": "nonexistent.wav"}],
                "master": {"levels": {}, "effects": [], "output": "out.wav"},
            },
        })
        data = resp.json()
        project_id = data["id"]

        resp2 = client.get(f"/api/v1/waveform/{project_id}/vocal?num_peaks=500")
        assert resp2.status_code == 200
        result = resp2.json()
        assert len(result["peaks"]) == 500


# ═══════════════════════════════════════════════════════════════════════
# ── Edge Case & Integration Tests ────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases in visualization code."""

    def test_peaks_very_short_audio(self):
        """Very short audio (1 sample) should still work."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        audio = np.array([0.5])
        peaks = _generate_waveform_peaks(audio, num_peaks=100)
        assert len(peaks) == 1
        assert peaks[0] == 1.0  # Normalized

    def test_peaks_float32_audio(self):
        """Float32 audio should work without errors."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        audio = np.sin(np.linspace(0, 2 * np.pi, 44100)).astype(np.float32)
        peaks = _generate_waveform_peaks(audio, num_peaks=200)
        assert len(peaks) == 200

    def test_spectrum_very_short_audio(self):
        """Audio shorter than FFT size should be zero-padded."""
        from vcmix.web.routes.waveform import _compute_fft_spectrum
        audio = np.array([1.0, -1.0, 0.5])
        result = _compute_fft_spectrum(audio, 44100, 2048)
        assert len(result["frequencies"]) == 1025  # rfft of 2048

    def test_demo_midi_different_bpm(self):
        """Demo MIDI with different BPM should preserve BPM."""
        from vcmix.web.routes.piano_roll import _generate_demo_midi
        result = _generate_demo_midi(140)
        assert result["bpm"] == 140

    def test_waveform_peaks_clipping(self):
        """Clipped audio (values > 1.0) should still normalize."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        t = np.linspace(0, 1, 44100)
        audio = np.sin(2 * np.pi * 440 * t) * 2.0  # Clipped
        peaks = _generate_waveform_peaks(audio, num_peaks=100)
        assert all(0.0 <= p <= 1.0 for p in peaks)

    def test_spectrum_dc_signal(self):
        """DC signal should have peak at 0Hz."""
        from vcmix.web.routes.waveform import _compute_fft_spectrum
        audio = np.ones(44100) * 0.5
        result = _compute_fft_spectrum(audio, 44100, 2048)
        peak_idx = np.argmax(result["magnitudes"])
        assert result["frequencies"][peak_idx] == pytest.approx(0.0)

    def test_note_to_name_all_12_semitones(self):
        """All 12 semitone names should be covered."""
        from vcmix.web.routes.piano_roll import _note_to_name
        expected = ["C4", "C#4", "D4", "D#4", "E4", "F4", "F#4", "G4", "G#4", "A4", "A#4", "B4"]
        for i, expected_name in enumerate(expected):
            assert _note_to_name(60 + i) == expected_name

    def test_waveform_peaks_num_peaks_boundary(self):
        """num_peaks=1 should return a single peak."""
        from vcmix.web.routes.waveform import _generate_waveform_peaks
        audio = np.sin(np.linspace(0, 2 * np.pi, 44100))
        peaks = _generate_waveform_peaks(audio, num_peaks=1)
        assert len(peaks) == 1
        assert 0 < peaks[0] <= 1.0

    def test_spectrum_negative_audio(self):
        """Negative audio values should work correctly."""
        from vcmix.web.routes.waveform import _compute_fft_spectrum
        t = np.linspace(0, 1, 44100)
        audio = -np.sin(2 * np.pi * 440 * t)
        result = _compute_fft_spectrum(audio, 44100, 4096)
        peak_idx = np.argmax(result["magnitudes"])
        assert abs(result["frequencies"][peak_idx] - 440) < 5
