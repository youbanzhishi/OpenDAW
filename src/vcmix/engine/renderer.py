"""
renderer.py — Main audio rendering engine for VCMix.

Orchestrates the 7-step rendering pipeline:
    1. Parse YAML project config
    2. Validate config & check audio files exist
    3. Build signal routing DAG (tracks -> insert chains -> master)
    4. Render each track through its effect chain (via PluginAdapter)
    5. Mix rendered tracks with master level balancing
    6. Apply master insert chain
    7. Write output file + optional analysis report

Features:
    - --report mode: emit RMS/Peak/spectrum after each effect
    - --stream log|json: real-time structured progress output
    - --auto-fix: automatic gain staging correction
    - Incremental rendering via SHA-256 cache fingerprints (Phase 2)

Usage:
    from vcmix.engine.renderer import Renderer
    renderer = Renderer(config, report=True, stream="json")
    output_path = renderer.run()

Dependencies: numpy, soundfile, vcmix.config, vcmix.audio, vcmix.plugins
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from vcmix.audio.io import read_audio, write_audio
from vcmix.audio.mixer import Mixer
from vcmix.engine.analyzer import Analyzer
from vcmix.engine.autofix import AutoFix
from vcmix.plugins.registry import PluginRegistry


@dataclass
class Renderer:
    """
    Main rendering engine.

    Args:
        config: Parsed ProjectConfig from parse_project().
        report: Emit analysis data after each effect.
        auto_fix: Enable gain staging auto-correction.
        stream: Output format — 'log' (human), 'json' (structured), 'none'.
    """

    config: Any  # ProjectConfig
    report: bool = False
    auto_fix: bool = False
    stream: str = "log"

    def _emit(self, step: str, data: dict[str, Any]) -> None:
        """Emit progress data in the configured stream format."""
        if self.stream == "none":
            return
        if self.stream == "json":
            print(json.dumps({"step": step, **data}, ensure_ascii=False), flush=True)
        else:  # log
            msg = f"[{step}] " + " | ".join(f"{k}={v}" for k, v in data.items())
            print(msg, flush=True)

    def _analyze_step(self, audio: np.ndarray, sr: int, label: str) -> dict[str, Any]:
        """Run analyzer on audio and return metrics dict."""
        analyzer = Analyzer(sample_rate=sr)
        rms = analyzer.compute_rms(audio)
        peak = analyzer.compute_peak(audio)
        true_peak = analyzer.compute_true_peak(audio)
        spectrum = analyzer.compute_spectrum(audio)
        sibilance = analyzer.compute_sibilance(audio)

        return {
            "label": label,
            "rms_db": round(20 * np.log10(rms) if rms > 0 else -120.0, 2),
            "peak_db": round(20 * np.log10(peak) if peak > 0 else -120.0, 2),
            "true_peak_db": round(20 * np.log10(true_peak) if true_peak > 0 else -120.0, 2),
            "sibilance_db": round(sibilance, 2),
            "spectrum_bands": len(spectrum),
        }

    def run(self) -> Path:
        """
        Execute the full 7-step rendering pipeline.

        Returns:
            Path to the rendered output file.

        Raises:
            FileNotFoundError: If a track audio file doesn't exist.
            RuntimeError: If a plugin CLI execution fails.
        """
        t0 = time.time()
        project = self.config
        sr = project.sample_rate
        project_dir = getattr(project, "_project_dir", Path("."))

        # ── Step 1: Parse (already done) ──
        self._emit("1_parse", {"name": project.name, "bpm": project.bpm})

        # ── Step 2: Validate ──
        for track in project.tracks:
            track_path = project_dir / track.file
            if not track_path.exists():
                raise FileNotFoundError(f"Track audio not found: {track_path}")
        self._emit("2_validate", {"tracks": len(project.tracks), "ok": True})

        # ── Step 3: Build DAG ──
        # Phase 1: simple linear chain, no DAG complexity
        self._emit("3_dag", {"topology": "linear_insert_chain"})

        # ── Step 4: Render tracks ──
        registry = PluginRegistry()
        rendered_tracks: dict[str, np.ndarray] = {}

        for track in project.tracks:
            if track.mute:
                self._emit("4_render", {"track": track.name, "status": "muted"})
                continue

            track_path = project_dir / track.file
            audio, audio_sr = read_audio(track_path)

            # Resample if needed
            if audio_sr != sr:
                self._emit("4_render", {
                    "track": track.name, "resample": f"{audio_sr}->{sr}"
                })

            # Apply track volume
            audio = audio * track.volume

            # Process insert chain
            prev_audio = audio
            for effect in track.effects:
                plugin = registry.get(effect.name)
                if plugin is None:
                    self._emit("4_render", {
                        "track": track.name,
                        "effect": effect.name,
                        "status": "SKIPPED (not found)"
                    })
                    continue

                processed = plugin.process(prev_audio, effect.params, sr)

                if self.report:
                    label = f"{track.name}/before_{effect.name}"
                    before = self._analyze_step(prev_audio, sr, label)
                    after = self._analyze_step(processed, sr, f"{track.name}/after_{effect.name}")
                    self._emit("4_report", {"before": before, "after": after})

                prev_audio = processed

            # Auto-fix gain staging if requested
            if self.auto_fix:
                fixer = AutoFix(sample_rate=sr)
                adjustments = fixer.analyze(prev_audio)
                if adjustments["gain_db"] != 0.0:
                    prev_audio = fixer.apply_gain(prev_audio, adjustments["gain_db"])
                    self._emit("4_autofix", {
                        "track": track.name,
                        "gain_db": adjustments["gain_db"]
                    })

            rendered_tracks[track.name] = prev_audio
            self._emit("4_render", {"track": track.name, "status": "done"})

        # ── Step 5: Mix tracks ──
        mixer = Mixer(sample_rate=sr)
        track_names = list(rendered_tracks.keys())
        track_audios = [rendered_tracks[n] for n in track_names]
        track_levels = [
            project.master.levels.get(n, 1.0) for n in track_names
        ]
        mixed = mixer.mix(track_audios, levels=track_levels)
        self._emit("5_mix", {"tracks": len(track_audios)})

        # ── Step 6: Master insert chain ──
        prev_audio = mixed
        for effect in project.master.effects:
            plugin = registry.get(effect.name)
            if plugin is None:
                continue
            processed = plugin.process(prev_audio, effect.params, sr)
            if self.report:
                after = self._analyze_step(processed, sr, f"master/{effect.name}")
                self._emit("6_master_report", {"effect": effect.name, "analysis": after})
            prev_audio = processed

        self._emit("6_master", {"effects": len(project.master.effects)})

        # ── Step 7: Output ──
        output_path = project_dir / project.master.output
        write_audio(prev_audio, output_path, sr)

        elapsed = round(time.time() - t0, 2)
        final_analysis = self._analyze_step(prev_audio, sr, "final") if self.report else {}
        self._emit("7_output", {
            "path": str(output_path),
            "elapsed_s": elapsed,
            **final_analysis,
        })

        return output_path
