"""
analysis_service.py — Audio analysis service for VCMix AI Agent API (Phase 11).

Provides comprehensive audio analysis data for AI Agents:
    - RMS/Peak/LUFS/True Peak per track
    - Frequency spectrum band energy
    - Sibilance ratio detection
    - Dynamic range measurement
    - Per-track and master bus analysis

Uses the existing Analyzer and Meter from the VCMix engine.

Usage:
    from vcmix.web.analysis_service import AnalysisService
    svc = AnalysisService()
    report = svc.analyze_project(yaml_path)
    track_report = svc.analyze_track(yaml_path, "vocal")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from vcmix.audio.io import read_audio
from vcmix.audio.meter import Meter
from vcmix.config.parser import parse_project
from vcmix.engine.analyzer import Analyzer


class AnalysisService:
    """
    Audio analysis service.

    Provides both per-track and project-level analysis.
    When audio files are not available (e.g., project not yet rendered),
    returns placeholder analysis from the YAML config structure.
    """

    def __init__(self) -> None:
        self._analyzer = Analyzer()
        self._meter = Meter()

    def analyze_project(self, yaml_path: Path | str) -> dict[str, Any]:
        """
        Analyze all tracks in a project.

        Args:
            yaml_path: Path to the YAML project file.

        Returns:
            Dict with per-track analysis and master summary.
        """
        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Project file not found: {yaml_path}")

        config = parse_project(yaml_path)
        project_dir = yaml_path.parent.resolve()
        sr = config.sample_rate

        track_analyses: list[dict[str, Any]] = []
        for track in config.tracks:
            track_type = getattr(track, "type", "audio")
            if track_type == "audio":
                analysis = self._analyze_audio_track(track, project_dir, sr)
            elif track_type == "midi":
                analysis = self._analyze_midi_track(track, config.bpm)
            elif track_type == "sampler":
                analysis = self._analyze_sampler_track(track, sr)
            else:
                analysis = self._placeholder_track(track.name, track_type)
            track_analyses.append(analysis)

        # Compute master analysis from rendered output if available
        master_analysis = self._analyze_master_output(config, project_dir, sr)

        return {
            "project": config.name,
            "bpm": config.bpm,
            "sample_rate": sr,
            "tracks": track_analyses,
            "master": master_analysis,
        }

    def analyze_track(
        self, yaml_path: Path | str, track_name: str
    ) -> dict[str, Any]:
        """
        Analyze a single track.

        Args:
            yaml_path: Path to the YAML project file.
            track_name: Name of the track to analyze.

        Returns:
            Track analysis dict.

        Raises:
            FileNotFoundError: If track not found.
        """
        yaml_path = Path(yaml_path)
        config = parse_project(yaml_path)
        project_dir = yaml_path.parent.resolve()
        sr = config.sample_rate

        track = None
        for t in config.tracks:
            if t.name == track_name:
                track = t
                break

        if track is None:
            raise FileNotFoundError(f"Track '{track_name}' not found")

        track_type = getattr(track, "type", "audio")
        if track_type == "audio":
            return self._analyze_audio_track(track, project_dir, sr)
        elif track_type == "midi":
            return self._analyze_midi_track(track, config.bpm)
        elif track_type == "sampler":
            return self._analyze_sampler_track(track, sr)
        else:
            return self._placeholder_track(track.name, track_type)

    # ── Private methods ────────────────────────────────────────────────────

    def _analyze_audio_track(
        self, track: Any, project_dir: Path, sr: int
    ) -> dict[str, Any]:
        """Analyze an audio track by reading its file."""
        file_path = project_dir / track.file
        if not file_path.exists():
            return {
                "name": track.name,
                "type": "audio",
                "status": "file_not_found",
                "file": track.file,
                **self._placeholder_metrics(),
            }

        try:
            audio, file_sr = read_audio(file_path)
            effective_sr = file_sr or sr
            return self._compute_full_analysis(track.name, audio, effective_sr, "audio")
        except Exception as e:
            return {
                "name": track.name,
                "type": "audio",
                "status": "error",
                "error": str(e),
                **self._placeholder_metrics(),
            }

    def _analyze_midi_track(self, track: Any, bpm: float) -> dict[str, Any]:
        """Analyze a MIDI track (structural analysis only)."""
        return {
            "name": track.name,
            "type": "midi",
            "synth": getattr(track, "synth", "sine"),
            "midi_file": getattr(track, "midi_file", None),
            "status": "midi_analysis",
            **self._placeholder_metrics(),
        }

    def _analyze_sampler_track(
        self, track: Any, sr: int
    ) -> dict[str, Any]:
        """Analyze a sampler track."""
        zones = getattr(track, "zones", [])
        return {
            "name": track.name,
            "type": "sampler",
            "zone_count": len(zones),
            "status": "sampler_analysis",
            **self._placeholder_metrics(),
        }

    def _analyze_master_output(
        self, config: Any, project_dir: Path, sr: int
    ) -> dict[str, Any]:
        """Analyze the master output file if it exists."""
        output_path = project_dir / config.master.output
        if output_path.exists():
            try:
                audio, file_sr = read_audio(output_path)
                effective_sr = file_sr or sr
                return self._compute_full_analysis("master", audio, effective_sr, "master")
            except Exception:
                pass
        return {
            "name": "master",
            "type": "master",
            "status": "not_rendered",
            **self._placeholder_metrics(),
        }

    def _compute_full_analysis(
        self, name: str, audio: np.ndarray, sr: int, track_type: str
    ) -> dict[str, Any]:
        """Compute full analysis from audio data."""
        rms = self._analyzer.compute_rms(audio)
        peak = self._analyzer.compute_peak(audio)
        true_peak = self._analyzer.compute_true_peak(audio)
        spectrum = self._analyzer.compute_spectrum(audio)
        sibilance = self._analyzer.compute_sibilance(audio)

        rms_db = 20.0 * np.log10(rms) if rms > 0 else -120.0
        peak_db = 20.0 * np.log10(peak) if peak > 0 else -120.0
        true_peak_db = 20.0 * np.log10(true_peak) if true_peak > 0 else -120.0
        dynamic_range_db = peak_db - rms_db

        # LUFS approximation
        lufs = self._meter.lufs(audio)

        return {
            "name": name,
            "type": track_type,
            "status": "analyzed",
            "rms_db": round(rms_db, 2),
            "peak_db": round(peak_db, 2),
            "true_peak_db": round(true_peak_db, 2),
            "lufs": round(lufs, 1),
            "dynamic_range_db": round(dynamic_range_db, 2),
            "sibilance_ratio": round(sibilance, 4),
            "spectrum": spectrum,
        }

    @staticmethod
    def _placeholder_metrics() -> dict[str, Any]:
        """Return placeholder metrics when audio is not available."""
        return {
            "rms_db": -120.0,
            "peak_db": -120.0,
            "true_peak_db": -120.0,
            "lufs": -120.0,
            "dynamic_range_db": 0.0,
            "sibilance_ratio": 0.0,
            "spectrum": {},
        }

    @staticmethod
    def _placeholder_track(name: str, track_type: str) -> dict[str, Any]:
        """Return placeholder for unsupported track types."""
        return {
            "name": name,
            "type": track_type,
            "status": "unsupported",
            "rms_db": -120.0,
            "peak_db": -120.0,
            "true_peak_db": -120.0,
            "lufs": -120.0,
            "dynamic_range_db": 0.0,
            "sibilance_ratio": 0.0,
            "spectrum": {},
        }
