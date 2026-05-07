"""
smart_mixer.py — Smart mixing closed-loop engine for VCMix (Phase 15).

Implements an iterative render→analyze→diagnose→adjust→re-render→verify
pipeline that automatically optimizes a mix toward target loudness,
spectral balance, and dynamic range targets.

Closed-loop pipeline:
    1. Initial render (or use provided audio)
    2. Analyze output (RMS/Peak/LUFS/spectrum/dynamic range)
    3. Diagnose problems
    4. Adjust parameters (gain/EQ/compression/limiting)
    5. Re-render with adjusted parameters
    6. Verify improvement
    7. Iterate until satisfied or max_iterations reached

Usage:
    from vcmix.ai.smart_mixer import SmartMixer
    mixer = SmartMixer()
    result = mixer.auto_mix("project.yaml", max_iterations=3)
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vcmix.engine.analyzer import Analyzer
from vcmix.audio.meter import Meter


# ── Target thresholds ────────────────────────────────────────────────────

_MASTER_TARGET_LUFS = -14.0
_MASTER_PEAK_CEILING = -1.0
_VOCAL_TARGET_RMS_DB = -18.0
_ACCOMP_TARGET_RMS_DB = -24.0
_DRUM_TARGET_PEAK_DB = -6.0
_LOW_FREQ_BUILDUP_RATIO = 0.15
_HIGH_FREQ_HARSH_THRESHOLD = 0.25
_DYNAMIC_RANGE_MIN = 3.0
_DYNAMIC_RANGE_MAX = 18.0
_SIBILANCE_THRESHOLD = 0.12

# Vocal track name patterns
_VOCAL_PATTERNS = ("vocal", "vox", "voice", "lead", "bgv", "choir")
_DRUM_PATTERNS = ("drum", "kick", "snare", "hihat", "cymbal", "perc")
_BASS_PATTERNS = ("bass", "808", "sub")


# ── Data structures ─────────────────────────────────────────────────────

@dataclass
class AudioAnalysis:
    """Analysis result for a rendered audio output.

    Attributes:
        rms_db: Overall RMS level in dBFS.
        peak_db: Sample peak in dBFS.
        true_peak_db: True peak in dBFS.
        lufs: Estimated LUFS (simplified).
        dynamic_range_db: Peak - RMS in dB.
        spectrum: Band energy dict (sub/low/mid/high_mid/high/air).
        sibilance: Sibilance energy ratio (0-1).
        low_freq_buildup: Low-frequency energy ratio.
        high_freq_harsh: High-frequency energy ratio.
    """

    rms_db: float = -120.0
    peak_db: float = -120.0
    true_peak_db: float = -120.0
    lufs: float = -120.0
    dynamic_range_db: float = 0.0
    spectrum: dict[str, float] = field(default_factory=dict)
    sibilance: float = 0.0
    low_freq_buildup: float = 0.0
    high_freq_harsh: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "rms_db": round(self.rms_db, 2),
            "peak_db": round(self.peak_db, 2),
            "true_peak_db": round(self.true_peak_db, 2),
            "lufs": round(self.lufs, 2),
            "dynamic_range_db": round(self.dynamic_range_db, 2),
            "spectrum": {k: round(v, 4) for k, v in self.spectrum.items()},
            "sibilance": round(self.sibilance, 4),
            "low_freq_buildup": round(self.low_freq_buildup, 4),
            "high_freq_harsh": round(self.high_freq_harsh, 4),
        }


@dataclass
class Diagnosis:
    """A diagnosed mixing problem.

    Attributes:
        target: Where the problem is (e.g. 'master', 'track:Vocal').
        problem: Description of the problem.
        severity: Severity level (1=critical, 2=important, 3=suggested).
        action: Recommended action type.
        params: Parameters for the action.
    """

    target: str
    problem: str
    severity: int = 3
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "target": self.target,
            "problem": self.problem,
            "severity": self.severity,
            "action": self.action,
            "params": self.params,
        }


@dataclass
class IterationResult:
    """Result of a single smart mixing iteration.

    Attributes:
        iteration: Iteration number (1-indexed).
        analysis_before: Analysis before adjustments.
        analysis_after: Analysis after adjustments (if re-rendered).
        diagnoses: List of diagnosed problems.
        adjustments: Parameter adjustments made.
        improved: Whether the mix improved.
    """

    iteration: int
    analysis_before: AudioAnalysis = field(default_factory=AudioAnalysis)
    analysis_after: AudioAnalysis = field(default_factory=AudioAnalysis)
    diagnoses: list[Diagnosis] = field(default_factory=list)
    adjustments: dict[str, Any] = field(default_factory=dict)
    improved: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "iteration": self.iteration,
            "analysis_before": self.analysis_before.to_dict(),
            "analysis_after": self.analysis_after.to_dict(),
            "diagnoses": [d.to_dict() for d in self.diagnoses],
            "adjustments": self.adjustments,
            "improved": self.improved,
        }


@dataclass
class SmartMixResult:
    """Complete result of smart mixing closed-loop.

    Attributes:
        project_config: Final (adjusted) VCMix project configuration.
        iterations: Per-iteration results.
        total_iterations: Number of iterations executed.
        converged: Whether the mix converged to targets.
        initial_analysis: Analysis of the initial render.
        final_analysis: Analysis of the final render.
        total_time_sec: Total processing time.
    """

    project_config: dict[str, Any] = field(default_factory=dict)
    iterations: list[IterationResult] = field(default_factory=list)
    total_iterations: int = 0
    converged: bool = False
    initial_analysis: AudioAnalysis = field(default_factory=AudioAnalysis)
    final_analysis: AudioAnalysis = field(default_factory=AudioAnalysis)
    total_time_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "total_iterations": self.total_iterations,
            "converged": self.converged,
            "initial_analysis": self.initial_analysis.to_dict(),
            "final_analysis": self.final_analysis.to_dict(),
            "iterations": [itr.to_dict() for itr in self.iterations],
            "total_time_sec": round(self.total_time_sec, 3),
        }


# ── SmartMixer class ────────────────────────────────────────────────────

class SmartMixer:
    """Smart mixing closed-loop engine.

    Iteratively analyzes, diagnoses, and adjusts a mix to meet
    target loudness, spectral balance, and dynamic range criteria.
    """

    def __init__(self, sample_rate: int = 44100, target_lufs: float = _MASTER_TARGET_LUFS) -> None:
        self.sample_rate = sample_rate
        self.target_lufs = target_lufs
        self._analyzer = Analyzer(sample_rate=sample_rate)
        self._meter = Meter(sample_rate=sample_rate)

    def auto_mix(
        self,
        project_config: dict[str, Any] | str,
        max_iterations: int = 3,
        render_fn: Any | None = None,
    ) -> SmartMixResult:
        """
        Run the smart mixing closed-loop.

        Args:
            project_config: VCMix project config dict or YAML file path.
            max_iterations: Maximum number of adjustment iterations.
            render_fn: Optional render function (config → audio_array).
                      If None, uses mock render for testing.

        Returns:
            SmartMixResult with iteration details and final config.
        """
        start_time = time.time()

        # Load config if path provided
        if isinstance(project_config, str):
            project_config = self._load_config(project_config)

        config = copy.deepcopy(project_config)
        result = SmartMixResult(project_config=config)

        # Initial analysis (from config structure)
        initial_audio = self._render_or_mock(config, render_fn)
        initial_analysis = self._analyze_output(initial_audio)
        result.initial_analysis = initial_analysis

        current_analysis = initial_analysis

        for i in range(1, max_iterations + 1):
            iteration = IterationResult(iteration=i)
            iteration.analysis_before = current_analysis

            # Diagnose
            diagnoses = self._diagnose(current_analysis, config)
            iteration.diagnoses = diagnoses

            if not diagnoses:
                # No problems found — converged!
                iteration.improved = True
                result.iterations.append(iteration)
                result.converged = True
                break

            # Adjust parameters
            adjustments = self._adjust_parameters(config, diagnoses)
            iteration.adjustments = adjustments

            # Re-render (or mock)
            new_audio = self._render_or_mock(config, render_fn)
            new_analysis = self._analyze_output(new_audio)
            iteration.analysis_after = new_analysis

            # Verify improvement
            improved = self._verify_improvement(current_analysis, new_analysis)
            iteration.improved = improved

            result.iterations.append(iteration)
            current_analysis = new_analysis

        result.final_analysis = current_analysis
        result.project_config = config
        result.total_iterations = len(result.iterations)
        result.total_time_sec = time.time() - start_time

        # Check if converged
        if not result.converged and result.iterations:
            last = result.iterations[-1]
            if last.improved and not last.diagnoses:
                result.converged = True

        return result

    def _load_config(self, path: str) -> dict[str, Any]:
        """Load a VCMix YAML config from file path."""
        import yaml
        from pathlib import Path
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        content = p.read_text(encoding="utf-8")
        return yaml.safe_load(content)

    def _render_or_mock(
        self, config: dict[str, Any], render_fn: Any | None
    ) -> np.ndarray:
        """Render audio or generate a mock for analysis."""
        if render_fn is not None:
            return render_fn(config)

        # Mock: generate a short audio signal from config parameters
        duration_sec = config.get("duration", 30)
        sr = self.sample_rate
        samples = int(duration_sec * sr)

        # Use BPM and energy to shape the mock signal
        bpm = config.get("bpm", 120)
        freq_base = bpm / 60.0 * 4.0  # Fundamental frequency based on BPM

        t = np.linspace(0, duration_sec, samples, dtype=np.float64)

        # Build a composite signal from track volumes
        total_volume = 0.0
        track_count = 0
        for track in config.get("tracks", []):
            vol = track.get("volume", 0.7)
            total_volume += vol
            track_count += 1

        avg_volume = total_volume / max(track_count, 1)

        # Generate composite signal
        signal = np.zeros(samples, dtype=np.float64)
        signal += avg_volume * 0.3 * np.sin(2 * np.pi * freq_base * t)        # Fundamental
        signal += avg_volume * 0.15 * np.sin(2 * np.pi * freq_base * 2 * t)   # Harmonic
        signal += avg_volume * 0.1 * np.sin(2 * np.pi * freq_base * 3 * t)    # Harmonic
        signal += avg_volume * 0.05 * np.sin(2 * np.pi * freq_base * 5 * t)   # Harmonic

        # Add noise floor
        rng = np.random.RandomState(42)
        signal += 0.001 * rng.randn(samples)

        # Apply arrangement energy curve
        arrangement = config.get("arrangement", [])
        if arrangement:
            for section in arrangement:
                start_bar = sum(s.get("duration_bars", 8) for s in arrangement[:arrangement.index(section)])
                start_sample = int(start_bar * (60.0 / bpm) * 4 * sr)
                end_bar = start_bar + section.get("duration_bars", 8)
                end_sample = min(int(end_bar * (60.0 / bpm) * 4 * sr), samples)
                if start_sample < samples:
                    energy = section.get("energy", 0.5)
                    signal[start_sample:end_sample] *= energy

        # Normalize to prevent clipping
        peak = np.max(np.abs(signal))
        if peak > 0.9:
            signal *= 0.9 / peak

        return signal.astype(np.float32)

    def _analyze_output(self, audio: np.ndarray) -> AudioAnalysis:
        """Analyze a rendered audio output."""
        if len(audio) == 0:
            return AudioAnalysis()

        # Ensure mono for analysis
        if audio.ndim == 2:
            audio = np.mean(audio, axis=1)

        # Basic measurements
        rms = self._analyzer.compute_rms(audio)
        peak = self._analyzer.compute_peak(audio)
        true_peak = self._analyzer.compute_true_peak(audio)

        # Convert to dB
        rms_db = 20.0 * np.log10(rms) if rms > 1e-10 else -120.0
        peak_db = 20.0 * np.log10(peak) if peak > 1e-10 else -120.0
        true_peak_db = 20.0 * np.log10(true_peak) if true_peak > 1e-10 else -120.0

        # Dynamic range
        dynamic_range_db = peak_db - rms_db if rms_db > -120.0 else 0.0

        # Simplified LUFS estimation (RMS-based approximation)
        # Real LUFS requires K-weighting; this is an approximation
        lufs = rms_db - 0.691  # Rough offset for LUFS ≈ RMS - 0.7

        # Spectral analysis
        spectrum = self._analyzer.compute_spectrum(audio) if hasattr(self._analyzer, 'compute_spectrum') else {}
        if not spectrum:
            # Fallback: basic FFT band analysis
            spectrum = self._basic_spectrum(audio)

        # Sibilance
        sibilance = self._analyzer.compute_sibilance(audio) if hasattr(self._analyzer, 'compute_sibilance') else 0.0

        # Low frequency buildup
        total = sum(spectrum.values()) if spectrum else 1.0
        low_freq_buildup = (spectrum.get("sub", 0.0) + spectrum.get("low", 0.0)) / total if total > 1e-10 else 0.0

        # High frequency harshness
        high_freq_harsh = (spectrum.get("high_mid", 0.0) + spectrum.get("high", 0.0)) / total if total > 1e-10 else 0.0

        return AudioAnalysis(
            rms_db=rms_db,
            peak_db=peak_db,
            true_peak_db=true_peak_db,
            lufs=lufs,
            dynamic_range_db=dynamic_range_db,
            spectrum=spectrum,
            sibilance=sibilance,
            low_freq_buildup=low_freq_buildup,
            high_freq_harsh=high_freq_harsh,
        )

    def _basic_spectrum(self, audio: np.ndarray) -> dict[str, float]:
        """Basic FFT-based band energy analysis."""
        if len(audio) < 256:
            return {"sub": 0.0, "low": 0.0, "mid": 0.0, "high_mid": 0.0, "high": 0.0, "air": 0.0}

        # Apply window
        windowed = audio * np.hanning(len(audio))

        # FFT
        fft = np.abs(np.fft.rfft(windowed.astype(np.float64)))
        n_bins = len(fft)
        sr = self.sample_rate
        bin_hz = sr / (2 * n_bins)

        # Band boundaries (in bins)
        sub_end = max(1, int(60 / bin_hz))       # 0-60 Hz
        low_end = max(sub_end + 1, int(250 / bin_hz))    # 60-250 Hz
        mid_end = max(low_end + 1, int(2000 / bin_hz))   # 250-2000 Hz
        high_mid_end = max(mid_end + 1, int(6000 / bin_hz))  # 2-6 kHz
        high_end = max(high_mid_end + 1, int(12000 / bin_hz))  # 6-12 kHz
        # air: 12+ kHz

        def band_energy(end1: int, end2: int) -> float:
            s = max(0, end1)
            e = min(end2, n_bins)
            if s >= e:
                return 0.0
            return float(np.mean(fft[s:e] ** 2))

        return {
            "sub": band_energy(0, sub_end),
            "low": band_energy(sub_end, low_end),
            "mid": band_energy(low_end, mid_end),
            "high_mid": band_energy(mid_end, high_mid_end),
            "high": band_energy(high_mid_end, high_end),
            "air": band_energy(high_end, n_bins),
        }

    def _diagnose(
        self, analysis: AudioAnalysis, config: dict[str, Any]
    ) -> list[Diagnosis]:
        """Diagnose mixing problems based on analysis and config."""
        diagnoses: list[Diagnosis] = []

        # ── Master-level problems ──

        # LUFS too low/high
        if analysis.lufs > -120.0:
            lufs_delta = self.target_lufs - analysis.lufs
            if abs(lufs_delta) > 2.0:
                direction = "low" if lufs_delta > 0 else "high"
                diagnoses.append(Diagnosis(
                    target="master",
                    problem=f"Master LUFS {analysis.lufs:.1f} is too {direction} (target: {self.target_lufs})",
                    severity=1,
                    action="gain",
                    params={"gain_db": round(lufs_delta, 1)},
                ))

        # True peak exceeds ceiling
        if analysis.true_peak_db > _MASTER_PEAK_CEILING:
            diagnoses.append(Diagnosis(
                target="master",
                problem=f"True peak {analysis.true_peak_db:.1f}dB exceeds ceiling {_MASTER_PEAK_CEILING}dB",
                severity=1,
                action="limiter",
                params={"ceiling": _MASTER_PEAK_CEILING},
            ))

        # Dynamic range issues
        if analysis.dynamic_range_db > _DYNAMIC_RANGE_MAX:
            diagnoses.append(Diagnosis(
                target="master",
                problem=f"Dynamic range {analysis.dynamic_range_db:.1f}dB is too wide (max: {_DYNAMIC_RANGE_MAX}dB)",
                severity=2,
                action="compressor",
                params={"threshold_db": -20, "ratio": 3, "attack_ms": 10, "release_ms": 100},
            ))
        elif analysis.dynamic_range_db < _DYNAMIC_RANGE_MIN and analysis.dynamic_range_db > 0:
            diagnoses.append(Diagnosis(
                target="master",
                problem=f"Dynamic range {analysis.dynamic_range_db:.1f}dB is too narrow (min: {_DYNAMIC_RANGE_MIN}dB)",
                severity=2,
                action="reduce_compression",
                params={"ratio_adjust": -1},
            ))

        # Low frequency buildup
        if analysis.low_freq_buildup > _LOW_FREQ_BUILDUP_RATIO:
            diagnoses.append(Diagnosis(
                target="master",
                problem=f"Low-frequency buildup detected (ratio: {analysis.low_freq_buildup:.2f})",
                severity=2,
                action="eq",
                params={"low_cut_hz": 40, "low_shelf_db": -2},
            ))

        # High frequency harshness
        if analysis.high_freq_harsh > _HIGH_FREQ_HARSH_THRESHOLD:
            diagnoses.append(Diagnosis(
                target="master",
                problem=f"High-frequency harshness detected (ratio: {analysis.high_freq_harsh:.2f})",
                severity=2,
                action="eq",
                params={"high_shelf_db": -2, "high_shelf_hz": 6000},
            ))

        # ── Track-level problems (based on config structure) ──
        for track in config.get("tracks", []):
            track_name = track.get("name", "").lower()
            volume = track.get("volume", 0.7)

            # Vocal tracks: check if too quiet
            if any(p in track_name for p in _VOCAL_PATTERNS):
                if volume < 0.6:
                    diagnoses.append(Diagnosis(
                        target=f"track:{track.get('name', '')}",
                        problem=f"Vocal track volume {volume:.2f} is too low",
                        severity=1,
                        action="gain",
                        params={"gain_db": 3.0},
                    ))

            # Drum tracks: check peak
            if any(p in track_name for p in _DRUM_PATTERNS):
                if volume > 0.9:
                    diagnoses.append(Diagnosis(
                        target=f"track:{track.get('name', '')}",
                        problem=f"Drum track volume {volume:.2f} may cause peaks",
                        severity=2,
                        action="gain",
                        params={"gain_db": -2.0},
                    ))

            # Bass tracks: check for low buildup
            if any(p in track_name for p in _BASS_PATTERNS):
                effects = track.get("effects", [])
                has_low_cut = any(
                    e.get("name") == "vc-eq" and e.get("params", {}).get("low_cut_hz", 0) > 0
                    for e in effects
                )
                if not has_low_cut:
                    diagnoses.append(Diagnosis(
                        target=f"track:{track.get('name', '')}",
                        problem="Bass track missing high-pass filter",
                        severity=3,
                        action="eq",
                        params={"low_cut_hz": 30},
                    ))

        # Sibilance
        if analysis.sibilance > _SIBILANCE_THRESHOLD:
            # Find vocal tracks
            vocal_tracks = [
                t for t in config.get("tracks", [])
                if any(p in t.get("name", "").lower() for p in _VOCAL_PATTERNS)
            ]
            for vt in vocal_tracks:
                effects = vt.get("effects", [])
                has_deesser = any(e.get("name") == "vc-deesser" for e in effects)
                if not has_deesser:
                    diagnoses.append(Diagnosis(
                        target=f"track:{vt.get('name', '')}",
                        problem=f"Sibilance detected (ratio: {analysis.sibilance:.2f})",
                        severity=2,
                        action="deesser",
                        params={"threshold": -35, "reduction": -6},
                    ))

        return diagnoses

    def _adjust_parameters(
        self, config: dict[str, Any], diagnoses: list[Diagnosis]
    ) -> dict[str, Any]:
        """Apply diagnosis-based adjustments to the project config.

        Returns a summary of all adjustments made.
        """
        adjustments: dict[str, Any] = {"applied": []}

        for diag in diagnoses:
            target = diag.target
            action = diag.action
            params = diag.params

            if target == "master":
                self._apply_master_adjustment(config, action, params)
            elif target.startswith("track:"):
                track_name = target.split(":", 1)[1]
                self._apply_track_adjustment(config, track_name, action, params)

            adjustments["applied"].append({
                "target": target,
                "action": action,
                "params": params,
            })

        return adjustments

    def _apply_master_adjustment(
        self, config: dict[str, Any], action: str, params: dict[str, Any]
    ) -> None:
        """Apply an adjustment to the master section (in-place)."""
        master = config.setdefault("master", {})
        effects = master.setdefault("effects", [])

        if action == "gain":
            gain_db = params.get("gain_db", 0.0)
            # Adjust all track volumes proportionally
            for track in config.get("tracks", []):
                old_vol = track.get("volume", 0.7)
                track["volume"] = round(min(1.0, max(0.0, old_vol * (10.0 ** (gain_db / 20.0)))), 4)

        elif action == "limiter":
            has_limiter = any(e.get("name") == "vc-limiter" for e in effects)
            if has_limiter:
                for e in effects:
                    if e.get("name") == "vc-limiter":
                        e.setdefault("params", {})["ceiling"] = params.get("ceiling", -1.0)
            else:
                effects.append({
                    "name": "vc-limiter",
                    "params": {"ceiling": params.get("ceiling", -1.0)},
                })

        elif action == "compressor":
            has_comp = any(e.get("name") == "vc-comp" for e in effects)
            if not has_comp:
                effects.append({
                    "name": "vc-comp",
                    "params": {
                        "threshold": params.get("threshold_db", -20),
                        "ratio": params.get("ratio", 3),
                        "attack": params.get("attack_ms", 10),
                        "release": params.get("release_ms", 100),
                    },
                })

        elif action == "reduce_compression":
            for e in effects:
                if e.get("name") == "vc-comp":
                    ratio = e.get("params", {}).get("ratio", 3)
                    e.setdefault("params", {})["ratio"] = max(1, ratio - 1)

        elif action == "eq":
            has_eq = any(e.get("name") == "vc-eq" for e in effects)
            if has_eq:
                for e in effects:
                    if e.get("name") == "vc-eq":
                        e.setdefault("params", {}).update(params)
            else:
                effects.append({"name": "vc-eq", "params": params})

    def _apply_track_adjustment(
        self, config: dict[str, Any], track_name: str, action: str, params: dict[str, Any]
    ) -> None:
        """Apply an adjustment to a specific track (in-place)."""
        tracks = config.get("tracks", [])
        track_cfg = None
        for t in tracks:
            if t.get("name") == track_name:
                track_cfg = t
                break

        if track_cfg is None:
            return

        effects = track_cfg.setdefault("effects", [])

        if action == "gain":
            gain_db = params.get("gain_db", 0.0)
            old_vol = track_cfg.get("volume", 0.7)
            track_cfg["volume"] = round(min(1.0, max(0.0, old_vol * (10.0 ** (gain_db / 20.0)))), 4)

        elif action == "limiter":
            has_limiter = any(e.get("name") == "vc-limiter" for e in effects)
            if not has_limiter:
                effects.append({"name": "vc-limiter", "params": {"ceiling": params.get("ceiling", -1)}})

        elif action == "compressor":
            has_comp = any(e.get("name") == "vc-comp" for e in effects)
            if not has_comp:
                effects.append({
                    "name": "vc-comp",
                    "params": {
                        "threshold": params.get("threshold_db", -20),
                        "ratio": params.get("ratio", 3),
                        "attack": params.get("attack_ms", 5),
                        "release": params.get("release_ms", 50),
                    },
                })

        elif action == "deesser":
            has_deesser = any(e.get("name") == "vc-deesser" for e in effects)
            if not has_deesser:
                effects.append({
                    "name": "vc-deesser",
                    "params": {
                        "threshold": params.get("threshold", -35),
                        "reduction": params.get("reduction", -6),
                    },
                })

        elif action == "eq":
            has_eq = any(e.get("name") == "vc-eq" for e in effects)
            if has_eq:
                for e in effects:
                    if e.get("name") == "vc-eq":
                        e.setdefault("params", {}).update(params)
            else:
                effects.append({"name": "vc-eq", "params": params})

    def _verify_improvement(
        self, before: AudioAnalysis, after: AudioAnalysis
    ) -> bool:
        """Verify whether the mix improved after adjustments.

        Checks:
            1. LUFS closer to target
            2. True peak within ceiling
            3. Dynamic range in acceptable range
            4. Less low-frequency buildup
        """
        improvements = 0
        total_checks = 0

        # LUFS improvement
        if before.lufs > -120.0 and after.lufs > -120.0:
            total_checks += 1
            delta_before = abs(before.lufs - self.target_lufs)
            delta_after = abs(after.lufs - self.target_lufs)
            if delta_after < delta_before:
                improvements += 1

        # True peak improvement
        if before.true_peak_db > _MASTER_PEAK_CEILING:
            total_checks += 1
            if after.true_peak_db <= _MASTER_PEAK_CEILING:
                improvements += 1
            elif after.true_peak_db < before.true_peak_db:
                improvements += 1

        # Dynamic range improvement
        if before.dynamic_range_db > _DYNAMIC_RANGE_MAX or before.dynamic_range_db < _DYNAMIC_RANGE_MIN:
            total_checks += 1
            if _DYNAMIC_RANGE_MIN <= after.dynamic_range_db <= _DYNAMIC_RANGE_MAX:
                improvements += 1
            elif abs(after.dynamic_range_db - (before.dynamic_range_db + _DYNAMIC_RANGE_MIN) / 2) < \
                 abs(before.dynamic_range_db - (before.dynamic_range_db + _DYNAMIC_RANGE_MIN) / 2):
                improvements += 1

        # Low-frequency improvement
        if before.low_freq_buildup > _LOW_FREQ_BUILDUP_RATIO:
            total_checks += 1
            if after.low_freq_buildup < before.low_freq_buildup:
                improvements += 1

        # If no checks were applicable, consider it improved
        if total_checks == 0:
            return True

        return improvements > total_checks / 2
