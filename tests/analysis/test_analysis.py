"""
tests/analysis/ — Unit tests for vcmix.analysis module.

Each analysis module has at least 3 tests.
"""

import numpy as np
import pytest

# ── Helper ────────────────────────────────────────────────────────────────

def _sine(freq: float, duration: float = 2.0, sr: int = 44100, amp: float = 0.1) -> np.ndarray:
    """Generate a sine wave. Returns 1D float32 array."""
    t = np.arange(int(sr * duration)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _stereo_sine(freq: float, duration: float = 2.0, sr: int = 44100, amp: float = 0.1) -> np.ndarray:
    """Generate a stereo sine wave. Returns 2D float32 array (2, samples)."""
    mono = _sine(freq, duration, sr, amp)
    return np.stack([mono, mono])


# ── Loudness tests ───────────────────────────────────────────────────────

class TestLoudness:
    """Tests for vcmix.analysis.loudness.LoudnessAnalyzer."""

    def test_lufs_known_signal(self):
        """LUFS for -20dBFS 1kHz sine should be approximately -23 LUFS."""
        from vcmix.analysis.loudness import LoudnessAnalyzer
        analyzer = LoudnessAnalyzer(44100)
        audio = _sine(1000, duration=5.0, amp=0.1)
        result = analyzer.analyze(audio)
        # -20dBFS sine RMS = -23.01 dBFS, LUFS ≈ -23 (K-weighting ~0dB at 1kHz)
        assert -25.0 < result.integrated_lufs < -20.0, f"LUFS={result.integrated_lufs}"

    def test_rms_silence(self):
        """RMS of silence should be very low."""
        from vcmix.analysis.loudness import LoudnessAnalyzer
        analyzer = LoudnessAnalyzer(44100)
        # Use 5 seconds of silence (pyloudnorm needs > 0.4s blocks)
        silence = np.zeros(44100 * 5, dtype=np.float32)
        result = analyzer.analyze(silence)
        assert result.rms_dbfs < -100.0

    def test_dynamic_range_positive(self):
        """Dynamic range should be positive for non-silent audio."""
        from vcmix.analysis.loudness import LoudnessAnalyzer
        analyzer = LoudnessAnalyzer(44100)
        audio = _sine(440, duration=3.0, amp=0.5)
        result = analyzer.analyze(audio)
        # For a sine wave: peak/RMS ≈ 3dB, so DR > 0
        assert result.dynamic_range_db > 0, f"DR={result.dynamic_range_db}"

    def test_stereo_handling(self):
        """Should handle stereo input correctly."""
        from vcmix.analysis.loudness import LoudnessAnalyzer
        analyzer = LoudnessAnalyzer(44100)
        audio = _stereo_sine(440, duration=2.0, amp=0.1)
        result = analyzer.analyze(audio)
        assert result.rms_dbfs > -120.0  # Not silence

    def test_true_peak_near_sample_peak(self):
        """True peak should be near or above sample peak."""
        from vcmix.analysis.loudness import LoudnessAnalyzer
        analyzer = LoudnessAnalyzer(44100)
        audio = _sine(1000, duration=2.0, amp=0.5)
        result = analyzer.analyze(audio)
        # True peak should be within a few dB of expected
        assert result.true_peak_dbfs > -20.0, f"TP={result.true_peak_dbfs}"


# ── Spectrum tests ──────────────────────────────────────────────────────

class TestSpectrum:
    """Tests for vcmix.analysis.spectrum.SpectrumAnalyzer."""

    def test_peak_band_matches_sine(self):
        """Peak band should be near the frequency of a pure sine."""
        from vcmix.analysis.spectrum import SpectrumAnalyzer
        analyzer = SpectrumAnalyzer(44100)
        audio = _sine(250, duration=2.0, amp=0.5)
        result = analyzer.analyze(audio)
        peak = result.peak_band
        assert "250" in peak or "315" in peak or "200" in peak, f"Peak band: {peak}"

    def test_balance_sums_to_one(self):
        """Spectral balance ratios should sum to ~1.0."""
        from vcmix.analysis.spectrum import SpectrumAnalyzer
        analyzer = SpectrumAnalyzer(44100)
        audio = _sine(1000, duration=2.0, amp=0.1)
        result = analyzer.analyze(audio)
        total = sum(result.balance.values())
        assert 0.95 < total < 1.05, f"Balance sum: {total}"

    def test_number_of_bands(self):
        """Should produce correct number of 1/3-octave bands."""
        from vcmix.analysis.spectrum import SpectrumAnalyzer
        analyzer = SpectrumAnalyzer(44100)
        audio = _sine(1000, duration=1.0, amp=0.1)
        result = analyzer.analyze(audio)
        assert len(result.bands) >= 28

    def test_dip_band_identified(self):
        """Dip band should be identified."""
        from vcmix.analysis.spectrum import SpectrumAnalyzer
        analyzer = SpectrumAnalyzer(44100)
        np.random.seed(42)
        noise = np.random.randn(44100 * 2).astype(np.float32) * 0.1
        result = analyzer.analyze(noise)
        assert result.dip_band != ""


# ── BPM tests ──────────────────────────────────────────────────────────

class TestBPM:
    """Tests for vcmix.analysis.bpm.BPMDetector."""

    def test_detects_bpm_from_clicks(self):
        """Should detect BPM from a simple click track."""
        from vcmix.analysis.bpm import BPMDetector
        detector = BPMDetector()
        sr = 44100
        duration = 10.0
        audio = np.zeros(int(sr * duration), dtype=np.float32)
        interval = int(60.0 / 120 * sr)
        for i in range(0, len(audio), interval):
            audio[i:i+100] = 0.8
        result = detector.analyze(audio, sample_rate=sr)
        assert 60 <= result.value <= 160, f"BPM: {result.value}"

    def test_confidence_range(self):
        """Confidence should be between 0 and 1."""
        from vcmix.analysis.bpm import BPMDetector
        detector = BPMDetector()
        sr = 44100
        audio = np.random.randn(sr * 5).astype(np.float32) * 0.1
        result = detector.analyze(audio, sample_rate=sr)
        assert 0.0 <= result.confidence <= 1.0

    def test_silence_handling(self):
        """Should handle silence gracefully."""
        from vcmix.analysis.bpm import BPMDetector
        detector = BPMDetector()
        sr = 44100
        audio = np.zeros(sr * 3, dtype=np.float32)
        result = detector.analyze(audio, sample_rate=sr)
        assert isinstance(result.value, float)


# ── Key detection tests ────────────────────────────────────────────────

class TestKeyDetection:
    """Tests for vcmix.analysis.key_detection.KeyDetector."""

    def test_detects_key_from_scale(self):
        """Should detect key from a scale."""
        from vcmix.analysis.key_detection import KeyDetector
        detector = KeyDetector()
        sr = 44100
        c_major_freqs = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88]
        audio = np.zeros(sr * 8, dtype=np.float32)
        for i, freq in enumerate(c_major_freqs):
            start = i * sr
            end = start + sr
            t = np.arange(sr) / sr
            audio[start:end] = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        result = detector.analyze(audio, sample_rate=sr)
        assert result.tonic in ["C", "G", "F"]  # Related keys are acceptable
        assert result.confidence > 0.0

    def test_profiles_populated(self):
        """All 24 key profiles should be present."""
        from vcmix.analysis.key_detection import KeyDetector
        detector = KeyDetector()
        audio = _sine(440, duration=3.0, amp=0.3)
        result = detector.analyze(audio, sample_rate=44100)
        assert len(result.profiles) == 24
        assert "C_major" in result.profiles
        assert "A_minor" in result.profiles

    def test_pearson_correlation(self):
        """Pearson correlation of identical arrays should be 1.0."""
        from vcmix.analysis.key_detection import KeyDetector
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0])
        corr = KeyDetector._pearson_correlation(x, x)
        assert abs(corr - 1.0) < 0.001, f"Self-correlation: {corr}"


