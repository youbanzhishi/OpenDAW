"""
autofix.py — Adaptive parameter adjustment engine for VCMix.

Phase 1: Simple gain adjustment based on target RMS/headroom.
Phase 2: Full gain staging chain analysis with per-effect diagnostics.

Automatically corrects common mixing issues:
    - Gain staging (target RMS/headroom per stage)
    - Clip prevention (limiter insertion on hot signals)
    - Over-compression warnings
    - Gain accumulation detection (consecutive boost → clip risk)
    - Gain starvation detection (consecutive cut → poor SNR)
    - Per-effect input/output level analysis

Rules-based engine in Phase 1-2; ML-based suggestions planned for Phase 3.

Usage:
    from vcmix.engine.autofix import AutoFix
    fixer = AutoFix(target_rms_db=-18.0, headroom_db=-1.0)

    # Phase 1 API (backward compatible)
    adjustments = fixer.analyze(audio)
    fixed_audio = fixer.apply_gain(audio, adjustments["gain_db"])

    # Phase 2 API — chain analysis
    analysis = fixer.analyze_chain(track_audio, effects_config)
    fixed_config = fixer.fix_gain_staging(track_config, analysis)

Dependencies: numpy, vcmix.engine.analyzer
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vcmix.engine.analyzer import Analyzer


@dataclass
class GainStageInfo:
    """
    Per-effect gain stage analysis result.

    Attributes:
        effect_name: Name of the effect.
        input_rms_db: Input RMS level in dBFS.
        output_rms_db: Output RMS level in dBFS.
        input_peak_db: Input peak level in dBFS.
        output_peak_db: Output peak level in dBFS.
        gain_delta_db: Gain change through this effect (RMS).
        issues: List of detected issues at this stage.
    """

    effect_name: str = ""
    input_rms_db: float = -120.0
    output_rms_db: float = -120.0
    input_peak_db: float = -120.0
    output_peak_db: float = -120.0
    gain_delta_db: float = 0.0
    issues: list[str] = field(default_factory=list)


@dataclass
class ChainAnalysis:
    """
    Full effect chain gain staging analysis.

    Attributes:
        stages: Per-effect gain stage info.
        total_gain_db: Cumulative gain through the chain.
        clip_risk: Whether the chain risks clipping.
        snr_risk: Whether the chain risks poor SNR.
        warnings: General warnings about the chain.
        recommendations: Recommended gain adjustments.
    """

    stages: list[GainStageInfo] = field(default_factory=list)
    total_gain_db: float = 0.0
    clip_risk: bool = False
    snr_risk: bool = False
    warnings: list[str] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AutoFix:
    """
    Auto-fix engine for gain staging and signal quality.

    Args:
        target_rms_db: Target RMS level in dBFS (default -18 dBFS).
        headroom_db: Target headroom ceiling in dBFS (default -1 dB peak).
        sample_rate: Audio sample rate.
        input_ceiling_db: Maximum allowed effect input level (default -6 dBFS).
        output_floor_db: Minimum allowed effect output level (default -24 dBFS).
    """

    target_rms_db: float = -18.0
    headroom_db: float = -1.0
    sample_rate: int = 44100
    input_ceiling_db: float = -6.0
    output_floor_db: float = -24.0

    # ── Phase 1 API (backward compatible) ──────────────────────────────────

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

    # ── Phase 2 API — Gain Staging Chain Analysis ──────────────────────────

    def analyze_chain(
        self,
        track_audio: np.ndarray,
        effects_config: list[dict[str, Any]],
        rendered_stages: list[tuple[str, np.ndarray, np.ndarray]] | None = None,
    ) -> ChainAnalysis:
        """
        Analyze the entire effect chain's gain flow.

        Takes either a list of (effect_name, before_audio, after_audio) tuples
        from actual rendering, or simulates analysis from the config.

        Args:
            track_audio: Original track audio before any processing.
            effects_config: List of effect config dicts (name, params).
            rendered_stages: Optional list of (effect_name, input_audio, output_audio)
                tuples from actual rendering. If provided, used for accurate analysis.

        Returns:
            ChainAnalysis with per-stage info and recommendations.
        """
        analyzer = Analyzer(sample_rate=self.sample_rate)
        analysis = ChainAnalysis()

        if rendered_stages:
            # Use actual rendered audio for analysis
            for effect_name, before, after in rendered_stages:
                stage = self._analyze_stage(effect_name, before, after, analyzer)
                analysis.stages.append(stage)
        else:
            # Analyze from config only — limited information
            # We can only check the original track audio level
            stage = GainStageInfo(
                effect_name="input",
                input_rms_db=self._to_db(analyzer.compute_rms(track_audio)),
                output_rms_db=self._to_db(analyzer.compute_rms(track_audio)),
                input_peak_db=self._to_db(analyzer.compute_peak(track_audio)),
                output_peak_db=self._to_db(analyzer.compute_peak(track_audio)),
            )
            analysis.stages.append(stage)

        # Analyze cumulative gain
        if analysis.stages:
            first = analysis.stages[0]
            last = analysis.stages[-1]
            analysis.total_gain_db = last.output_rms_db - first.input_rms_db

        # Detect gain accumulation issues
        self._detect_accumulation_issues(analysis)

        return analysis

    def _analyze_stage(
        self,
        effect_name: str,
        before: np.ndarray,
        after: np.ndarray,
        analyzer: Analyzer,
    ) -> GainStageInfo:
        """Analyze a single effect's gain stage."""
        before_rms = analyzer.compute_rms(before)
        after_rms = analyzer.compute_rms(after)
        before_peak = analyzer.compute_peak(before)
        after_peak = analyzer.compute_peak(after)

        input_rms_db = self._to_db(before_rms)
        output_rms_db = self._to_db(after_rms)
        input_peak_db = self._to_db(before_peak)
        output_peak_db = self._to_db(after_peak)

        gain_delta = output_rms_db - input_rms_db if before_rms > 1e-10 else 0.0

        issues: list[str] = []

        # Rule 1: Input should not exceed input ceiling (-6 dBFS)
        if input_peak_db > self.input_ceiling_db:
            issues.append(
                f"Input peak ({input_peak_db:.1f} dBFS) exceeds ceiling "
                f"({self.input_ceiling_db:.1f} dBFS) — reduce input gain"
            )

        # Rule 2: Output should not fall below output floor (-24 dBFS)
        if output_rms_db < self.output_floor_db:
            issues.append(
                f"Output RMS ({output_rms_db:.1f} dBFS) below floor "
                f"({self.output_floor_db:.1f} dBFS) — poor SNR risk"
            )

        # Rule 3: Output peak should not exceed headroom
        if output_peak_db > self.headroom_db:
            issues.append(
                f"Output peak ({output_peak_db:.1f} dBFS) exceeds headroom "
                f"({self.headroom_db:.1f} dBFS) — clip risk"
            )

        return GainStageInfo(
            effect_name=effect_name,
            input_rms_db=round(input_rms_db, 2),
            output_rms_db=round(output_rms_db, 2),
            input_peak_db=round(input_peak_db, 2),
            output_peak_db=round(output_peak_db, 2),
            gain_delta_db=round(gain_delta, 2),
            issues=issues,
        )

    def _detect_accumulation_issues(self, analysis: ChainAnalysis) -> None:
        """
        Detect gain accumulation problems across the chain.

        Rules:
            1. Consecutive gain boosts > 6dB total → clip risk
            2. Consecutive gain cuts > 12dB total → SNR risk
            3. Final output above -1 dBFS → clip risk
            4. Final output below -24 dBFS → SNR risk
        """
        if len(analysis.stages) < 2:
            return

        # Track consecutive boost/cut streaks
        consecutive_boost = 0.0
        consecutive_cut = 0.0

        for stage in analysis.stages:
            delta = stage.gain_delta_db

            if delta > 0:
                consecutive_boost += delta
                consecutive_cut = 0.0
            elif delta < 0:
                consecutive_cut += abs(delta)
                consecutive_boost = 0.0
            else:
                consecutive_boost = 0.0
                consecutive_cut = 0.0

            # Rule: consecutive boost > 6dB → clip risk
            if consecutive_boost > 6.0:
                analysis.clip_risk = True
                analysis.warnings.append(
                    f"Consecutive gain boost of {consecutive_boost:.1f} dB "
                    f"through chain — clip risk at '{stage.effect_name}'"
                )

            # Rule: consecutive cut > 12dB → SNR risk
            if consecutive_cut > 12.0:
                analysis.snr_risk = True
                analysis.warnings.append(
                    f"Consecutive gain cut of {consecutive_cut:.1f} dB "
                    f"through chain — SNR risk at '{stage.effect_name}'"
                )

        # Final output checks
        last_stage = analysis.stages[-1]
        if last_stage.output_peak_db > self.headroom_db:
            analysis.clip_risk = True
            analysis.warnings.append(
                f"Final output peak ({last_stage.output_peak_db:.1f} dBFS) "
                f"exceeds headroom — clip risk"
            )

        if last_stage.output_rms_db < self.output_floor_db:
            analysis.snr_risk = True
            analysis.warnings.append(
                f"Final output RMS ({last_stage.output_rms_db:.1f} dBFS) "
                f"below floor — poor SNR"
            )

    def fix_gain_staging(
        self,
        track_config: dict[str, Any],
        analysis: ChainAnalysis,
    ) -> dict[str, Any]:
        """
        Auto-fix gain staging based on chain analysis.

        Inserts gain adjustment nodes at key points:
            - Before effects with excessive input level
            - After effects that cut too much signal
            - At the end of chain to hit target output level

        Rules:
            1. Effect input ≤ -6 dBFS (headroom)
            2. Effect output ≥ -24 dBFS (SNR floor)
            3. Final output ≤ -1 dBFS (clip prevention)
            4. Gain compensation: if effect attenuates, compensate after

        Args:
            track_config: Track configuration dict with 'effects' list.
            analysis: ChainAnalysis from analyze_chain().

        Returns:
            Modified track_config with gain adjustments inserted.
        """
        import copy
        fixed_config = copy.deepcopy(track_config)
        effects = fixed_config.get("effects", [])

        # Build a list of (index, gain_db) adjustments to insert
        insertions: list[tuple[int, float]] = []

        for i, stage in enumerate(analysis.stages):
            if not stage.issues:
                continue

            for issue in stage.issues:
                if "exceeds ceiling" in issue:
                    # Need to reduce input gain
                    excess = stage.input_peak_db - self.input_ceiling_db
                    if excess > 0:
                        insertions.append((i, -round(excess + 1.0, 1)))

                elif "below floor" in issue:
                    # Need to boost output
                    deficit = self.output_floor_db - stage.output_rms_db
                    if deficit > 0:
                        insertions.append((i + 1, round(deficit + 1.0, 1)))

        # Apply insertions (reverse order to maintain indices)
        for idx, gain_db in sorted(insertions, reverse=True):
            gain_effect = {
                "name": "vc-gain",
                "params": {"gain": gain_db},
            }
            effects.insert(idx, gain_effect)

        # Final output level check — ensure not clipping
        if analysis.stages:
            last = analysis.stages[-1]
            if last.output_peak_db > self.headroom_db:
                excess = last.output_peak_db - self.headroom_db
                effects.append({
                    "name": "vc-gain",
                    "params": {"gain": -round(excess + 0.5, 1)},
                })

        fixed_config["effects"] = effects
        return fixed_config

    @staticmethod
    def _to_db(value: float) -> float:
        """Convert linear value to dBFS. Returns -120 for zero/near-zero."""
        if value > 1e-10:
            return 20.0 * np.log10(value)
        return -120.0
