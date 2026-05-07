"""
arrangement_mixer.py — Arrangement-mixing integration (Phase 15).

One-click compose + mix: generates a complete arrangement AND
applies smart mixing in a single pipeline.

Pipeline:
    1. AI composition → complete project config
    2. Auto-match mix preset → initial mixing parameters
    3. Initial render
    4. Smart mixing closed-loop optimization
    5. Output final audio + config

Usage:
    from vcmix.ai.arrangement_mixer import ArrangementMixer
    mixer = ArrangementMixer()
    result = mixer.compose_and_mix(
        genre="pop", duration=180, bpm=120,
        key="C", mood="happy", output_path="output.wav"
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from vcmix.ai.composer import AIComposer, CompositionResult
from vcmix.ai.smart_mixer import SmartMixer, SmartMixResult


@dataclass
class ComposeAndMixResult:
    """Result of one-click compose + mix.

    Attributes:
        composition: AI composition result.
        mix_result: Smart mixing result.
        final_config: Final project configuration after mixing.
        total_time_sec: Total processing time.
        status: Pipeline status ('success', 'partial', 'failed').
    """

    composition: CompositionResult | None = None
    mix_result: SmartMixResult | None = None
    final_config: dict[str, Any] = field(default_factory=dict)
    total_time_sec: float = 0.0
    status: str = "success"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "composition": self.composition.to_dict() if self.composition else None,
            "mix_result": self.mix_result.to_dict() if self.mix_result else None,
            "status": self.status,
            "total_time_sec": round(self.total_time_sec, 3),
            "final_config_keys": list(self.final_config.keys()) if self.final_config else [],
        }


class ArrangementMixer:
    """Arrangement-mixing integration.

    Combines AIComposer and SmartMixer into a single one-click pipeline.
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self.sample_rate = sample_rate
        self._composer = AIComposer()
        self._smart_mixer = SmartMixer(sample_rate=sample_rate)

    def compose_and_mix(
        self,
        genre: str,
        duration: float,
        bpm: float,
        key: str,
        mood: str,
        output_path: str | None = None,
        max_mix_iterations: int = 3,
        reference: str | None = None,
        render_fn: Any | None = None,
    ) -> ComposeAndMixResult:
        """
        One-click compose + mix pipeline.

        Args:
            genre: Musical genre (pop/rock/edm/hiphop/rnb/ballad).
            duration: Target duration in seconds.
            bpm: Tempo in beats per minute.
            key: Musical key (e.g. 'C', 'Am').
            mood: Mood (happy/sad/energetic/calm/dark/bright).
            output_path: Optional output file path.
            max_mix_iterations: Maximum smart mixing iterations.
            reference: Optional reference track path.
            render_fn: Optional render function for testing.

        Returns:
            ComposeAndMixResult with composition and mixing details.
        """
        start_time = time.time()
        result = ComposeAndMixResult()

        try:
            # Step 1: AI Composition
            composition = self._composer.compose(
                genre=genre,
                duration=duration,
                bpm=bpm,
                key=key,
                mood=mood,
                reference=reference,
            )
            result.composition = composition

            # Step 2: Auto-match mix preset (embedded in composition)
            # The composer already includes genre-appropriate effects

            # Step 3-4: Smart mixing closed-loop
            mix_result = self._smart_mixer.auto_mix(
                project_config=composition.project_config,
                max_iterations=max_mix_iterations,
                render_fn=render_fn,
            )
            result.mix_result = mix_result

            # Step 5: Final config
            result.final_config = mix_result.project_config
            result.status = "success" if mix_result.converged else "partial"

        except Exception as e:
            result.status = "failed"
            # Preserve partial results if available
            if result.composition is None:
                result.composition = CompositionResult(
                    project_config={"error": str(e)},
                    genre=genre,
                    key=key,
                    bpm=bpm,
                )

        result.total_time_sec = time.time() - start_time
        return result

    def compose_only(
        self,
        genre: str,
        duration: float,
        bpm: float,
        key: str,
        mood: str,
        reference: str | None = None,
    ) -> CompositionResult:
        """Run composition only, without mixing.

        Args:
            genre: Musical genre.
            duration: Target duration in seconds.
            bpm: Tempo in beats per minute.
            key: Musical key.
            mood: Mood.
            reference: Optional reference track.

        Returns:
            CompositionResult.
        """
        return self._composer.compose(
            genre=genre,
            duration=duration,
            bpm=bpm,
            key=key,
            mood=mood,
            reference=reference,
        )

    def mix_only(
        self,
        project_config: dict[str, Any] | str,
        max_iterations: int = 3,
        render_fn: Any | None = None,
    ) -> SmartMixResult:
        """Run smart mixing only, without composition.

        Args:
            project_config: VCMix project config dict or YAML file path.
            max_iterations: Maximum smart mixing iterations.
            render_fn: Optional render function for testing.

        Returns:
            SmartMixResult.
        """
        return self._smart_mixer.auto_mix(
            project_config=project_config,
            max_iterations=max_iterations,
            render_fn=render_fn,
        )
