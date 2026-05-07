"""
renderer.py — Main audio rendering engine for VCMix.

Orchestrates the rendering pipeline:
    1. Parse YAML project config
    2. Validate config & check audio files exist
    3. Build signal routing DAG (tracks -> insert chains -> sends -> master)
    4. Render each track through its effect chain (via PluginAdapter)
    5. Process Send/Return buses (Phase 2)
    6. Mix rendered tracks with master level balancing
    7. Apply master insert chain
    8. Write output file + optional analysis report

Phase 2 additions:
    - Send/Return bus processing
    - Sidechain routing
    - A/B comparison rendering
    - Gain staging chain analysis (AutoFix v2)

Phase 4 additions:
    - DataStream integration for closed-loop control rendering
    - Real-time track level / effect delta / master level events
    - Warning detection (clipping, low SNR, sibilance)
    - Decision events (auto-fix applied)

Features:
    - --report mode: emit RMS/Peak/spectrum after each effect
    - --stream log|json: real-time structured progress output
    - --auto-fix: automatic gain staging correction
    - --ab: render both A and B effect chains
    - --ab --diff: include difference analysis

Usage:
    from vcmix.engine.renderer import Renderer
    renderer = Renderer(config, report=True, stream="json")
    output_path = renderer.run()

Dependencies: numpy, soundfile, vcmix.config, vcmix.audio, vcmix.plugins
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from vcmix.audio.io import read_audio, write_audio
from vcmix.audio.mixer import Mixer
from vcmix.engine.analyzer import Analyzer
from vcmix.engine.autofix import AutoFix, ChainAnalysis
from vcmix.engine.bus import BusManager
from vcmix.plugins.registry import PluginRegistry
from vcmix.stream.emitter import DataStream, EventLevel

# ── Thresholds for warning detection ──────────────────────────────────────
_CLIP_THRESHOLD_DB = -1.0       # Peak above this = clipping warning
_LOW_SNR_THRESHOLD_DB = -36.0   # RMS below this = low SNR warning
_SIBILANCE_THRESHOLD = 0.15     # Sibilance ratio above this = de-ess needed


@dataclass
class Renderer:
    """
    Main rendering engine.

    Args:
        config: Parsed ProjectConfig from parse_project().
        report: Emit analysis data after each effect.
        auto_fix: Enable gain staging auto-correction.
        stream: Output format — 'log' (human), 'json' (structured), 'none'.
        ab_mode: Enable A/B comparison rendering (Phase 2).
        ab_diff: Include difference analysis in A/B mode (Phase 2).
    """

    config: Any  # ProjectConfig
    report: bool = False
    auto_fix: bool = False
    stream: str = "log"
    ab_mode: bool = False
    ab_diff: bool = False
    # Phase 4: DataStream instance for real-time closed-loop data
    data_stream: DataStream = field(default=None, init=False, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Initialize DataStream based on stream format."""
        if self.stream == "json":
            self.data_stream = DataStream(format="json")
        else:
            self.data_stream = DataStream(format="dict")

    def _emit(self, step: str, data: dict[str, Any]) -> None:
        """Emit progress data in the configured stream format."""
        if self.stream == "none":
            return
        if self.stream == "json":
            print(json.dumps({"step": step, **data}, ensure_ascii=False), flush=True)
        else:  # log
            msg = f"[{step}] " + " | ".join(f"{k}={v}" for k, v in data.items())
            print(msg, flush=True)

    # ── DataStream helper methods (Phase 4) ───────────────────────────────

    def _db(self, linear: float) -> float:
        """Convert linear value to dBFS, returning -120 for near-zero."""
        if linear > 1e-10:
            return float(20 * np.log10(linear))
        return -120.0

    def _emit_track_level(self, track_name: str, audio: np.ndarray, sr: int) -> None:
        """Emit per-track level data via DataStream."""
        analyzer = Analyzer(sample_rate=sr)
        rms = analyzer.compute_rms(audio)
        peak = analyzer.compute_peak(audio)
        true_peak = analyzer.compute_true_peak(audio)
        self.data_stream.emit_track_level(
            track_name,
            rms_db=self._db(rms),
            peak_db=self._db(peak),
            true_peak_db=self._db(true_peak),
        )

    def _emit_effect_delta(
        self,
        track_name: str,
        effect_name: str,
        before: np.ndarray,
        after: np.ndarray,
        sr: int,
    ) -> None:
        """Emit per-effect before/after analysis via DataStream."""
        analyzer = Analyzer(sample_rate=sr)
        before_rms = analyzer.compute_rms(before)
        after_rms = analyzer.compute_rms(after)
        before_peak = analyzer.compute_peak(before)
        after_peak = analyzer.compute_peak(after)
        delta_db = self._db(after_rms) - self._db(before_rms) if before_rms > 1e-10 else 0.0
        self.data_stream.emit_effect_delta(
            track_name,
            effect_name,
            before_rms=self._db(before_rms),
            after_rms=self._db(after_rms),
            before_peak=self._db(before_peak),
            after_peak=self._db(after_peak),
            delta_db=delta_db,
        )

    def _emit_master_level(self, audio: np.ndarray, sr: int) -> None:
        """Emit master bus level data via DataStream."""
        analyzer = Analyzer(sample_rate=sr)
        rms = analyzer.compute_rms(audio)
        peak = analyzer.compute_peak(audio)
        true_peak = analyzer.compute_true_peak(audio)
        self.data_stream.emit_master_level(
            rms_db=self._db(rms),
            peak_db=self._db(peak),
            true_peak_db=self._db(true_peak),
        )

    def _check_warnings(
        self,
        track_name: str,
        audio: np.ndarray,
        sr: int,
    ) -> None:
        """Check for clipping, low SNR, and sibilance warnings."""
        analyzer = Analyzer(sample_rate=sr)
        rms = analyzer.compute_rms(audio)
        peak = analyzer.compute_peak(audio)
        sibilance = analyzer.compute_sibilance(audio)

        rms_db = self._db(rms)
        peak_db = self._db(peak)

        # Clipping detection
        if peak_db > _CLIP_THRESHOLD_DB:
            self.data_stream.emit_warning(
                track_name,
                "clipping",
                f"Peak {peak_db:.1f} dBFS exceeds {_CLIP_THRESHOLD_DB:.1f} dBFS — clip risk",
            )

        # Low SNR detection
        if rms_db < _LOW_SNR_THRESHOLD_DB and rms_db > -120.0:
            self.data_stream.emit_warning(
                track_name,
                "low_snr",
                f"RMS {rms_db:.1f} dBFS below {_LOW_SNR_THRESHOLD_DB:.1f} dBFS — poor SNR",
            )

        # Sibilance detection
        if sibilance > _SIBILANCE_THRESHOLD:
            sib_db = float(20 * np.log10(sibilance)) if sibilance > 1e-10 else -120.0
            self.data_stream.emit_sibilance(track_name, sib_db)
            self.data_stream.emit_warning(
                track_name,
                "sibilance",
                f"Sibilance ratio {sibilance:.3f} exceeds {_SIBILANCE_THRESHOLD:.2f} — de-ess needed",
            )

    # ── Legacy analysis method ────────────────────────────────────────────

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

    # ── Track rendering ───────────────────────────────────────────────────

    def _render_track(
        self,
        track: Any,
        registry: PluginRegistry,
        sr: int,
        project_dir: Path,
        rendered_tracks: dict[str, np.ndarray],
        chain_key: str = "effects",
    ) -> np.ndarray:
        """
        Render a single track through its effect chain.

        Args:
            track: TrackConfig instance.
            registry: Plugin registry.
            sr: Project sample rate.
            project_dir: Project directory for resolving file paths.
            rendered_tracks: Dict of already-rendered tracks (for sidechain lookup).
            chain_key: Which effect chain to use ("effects", "effects_a", "effects_b").

        Returns:
            Rendered audio array.
        """
        track_path = project_dir / track.file
        audio, audio_sr = read_audio(track_path)

        # Apply track volume
        audio = audio * track.volume

        # Phase 4: Emit initial track level
        self._emit_track_level(track.name, audio, sr)

        # Get the effect chain
        effects = getattr(track, chain_key, None) or track.effects

        # Process insert chain
        prev_audio = audio
        for effect in effects:
            plugin = registry.get(effect.name)
            if plugin is None:
                self._emit("4_render", {
                    "track": track.name,
                    "effect": effect.name,
                    "status": "SKIPPED (not found)"
                })
                continue

            # Handle sidechain routing
            if effect.sidechain is not None and effect.sidechain in rendered_tracks:
                sc_audio = rendered_tracks[effect.sidechain]
                processed = plugin.process_with_sidechain(
                    prev_audio, effect.params, sr,
                    sidechain_audio=sc_audio,
                )
                self._emit("4_render", {
                    "track": track.name,
                    "effect": effect.name,
                    "sidechain": effect.sidechain,
                })
            else:
                processed = plugin.process(prev_audio, effect.params, sr)

            # Phase 4: Emit effect delta (before/after each effect)
            self._emit_effect_delta(track.name, effect.name, prev_audio, processed, sr)

            if self.report:
                label = f"{track.name}/before_{effect.name}"
                before = self._analyze_step(prev_audio, sr, label)
                after = self._analyze_step(processed, sr, f"{track.name}/after_{effect.name}")
                self._emit("4_report", {"before": before, "after": after})

            prev_audio = processed

        # Phase 4: Check for warnings on rendered track
        self._check_warnings(track.name, prev_audio, sr)

        # Phase 4: Emit final track level after all effects
        self._emit_track_level(track.name, prev_audio, sr)

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
                # Phase 4: Emit decision event for auto-fix
                self.data_stream.emit_decision(
                    track.name,
                    action="auto_fix_gain",
                    params={"gain_db": adjustments["gain_db"]},
                    reason=f"Auto-fix applied {adjustments['gain_db']:.1f} dB gain to hit target RMS",
                )

        return prev_audio

    def run(self) -> Path:
        """
        Execute the full rendering pipeline.

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

        # Phase 4: Start the DataStream timer
        self.data_stream.start()

        # ── Step 1: Parse (already done) ──
        self._emit("1_parse", {"name": project.name, "bpm": project.bpm})

        # ── Step 2: Validate ──
        for track in project.tracks:
            track_path = project_dir / track.file
            if not track_path.exists():
                raise FileNotFoundError(f"Track audio not found: {track_path}")
        self._emit("2_validate", {"tracks": len(project.tracks), "ok": True})

        # ── Step 3: Build DAG ──
        has_sends = len(project.sends) > 0 or any(t.sends for t in project.tracks)
        self._emit("3_dag", {
            "topology": "send_return" if has_sends else "linear_insert_chain",
            "sends": len(project.sends),
        })

        # ── Step 4: Render tracks ──
        registry = PluginRegistry()

        # Determine render order: sidechain sources must be rendered first
        render_order = self._resolve_render_order(project)

        rendered_tracks: dict[str, np.ndarray] = {}

        for track_name in render_order:
            track = next((t for t in project.tracks if t.name == track_name), None)
            if track is None or track.mute:
                self._emit("4_render", {"track": track_name, "status": "muted" if track else "missing"})
                continue

            prev_audio = self._render_track(track, registry, sr, project_dir, rendered_tracks)
            rendered_tracks[track.name] = prev_audio
            self._emit("4_render", {"track": track.name, "status": "done"})

        # ── Step 4.5: Process Send/Return buses ──
        bus_return_audio = np.zeros(1, dtype=np.float32)
        if has_sends and project.sends:
            bus_manager = BusManager.from_config(
                [s.model_dump() for s in project.sends],
                bpm=project.bpm,
            )

            all_returns: list[dict[str, np.ndarray]] = []
            for track in project.tracks:
                if track.name not in rendered_tracks or not track.sends:
                    continue
                track_returns = bus_manager.process_sends(
                    track.name,
                    rendered_tracks[track.name],
                    track.sends,
                    registry,
                    sr,
                )
                all_returns.append(track_returns)
                self._emit("4.5_sends", {
                    "track": track.name,
                    "buses": list(track.sends.keys()),
                })

            if all_returns:
                # Determine max length
                max_len = max(
                    max(len(a.flatten()) for a in returns.values())
                    for returns in all_returns
                    if returns
                )
                # Also consider rendered track lengths
                for audio in rendered_tracks.values():
                    max_len = max(max_len, len(audio.flatten()))

                bus_return_audio = bus_manager.mix_returns(all_returns, max_len)
                self._emit("4.5_returns", {"total_buses": len(bus_manager.buses)})

        # ── Step 5: Mix tracks ──
        mixer = Mixer(sample_rate=sr)
        track_names = list(rendered_tracks.keys())
        track_audios = [rendered_tracks[n] for n in track_names]
        track_levels = [
            project.master.levels.get(n, 1.0) for n in track_names
        ]
        mixed = mixer.mix(track_audios, levels=track_levels)

        # Add bus returns to mix
        if has_sends and len(bus_return_audio) > 1:
            mixed_flat = mixed.flatten().astype(np.float64)
            bus_flat = bus_return_audio.flatten().astype(np.float64)
            min_len = min(len(mixed_flat), len(bus_flat))
            mixed_flat[:min_len] += bus_flat[:min_len]
            mixed = mixed_flat.astype(np.float32)
            self._emit("5_mix", {"tracks": len(track_audios), "bus_returns": True})
        else:
            self._emit("5_mix", {"tracks": len(track_audios)})

        # Phase 4: Emit master level after mix (before master effects)
        self._emit_master_level(mixed, sr)

        # ── Step 6: Master insert chain ──
        prev_audio = mixed
        for effect in project.master.effects:
            plugin = registry.get(effect.name)
            if plugin is None:
                continue
            processed = plugin.process(prev_audio, effect.params, sr)

            # Phase 4: Emit effect delta for master effects
            self._emit_effect_delta("master", effect.name, prev_audio, processed, sr)

            if self.report:
                after = self._analyze_step(processed, sr, f"master/{effect.name}")
                self._emit("6_master_report", {"effect": effect.name, "analysis": after})
            prev_audio = processed

        # Phase 4: Emit final master level + check warnings
        self._emit_master_level(prev_audio, sr)
        self._check_warnings("master", prev_audio, sr)

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

        # ── A/B comparison mode ──
        if self.ab_mode and project.has_ab:
            self._render_ab(project, registry, sr, project_dir, output_path)

        return output_path

    def _render_ab(
        self,
        project: Any,
        registry: PluginRegistry,
        sr: int,
        project_dir: Path,
        original_output: Path,
    ) -> None:
        """
        Render A/B comparison versions.

        For each track with effects_a/effects_b, renders both chains
        and outputs separate files + optional diff analysis.
        """
        self._emit("7ab_start", {"mode": "A/B comparison"})

        # Render A version
        rendered_a: dict[str, np.ndarray] = {}
        for track in project.tracks:
            if track.effects_a is not None:
                audio = self._render_track(
                    track, registry, sr, project_dir, rendered_a, chain_key="effects_a"
                )
            else:
                audio = self._render_track(
                    track, registry, sr, project_dir, rendered_a, chain_key="effects"
                )
            rendered_a[track.name] = audio

        # Mix A
        mixer = Mixer(sample_rate=sr)
        track_names_a = list(rendered_a.keys())
        track_audios_a = [rendered_a[n] for n in track_names_a]
        track_levels_a = [project.master.levels.get(n, 1.0) for n in track_names_a]
        mixed_a = mixer.mix(track_audios_a, levels=track_levels_a)

        # Apply master chain to A
        for effect in project.master.effects:
            plugin = registry.get(effect.name)
            if plugin is None:
                continue
            mixed_a = plugin.process(mixed_a, effect.params, sr)

        # Write A output
        output_a = project_dir / original_output.with_name(
            original_output.stem + "_a" + original_output.suffix
        )
        write_audio(mixed_a, output_a, sr)
        self._emit("7ab_output_a", {"path": str(output_a)})

        # Render B version
        rendered_b: dict[str, np.ndarray] = {}
        for track in project.tracks:
            if track.effects_b is not None:
                audio = self._render_track(
                    track, registry, sr, project_dir, rendered_b, chain_key="effects_b"
                )
            else:
                audio = self._render_track(
                    track, registry, sr, project_dir, rendered_b, chain_key="effects"
                )
            rendered_b[track.name] = audio

        # Mix B
        track_names_b = list(rendered_b.keys())
        track_audios_b = [rendered_b[n] for n in track_names_b]
        track_levels_b = [project.master.levels.get(n, 1.0) for n in track_names_b]
        mixed_b = mixer.mix(track_audios_b, levels=track_levels_b)

        # Apply master chain to B
        for effect in project.master.effects:
            plugin = registry.get(effect.name)
            if plugin is None:
                continue
            mixed_b = plugin.process(mixed_b, effect.params, sr)

        # Write B output
        output_b = project_dir / original_output.with_name(
            original_output.stem + "_b" + original_output.suffix
        )
        write_audio(mixed_b, output_b, sr)
        self._emit("7ab_output_b", {"path": str(output_b)})

        # Diff analysis
        if self.ab_diff:
            analyzer = Analyzer(sample_rate=sr)
            diff_report = analyzer.compare(mixed_a, mixed_b)

            # Compute sample-level difference
            min_len = min(len(mixed_a.flatten()), len(mixed_b.flatten()))
            a_flat = mixed_a.flatten()[:min_len].astype(np.float64)
            b_flat = mixed_b.flatten()[:min_len].astype(np.float64)
            diff_audio = a_flat - b_flat

            diff_rms = float(np.sqrt(np.mean(diff_audio ** 2)))
            diff_peak = float(np.max(np.abs(diff_audio)))
            diff_report["diff_rms_db"] = round(20 * np.log10(diff_rms) if diff_rms > 0 else -120.0, 2)
            diff_report["diff_peak_db"] = round(20 * np.log10(diff_peak) if diff_peak > 0 else -120.0, 2)

            self._emit("7ab_diff", diff_report)

    def _resolve_render_order(self, project: Any) -> list[str]:
        """
        Resolve track rendering order based on sidechain dependencies.

        If track B sidechains from track A, A must be rendered first.
        Uses topological sort on the dependency graph.
        """
        track_names = [t.name for t in project.tracks]
        # Build dependency graph: sidechain_source -> sidechain_consumer
        deps: dict[str, set[str]] = {name: set() for name in track_names}

        for track in project.tracks:
            for effect in track.effects:
                if effect.sidechain is not None and effect.sidechain in track_names:
                    # track depends on effect.sidechain being rendered first
                    deps[track.name].add(effect.sidechain)

        # Topological sort (Kahn's algorithm)
        in_degree = {name: 0 for name in track_names}
        for name, dep_set in deps.items():
            for dep in dep_set:
                in_degree[name] = in_degree.get(name, 0)  # ensure exists

        # Compute in-degrees properly
        in_degree = {name: 0 for name in track_names}
        for name, dep_set in deps.items():
            in_degree[name] = len(dep_set)

        queue = [name for name in track_names if in_degree[name] == 0]
        order: list[str] = []

        while queue:
            current = queue.pop(0)
            order.append(current)
            # Find all tracks that depend on current
            for name in track_names:
                if current in deps.get(name, set()):
                    deps[name].discard(current)
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)

        # If there's a cycle, just append remaining tracks
        remaining = [name for name in track_names if name not in order]
        order.extend(remaining)

        return order

    def get_stream_events(self) -> list[Any]:
        """Get all accumulated DataStream events (for format='dict')."""
        return self.data_stream.get_events()
