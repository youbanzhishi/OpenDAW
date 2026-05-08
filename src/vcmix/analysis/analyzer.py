"""
analyzer.py — Main audio analysis engine for VCMix.

Orchestrates all analysis modules:
    - LoudnessAnalyzer
    - SpectrumAnalyzer
    - BPMDetector
    - KeyDetector
    - SibilanceDetector
    - DynamicsAnalyzer
    - ReportGenerator

Supports selective analysis via items parameter:
    analyzer.analyze("file.wav", items=["loudness", "bpm"])

Usage:
    from vcmix.analysis import AudioAnalyzer
    analyzer = AudioAnalyzer()
    result = analyzer.analyze("input.wav")
    result = analyzer.analyze("input.wav", items=["loudness", "key"])
    result = analyzer.analyze("input.wav", duration=20)

Dependencies: numpy, soundfile, vcmix.analysis.*
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import soundfile as sf

from vcmix.analysis.bpm import BPMDetector
from vcmix.analysis.dynamics import DynamicsAnalyzer
from vcmix.analysis.key_detection import KeyDetector
from vcmix.analysis.loudness import LoudnessAnalyzer
from vcmix.analysis.report import ReportGenerator
from vcmix.analysis.sibilance import SibilanceDetector
from vcmix.analysis.spectrum import SpectrumAnalyzer

# All available analysis items
ALL_ITEMS = {"loudness", "spectrum", "bpm", "key", "sibilance", "dynamics"}


class AudioAnalyzer:
    """
    Main audio analysis engine.

    Coordinates all analysis modules and produces unified results.

    Args:
        sample_rate: Default sample rate for analysis.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self._loudness = LoudnessAnalyzer(sample_rate)
        self._spectrum = SpectrumAnalyzer(sample_rate)
        self._bpm = BPMDetector()
        self._key = KeyDetector()
        self._sibilance = SibilanceDetector(sample_rate)
        self._dynamics = DynamicsAnalyzer(sample_rate)
        self._report = ReportGenerator()

    def analyze(
        self,
        path: str | Path,
        items: Sequence[str] | None = None,
        duration: float = 0.0,
        sr: int | None = None,
    ) -> dict[str, Any]:
        """
        Analyze an audio file.

        Args:
            path: Path to audio file.
            items: Analysis items to run. None = all items.
                   Valid: "loudness", "spectrum", "bpm", "key", "sibilance", "dynamics"
            duration: Analysis duration in seconds. 0 = entire file.
            sr: Override sample rate. None = use file's native rate.

        Returns:
            Dict with analysis results.

        Raises:
            FileNotFoundError: If audio file doesn't exist.
            RuntimeError: If analysis fails.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        # Read audio
        audio, file_sr = sf.read(str(path), dtype="float32")
        actual_sr = sr or file_sr

        # Resample if needed
        if actual_sr != file_sr:
            try:
                import librosa
                if audio.ndim == 2:
                    audio = librosa.resample(audio.T, orig_sr=file_sr, target_sr=actual_sr).T
                else:
                    audio = librosa.resample(audio, orig_sr=file_sr, target_sr=actual_sr)
            except ImportError:
                # Proceed with native sample rate
                actual_sr = file_sr

        # Ensure 2D shape (channels, samples)
        if audio.ndim == 1:
            audio = audio.reshape(1, -1)
        else:
            # soundfile returns (samples, channels), transpose to (channels, samples)
            audio = audio.T

        # Truncate duration if specified
        if duration > 0:
            max_samples = int(duration * actual_sr)
            audio = audio[:, :max_samples]

        n_channels = audio.shape[0]
        n_samples = audio.shape[1]
        file_duration = round(n_samples / actual_sr, 1)

        # Determine which items to analyze
        if items is None:
            active_items = ALL_ITEMS
        else:
            active_items = set(items) & ALL_ITEMS
            unknown = set(items) - ALL_ITEMS
            if unknown:
                import warnings
                warnings.warn(f"Unknown analysis items ignored: {unknown}")

        # Run analysis
        result: dict[str, Any] = {
            "file": str(path),
            "duration": file_duration,
            "sample_rate": actual_sr,
            "channels": n_channels,
        }

        if "loudness" in active_items:
            try:
                loudness_result = self._loudness.analyze(audio)
                result["loudness"] = self._loudness.to_dict(loudness_result)
            except Exception as exc:
                result["loudness"] = {"error": str(exc)}

        if "spectrum" in active_items:
            try:
                spectrum_result = self._spectrum.analyze(audio)
                result["spectrum"] = self._spectrum.to_dict(spectrum_result)
            except Exception as exc:
                result["spectrum"] = {"error": str(exc)}

        if "bpm" in active_items:
            try:
                bpm_result = self._bpm.analyze(audio, sample_rate=actual_sr)
                result["bpm"] = self._bpm.to_dict(bpm_result)
            except Exception as exc:
                result["bpm"] = {"error": str(exc)}

        if "key" in active_items:
            try:
                key_result = self._key.analyze(audio, sample_rate=actual_sr)
                result["key"] = self._key.to_dict(key_result)
            except Exception as exc:
                result["key"] = {"error": str(exc)}

        if "sibilance" in active_items:
            try:
                sibilance_result = self._sibilance.analyze(audio)
                result["sibilance"] = self._sibilance.to_dict(sibilance_result)
            except Exception as exc:
                result["sibilance"] = {"error": str(exc)}

        if "dynamics" in active_items:
            try:
                dynamics_result = self._dynamics.analyze(audio)
                result["dynamics"] = self._dynamics.to_dict(dynamics_result)
            except Exception as exc:
                result["dynamics"] = {"error": str(exc)}

        return result

    def format_report(
        self, result: dict[str, Any], format: str = "json"
    ) -> str:
        """
        Format analysis result as report.

        Args:
            result: Analysis result dict.
            format: "json", "text", or "markdown".

        Returns:
            Formatted report string.
        """
        return self._report.generate(result, format=format)
