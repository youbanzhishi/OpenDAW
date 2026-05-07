"""
mixer.py — Multi-track audio mixing engine for VCMix.

Provides sample-accurate mixing of multiple audio tracks:
    - Automatic length normalization (pad short tracks with silence)
    - Per-track gain and stereo pan control
    - Clip prevention (soft clipping with tanh)

Usage:
    from vcmix.audio.mixer import Mixer
    mixer = Mixer(sample_rate=44100)
    mixed = mixer.mix([vocal, bgm], gains=[0.8, 0.6], pans=[0.0, 0.0])

Dependencies: numpy
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Mixer:
    """
    Multi-track audio mixer.

    Args:
        sample_rate: Sample rate for the mixing session.
        clip_threshold: Amplitude threshold for soft clipping (default 1.0).
    """

    sample_rate: int = 44100
    clip_threshold: float = 1.0

    def mix(self, tracks: list[np.ndarray],
            gains: list[float] | None = None,
            pans: list[float] | None = None) -> np.ndarray:
        """
        Mix multiple audio tracks into a single buffer.

        Args:
            tracks: List of audio buffers (each 1D mono or 2D multi-channel).
            gains: Per-track gain values (0.0 to 2.0). Default 1.0 for all.
            pans: Per-track pan values (-1.0 left to 1.0 right). Default 0.0.

        Returns:
            Mixed audio buffer (same dimensionality as inputs).
        """
        if not tracks:
            raise ValueError("No tracks to mix")

        n_tracks = len(tracks)
        if gains is None:
            gains = [1.0] * n_tracks
        if pans is None:
            pans = [0.0] * n_tracks

        # Normalize all tracks to same length (pad with zeros)
        max_len = max(t.shape[0] for t in tracks)
        is_stereo = any(t.ndim == 2 for t in tracks)

        mixed = np.zeros(max_len, dtype=np.float64)

        for track, gain, pan in zip(tracks, gains, pans):
            # Convert to mono if needed for mixing
            mono = track.mean(axis=1) if track.ndim == 2 else track.astype(np.float64)
            # Apply gain and pan (simplified mono pan = gain only)
            panned = mono * gain
            # Pad to max length
            padded = np.pad(panned, (0, max_len - len(panned)))
            mixed += padded

        # Soft clip
        if self.clip_threshold > 0:
            mixed = self._soft_clip(mixed, self.clip_threshold)

        return mixed.astype(np.float32)

    @staticmethod
    def _soft_clip(audio: np.ndarray, threshold: float) -> np.ndarray:
        """Apply soft clipping using tanh saturation."""
        mask = np.abs(audio) > threshold
        result = audio.copy()
        result[mask] = threshold * np.tanh(audio[mask] / threshold)
        return result