# ── Sibilance tests ────────────────────────────────────────────────────

class TestSibilance:
    """Tests for vcmix.analysis.sibilance.SibilanceDetector."""

    def test_high_freq_has_higher_sibilance(self):
        """High-frequency signal should have higher sibilance than low-frequency."""
        from vcmix.analysis.sibilance import SibilanceDetector
        detector = SibilanceDetector(44100)
        low = _sine(200, duration=2.0, amp=0.5)
        high = _sine(7000, duration=2.0, amp=0.5)
        result_low = detector.analyze(low)
        result_high = detector.analyze(high)
        assert result_high.index > result_low.index

    def test_silence_has_zero_sibilance(self):
        """Silence should have zero sibilance."""
        from vcmix.analysis.sibilance import SibilanceDetector
        detector = SibilanceDetector(44100)
        silence = np.zeros(44100 * 2, dtype=np.float32)
        result = detector.analyze(silence)
        assert result.index == 0.0
        assert result.energy_ratio == 0.0

    def test_sibilance_index_range(self):
        """Sibilance index should be between 0 and 1."""
        from vcmix.analysis.sibilance import SibilanceDetector
        detector = SibilanceDetector(44100)
        audio = _sine(5000, duration=2.0, amp=0.5)
        result = detector.analyze(audio)
        assert 0.0 <= result.index <= 1.0

    def test_peak_freq_in_sibilance_range(self):
        """Peak sibilance frequency should be in 6-8kHz range for 7kHz sine."""
        from vcmix.analysis.sibilance import SibilanceDetector
        detector = SibilanceDetector(44100)
        audio = _sine(7000, duration=2.0, amp=0.5)
        result = detector.analyze(audio)
        assert 6000 <= result.peak_freq <= 8500, f"Peak freq: {result.peak_freq}"


