"""
reference_matcher_v2.py — Reference track matching engine v2 for VCMix (Phase 17).

Analyzes a reference track's style features and recommends matching
arrangement templates and mixing presets.

Pipeline:
    1. Analyze reference features (BPM, key, genre, energy, frequency, dynamics)
    2. Match arrangement template based on features
    3. Match mixing preset based on features
    4. Generate style parameters for downstream use

Usage:
    from vcmix.ai.reference_matcher_v2 import ReferenceMatcherV2
    matcher = ReferenceMatcherV2()
    result = matcher.match_style("reference.wav")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vcmix.ai.music_theory import detect_key as ks_detect_key
from vcmix.engine.analyzer import Analyzer

# ── Data structures ─────────────────────────────────────────────────────

@dataclass
class StyleFeatures:
    """Style features extracted from a reference track."""
    bpm: float = 120.0
    key: str = "C"
    scale_type: str = "major"
    genre: str = "pop"
    energy_profile: list[float] = field(default_factory=list)
    frequency_balance: dict[str, float] = field(default_factory=dict)
    dynamic_range: float = 8.0
    spectral_centroid: float = 2000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "bpm": round(self.bpm, 1),
            "key": self.key,
            "scale_type": self.scale_type,
            "genre": self.genre,
            "energy_profile": [round(v, 4) for v in self.energy_profile[:30]],
            "frequency_balance": {k: round(v, 4) for k, v in self.frequency_balance.items()},
            "dynamic_range": round(self.dynamic_range, 2),
            "spectral_centroid": round(self.spectral_centroid, 1),
        }


@dataclass
class TemplateMatch:
    """A matched arrangement template."""
    template_name: str = ""
    genre: str = ""
    match_score: float = 0.0
    match_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_name": self.template_name,
            "genre": self.genre,
            "match_score": round(self.match_score, 4),
            "match_reasons": self.match_reasons,
        }


@dataclass
class MixPresetMatch:
    """A matched mixing preset."""
    preset_name: str = ""
    genre: str = ""
    match_score: float = 0.0
    preset_params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_name": self.preset_name,
            "genre": self.genre,
            "match_score": round(self.match_score, 4),
            "preset_params": self.preset_params,
        }


@dataclass
class StyleMatchResult:
    """Complete style match result."""
    features: StyleFeatures = field(default_factory=StyleFeatures)
    recommended_template: TemplateMatch = field(default_factory=TemplateMatch)
    recommended_mix_preset: MixPresetMatch = field(default_factory=MixPresetMatch)
    style_parameters: dict[str, Any] = field(default_factory=dict)
    match_time_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "features": self.features.to_dict(),
            "recommended_template": self.recommended_template.to_dict(),
            "recommended_mix_preset": self.recommended_mix_preset.to_dict(),
            "style_parameters": self.style_parameters,
            "match_time_sec": round(self.match_time_sec, 3),
        }


# ── Genre classification rules ──────────────────────────────────────────

# Each rule: (genre_name, bpm_range, freq_balance_hints)
# freq_balance_hints: keys that should be dominant for this genre
GENRE_RULES: list[dict[str, Any]] = [
    {
        "genre": "edm",
        "bpm_min": 118, "bpm_max": 160,
        "conditions": ["four_on_floor", "strong_low"],
        "description": "BPM>118 + 4-on-floor kick + strong low freq",
    },
    {
        "genre": "hiphop",
        "bpm_min": 70, "bpm_max": 115,
        "conditions": ["strong_low", "sparse_hi"],
        "description": "BPM 70-115 + strong low freq",
    },
    {
        "genre": "rock",
        "bpm_min": 95, "bpm_max": 140,
        "conditions": ["strong_mid", "guitar_freq"],
        "description": "BPM 95-140 + strong mid/guitar freq",
    },
    {
        "genre": "ballad",
        "bpm_min": 55, "bpm_max": 100,
        "conditions": ["low_energy", "smooth_dynamics"],
        "description": "BPM 55-100 + low energy + smooth dynamics",
    },
    {
        "genre": "rnb",
        "bpm_min": 80, "bpm_max": 115,
        "conditions": ["smooth_dynamics", "mid_focus"],
        "description": "BPM 80-115 + smooth dynamics + mid focus",
    },
    {
        "genre": "pop",
        "bpm_min": 90, "bpm_max": 140,
        "conditions": [],
        "description": "Default: BPM 90-140 (broad category)",
    },
]


# ── Mix presets per genre ───────────────────────────────────────────────

GENRE_MIX_PRESETS: dict[str, dict[str, Any]] = {
    "pop": {
        "vocal_gain_db": 0,
        "bass_gain_db": -2,
        "drums_gain_db": -1,
        "eq_high_shelf_db": 1.5,
        "eq_high_shelf_hz": 8000,
        "comp_threshold": -14,
        "comp_ratio": 2.5,
        "reverb_wet": 0.25,
        "reverb_room": 0.5,
        "delay_time_ms": 300,
        "delay_feedback": 0.25,
    },
    "rock": {
        "vocal_gain_db": 1,
        "bass_gain_db": 0,
        "drums_gain_db": 1,
        "eq_high_shelf_db": 2.0,
        "eq_high_shelf_hz": 6000,
        "comp_threshold": -12,
        "comp_ratio": 3.0,
        "reverb_wet": 0.2,
        "reverb_room": 0.4,
        "delay_time_ms": 200,
        "delay_feedback": 0.2,
    },
    "edm": {
        "vocal_gain_db": -1,
        "bass_gain_db": 2,
        "drums_gain_db": 2,
        "eq_high_shelf_db": 1.0,
        "eq_high_shelf_hz": 10000,
        "comp_threshold": -10,
        "comp_ratio": 4.0,
        "reverb_wet": 0.3,
        "reverb_room": 0.6,
        "delay_time_ms": 250,
        "delay_feedback": 0.35,
    },
    "hiphop": {
        "vocal_gain_db": 2,
        "bass_gain_db": 3,
        "drums_gain_db": 1,
        "eq_high_shelf_db": 0.5,
        "eq_high_shelf_hz": 8000,
        "comp_threshold": -16,
        "comp_ratio": 3.0,
        "reverb_wet": 0.15,
        "reverb_room": 0.3,
        "delay_time_ms": 375,
        "delay_feedback": 0.2,
    },
    "ballad": {
        "vocal_gain_db": 3,
        "bass_gain_db": -3,
        "drums_gain_db": -4,
        "eq_high_shelf_db": 2.0,
        "eq_high_shelf_hz": 10000,
        "comp_threshold": -18,
        "comp_ratio": 2.0,
        "reverb_wet": 0.35,
        "reverb_room": 0.7,
        "delay_time_ms": 400,
        "delay_feedback": 0.3,
    },
    "rnb": {
        "vocal_gain_db": 2,
        "bass_gain_db": 0,
        "drums_gain_db": -2,
        "eq_high_shelf_db": 1.5,
        "eq_high_shelf_hz": 9000,
        "comp_threshold": -16,
        "comp_ratio": 2.5,
        "reverb_wet": 0.3,
        "reverb_room": 0.55,
        "delay_time_ms": 350,
        "delay_feedback": 0.25,
    },
}


# ── Template matching data ──────────────────────────────────────────────

GENRE_TEMPLATE_MAP: dict[str, str] = {
    "pop": "pop_standard",
    "rock": "rock_standard",
    "edm": "edm_buildup",
    "hiphop": "hiphop_standard",
    "ballad": "ballad_standard",
    "rnb": "rnb_groove",
}


# ── Reference Matcher V2 ────────────────────────────────────────────────

class ReferenceMatcherV2:
    """Reference track matching engine v2.

    Analyzes a reference track's style features and recommends matching
    arrangement templates and mixing presets.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self._analyzer = Analyzer(sample_rate=sample_rate)

    def match_style(
        self,
        reference_path: str | None = None,
        reference_audio: np.ndarray | None = None,
    ) -> StyleMatchResult:
        """
        Analyze reference style and recommend template + preset.

        Args:
            reference_path: Path to reference audio file.
            reference_audio: Pre-loaded audio array (alternative to path).

        Returns:
            StyleMatchResult with features, template, preset, and style params.
        """
        start_time = time.time()
        result = StyleMatchResult()

        # Load audio
        audio = self._resolve_audio(reference_path, reference_audio)

        # Step 1: Extract features
        features = self._extract_features(audio)
        result.features = features

        # Step 2: Match arrangement template
        result.recommended_template = self._match_template(features)

        # Step 3: Match mixing preset
        result.recommended_mix_preset = self._match_mix_preset(features)

        # Step 4: Extract style parameters
        result.style_parameters = self._extract_style_params(features)

        result.match_time_sec = time.time() - start_time
        return result

    # ── Audio Loading ────────────────────────────────────────────────────

    def _resolve_audio(
        self,
        reference_path: str | None,
        reference_audio: np.ndarray | None,
    ) -> np.ndarray:
        """Resolve audio from path or array."""
        if reference_audio is not None:
            return reference_audio.astype(np.float64)

        if reference_path is not None:
            try:
                import soundfile as sf
                audio, sr = sf.read(reference_path)
                if audio.ndim == 1:
                    audio = audio.reshape(1, -1)
                elif audio.ndim == 2:
                    audio = audio.T
                return audio.astype(np.float64)
            except ImportError:
                pass

        # Fallback: return silence
        return np.zeros((1, self.sample_rate * 10), dtype=np.float64)

    # ── Feature Extraction ───────────────────────────────────────────────

    def _extract_features(self, audio: np.ndarray) -> StyleFeatures:
        """Extract complete style features from audio."""
        features = StyleFeatures()

        # BPM
        features.bpm = self._detect_bpm(audio)

        # Key
        mono = self._to_mono(audio)
        chroma = self._compute_chroma(mono)
        root, scale_type, confidence = ks_detect_key(chroma)
        features.key = root
        features.scale_type = scale_type

        # Genre classification
        features.genre = self._classify_genre(audio, features.bpm)

        # Energy profile
        features.energy_profile = self._compute_energy_profile(mono)

        # Frequency balance
        features.frequency_balance = self._compute_freq_balance(mono)

        # Dynamic range
        features.dynamic_range = self._compute_dynamic_range(mono)

        # Spectral centroid
        features.spectral_centroid = self._compute_spectral_centroid(mono)

        return features

    # ── Genre Classification ─────────────────────────────────────────────

    def _classify_genre(self, audio: np.ndarray, bpm: float) -> str:
        """Classify genre based on audio features and BPM.

        Rule-based classification:
            BPM > 130 + 4-on-floor → EDM
            BPM 80-115 + strong low freq → Hip-Hop
            BPM 100-130 + strong mid freq → Rock
            BPM 60-100 + low energy → Ballad
            Default → Pop
        """
        mono = self._to_mono(audio)
        freq_balance = self._compute_freq_balance(mono)
        energy_profile = self._compute_energy_profile(mono)
        dynamic_range = self._compute_dynamic_range(mono)

        # Compute key indicators
        low_energy = freq_balance.get("low", 0.0) + freq_balance.get("sub", 0.0)
        mid_energy = freq_balance.get("mid", 0.0) + freq_balance.get("mid_low", 0.0)
        high_energy = freq_balance.get("high", 0.0) + freq_balance.get("air", 0.0)
        avg_energy = np.mean(energy_profile) if energy_profile else 0.0

        # Check for 4-on-floor pattern (regular kick every 0.5s at BPM ~128)
        four_on_floor = self._check_four_on_floor(mono, bpm)

        # Score each genre
        scores: dict[str, float] = {}

        for rule in GENRE_RULES:
            score = 0.0
            genre = rule["genre"]

            # BPM match
            bpm_min = rule.get("bpm_min", 0)
            bpm_max = rule.get("bpm_max", 300)
            if bpm_min <= bpm <= bpm_max:
                score += 0.4
                # How centered in range
                center = (bpm_min + bpm_max) / 2
                range_half = (bpm_max - bpm_min) / 2
                if range_half > 0:
                    closeness = 1.0 - abs(bpm - center) / range_half
                    score += closeness * 0.1

            # Condition matching
            conditions = rule.get("conditions", [])
            for cond in conditions:
                if cond == "four_on_floor" and four_on_floor:
                    score += 0.3
                elif cond == "strong_low" and low_energy > 0.3:
                    score += 0.2
                elif cond == "sparse_hi" and high_energy < 0.15:
                    score += 0.1
                elif cond == "strong_mid" and mid_energy > 0.3:
                    score += 0.2
                elif cond == "guitar_freq" and mid_energy > 0.25:
                    score += 0.15
                elif cond == "low_energy" and avg_energy < 0.1:
                    score += 0.2
                elif cond == "smooth_dynamics" and dynamic_range < 10:
                    score += 0.15
                elif cond == "mid_focus" and mid_energy > 0.25:
                    score += 0.1

            scores[genre] = score

        # Select highest scoring genre
        if not scores:
            return "pop"

        best_genre = max(scores, key=lambda g: scores[g])

        # If no genre scores above a minimum threshold, default to pop
        if scores[best_genre] < 0.1:
            return "pop"

        return best_genre

    def _check_four_on_floor(self, mono: np.ndarray, bpm: float) -> bool:
        """Check if the audio has a 4-on-the-floor kick pattern.

        Looks for regular energy peaks at quarter-note intervals.
        """
        sr = self.sample_rate
        beat_interval = int(60.0 / bpm * sr) if bpm > 0 else sr // 2
        n_beats = max(1, len(mono) // beat_interval)

        if n_beats < 8:
            return False

        # Compute energy at each beat position
        window_size = max(1, beat_interval // 8)
        beat_energies: list[float] = []

        for i in range(n_beats):
            pos = i * beat_interval
            end = min(pos + window_size, len(mono))
            if pos < len(mono):
                energy = float(np.sqrt(np.mean(mono[pos:end] ** 2)))
                beat_energies.append(energy)

        if not beat_energies:
            return False

        # Check if beats on quarter notes (every beat) have consistent energy
        mean_energy = np.mean(beat_energies)
        if mean_energy < 1e-6:
            return False

        # Variance of beat energies - low variance = regular pattern
        variance = np.var(beat_energies)
        cv = np.sqrt(variance) / mean_energy  # coefficient of variation

        # 4-on-floor has low variation between beats
        return bool(cv < 0.5)

    # ── Feature Computation ──────────────────────────────────────────────

    def _detect_bpm(self, audio: np.ndarray) -> float:
        """Detect BPM from audio using autocorrelation."""
        mono = self._to_mono(audio)
        sr = self.sample_rate

        hop_length = 512
        frame_size = 2048
        n_frames = max(1, (len(mono) - frame_size) // hop_length + 1)

        if n_frames < 10:
            return 120.0

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

        # Autocorrelation
        n = len(onset_env)
        fft_size = 1
        while fft_size < 2 * n:
            fft_size *= 2
        fft_sig = np.fft.rfft(onset_env, n=fft_size)
        acf = np.fft.irfft(fft_sig * np.conj(fft_sig))[:n]
        if acf[0] > 0:
            acf = acf / acf[0]

        frames_per_sec = sr / hop_length
        min_lag = max(1, int(frames_per_sec * 60.0 / 200))
        max_lag = min(len(acf) - 1, int(frames_per_sec * 60.0 / 60))

        if max_lag <= min_lag:
            return 120.0

        search_region = acf[min_lag:max_lag + 1]
        if len(search_region) == 0:
            return 120.0

        best_lag = min_lag + int(np.argmax(search_region))
        bpm = 60.0 * frames_per_sec / best_lag

        while bpm < 80:
            bpm *= 2
        while bpm > 160:
            bpm /= 2

        return round(bpm, 1)

    def _compute_chroma(self, mono: np.ndarray) -> list[float]:
        """Compute chroma histogram."""
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

    def _compute_energy_profile(self, mono: np.ndarray) -> list[float]:
        """Compute per-second energy profile (RMS)."""
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

    def _compute_freq_balance(self, mono: np.ndarray) -> dict[str, float]:
        """Compute frequency band balance.

        Bands: sub (20-60), low (60-250), mid_low (250-500),
               mid (500-2000), mid_high (2000-4000),
               high (4000-12000), air (12000+)
        """
        n_fft = min(16384, len(mono))
        if n_fft < 256:
            return {}

        windowed = mono[:n_fft].astype(np.float64) * np.hanning(n_fft)
        spectrum = np.abs(np.fft.rfft(windowed, n=n_fft))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)

        bands_def = {
            "sub": (20, 60),
            "low": (60, 250),
            "mid_low": (250, 500),
            "mid": (500, 2000),
            "mid_high": (2000, 4000),
            "high": (4000, 12000),
            "air": (12000, 22050),
        }

        total_energy = float(np.sum(spectrum[freqs > 20]))
        if total_energy < 1e-10:
            return {k: 0.0 for k in bands_def}

        balance: dict[str, float] = {}
        for name, (f_low, f_high) in bands_def.items():
            mask = (freqs >= f_low) & (freqs < f_high)
            band_energy = float(np.sum(spectrum[mask]))
            balance[name] = round(band_energy / total_energy, 4)

        return balance

    def _compute_dynamic_range(self, mono: np.ndarray) -> float:
        """Compute dynamic range (peak - RMS in dB)."""
        rms = float(np.sqrt(np.mean(mono ** 2)))
        peak = float(np.max(np.abs(mono)))

        if rms < 1e-10:
            return 0.0
        if peak < 1e-10:
            return 0.0

        rms_db = 20 * np.log10(rms)
        peak_db = 20 * np.log10(peak)

        return round(float(peak_db - rms_db), 2)

    def _compute_spectral_centroid(self, mono: np.ndarray) -> float:
        """Compute spectral centroid (brightness indicator)."""
        n_fft = min(4096, len(mono))
        if n_fft < 2:
            return 0.0

        windowed = mono[:n_fft].astype(np.float64) * np.hanning(n_fft)
        fft_data = np.fft.rfft(windowed, n=n_fft)
        magnitudes = np.abs(fft_data)
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)

        total_mag = np.sum(magnitudes)
        if total_mag < 1e-10:
            return 0.0

        return round(float(np.sum(freqs * magnitudes) / total_mag), 1)

    # ── Template Matching ────────────────────────────────────────────────

    def _match_template(self, features: StyleFeatures) -> TemplateMatch:
        """Match features to an arrangement template."""
        genre = features.genre
        template_name = GENRE_TEMPLATE_MAP.get(genre, "pop_standard")

        # Compute match score
        score = 0.6  # Base score for genre match

        # Bonus for BPM in genre's sweet spot
        genre_rules = next(
            (r for r in GENRE_RULES if r["genre"] == genre), None
        )
        reasons: list[str] = []

        if genre_rules:
            bpm_min = genre_rules.get("bpm_min", 0)
            bpm_max = genre_rules.get("bpm_max", 300)
            if bpm_min <= features.bpm <= bpm_max:
                score += 0.2
                reasons.append(f"BPM {features.bpm} in {genre} range")
            else:
                score -= 0.1
                reasons.append(f"BPM {features.bpm} outside {genre} typical range")

        # Bonus for key/scale consistency
        if features.scale_type in ("natural_minor", "harmonic_minor") and genre in ("edm", "hiphop", "rnb"):
            score += 0.1
            reasons.append(f"Minor key fits {genre}")
        elif features.scale_type == "major" and genre in ("pop", "ballad"):
            score += 0.1
            reasons.append(f"Major key fits {genre}")

        reasons.insert(0, f"Genre classified as {genre}")

        return TemplateMatch(
            template_name=template_name,
            genre=genre,
            match_score=min(1.0, max(0.0, score)),
            match_reasons=reasons,
        )

    # ── Mix Preset Matching ──────────────────────────────────────────────

    def _match_mix_preset(self, features: StyleFeatures) -> MixPresetMatch:
        """Match features to a mixing preset."""
        genre = features.genre
        preset_name = f"{genre}_mix"
        preset_params = GENRE_MIX_PRESETS.get(genre, GENRE_MIX_PRESETS["pop"]).copy()

        # Adjust preset based on specific features
        if features.dynamic_range > 15:
            preset_params["comp_ratio"] = min(6.0, preset_params.get("comp_ratio", 2.5) + 1)
        if features.spectral_centroid > 4000:
            preset_params["eq_high_shelf_db"] = max(-2.0, preset_params.get("eq_high_shelf_db", 1.5) - 2)

        score = 0.7  # Base match score

        return MixPresetMatch(
            preset_name=preset_name,
            genre=genre,
            match_score=score,
            preset_params=preset_params,
        )

    # ── Style Parameters Extraction ──────────────────────────────────────

    def _extract_style_params(self, features: StyleFeatures) -> dict[str, Any]:
        """Extract style parameters for downstream use (style transfer etc.)."""
        return {
            "bpm": features.bpm,
            "key": features.key,
            "scale_type": features.scale_type,
            "genre": features.genre,
            "dynamic_range": features.dynamic_range,
            "spectral_centroid": features.spectral_centroid,
            "frequency_balance": features.frequency_balance,
            "avg_energy": float(np.mean(features.energy_profile)) if features.energy_profile else 0.0,
            "energy_variance": float(np.var(features.energy_profile)) if features.energy_profile else 0.0,
        }

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _to_mono(audio: np.ndarray) -> np.ndarray:
        """Convert audio to mono (1D float64)."""
        mono = audio.astype(np.float64)
        if mono.ndim == 2:
            mono = np.mean(mono, axis=0)
        return mono.ravel()
