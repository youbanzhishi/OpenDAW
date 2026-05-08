"""
dynamics.py — Dynamics analysis with compression suggestions for VCMix.

Implements:
    - Signal level distribution histogram (with silence exclusion)
    - Compression suggestions (threshold/ratio + reason)
    - Crest factor (peak-to-RMS ratio)

Compression suggestion logic:
    1. Build level distribution histogram (10dB bins from -80 to 0 dBFS)
    2. Exclude silence (below -60 dBFS)
    3. Find the most active bin among non-silent signal
    4. Set threshold at that bin's lower edge to capture the signal body
    5. Recommend ratio based on dynamic range of active signal

Usage:
    from vcmix.analysis.dynamics import DynamicsAnalyzer
    analyzer = DynamicsAnalyzer(sample_rate=44100)
    result = analyzer.analyze(audio)

Dependencies: numpy
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class CompressionSuggestion:
    """Compression parameter suggestion with reasoning."""
    threshold_db: float
    ratio: float
    reason: str


@dataclass
class DynamicsResult:
    """Dynamics analysis result."""
    crest_factor_db: float
    level_distribution: dict[str, float]       # bin_range -> ratio
    compression_suggestion: CompressionSuggestion


class DynamicsAnalyzer:
    """
    Dynamics analyzer with compression suggestions.

    Args:
        sample_rate: Audio sample rate in Hz.
        silence_threshold_db: Level below which is considered silence (dBFS).
    """

    # Level distribution histogram bins (dBFS ranges)
    BINS = [
        (-80, -70), (-70, -60), (-60, -50), (-50, -40),
        (-40, -30), (-30, -20), (-20, -10), (-10, 0),
    ]

    def __init__(
        self,
        sample_rate: int = 44100,
        silence_threshold_db: float = -60.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.silence_threshold_db = silence_threshold_db

    def analyze(self, audio: np.ndarray) -> DynamicsResult:
        """
        Perform dynamics analysis.

        Args:
            audio: Audio array (1D mono or 2D multi-channel, float).

        Returns:
            DynamicsResult with crest factor, level distribution, and
            compression suggestion.
        """
        # Convert to mono
        if audio.ndim == 2:
            mono = np.mean(audio.astype(np.float64), axis=0)
        else:
            mono = audio.astype(np.float64)

        # Compute short-term RMS levels (50ms windows)
        win_size = int(self.sample_rate * 0.05)  # 50ms
        n_windows = max(1, len(mono) // win_size)

        levels = []
        for i in range(n_windows):
            start = i * win_size
            end = min(start + win_size, len(mono))
            block = mono[start:end]
            rms = np.sqrt(np.mean(block ** 2))
            if rms > 1e-20:
                levels.append(20.0 * np.log10(rms))
            else:
                levels.append(-120.0)

        levels = np.array(levels)

        # Separate active and silent levels
        active_levels = levels[levels > self.silence_threshold_db]
        silent_count = np.sum(levels <= self.silence_threshold_db)
        total_count = len(levels)

        if len(active_levels) < 2:
            return DynamicsResult(
                crest_factor_db=0.0,
                level_distribution=self._compute_distribution(levels),
                compression_suggestion=CompressionSuggestion(
                    threshold_db=-30.0,
                    ratio=2.0,
                    reason="信号不足，使用默认参数",
                ),
            )

        # Crest factor (based on active signal only)
        peak_db = np.max(active_levels)
        rms_db = np.mean(active_levels)
        crest_factor = round(float(peak_db - rms_db), 2)

        # Level distribution (all signal, including silence)
        level_dist = self._compute_distribution(levels)

        # Compression suggestion (based on active signal only)
        suggestion = self._suggest_compression(active_levels, crest_factor, silent_count, total_count)

        return DynamicsResult(
            crest_factor_db=crest_factor,
            level_distribution=level_dist,
            compression_suggestion=suggestion,
        )

    def _compute_distribution(self, levels: np.ndarray) -> dict[str, float]:
        """
        Compute level distribution histogram.

        Args:
            levels: Array of dBFS levels.

        Returns:
            Dict of bin_range -> ratio (sums to ~1.0).
        """
        total = len(levels)
        if total == 0:
            return {f"{lo}_to_{hi}": 0.0 for lo, hi in self.BINS}

        result = {}
        for lo, hi in self.BINS:
            count = np.sum((levels >= lo) & (levels < hi))
            key = f"{lo}_to_{hi}"
            result[key] = round(float(count / total), 2)

        return result

    def _suggest_compression(
        self, active_levels: np.ndarray, crest_factor: float,
        silent_count: int, total_count: int,
    ) -> CompressionSuggestion:
        """
        Generate compression suggestion based on active level distribution.

        Logic:
            1. Find the most populated bin among active signal
            2. Set threshold at the lower edge of that bin
            3. Ratio based on dynamic range:
               - crest < 6dB: gentle (ratio 2:1)
               - crest 6-12dB: moderate (ratio 3:1)
               - crest > 12dB: heavier (ratio 4:1)

        Args:
            active_levels: Array of dBFS levels (silence excluded).
            crest_factor: Crest factor in dB.
            silent_count: Number of silent windows.
            total_count: Total number of windows.

        Returns:
            CompressionSuggestion with threshold, ratio, and reason.
        """
        total_active = len(active_levels)
        if total_active == 0:
            return CompressionSuggestion(
                threshold_db=-30.0, ratio=2.0,
                reason="信号不足，使用默认参数",
            )

        # Find most populated bin among active levels
        active_bins = [b for b in self.BINS if b[0] >= self.silence_threshold_db]
        best_bin = active_bins[0]
        best_count = 0
        for lo, hi in active_bins:
            count = np.sum((active_levels >= lo) & (active_levels < hi))
            if count > best_count:
                best_count = count
                best_bin = (lo, hi)

        # Threshold at lower edge of most populated bin
        threshold = float(best_bin[0])

        # Ratio based on crest factor
        if crest_factor < 6.0:
            ratio = 2.0
            ratio_desc = "2:1 轻度压缩"
        elif crest_factor < 12.0:
            ratio = 3.0
            ratio_desc = "3:1 中等压缩"
        else:
            ratio = 4.0
            ratio_desc = "4:1 较强压缩"

        # Generate reason with context
        pct = round(float(best_count / total_active * 100), 0)
        silence_pct = round(float(silent_count / total_count * 100), 0) if total_count > 0 else 0
        reason = (
            f"大部分活跃信号在{best_bin[0]}~{best_bin[1]}dBFS区间"
            f"（占活跃信号{int(pct)}%）"
        )
        if silence_pct > 10:
            reason += f"，静音段占{int(silence_pct)}%"
        reason += (
            f"；{threshold}dB阈值可捕捉主体信号；"
            f"峰值因子{crest_factor:.1f}dB，建议{ratio_desc}"
        )

        return CompressionSuggestion(
            threshold_db=threshold,
            ratio=ratio,
            reason=reason,
        )

    def to_dict(self, result: DynamicsResult) -> dict[str, Any]:
        """Convert DynamicsResult to dict for JSON serialization."""
        return {
            "crest_factor_db": result.crest_factor_db,
            "level_distribution": result.level_distribution,
            "compression_suggestion": {
                "threshold_db": result.compression_suggestion.threshold_db,
                "ratio": result.compression_suggestion.ratio,
                "reason": result.compression_suggestion.reason,
            },
        }
