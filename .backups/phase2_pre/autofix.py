"""
autofix.py — Adaptive parameter adjustment engine for VCMix.

Automatically corrects common mixing issues:
    - Gain staging (target RMS/headroom per stage)
    - Clip prevention (limiter insertion on hot signals)
    - Over-compression warnings

Rules-based engine in Phase 1; ML-based suggestions planned for Phase 3.

Usage:
    from vcmix.engine.autofix import AutoFix
    fixer = AutoFix(target_rms_db=-18.0, headroom_db=-1.0)
    adjustments = fixer.analyze(audio)
    fixed_audio = fixer.apply_gain(audio, adjustments["gain_db"])

Dependencies: numpy, vcmix.engine.analyzer
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from vcmix.engine.analyzer import Analyzer


@dataclass
class AutoFix:
    """
    Auto-fix engine for gain staging and signal quality.

    Args:
        target_rms_db: Target RMS level in dBFS (default -18 dBFS).
        headroom_db: Target headroom ceiling in dBFS (default -1 dB peak).
        sample_rate: Audio sample rate.
    """

    target_rms_db: float = -18.0
    headroom_db: float = -1.0
    sample_rate: int = 44100

    def analyze(self, audio: np.ndarray, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Analyze audio and compute recommended adjustments.

        Args:
            audio: Audio buffer to analyze.
            config: Optional track configuration dict.

        Returns:
            Dict with gain_db, limiter recommendation, and warnings.
        """
        analyzer = Analyzer(sample_rate=self.sample_rate)
        current_rms = analyzer.compute_rms(audio)
        current_peak = analyzer.compute_peak(audio)

        adjustments: dict[str, Any] = {
            "gain_db": 0.0,
            "limiter": False,
            "warnings": [],
        }

        if current_rms <= 0:
            adjustments["warnings"].append("Silent or near-silent track detected")
            return adjustments

        current_rms_db = 20 * np.log10(current_rms)
        current_peak_db = 20 * np.log10(current_peak) if current_peak > 0 else -120.0

        # Gain adjustment to hit target RMS
        gain_db = self.target_rms_db - current_rms_db
        adjustments["gain_db"] = round(gain_db, 2)

        # Check if limiter needed
        projected_peak_db = current_peak_db + gain_db
        if projected_peak_db > self.headroom_db:
            adjustments["limiter"] = True
            adjustments["warnings"].append(
                f"Peak would exceed headroom "
                f"({projected_peak_db:.1f} dBFS > {self.headroom_db:.1f} dBFS)"
            )

        # Warn on over-compression (very low dynamic range)
        dynamic_range = current_peak_db - current_rms_db
        if dynamic_range < 3.0:
            adjustments["warnings"].append(
                f"Low dynamic range ({dynamic_range:.1f} dB) — possible over-compression"
            )

        return adjustments

    def apply_gain(self, audio: np.ndarray, gain_db: float) -> np.ndarray:
        """
        Apply gain adjustment to audio buffer.

        Args:
            audio: Audio buffer.
            gain_db: Gain in dB to apply.

        Returns:
            Adjusted audio buffer (new array).
        """
        gain_linear = 10.0 ** (gain_db / 20.0)
        return audio * gain_linear
