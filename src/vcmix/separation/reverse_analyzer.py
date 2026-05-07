"""
reverse_analyzer.py — Reverse engineering mixing parameters from audio stems.

Analyzes each separated stem to recover the mixing engineer's手法:
    - EQ curve detection via FFT spectral comparison
    - Compression parameter estimation from RMS envelope dynamics
    - Reverb analysis from tail decay (RT60 and pre-delay)
    - Delay detection via autocorrelation
    - Stereo panning and width analysis

All analysis uses numpy/scipy — no deep learning required.

Usage:
    from vcmix.separation.reverse_analyzer import ReverseMixAnalyzer

    analyzer = ReverseMixAnalyzer(sample_rate=44100)
    result = analyzer.analyze_stem(audio_array, "vocals")
    # result = {"track_name": "vocals", "eq_curve": {...}, ...}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy import signal as sp_signal


# ── Data classes ──────────────────────────────────────────────────────

@dataclass
class EQBand:
    """A single EQ band measurement."""
    freq: float          # Center frequency in Hz
    gain_db: float       # Gain in dB (positive = boost, negative = cut)
    q: float = 1.0       # Q factor (bandwidth)


@dataclass
class EQCurve:
    """Detected EQ curve."""
    bands: list[EQBand] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bands": [
                {"freq": b.freq, "gain_db": round(b.gain_db, 1), "q": round(b.q, 2)}
                for b in self.bands
            ]
        }


@dataclass
class CompressionParams:
    """Detected compression parameters."""
    threshold_db: float = -20.0
    ratio: float = 2.0
    attack_ms: float = 10.0
    release_ms: float = 100.0
    makeup_gain_db: float = 0.0

    def to_dict(self) -> dict:
        return {
            "threshold_db": round(self.threshold_db, 1),
            "ratio": round(self.ratio, 1),
            "attack_ms": round(self.attack_ms, 1),
            "release_ms": round(self.release_ms, 1),
            "makeup_gain_db": round(self.makeup_gain_db, 1),
        }


@dataclass
class ReverbParams:
    """Detected reverb parameters."""
    rt60_ms: float = 0.0
    pre_delay_ms: float = 0.0
    wet_ratio: float = 0.0

    def to_dict(self) -> dict:
        return {
            "rt60_ms": round(self.rt60_ms, 1),
            "pre_delay_ms": round(self.pre_delay_ms, 1),
            "wet_ratio": round(self.wet_ratio, 3),
        }


@dataclass
class DelayParams:
    """Detected delay parameters."""
    delay_ms: float = 0.0
    feedback: float = 0.0
    tap_count: int = 0

    def to_dict(self) -> dict:
        return {
            "delay_ms": round(self.delay_ms, 1),
            "feedback": round(self.feedback, 3),
            "tap_count": self.tap_count,
        }


@dataclass
class PanParams:
    """Detected stereo panning."""
    position: float = 0.0   # -1.0 (left) to +1.0 (right), 0.0 = center
    stereo_width: float = 0.5  # 0.0 (mono) to 1.0 (full stereo)

    def to_dict(self) -> dict:
        return {
            "position": round(self.position, 2),
            "stereo_width": round(self.stereo_width, 2),
        }


@dataclass
class StemMixAnalysis:
    """Complete reverse mix analysis for a single stem."""
    track_name: str
    eq_curve: EQCurve = field(default_factory=EQCurve)
    compression: CompressionParams = field(default_factory=CompressionParams)
    reverb: ReverbParams = field(default_factory=ReverbParams)
    delay: DelayParams = field(default_factory=DelayParams)
    pan: PanParams = field(default_factory=PanParams)
    rms_db: float = -60.0
    peak_db: float = -60.0

    def to_dict(self) -> dict:
        return {
            "track_name": self.track_name,
            "eq_curve": self.eq_curve.to_dict(),
            "compression": self.compression.to_dict(),
            "reverb": self.reverb.to_dict(),
            "delay": self.delay.to_dict(),
            "pan": self.pan.to_dict(),
            "rms_db": round(self.rms_db, 1),
            "peak_db": round(self.peak_db, 1),
        }


# ── Main analyzer ─────────────────────────────────────────────────────

class ReverseMixAnalyzer:
    """Reverse-engineer mixing parameters from an audio stem.

    Parameters
    ----------
    sample_rate : int
        Sample rate of the audio to analyze.
    fft_size : int
        FFT window size for spectral analysis.
    """

    def __init__(self, sample_rate: int = 44100, fft_size: int = 8192):
        self.sample_rate = sample_rate
        self.fft_size = fft_size

    def analyze_stem(
        self,
        audio: np.ndarray,
        stem_name: str,
    ) -> StemMixAnalysis:
        """Analyze a single stem and recover mixing parameters.

        Parameters
        ----------
        audio : np.ndarray
            Audio array. Mono: 1D shape (samples,).
            Stereo: 2D shape (2, samples).
        stem_name : str
            Name of the stem (e.g. "vocals", "drums").

        Returns
        -------
        StemMixAnalysis
            Complete analysis results.
        """
        # Convert to mono for most analyses
        mono = self._to_mono(audio)

        result = StemMixAnalysis(track_name=stem_name)

        # Basic levels
        rms = float(np.sqrt(np.mean(mono ** 2)))
        peak = float(np.max(np.abs(mono)))
        result.rms_db = 20 * np.log10(rms) if rms > 1e-10 else -120.0
        result.peak_db = 20 * np.log10(peak) if peak > 1e-10 else -120.0

        # EQ analysis
        result.eq_curve = self._analyze_eq(mono)

        # Compression analysis
        result.compression = self._analyze_compression(mono)

        # Reverb analysis
        result.reverb = self._analyze_reverb(mono)

        # Delay analysis
        result.delay = self._analyze_delay(mono)

        # Pan / stereo analysis
        if audio.ndim == 2 and audio.shape[0] >= 2:
            result.pan = self._analyze_pan(audio)
        else:
            result.pan = PanParams(position=0.0, stereo_width=0.0)

        return result

    # ------------------------------------------------------------------
    # EQ Analysis
    # ------------------------------------------------------------------

    def _analyze_eq(self, mono: np.ndarray) -> EQCurve:
        """Detect EQ curve by comparing spectral shape to a flat reference.

        Strategy: Compute FFT magnitude, smooth it, then identify peaks
        and dips relative to the smoothed spectral envelope.  Each
        significant deviation is reported as an EQ band.
        """
        n_fft = min(self.fft_size, len(mono))
        windowed = mono[:n_fft].astype(np.float64) * np.hanning(n_fft)
        spectrum = np.abs(np.fft.rfft(windowed, n=n_fft))
        freqs = np.fft.rfftfreq(n_fft, 1.0 / self.sample_rate)

        # Skip DC and very low frequencies
        min_freq = 50.0
        mask = freqs >= min_freq
        spectrum = spectrum[mask]
        freqs = freqs[mask]

        if len(spectrum) < 10:
            return EQCurve()

        # Convert to dB
        spectrum_db = 20 * np.log10(spectrum + 1e-10)

        # Compute a smooth reference envelope (moving average over ~1 octave)
        # Approximate 1-octave smoothing in log-frequency domain
        log_freqs = np.log2(freqs + 1)
        smooth_size = max(3, len(spectrum_db) // 20)
        kernel = np.ones(smooth_size) / smooth_size
        envelope_db = np.convolve(spectrum_db, kernel, mode="same")

        # Deviation from envelope
        deviation_db = spectrum_db - envelope_db

        # Find peaks and dips in the deviation
        bands = self._find_eq_bands(freqs, deviation_db, log_freqs)

        return EQCurve(bands=bands)

    def _find_eq_bands(
        self,
        freqs: np.ndarray,
        deviation_db: np.ndarray,
        log_freqs: np.ndarray,
        threshold_db: float = 3.0,
    ) -> list[EQBand]:
        """Identify EQ bands from spectral deviation peaks/dips."""
        bands: list[EQBand] = []

        # Find local extrema using scipy
        if len(deviation_db) < 5:
            return bands

        # Smooth deviation slightly
        kernel = np.ones(5) / 5
        smooth_dev = np.convolve(deviation_db, kernel, mode="same")

        # Find peaks (boosts)
        peaks, _ = sp_signal.find_peaks(smooth_dev, height=threshold_db, distance=10)
        # Find valleys (cuts)
        valleys, _ = sp_signal.find_peaks(-smooth_dev, height=threshold_db, distance=10)

        for idx in peaks:
            freq = float(freqs[idx])
            gain = float(deviation_db[idx])
            q = self._estimate_q(freqs, deviation_db, idx)
            bands.append(EQBand(freq=freq, gain_db=gain, q=q))

        for idx in valleys:
            freq = float(freqs[idx])
            gain = float(deviation_db[idx])  # negative
            q = self._estimate_q(freqs, deviation_db, idx)
            bands.append(EQBand(freq=freq, gain_db=gain, q=q))

        # Sort by frequency
        bands.sort(key=lambda b: b.freq)

        # Keep at most 8 bands (avoid over-reporting)
        if len(bands) > 8:
            bands.sort(key=lambda b: abs(b.gain_db), reverse=True)
            bands = bands[:8]
            bands.sort(key=lambda b: b.freq)

        return bands

    @staticmethod
    def _estimate_q(
        freqs: np.ndarray,
        deviation_db: np.ndarray,
        peak_idx: int,
    ) -> float:
        """Estimate Q factor from the width of a spectral peak/dip.

        Q = center_freq / bandwidth_3dB
        """
        center_freq = freqs[peak_idx]
        center_gain = deviation_db[peak_idx]
        half_gain = center_gain / 2.0

        # Search left for -3dB point
        left_idx = peak_idx
        for i in range(peak_idx - 1, max(0, peak_idx - 200), -1):
            if abs(deviation_db[i]) < abs(half_gain):
                left_idx = i
                break

        # Search right for -3dB point
        right_idx = peak_idx
        for i in range(peak_idx + 1, min(len(deviation_db), peak_idx + 200)):
            if abs(deviation_db[i]) < abs(half_gain):
                right_idx = i
                break

        bw = freqs[right_idx] - freqs[left_idx]
        if bw > 0 and center_freq > 0:
            q = center_freq / bw
            return max(0.1, min(q, 20.0))  # Clamp Q
        return 1.0

    # ------------------------------------------------------------------
    # Compression Analysis
    # ------------------------------------------------------------------

    def _analyze_compression(self, mono: np.ndarray) -> CompressionParams:
        """Estimate compression parameters from the dynamic envelope.

        Strategy:
        1. Compute RMS envelope in short windows (10ms).
        2. Build a histogram of RMS levels.
        3. The "knee" in the histogram reveals the threshold.
        4. The ratio is estimated from the slope above vs below threshold.
        5. Attack/release from the envelope response to transients.
        """
        win_samples = max(1, int(self.sample_rate * 0.01))  # 10ms
        n_windows = len(mono) // win_samples
        if n_windows < 10:
            return CompressionParams()

        # RMS envelope
        envelope = np.array([
            np.sqrt(np.mean(mono[i * win_samples:(i + 1) * win_samples] ** 2))
            for i in range(n_windows)
        ])

        # Convert to dB
        env_db = 20 * np.log10(envelope + 1e-10)

        # Build histogram of levels
        valid = env_db[env_db > -80]
        if len(valid) < 5:
            return CompressionParams()

        hist, bin_edges = np.histogram(valid, bins=50)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        # Find threshold: the level where the distribution drops sharply
        # (the "knee" point from the right side)
        threshold_db = self._find_compression_knee(hist, bin_centers)

        # Estimate ratio: compare dynamic range above vs below threshold
        above = env_db[env_db > threshold_db]
        below = env_db[env_db <= threshold_db]

        if len(above) > 2 and len(below) > 2:
            range_above = np.std(above)
            range_below = np.std(below)
            if range_above > 0.1:
                ratio = min(20.0, max(1.0, range_below / range_above))
            else:
                ratio = 1.0
        else:
            ratio = 1.0

        # Estimate attack/release from transient response
        attack_ms, release_ms = self._estimate_attack_release(
            envelope, win_samples,
        )

        # Makeup gain: difference between average level and threshold
        avg_db = float(np.mean(valid))
        makeup = max(0, threshold_db - avg_db) if avg_db < threshold_db else 0.0

        return CompressionParams(
            threshold_db=round(threshold_db, 1),
            ratio=round(ratio, 1),
            attack_ms=round(attack_ms, 1),
            release_ms=round(release_ms, 1),
            makeup_gain_db=round(makeup, 1),
        )

    @staticmethod
    def _find_compression_knee(
        hist: np.ndarray, bin_centers: np.ndarray,
    ) -> float:
        """Find the compression threshold (knee point) in a level histogram.

        The knee is the bin where the distribution starts to fall off
        from its peak on the high-level side.
        """
        # Find the peak bin
        peak_idx = np.argmax(hist)

        # Look for the point where histogram drops to half the peak
        # on the high-level side (right of peak)
        half_peak = hist[peak_idx] / 2
        for i in range(peak_idx, len(hist)):
            if hist[i] < half_peak:
                return float(bin_centers[i])

        # Fallback: use the mean of the distribution
        return float(bin_centers[peak_idx])

    def _estimate_attack_release(
        self,
        envelope: np.ndarray,
        win_samples: int,
    ) -> tuple[float, float]:
        """Estimate attack and release times from the RMS envelope.

        Looks at how quickly the envelope rises (attack) and falls
        (release) after sudden level changes.
        """
        if len(envelope) < 5:
            return (10.0, 100.0)

        # Find significant transients (sudden level increases)
        diff = np.diff(envelope)
        rises = diff[diff > 0]
        falls = diff[diff < 0]

        # Attack time: average rise rate (time to go from 10% to 90% of rise)
        attack_ms = 10.0  # default
        if len(rises) > 5:
            avg_rise = float(np.mean(rises))
            if avg_rise > 0:
                # Estimate time to reach steady state
                attack_ms = max(1.0, min(50.0, win_samples / self.sample_rate * 1000 * 5))

        # Release time: average fall rate
        release_ms = 100.0  # default
        if len(falls) > 5:
            avg_fall = float(np.mean(np.abs(falls)))
            if avg_fall > 0:
                avg_rise_val = float(np.mean(rises)) if len(rises) > 0 else 1.0
                ratio = avg_rise_val / avg_fall if avg_fall > 0 else 1.0
                release_ms = max(10.0, min(500.0, attack_ms * ratio * 2))

        return (attack_ms, release_ms)

    # ------------------------------------------------------------------
    # Reverb Analysis
    # ------------------------------------------------------------------

    def _analyze_reverb(self, mono: np.ndarray) -> ReverbParams:
        """Analyze reverb from the audio tail decay.

        Strategy:
        1. Find a significant transient (high-energy onset).
        2. Measure the decay after the transient.
        3. Fit the decay to estimate RT60.
        4. Pre-delay = time between transient onset and decay start.
        5. Wet ratio = energy in the decay tail vs direct signal.
        """
        win_samples = max(1, int(self.sample_rate * 0.01))  # 10ms
        n_windows = len(mono) // win_samples
        if n_windows < 20:
            return ReverbParams()

        # Compute RMS envelope
        envelope = np.array([
            np.sqrt(np.mean(mono[i * win_samples:(i + 1) * win_samples] ** 2))
            for i in range(n_windows)
        ])

        # Find the strongest transient
        diff = np.diff(envelope)
        onset_idx = int(np.argmax(diff))

        if onset_idx >= n_windows - 5:
            return ReverbParams()

        peak_val = envelope[onset_idx + 1] if onset_idx + 1 < len(envelope) else envelope[onset_idx]
        if peak_val < 1e-10:
            return ReverbParams()

        # Measure RT60 from the decay
        decay = envelope[onset_idx + 1:]
        if len(decay) < 5:
            return ReverbParams()

        # Find where level drops 60dB below peak
        peak_db = 20 * np.log10(peak_val + 1e-10)
        target_db = peak_db - 60

        rt60_ms = 0.0
        for i in range(len(decay)):
            level_db = 20 * np.log10(decay[i] + 1e-10)
            if level_db <= target_db:
                rt60_ms = (i + 1) * win_samples / self.sample_rate * 1000
                break

        # If we didn't find full 60dB drop, extrapolate
        if rt60_ms == 0.0 and len(decay) > 2:
            end_db = 20 * np.log10(decay[-1] + 1e-10)
            if end_db < peak_db - 10:
                available_decay = peak_db - end_db
                time_to_end = len(decay) * win_samples / self.sample_rate * 1000
                rt60_ms = time_to_end * (60.0 / available_decay)

        # Pre-delay: time between onset and when decay starts
        pre_delay_ms = 0.0
        if onset_idx > 0:
            # Small gap between onset and peak
            peak_envelope_idx = int(np.argmax(envelope))
            if peak_envelope_idx > onset_idx:
                pre_delay_ms = (peak_envelope_idx - onset_idx) * win_samples / self.sample_rate * 1000

        # Wet ratio: energy in tail vs total energy
        # "Tail" = signal after the transient decay
        direct_end = min(onset_idx + 10, len(envelope))
        direct_energy = float(np.sum(envelope[onset_idx:direct_end] ** 2))
        tail_energy = float(np.sum(envelope[direct_end:] ** 2))
        total_energy = direct_energy + tail_energy
        wet_ratio = tail_energy / total_energy if total_energy > 0 else 0.0

        return ReverbParams(
            rt60_ms=round(rt60_ms, 1),
            pre_delay_ms=round(pre_delay_ms, 1),
            wet_ratio=round(min(wet_ratio, 1.0), 3),
        )

    # ------------------------------------------------------------------
    # Delay Analysis
    # ------------------------------------------------------------------

    def _analyze_delay(self, mono: np.ndarray) -> DelayParams:
        """Detect delay/echo via autocorrelation.

        Strategy:
        1. Compute autocorrelation of the signal.
        2. Skip the zero-lag peak.
        3. Find the next significant peak — its position gives delay time.
        4. The peak height relative to zero-lag gives feedback estimate.
        """
        # Use a segment of the audio for speed
        max_samples = min(len(mono), self.sample_rate * 10)  # max 10 seconds
        segment = mono[:max_samples].astype(np.float64)

        if len(segment) < self.sample_rate // 10:  # need at least 100ms
            return DelayParams()

        # Normalize
        rms = float(np.sqrt(np.mean(segment ** 2)))
        if rms < 1e-10:
            return DelayParams()
        segment = segment / rms

        # Autocorrelation via FFT (fast)
        n = len(segment)
        fft_size = 1
        while fft_size < 2 * n:
            fft_size *= 2

        fft_seg = np.fft.rfft(segment, n=fft_size)
        acf = np.fft.irfft(fft_seg * np.conj(fft_seg))[:n]

        # Normalize so zero-lag = 1.0
        if acf[0] > 0:
            acf = acf / acf[0]

        # Skip zero-lag region (at least 10ms)
        min_lag = max(1, int(self.sample_rate * 0.01))  # 10ms minimum delay
        search_region = acf[min_lag:]

        if len(search_region) < 2:
            return DelayParams()

        # Find peaks in autocorrelation
        peaks, properties = sp_signal.find_peaks(
            search_region,
            height=0.1,       # at least 10% correlation
            distance=int(self.sample_rate * 0.005),  # 5ms minimum gap
        )

        if len(peaks) == 0:
            return DelayParams()

        # The first significant peak is the delay
        best_peak = peaks[0]
        delay_samples = best_peak + min_lag
        delay_ms = delay_samples / self.sample_rate * 1000

        # Feedback estimate: peak height relative to zero-lag
        feedback = float(search_region[best_peak])
        # Clamp feedback
        feedback = max(0.0, min(feedback, 0.95))

        # Count taps: how many peaks above 0.1
        tap_count = len(peaks)

        return DelayParams(
            delay_ms=round(delay_ms, 1),
            feedback=round(feedback, 3),
            tap_count=tap_count,
        )

    # ------------------------------------------------------------------
    # Pan / Stereo Analysis
    # ------------------------------------------------------------------

    def _analyze_pan(self, audio: np.ndarray) -> PanParams:
        """Analyze stereo panning and width from a stereo signal.

        Parameters
        ----------
        audio : np.ndarray
            Stereo audio, shape (2, samples).

        Returns
        -------
        PanParams
        """
        left = audio[0].astype(np.float64)
        right = audio[1].astype(np.float64)

        # RMS of each channel
        rms_l = float(np.sqrt(np.mean(left ** 2)))
        rms_r = float(np.sqrt(np.mean(right ** 2)))

        # Pan position: -1 (full left) to +1 (full right)
        total = rms_l + rms_r
        if total > 1e-10:
            position = (rms_r - rms_l) / total
        else:
            position = 0.0

        # Stereo width: correlation-based
        # Mid = (L+R)/2, Side = (L-R)/2
        mid = (left + right) / 2
        side = (left - right) / 2
        mid_rms = float(np.sqrt(np.mean(mid ** 2)))
        side_rms = float(np.sqrt(np.mean(side ** 2)))

        if mid_rms > 1e-10:
            width = min(1.0, side_rms / mid_rms)
        else:
            width = 0.0

        return PanParams(
            position=round(position, 2),
            stereo_width=round(width, 2),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_mono(audio: np.ndarray) -> np.ndarray:
        """Convert audio to mono (1D float64)."""
        mono = audio.astype(np.float64)
        if mono.ndim == 2:
            mono = np.mean(mono, axis=0)
        return mono.ravel()


# ── Convenience function ──────────────────────────────────────────────

def analyze_stem_mix(
    audio: np.ndarray,
    sample_rate: int,
    stem_name: str,
) -> dict[str, Any]:
    """Analyze a stem and return results as a plain dict.

    This is the convenience wrapper that returns the JSON-serializable
    format matching the task spec.
    """
    analyzer = ReverseMixAnalyzer(sample_rate=sample_rate)
    result = analyzer.analyze_stem(audio, stem_name)
    return result.to_dict()



# ── Backward compatibility (Phase 3-5 legacy API) ─────────────────────
# The old API used StemAnalysis (different from StemMixAnalysis) and
# analyze_stem / _generate_config.  We keep these available so that
# existing tests and code continue to work.

@dataclass
class StemAnalysis:
    """Legacy stem analysis result (Phase 3-5 compatibility).

    .. deprecated::
        Use :class:`StemMixAnalysis` and :class:`ReverseMixAnalyzer` instead.
    """
    name: str
    rms_db: float = 0.0
    peak_db: float = 0.0
    spectral_centroid: float = 0.0
    effects_chain: list[dict[str, Any]] = field(default_factory=list)


def analyze_stem(audio: np.ndarray, sample_rate: int, stem_name: str) -> StemAnalysis:
    """Legacy stem analysis function (Phase 3-5 compatibility).

    .. deprecated::
        Use :meth:`ReverseMixAnalyzer.analyze_stem` instead.
    """
    from vcmix.engine.analyzer import Analyzer

    analyzer = Analyzer(sample_rate=sample_rate)
    result = StemAnalysis(name=stem_name)
    rms = analyzer.compute_rms(audio)
    peak = analyzer.compute_peak(audio)
    result.rms_db = 20 * np.log10(rms) if rms > 0 else -120.0
    result.peak_db = 20 * np.log10(peak) if peak > 0 else -120.0

    if stem_name == "vocals":
        result.effects_chain = _legacy_vocal_chain(audio, sample_rate, analyzer, result)
    elif stem_name == "drums":
        result.effects_chain = _legacy_drums_chain(analyzer, result)
    elif stem_name == "bass":
        result.effects_chain = _legacy_bass_chain(analyzer, result)
    else:
        result.effects_chain = _legacy_other_chain(audio, sample_rate, analyzer)
    return result


def _legacy_vocal_chain(audio, sr, analyzer, stem):
    chain = []
    sibilance = analyzer.compute_sibilance(audio)
    if sibilance > -25:
        chain.append({
            "name": "vc-deesser",
            "params": {"threshold": -40, "reduction": round(max(-3, sibilance + 20), 1)}
        })
    chain.append({"name": "vc-eq", "params": {"low_cut": 80, "high_shelf": 8000}})
    dynamic_range = stem.peak_db - stem.rms_db
    if dynamic_range > 12:
        chain.append({"name": "vc-comp", "params": {"threshold": -24,
                "ratio": min(4.0, dynamic_range / 5),
                "attack": 5, "release": 50
            }})
    chain.append({"name": "vc-limiter", "params": {"ceiling": -1}})
    return chain


def _legacy_drums_chain(analyzer, stem):
    return [
        {"name": "vc-eq", "params": {"low_cut": 30, "high_shelf": 8000}},
        {"name": "vc-comp", "params": {"threshold": -18, "ratio": 2.5, "attack": 1, "release": 20}},
        {"name": "vc-limiter", "params": {"ceiling": -1}},
    ]


def _legacy_bass_chain(analyzer, stem):
    return [
        {"name": "vc-eq", "params": {"low_cut": 30, "high_shelf": 5000}},
        {"name": "vc-comp", "params": {"threshold": -20, "ratio": 3, "attack": 10, "release": 80}},
        {"name": "vc-limiter", "params": {"ceiling": -1}},
    ]


def _legacy_other_chain(audio, sr, analyzer):
    chain = [{"name": "vc-eq", "params": {"low_cut": 60, "high_shelf": 8000}}]
    chain.append({"name": "vc-limiter", "params": {"ceiling": -1}})
    return chain


def _generate_config(analysis):
    """Legacy config generator (Phase 3-5 compatibility)."""
    tracks = []
    levels = {}
    for stem_name, stem in analysis.stems.items():
        tracks.append({
            "name": stem.name,
            "file": f"{stem.name}.wav",
            "effects": stem.effects_chain,
        })
        level = min(1.0, max(0.1, 10 ** (stem.rms_db / 20) * 5))
        levels[stem_name] = round(level, 2)
    return {
        "name": "reference_analysis",
        "bpm": analysis.bpm,
        "sample_rate": 44100,
        "tracks": tracks,
        "master": {"levels": levels, "effects": [], "output": "reference_mix.wav"},
    }


def analyze_reference(input_path, output_dir=None, separate=True):
    """Legacy reference analysis function (Phase 3-5 compatibility)."""
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Reference not found: {input_path}")
    from vcmix.bpm.detector import detect_bpm

    result = type("R", (), {"bpm": 120.0, "stems": {}, "vcmix_config": {}})()
    try:
        result.bpm = detect_bpm(str(input_path))
    except Exception:
        result.bpm = 120.0

    stems_paths = {}
    if separate:
        try:
            from vcmix.separation.demucs_wrapper import separate_stems
            stems_paths = separate_stems(input_path, output_dir=output_dir)
        except (ImportError, RuntimeError):
            stems_paths = {"full_mix": input_path}

    for stem_name, stem_path in stems_paths.items():
        try:
            from vcmix.audio.io import read_audio
            audio, sr = read_audio(stem_path)
            result.stems[stem_name] = analyze_stem(audio, sr, stem_name)
        except Exception:
            pass

    result.vcmix_config = _generate_config(result)
    return result
