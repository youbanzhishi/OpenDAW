"""
transcription.py — AI transcription pipeline for VCMix (Phase 17).

Implements the complete "AI扒带" (transcription) pipeline:
    1. Demucs source separation (vocals/drums/bass/other)
    2. Per-stem reverse mixing analysis (EQ/compression/reverb/delay/pan)
    3. Arrangement structure analysis (sections + instrument entries/exits)
    4. Key detection (Krumhansl-Schmuckler algorithm)
    5. BPM detection (onset detection + autocorrelation)
    6. Generate VCMix project configuration
    7. Output complete project to output_dir

Usage:
    from vcmix.ai.transcription import AITranscription
    transcriber = AITranscription()
    result = transcriber.transcribe("reference.wav", "output_project/")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from vcmix.ai.music_theory import detect_key as ks_detect_key
from vcmix.engine.analyzer import Analyzer
from vcmix.separation.reverse_analyzer import ReverseMixAnalyzer

# ── Data structures ─────────────────────────────────────────────────────

@dataclass
class BPMInfo:
    """Detected BPM information."""
    bpm: float = 120.0
    confidence: float = 0.0
    method: str = "onset_autocorrelation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bpm": round(self.bpm, 1),
            "confidence": round(self.confidence, 4),
            "method": self.method,
        }


@dataclass
class KeyInfo:
    """Detected musical key information."""
    root: str = "C"
    scale_type: str = "major"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "scale_type": self.scale_type,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class ArrangementSection:
    """A detected section in the arrangement."""
    name: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    energy: float = 0.5
    active_stems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_sec": round(self.start_sec, 2),
            "end_sec": round(self.end_sec, 2),
            "energy": round(self.energy, 3),
            "active_stems": self.active_stems,
        }


@dataclass
class ArrangementAnalysis:
    """Complete arrangement analysis result."""
    sections: list[ArrangementSection] = field(default_factory=list)
    total_duration_sec: float = 0.0
    section_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sections": [s.to_dict() for s in self.sections],
            "total_duration_sec": round(self.total_duration_sec, 2),
            "section_count": self.section_count,
        }


@dataclass
class TranscriptionResult:
    """Complete AI transcription result."""
    project_yaml: str = ""
    stems: dict[str, str] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    arrangement: dict[str, Any] = field(default_factory=dict)
    bpm_info: BPMInfo = field(default_factory=BPMInfo)
    key_info: KeyInfo = field(default_factory=KeyInfo)
    stem_analyses: dict[str, dict[str, Any]] = field(default_factory=dict)
    transcription_time_sec: float = 0.0
    status: str = "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_yaml": self.project_yaml,
            "stems": self.stems,
            "analysis": self.analysis,
            "arrangement": self.arrangement,
            "bpm_info": self.bpm_info.to_dict(),
            "key_info": self.key_info.to_dict(),
            "stem_analyses": self.stem_analyses,
            "transcription_time_sec": round(self.transcription_time_sec, 3),
            "status": self.status,
        }


# ── AI Transcription Engine ─────────────────────────────────────────────

class AITranscription:
    """AI transcription pipeline.

    Complete "AI扒带" flow: reference audio -> separation -> reverse analysis
    -> VCMix project configuration.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self._reverse_analyzer = ReverseMixAnalyzer(sample_rate=sample_rate)
        self._analyzer = Analyzer(sample_rate=sample_rate)

    def transcribe(
        self,
        reference_path: str,
        output_dir: str,
        separate_fn: Any | None = None,
    ) -> TranscriptionResult:
        """
        Complete transcription pipeline.

        Args:
            reference_path: Path to the reference audio file.
            output_dir: Directory to write output project files.
            separate_fn: Optional custom separation function
                         (path, dir) -> dict[str, Path]. If None, uses Demucs.

        Returns:
            TranscriptionResult with project YAML, stems, and analysis.
        """
        start_time = time.time()
        result = TranscriptionResult()

        ref_path = Path(reference_path)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: Source separation
            stem_paths = self._separate(ref_path, out_path, separate_fn)
            result.stems = {k: str(v) for k, v in stem_paths.items()}

            # Step 2: Load stems and analyze
            stem_audios = self._load_stems(stem_paths)
            result.stem_analyses = {}
            for stem_name, audio in stem_audios.items():
                analysis = self._reverse_analyzer.analyze_stem(audio, stem_name)
                result.stem_analyses[stem_name] = analysis.to_dict()

            # Step 3: BPM detection
            full_audio = self._load_audio(ref_path)
            result.bpm_info = self._detect_bpm(full_audio)

            # Step 4: Key detection
            result.key_info = self._detect_key(full_audio)

            # Step 5: Arrangement analysis
            arrangement = self._analyze_arrangement(stem_audios)
            result.arrangement = arrangement.to_dict()

            # Step 6: Build analysis summary
            result.analysis = self._build_analysis_summary(
                result.bpm_info, result.key_info, result.stem_analyses
            )

            # Step 7: Generate VCMix project configuration
            project_config = self._generate_project_config(
                result.bpm_info, result.key_info, result.stem_analyses,
                arrangement, result.stems,
            )
            project_yaml_path = str(out_path / "project.yaml")
            self._write_yaml(project_config, project_yaml_path)
            result.project_yaml = project_yaml_path

        except Exception as e:
            result.status = "failed"
            result.analysis = {"error": str(e)}

        result.transcription_time_sec = time.time() - start_time
        return result

    # ── Source Separation ────────────────────────────────────────────────

    def _separate(
        self,
        ref_path: Path,
        out_path: Path,
        separate_fn: Any | None = None,
    ) -> dict[str, Path]:
        """Run source separation on the reference track."""
        if separate_fn is not None:
            return separate_fn(ref_path, out_path)

        try:
            from vcmix.separation.demucs_wrapper import separate_stems
            return separate_stems(ref_path, output_dir=out_path / "stems")
        except (ImportError, RuntimeError):
            # Fallback: use full mix as single stem
            return {"full_mix": ref_path}

    # ── Audio Loading ────────────────────────────────────────────────────

    def _load_audio(self, path: Path) -> np.ndarray:
        """Load audio file as numpy array."""
        try:
            import soundfile as sf
            audio, sr = sf.read(str(path))
            if audio.ndim == 1:
                audio = audio.reshape(1, -1)
            elif audio.ndim == 2:
                audio = audio.T  # (channels, samples)
            if sr != self.sample_rate:
                ratio = self.sample_rate / sr
                new_len = int(audio.shape[-1] * ratio)
                indices = np.linspace(0, audio.shape[-1] - 1, new_len).astype(int)
                audio = audio[:, indices]
            return audio.astype(np.float64)
        except ImportError:
            return np.zeros((1, self.sample_rate * 10), dtype=np.float64)

    def _load_stems(self, stem_paths: dict[str, Path]) -> dict[str, np.ndarray]:
        """Load all stem audio files."""
        stem_audios: dict[str, np.ndarray] = {}
        for name, path in stem_paths.items():
            if path.exists():
                stem_audios[name] = self._load_audio(path)
        return stem_audios

    # ── BPM Detection ────────────────────────────────────────────────────

    def _detect_bpm(self, audio: np.ndarray) -> BPMInfo:
        """Detect BPM using onset detection + autocorrelation.

        Strategy:
            1. Compute onset strength envelope via spectral flux
            2. Compute autocorrelation of onset envelope
            3. Find peaks in autocorrelation at musically plausible lags
            4. Select the most likely BPM from peak positions
        """
        mono = self._to_mono(audio)
        sr = self.sample_rate

        hop_length = 512
        frame_size = 2048
        n_frames = max(1, (len(mono) - frame_size) // hop_length + 1)

        if n_frames < 10:
            return BPMInfo(bpm=120.0, confidence=0.0)

        # Compute spectral flux as onset strength
        onset_env = np.zeros(n_frames)
        prev_spectrum = np.zeros(frame_size // 2 + 1)

        for i in range(n_frames):
            start = i * hop_length
            end = min(start + frame_size, len(mono))
            frame = np.zeros(frame_size)
            frame[:end - start] = mono[start:end]
            windowed = frame * np.hanning(frame_size)
            spectrum = np.abs(np.fft.rfft(windowed))
            flux = np.sum(np.maximum(0, spectrum - prev_spectrum))
            onset_env[i] = flux
            prev_spectrum = spectrum

        onset_max = np.max(onset_env)
        if onset_max > 1e-10:
            onset_env = onset_env / onset_max

        # Autocorrelation of onset envelope
        acf = self._autocorrelation(onset_env)

        # Find BPM candidates from autocorrelation
        frames_per_sec = sr / hop_length
        min_lag = max(1, int(frames_per_sec * 60.0 / 200))  # 200 BPM
        max_lag = min(len(acf) - 1, int(frames_per_sec * 60.0 / 60))   # 60 BPM

        if max_lag <= min_lag:
            return BPMInfo(bpm=120.0, confidence=0.0)

        search_region = acf[min_lag:max_lag + 1]
        if len(search_region) == 0:
            return BPMInfo(bpm=120.0, confidence=0.0)

        best_lag = min_lag + int(np.argmax(search_region))
        bpm = 60.0 * frames_per_sec / best_lag

        # Normalize BPM to 80-160 range
        while bpm < 80:
            bpm *= 2
        while bpm > 160:
            bpm /= 2

        confidence = float(search_region[int(np.argmax(search_region))])
        confidence = max(0.0, min(1.0, confidence))

        return BPMInfo(
            bpm=round(bpm, 1),
            confidence=confidence,
            method="onset_autocorrelation",
        )

    def _autocorrelation(self, signal: np.ndarray) -> np.ndarray:
        """Compute autocorrelation via FFT."""
        n = len(signal)
        fft_size = 1
        while fft_size < 2 * n:
            fft_size *= 2
        fft_sig = np.fft.rfft(signal, n=fft_size)
        acf = np.fft.irfft(fft_sig * np.conj(fft_sig))[:n]
        if acf[0] > 0:
            acf = acf / acf[0]
        return acf

    # ── Key Detection ────────────────────────────────────────────────────

    def _detect_key(self, audio: np.ndarray) -> KeyInfo:
        """Detect musical key using Krumhansl-Schmuckler algorithm."""
        mono = self._to_mono(audio)
        chroma = self._compute_chroma(mono)
        root, scale_type, confidence = ks_detect_key(chroma)
        return KeyInfo(root=root, scale_type=scale_type, confidence=confidence)

    def _compute_chroma(self, mono: np.ndarray) -> list[float]:
        """Compute chroma histogram from mono audio."""
        n_fft = min(8192, len(mono))
        if n_fft < 256:
            return [0.0] * 12

        windowed = mono[:n_fft].astype(np.float64) * np.hanning(n_fft)
        spectrum = np.abs(np.fft.rfft(windowed, n=n_fft))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)

        chroma = np.zeros(12)
        for i, freq in enumerate(freqs):
            if freq < 30 or freq > 5000:
                continue
            midi_note = 12 * np.log2(freq / 440.0) + 69
            pitch_class = int(round(midi_note)) % 12
            chroma[pitch_class] += spectrum[i]

        total = np.sum(chroma)
        if total > 1e-10:
            chroma = chroma / total

        return [float(c) for c in chroma]

    # ── Arrangement Analysis ─────────────────────────────────────────────

    def _analyze_arrangement(
        self, stem_audios: dict[str, np.ndarray]
    ) -> ArrangementAnalysis:
        """Analyze arrangement structure from stem audio."""
        if not stem_audios:
            return ArrangementAnalysis()

        energy_profiles: dict[str, list[float]] = {}
        for name, audio in stem_audios.items():
            mono = self._to_mono(audio)
            energy_profiles[name] = self._compute_energy_profile(mono)

        if not energy_profiles:
            return ArrangementAnalysis()

        max_len = max(len(v) for v in energy_profiles.values())
        total_duration = float(max_len)

        if max_len == 0:
            return ArrangementAnalysis(total_duration_sec=0.0)

        combined = np.zeros(max_len)
        for profile in energy_profiles.values():
            padded = np.zeros(max_len)
            padded[:len(profile)] = profile
            combined += padded

        sections = self._detect_sections(combined, energy_profiles, total_duration)

        return ArrangementAnalysis(
            sections=sections,
            total_duration_sec=total_duration,
            section_count=len(sections),
        )

    def _compute_energy_profile(self, mono: np.ndarray) -> list[float]:
        """Compute per-second RMS energy profile."""
        sr = self.sample_rate
        n_seconds = max(1, len(mono) // sr)
        profile: list[float] = []

        for i in range(n_seconds):
            start = i * sr
            end = min((i + 1) * sr, len(mono))
            if start >= len(mono):
                profile.append(0.0)
                continue
            segment = mono[start:end]
            rms = float(np.sqrt(np.mean(segment ** 2)))
            profile.append(rms)

        return profile

    def _detect_sections(
        self,
        combined: np.ndarray,
        energy_profiles: dict[str, list[float]],
        total_duration: float,
    ) -> list[ArrangementSection]:
        """Detect arrangement sections from energy profile transitions."""
        n_seconds = len(combined)
        if n_seconds == 0:
            return [ArrangementSection(
                name="full", start_sec=0.0, end_sec=total_duration,
                energy=0.5, active_stems=list(energy_profiles.keys()),
            )]

        kernel_size = max(1, n_seconds // 20)
        kernel = np.ones(kernel_size) / kernel_size
        smoothed = np.convolve(combined, kernel, mode="same")

        sm_max = np.max(smoothed)
        if sm_max > 1e-10:
            smoothed = smoothed / sm_max

        diff = np.abs(np.diff(smoothed))
        threshold = np.mean(diff) + np.std(diff) * 1.5 if len(diff) > 0 else 0

        boundaries = [0]
        for i in range(len(diff)):
            if diff[i] > threshold:
                boundaries.append(i + 1)
        boundaries.append(n_seconds)

        # Remove boundaries that are too close together (< 4 seconds)
        filtered = [boundaries[0]]
        for b in boundaries[1:]:
            if b - filtered[-1] >= 4:
                filtered.append(b)
        if filtered[-1] != n_seconds:
            filtered.append(n_seconds)
        boundaries = filtered

        sections: list[ArrangementSection] = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1]

            if end <= start:
                energy = 0.5
            else:
                energy = float(np.mean(smoothed[start:end]))

            active: list[str] = []
            for name, profile in energy_profiles.items():
                seg_start = min(start, len(profile) - 1)
                seg_end = min(end, len(profile))
                if seg_start < seg_end:
                    seg_max = max(profile[seg_start:seg_end])
                    if seg_max > 1e-6:
                        active.append(name)

            if i == 0:
                section_name = "intro"
            elif i == len(boundaries) - 2:
                section_name = "outro"
            elif energy > 0.7:
                section_name = "chorus"
            elif energy < 0.3:
                section_name = "bridge"
            else:
                section_name = "verse"

            sections.append(ArrangementSection(
                name=section_name,
                start_sec=float(start),
                end_sec=float(end),
                energy=round(energy, 3),
                active_stems=active,
            ))

        if len(sections) == 1 and total_duration > 8:
            sections[0].name = "verse"

        return sections

    # ── Analysis Summary ─────────────────────────────────────────────────

    def _build_analysis_summary(
        self,
        bpm_info: BPMInfo,
        key_info: KeyInfo,
        stem_analyses: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Build analysis summary dict."""
        return {
            "bpm": bpm_info.bpm,
            "key": key_info.root,
            "scale_type": key_info.scale_type,
            "key_confidence": key_info.confidence,
            "stem_count": len(stem_analyses),
            "stem_names": list(stem_analyses.keys()),
            "stem_levels": {
                name: analysis.get("rms_db", -60.0)
                for name, analysis in stem_analyses.items()
            },
        }

    # ── Project Config Generation ────────────────────────────────────────

    def _generate_project_config(
        self,
        bpm_info: BPMInfo,
        key_info: KeyInfo,
        stem_analyses: dict[str, dict[str, Any]],
        arrangement: ArrangementAnalysis,
        stem_paths: dict[str, str],
    ) -> dict[str, Any]:
        """Generate VCMix project YAML configuration from analysis results."""
        tracks: list[dict[str, Any]] = []

        for stem_name, analysis in stem_analyses.items():
            track: dict[str, Any] = {
                "name": stem_name,
                "type": "audio",
                "file": stem_paths.get(stem_name, f"{stem_name}.wav"),
                "volume": self._rms_to_volume(analysis.get("rms_db", -18.0)),
                "effects": self._analysis_to_effects(analysis, stem_name),
            }
            tracks.append(track)

        arrangement_list: list[dict[str, Any]] = []
        for section in arrangement.sections:
            arrangement_list.append(section.to_dict())

        master: dict[str, Any] = {
            "target_lufs": -14.0,
            "true_peak_ceiling": -1.0,
            "effects": [
                {"name": "vc-limiter", "params": {"ceiling": -1.0}},
            ],
        }

        project: dict[str, Any] = {
            "name": "Transcription Project",
            "bpm": bpm_info.bpm,
            "key": key_info.root,
            "scale": key_info.scale_type,
            "sample_rate": self.sample_rate,
            "tracks": tracks,
            "arrangement": arrangement_list,
            "master": master,
        }

        return project

    def _rms_to_volume(self, rms_db: float) -> float:
        """Convert RMS dB to a volume value (0.0-1.0)."""
        if rms_db <= -60.0:
            return 0.0
        volume = (rms_db + 60.0) / 60.0
        return round(max(0.0, min(1.0, volume)), 4)

    def _analysis_to_effects(
        self, analysis: dict[str, Any], stem_name: str
    ) -> list[dict[str, Any]]:
        """Convert reverse analysis results to VCMix effect chain."""
        effects: list[dict[str, Any]] = []

        eq_bands = analysis.get("eq_curve", {}).get("bands", [])
        if eq_bands:
            eq_params: dict[str, Any] = {}
            for band in eq_bands:
                freq = band.get("freq", 1000)
                gain = band.get("gain_db", 0)
                if freq < 200:
                    eq_params["low_shelf_db"] = gain
                    eq_params["low_shelf_hz"] = freq
                elif freq < 2000:
                    eq_params["peak_freq"] = freq
                    eq_params["peak_gain"] = gain
                else:
                    eq_params["high_shelf_db"] = gain
                    eq_params["high_shelf_hz"] = freq
            effects.append({"name": "vc-eq", "params": eq_params})

        comp = analysis.get("compression", {})
        if comp.get("ratio", 1.0) > 1.5:
            effects.append({
                "name": "vc-comp",
                "params": {
                    "threshold": comp.get("threshold_db", -20),
                    "ratio": comp.get("ratio", 2.0),
                    "attack": comp.get("attack_ms", 10),
                    "release": comp.get("release_ms", 100),
                },
            })

        reverb = analysis.get("reverb", {})
        if reverb.get("wet_ratio", 0) > 0.05:
            effects.append({
                "name": "vc-reverb",
                "params": {
                    "wet": round(min(0.5, reverb.get("wet_ratio", 0.2)), 3),
                    "room_size": round(min(1.0, reverb.get("rt60_ms", 500) / 3000.0), 3),
                },
            })

        delay = analysis.get("delay", {})
        if delay.get("delay_ms", 0) > 10:
            effects.append({
                "name": "vc-delay",
                "params": {
                    "time_ms": round(delay.get("delay_ms", 250)),
                    "feedback": round(min(0.6, delay.get("feedback", 0.3)), 3),
                },
            })

        effects.append({"name": "vc-limiter", "params": {"ceiling": -1.0}})

        return effects

    # ── YAML Writing ─────────────────────────────────────────────────────

    def _write_yaml(self, config: dict[str, Any], path: str) -> None:
        """Write project config as YAML file."""
        try:
            import yaml
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        except ImportError:
            import json
            json_path = path.replace(".yaml", ".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _to_mono(audio: np.ndarray) -> np.ndarray:
        """Convert audio to mono (1D float64)."""
        mono = audio.astype(np.float64)
        if mono.ndim == 2:
            mono = np.mean(mono, axis=0)
        return mono.ravel()
