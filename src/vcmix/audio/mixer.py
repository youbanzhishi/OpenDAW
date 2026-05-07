"""
mixer.py — Multi-track audio mixing for VCMix.

Provides numpy-vectorized multi-track mixing with:
    - Per-track level (volume) control
    - Automatic length matching (zero-pad shorter tracks)
    - Master bus summing with clip prevention

Design principles:
    - No per-sample Python loops — all numpy vectorized
    - Supports arbitrary number of tracks
    - Mono/stereo compatible (broadcasts mono to stereo if needed)

Usage:
    from vcmix.audio.mixer import Mixer
    mixer = Mixer(sample_rate=44100)
    mixed = mixer.mix([vocal_audio, accomp_audio], levels=[0.8, 0.35])

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
        sample_rate: Project sample rate (used for future SRC support).
        clip_threshold: Hard clip threshold (default 1.0 = 0 dBFS).
    """

    sample_rate: int = 44100
    clip_threshold: float = 1.0

    def mix(
        self,
        tracks: list[np.ndarray],
        levels: list[float] | None = None,
    ) -> np.ndarray:
        """
        Mix multiple audio tracks into a single output.

        Each track is multiplied by its level, then all tracks are
        summed. Shorter tracks are zero-padded to match the longest.
        Output is hard-clipped at clip_threshold.

        Args:
            tracks: List of audio arrays (1D mono or 2D multi-channel).
            levels: Per-track level multipliers. None = all unity.

        Returns:
            Mixed audio array (same ndim as input tracks).

        Raises:
            ValueError: If tracks list is empty.
        """
        if not tracks:
            raise ValueError("Cannot mix empty track list")

        if levels is None:
            levels = [1.0] * len(tracks)

        if len(tracks) != len(levels):
            raise ValueError(
                f"Track count ({len(tracks)}) != level count ({len(levels)})"
            )

        # Determine output shape
        max_samples = max(t.shape[-1] for t in tracks)
        is_stereo = any(t.ndim == 2 for t in tracks)
        n_channels = max(t.shape[0] if t.ndim == 2 else 1 for t in tracks)

        # Build output
        if is_stereo:
            output = np.zeros((n_channels, max_samples), dtype=np.float64)
        else:
            output = np.zeros(max_samples, dtype=np.float64)

        for track, level in zip(tracks, levels):
            # Apply level
            scaled = track.astype(np.float64) * level

            # Broadcast mono to stereo if needed
            if is_stereo and scaled.ndim == 1:
                # Mono -> duplicate to all channels
                for ch in range(n_channels):
                    padded = np.zeros(max_samples, dtype=np.float64)
                    padded[:scaled.shape[0]] = scaled
                    output[ch] += padded
            elif scaled.ndim == 2 and is_stereo:
                for ch in range(scaled.shape[0]):
                    padded = np.zeros(max_samples, dtype=np.float64)
                    padded[:scaled.shape[1]] = scaled[ch]
                    output[ch] += padded
            else:
                # Mono mix
                padded = np.zeros(max_samples, dtype=np.float64)
                length = scaled.shape[0]
                padded[:length] = scaled
                output += padded

        # Hard clip at threshold
        output = np.clip(output, -self.clip_threshold, self.clip_threshold)

        return output.astype(np.float32)