# ── Dynamics tests ─────────────────────────────────────────────────────

class TestDynamics:
    """Tests for vcmix.analysis.dynamics.DynamicsAnalyzer."""

    def test_crest_factor_positive(self):
        """Crest factor should be positive for non-silent audio."""
        from vcmix.analysis.dynamics import DynamicsAnalyzer
        analyzer = DynamicsAnalyzer(44100)
        # Use varying amplitude signal (not pure sine which has near-constant RMS)
        sr = 44100
        t = np.arange(sr * 3) / sr
        # Amplitude-modulated signal
        audio = (0.5 * np.sin(2 * np.pi * 440 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 2 * t))).astype(np.float32)
        result = analyzer.analyze(audio)
        assert result.crest_factor_db >= 0, f"Crest: {result.crest_factor_db}"

    def test_compression_suggestion_has_reason(self):
        """Compression suggestion should include a descriptive reason."""
        from vcmix.analysis.dynamics import DynamicsAnalyzer
        analyzer = DynamicsAnalyzer(44100)
        audio = _sine(1000, duration=3.0, amp=0.3)
        result = analyzer.analyze(audio)
        comp = result.compression_suggestion
        assert len(comp.reason) > 10, f"Reason too short: {comp.reason}"
        assert "dB" in comp.reason or "压缩" in comp.reason

    def test_level_distribution_sums_to_one(self):
        """Level distribution ratios should sum to approximately 1.0."""
        from vcmix.analysis.dynamics import DynamicsAnalyzer
        analyzer = DynamicsAnalyzer(44100)
        audio = _sine(440, duration=3.0, amp=0.3)
        result = analyzer.analyze(audio)
        total = sum(result.level_distribution.values())
        assert 0.9 < total < 1.1, f"Distribution sum: {total}"

    def test_silence_gives_default_suggestion(self):
        """Silent input should give default compression suggestion."""
        from vcmix.analysis.dynamics import DynamicsAnalyzer
        analyzer = DynamicsAnalyzer(44100)
        silence = np.zeros(44100 * 3, dtype=np.float32)
        result = analyzer.analyze(silence)
        assert result.crest_factor_db == 0.0
        assert "默认" in result.compression_suggestion.reason


# ── Report tests ───────────────────────────────────────────────────────

class TestReport:
    """Tests for vcmix.analysis.report.ReportGenerator."""

    def test_json_output_valid(self):
        """JSON output should be valid JSON."""
        import json

        from vcmix.analysis.report import ReportGenerator
        gen = ReportGenerator()
        result = {"file": "test.wav", "duration": 10.0, "sample_rate": 44100}
        output = gen.generate(result, format="json")
        parsed = json.loads(output)
        assert parsed["file"] == "test.wav"

    def test_text_output_has_sections(self):
        """Text output should contain section markers."""
        from vcmix.analysis.report import ReportGenerator
        gen = ReportGenerator()
        result = {
            "file": "test.wav", "duration": 10.0,
            "sample_rate": 44100, "channels": 2,
            "loudness": {"integrated_lufs": -20.0, "rms_dbfs": -22.0,
                        "true_peak_dbfs": -10.0, "dynamic_range_db": 12.0,
                        "loudness_range_lu": 5.0},
        }
        output = gen.generate(result, format="text")
        assert "Loudness" in output
        assert "-20.0" in output

    def test_markdown_output_has_headers(self):
        """Markdown output should contain headers."""
        from vcmix.analysis.report import ReportGenerator
        gen = ReportGenerator()
        result = {
            "file": "test.wav", "duration": 10.0,
            "sample_rate": 44100, "channels": 2,
        }
        output = gen.generate(result, format="markdown")
        assert "# " in output
        assert "test.wav" in output

    def test_invalid_format_raises(self):
        """Invalid format should raise ValueError."""
        from vcmix.analysis.report import ReportGenerator
        gen = ReportGenerator()
        with pytest.raises(ValueError):
            gen.generate({}, format="xml")
