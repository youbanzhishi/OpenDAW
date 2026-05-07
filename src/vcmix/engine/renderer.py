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

Phase 7 additions:
    - Arrangement-aware rendering mode (--arrangement-aware)
    - Dynamic effect parameter adjustment per song section
    - Crossfade interpolation between sections
    - Integration with ArrangementStrategy for section-level mixing

Phase 9 additions:
    - MIDI track rendering via NoteScheduler
    - Automation curve parameter application (gain + plugin params)
    - Chain preset integration for effect chains

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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from vcmix.audio.io import read_audio, write_audio
from vcmix.audio.mixer import Mixer
from vcmix.automation.automation_engine import AutomationEngine
from vcmix.engine.analyzer import Analyzer
from vcmix.engine.arrangement_strategy import ArrangementStrategy
from vcmix.engine.autofix import AutoFix
from vcmix.engine.bus import BusManager

# Phase 9: MIDI and automation integration
from vcmix.midi.midi_parser import MidiParser
from vcmix.midi.note_scheduler import NoteScheduler
from vcmix.plugins.registry import PluginRegistry
from vcmix.separation.arrangement import ArrangementExtractor, Section
from vcmix.stream.emitter import DataStream
from vcmix.vst3.vst3_track import VST3ParamOverride, VST3Track, VST3TrackConfig

# ── Thresholds for warning detection ──────────────────────────────────────
_CLIP_THRESHOLD_DB = -1.0       # Peak above this = clipping warning
_LOW_SNR_THRESHOLD_DB = -36.0   # RMS below this = low SNR warning
_SIBILANCE_THRESHOLD = 0.15     # Sibilance ratio above this = de-ess needed


# ── Helper functions for arrangement-aware rendering ──────────────────────

def _simulate_reverb(audio: np.ndarray, mix: float, sr: int, beat_samples: int) -> np.ndarray:
    """Simple exponential decay reverb simulation."""
    decay = np.exp(-np.arange(beat_samples) / (sr * 0.3))
    impulse = np.zeros(beat_samples, dtype=np.float64)
    impulse[0] = 1.0
    # Simple multi-tap reverb
    for tap in [0.02, 0.04, 0.06]:
        idx = int(tap * sr)
        if idx < beat_samples:
            impulse[idx] = 0.3
    tail = np.convolve(
        audio.astype(np.float64),
        impulse * decay[:len(impulse)],
        mode="full",
    )[:beat_samples]
    return tail.astype(np.float32)


def _simulate_delay(audio: np.ndarray, mix: float, beat_samples: int) -> np.ndarray:
    """Simple delay simulation."""
    output = np.zeros(beat_samples, dtype=np.float64)
    src = audio.astype(np.float64)
    output[:len(src)] = src
    delay_samples = beat_samples // 2
    if delay_samples < len(src):
        end = delay_samples + len(src) - delay_samples
        output[delay_samples:end] += (
            src[:-delay_samples] * mix * 0.5
        )
    return output.astype(np.float32)


def _simulate_compression(audio: np.ndarray, ratio: float) -> np.ndarray:
    """Simple compression simulation."""
    threshold = 0.5
    output = audio.astype(np.float64).copy()
    mask = np.abs(output) > threshold
    output[mask] = np.sign(output[mask]) * (threshold + (np.abs(output[mask]) - threshold) / ratio)
    return output.astype(np.float32)


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
        arrangement_aware: Enable arrangement-aware rendering (Phase 7).
    """

    config: Any  # ProjectConfig
    report: bool = False
    auto_fix: bool = False
    stream: str = "log"
    ab_mode: bool = False
    ab_diff: bool = False
    # Phase 7: Arrangement-aware rendering
    arrangement_aware: bool = False
    # Phase 4: DataStream instance for real-time closed-loop data
    data_stream: DataStream = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    # Phase 7: Arrangement strategy (populated in __post_init__ if arrangement_aware)
    _arrangement_strategy: Any = field(default=None, init=False, repr=False)
    _arrangement_sections: list = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize DataStream based on stream format and arrangement strategy."""
        if self.stream == "json":
            self.data_stream = DataStream(format="json")
        else:
            self.data_stream = DataStream(format="dict")
        # Phase 7: Initialize arrangement strategy if arrangement_aware mode
        if self.arrangement_aware:
            self._init_arrangement_strategy()

    # ── Arrangement-aware rendering methods (Phase 7) ────────────────────

    def _init_arrangement_strategy(self) -> None:
        """Initialize the arrangement strategy from project stems."""
        project = self.config
        bpm = getattr(project, "bpm", 120)
        sr = getattr(project, "sample_rate", 44100)

        stems = getattr(project, "_stems", None)
        if stems and len(stems) > 0:
            extractor = ArrangementExtractor()
            self._arrangement_sections = extractor.extract(stems, sr, bpm)
        else:
            self._arrangement_sections = self._create_default_sections(bpm, sr)

        if self._arrangement_sections:
            self._arrangement_strategy = ArrangementStrategy.from_sections(
                self._arrangement_sections
            )
            self._emit("arrangement_init", {
                "sections": len(self._arrangement_sections),
                "total_beats": self._arrangement_strategy.total_beats,
            })

    def _create_default_sections(self, bpm: float, sr: int) -> list:
        """Create a default arrangement when no stems are available."""
        project = self.config
        project_dir = getattr(project, "_project_dir", Path("."))
        total_duration = 0.0

        for track in project.tracks:
            track_path = project_dir / track.file
            try:
                info = __import__("soundfile").info(str(track_path))
                total_duration = max(total_duration, info.duration)
            except Exception:
                pass

        if total_duration <= 0:
            total_duration = 180.0

        beat_sec = 60.0 / bpm if bpm > 0 else 0.5
        total_beats = int(total_duration / beat_sec)

        sections_def = [
            ("intro", 0, min(8, total_beats // 6)),
            ("verse", min(8, total_beats // 6), min(24, total_beats // 2)),
            ("chorus", min(24, total_beats // 2), min(40, total_beats * 2 // 3)),
            ("bridge", min(40, total_beats * 2 // 3), min(48, total_beats * 5 // 6)),
            ("outro", min(48, total_beats * 5 // 6), total_beats),
        ]

        result = []
        for name, start, end in sections_def:
            if end > start:
                result.append(Section(
                    name=name,
                    start_beat=start,
                    end_beat=end,
                    start_sec=start * beat_sec,
                    end_sec=end * beat_sec,
                    active_stems=[],
                    energy_level="medium",
                ))
        return result

    def _apply_arrangement_params(
        self,
        audio: np.ndarray,
        sr: int,
        bpm: float,
    ) -> np.ndarray:
        """Apply arrangement-aware effect parameters to audio."""
        if self._arrangement_strategy is None:
            return audio

        beat_samples = int(sr * 60.0 / bpm) if bpm > 0 else int(sr * 0.5)
        audio_flat = audio.flatten().astype(np.float64)
        total_samples = len(audio_flat)
        total_beats = (total_samples + beat_samples - 1) // beat_samples

        output = np.zeros_like(audio_flat)

        for beat in range(total_beats):
            start_sample = beat * beat_samples
            end_sample = min(start_sample + beat_samples, total_samples)
            beat_audio = audio_flat[start_sample:end_sample]

            params = self._arrangement_strategy.get_params_at_beat(beat)

            gain_linear = 10.0 ** (params.gain_db / 20.0)
            processed = beat_audio * gain_linear

            if params.reverb_mix > 0:
                reverb_tail = _simulate_reverb(processed, params.reverb_mix, sr, beat_samples)
                processed = processed * (1.0 - params.reverb_mix) + reverb_tail * params.reverb_mix

            if params.delay_mix > 0:
                delay_signal = _simulate_delay(processed, params.delay_mix, beat_samples)
                processed = processed * (1.0 - params.delay_mix) + delay_signal * params.delay_mix

            if params.compression_ratio > 1.0:
                processed = _simulate_compression(processed, params.compression_ratio)

            output[start_sample:end_sample] = processed[:end_sample - start_sample]

        if audio.ndim == 2:
            return output.reshape(audio.shape)
        return output.astype(np.float32)

    # ── Progress emission ────────────────────────────────────────────────

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
                f"Sibilance ratio {sibilance:.3f} "
                f"exceeds {_SIBILANCE_THRESHOLD:.2f} — de-ess needed",
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

        Phase 9: Supports MIDI tracks (type='midi') rendered via NoteScheduler,
        and audio tracks loaded from file. Automation curves are applied
        after the initial audio source is loaded/generated.

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
        # Phase 9: MIDI track rendering / VST3 track rendering
        track_type = getattr(track, 'type', 'audio')
        if track_type == 'midi' and track.midi_file:
            audio = self._render_midi_track(track, sr, project_dir)
        elif track_type == 'vst3' and getattr(track, 'plugin_path', None):
            audio = self._render_vst3_track(track, sr, project_dir)
        else:
            track_path = project_dir / track.file
            audio, audio_sr = read_audio(track_path)

        # Apply track volume
        audio = audio * track.volume

        # Phase 4: Emit initial track level
        self._emit_track_level(track.name, audio, sr)

        # Phase 7: Apply arrangement-aware processing if enabled
        if self.arrangement_aware:
            audio = self._apply_arrangement_params(audio, sr, self.config.bpm)

        # Get the effect chain
        effects = getattr(track, chain_key, None) or track.effects

        # Process insert chain
        # Phase 9: Check if track has plugin parameter automation
        has_automation = bool(getattr(track, 'automation', None))

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

            # Phase 9: Apply automation overrides to plugin params if needed
            # For block-level automation, use midpoint of current audio
            effect_params = dict(effect.params)
            if has_automation:
                # Use midpoint beat position for this effect processing pass
                bpm = self.config.bpm
                samples_per_beat = 60.0 / bpm * sr if bpm > 0 else sr * 0.5
                total_samples = len(prev_audio.flatten())
                mid_beat = (total_samples / 2) / samples_per_beat if samples_per_beat > 0 else 0.0
                effect_params = self._get_automation_overrides(
                    track, effect.name, effect.params, mid_beat
                )

            # Handle sidechain routing
            if effect.sidechain is not None and effect.sidechain in rendered_tracks:
                sc_audio = rendered_tracks[effect.sidechain]
                processed = plugin.process_with_sidechain(
                    prev_audio, effect_params, sr,
                    sidechain_audio=sc_audio,
                )
                self._emit("4_render", {
                    "track": track.name,
                    "effect": effect.name,
                    "sidechain": effect.sidechain,
                })
            else:
                processed = plugin.process(prev_audio, effect_params, sr)

            # Phase 4: Emit effect delta (before/after each effect)
            self._emit_effect_delta(track.name, effect.name, prev_audio, processed, sr)

            if self.report:
                label = f"{track.name}/before_{effect.name}"
                before = self._analyze_step(prev_audio, sr, label)
                after = self._analyze_step(processed, sr, f"{track.name}/after_{effect.name}")
                self._emit("4_report", {"before": before, "after": after})

            prev_audio = processed

        # Phase 9: Apply gain automation curves (block-by-block)
        if has_automation:
            prev_audio = self._render_track_with_automation(track, prev_audio, sr)
            self._emit("9_automation", {
                "track": track.name,
                "status": "applied",
            })

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
                    reason=(
                        f"Auto-fix applied {adjustments['gain_db']:.1f} "
                        f"dB gain to hit target RMS"
                    ),
                )

        return prev_audio

    # ── Phase 9: MIDI track rendering ──────────────────────────────────

    def _render_vst3_track(
        self,
        track: Any,
        sr: int,
        project_dir: Path,
    ) -> np.ndarray:
        """
        Render a VST3 plugin track.

        Supports two modes:
        - Instrument: generates audio from MIDI input
        - Effect: processes input audio through VST3 effect

        Args:
            track: TrackConfig with type='vst3'.
            sr: Sample rate.
            project_dir: Project directory.

        Returns:
            Rendered audio array.
        """
        plugin_path = getattr(track, 'plugin_path', '')
        if not plugin_path:
            raise ValueError(f"VST3 track '{track.name}' missing plugin_path")

        # Build VST3 track config from YAML track
        param_overrides = []
        raw_params = getattr(track, 'params', [])
        if isinstance(raw_params, list):
            for p in raw_params:
                if isinstance(p, dict):
                    param_overrides.append(VST3ParamOverride(
                        index=int(p.get("index", 0)),
                        value=float(p.get("value", 0.5)),
                    ))

        vst3_config = VST3TrackConfig(
            name=track.name,
            plugin_path=plugin_path,
            file=track.file,
            preset=getattr(track, 'preset', '') or '',
            preset_file=getattr(track, 'preset_file', '') or '',
            params=param_overrides,
            midi_file=getattr(track, 'midi_file', '') or '',
            bpm=self.config.bpm,
            sample_rate=sr,
            volume=track.volume,
            mute=track.mute,
        )

        vst3_track = VST3Track(vst3_config)

        # Determine render mode
        if vst3_track.is_instrument:
            # Instrument: render from MIDI
            duration = 0.0
            if vst3_track.config.midi_file:
                midi_path = project_dir / vst3_track.config.midi_file
                if midi_path.exists():
                    # Estimate duration from MIDI file
                    try:
                        parser = MidiParser()
                        midi_data = parser.parse(str(midi_path))
                        if midi_data and midi_data.get('duration_sec', 0) > 0:
                            duration = midi_data['duration_sec']
                    except Exception:
                        pass

            if duration <= 0:
                duration = 10.0  # default

            self._emit("4_vst3_render", {
                "track": track.name,
                "mode": "instrument",
                "plugin": plugin_path,
                "duration": duration,
            })

            audio = vst3_track.render(duration=duration)
        else:
            # Effect: process input audio
            if not track.file:
                raise ValueError(
                    f"VST3 effect track '{track.name}' requires 'file' for input audio"
                )

            input_path = project_dir / track.file
            input_audio, _ = read_audio(input_path)

            self._emit("4_vst3_render", {
                "track": track.name,
                "mode": "effect",
                "plugin": plugin_path,
                "input": str(input_path),
            })

            audio = vst3_track.render(input_audio=input_audio)

        self._emit("4_vst3_done", {
            "track": track.name,
            "samples": len(audio.flatten()),
        })

        return audio

    def _render_midi_track(
        self,
        track: Any,
        sr: int,
        project_dir: Path,
    ) -> np.ndarray:
        """Render a MIDI track using the NoteScheduler.

        Parses the MIDI file, creates a NoteScheduler with the configured
        synth type, and renders all notes into an audio buffer.

        Args:
            track: TrackConfig with type='midi' and midi_file set.
            sr: Project sample rate.
            project_dir: Project directory for resolving MIDI file path.

        Returns:
            1D or 2D float32 audio array.
        """
        midi_path = project_dir / track.midi_file
        parser = MidiParser()
        midi_tracks, midi_info = parser.parse(midi_path)

        # Determine BPM: prefer MIDI file tempo, fall back to project BPM
        bpm = midi_info.bpm if midi_info.bpm > 0 else self.config.bpm

        # Determine synth type
        synth_type = track.synth or 'sine'

        # Create NoteScheduler
        scheduler = NoteScheduler(
            bpm=bpm,
            sample_rate=sr,
            synth=synth_type,
        )

        # Merge all MIDI tracks' notes into a single list
        all_notes = []
        for mt in midi_tracks:
            all_notes.extend(mt.notes)

        if not all_notes:
            self._emit("9_midi_render", {
                "track": track.name,
                "status": "no_notes",
            })
            return np.zeros(1, dtype=np.float32)

        # Compute total beats from all notes
        max_end_beat = max(n.start_beat + n.duration_beats for n in all_notes)

        # Render all notes
        audio = scheduler.render_note_list(
            notes=all_notes,
            total_beats=max_end_beat,
        )

        # Ensure output is at least 1D
        if audio.ndim == 0 or len(audio) == 0:
            audio = np.zeros(1, dtype=np.float32)

        self._emit("9_midi_render", {
            "track": track.name,
            "synth": synth_type,
            "bpm": bpm,
            "note_count": len(all_notes),
            "total_beats": round(max_end_beat, 2),
            "duration_samples": len(audio),
        })

        return audio

    # ── Phase 9: Automation parameter application ──────────────────────

    def _render_track_with_automation(
        self,
        track: Any,
        audio: np.ndarray,
        sr: int,
    ) -> np.ndarray:
        """Apply automation curves to a track's audio.

        Processes the audio block-by-block, applying gain automation
        and preparing plugin parameter overrides for each block's
        beat position.

        Args:
            track: TrackConfig with automation definitions.
            audio: Pre-rendered audio (after effects chain).
            sr: Project sample rate.

        Returns:
            Audio with automation applied.
        """
        automation = getattr(track, 'automation', None)
        if not automation:
            return audio

        # Build AutomationEngine from the track's automation config
        track_config_dict = {
            "name": track.name,
            "automation": automation,
        }
        auto_engine = AutomationEngine.from_config(
            [track_config_dict],
            bpm=self.config.bpm,
        )

        if not auto_engine.has_automation:
            return audio

        bpm = self.config.bpm
        samples_per_beat = 60.0 / bpm * sr if bpm > 0 else sr * 0.5
        block_size = min(1024, len(audio))
        audio_flat = audio.flatten().astype(np.float64)
        total_samples = len(audio_flat)
        output = np.zeros_like(audio_flat)

        for i in range(0, total_samples, block_size):
            end = min(i + block_size, total_samples)
            block = audio_flat[i:end].copy()
            position_beat = i / samples_per_beat

            # Get automation parameters at this beat position
            params = auto_engine.get_params_at_beat(track.name, position_beat)

            # Apply gain automation (gain is in dB)
            if 'gain' in params:
                gain_db = params['gain']
                gain_linear = 10.0 ** (gain_db / 20.0)
                block *= gain_linear

            output[i:end] = block

        if audio.ndim == 2:
            return output.reshape(audio.shape).astype(np.float32)
        return output.astype(np.float32)

    def _get_automation_overrides(
        self,
        track: Any,
        plugin_name: str,
        static_params: dict[str, Any],
        beat: float,
    ) -> dict[str, Any]:
        """Get plugin parameters with automation overrides applied.

        Automation values take precedence over static values.

        Args:
            track: TrackConfig with automation definitions.
            plugin_name: Plugin identifier (e.g. 'vc-reverb').
            static_params: Original (static) parameters from YAML.
            beat: Current beat position.

        Returns:
            Updated parameters dict with automation overrides.
        """
        automation = getattr(track, 'automation', None)
        if not automation:
            return dict(static_params)

        track_config_dict = {
            "name": track.name,
            "automation": automation,
        }
        auto_engine = AutomationEngine.from_config(
            [track_config_dict],
            bpm=self.config.bpm,
        )

        return auto_engine.apply_automation_to_params(
            track.name,
            plugin_name,
            static_params,
            beat,
        )

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
        # Phase 9: MIDI tracks validated differently from audio tracks
        for track in project.tracks:
            if getattr(track, 'type', 'audio') == 'midi' and track.midi_file:
                midi_path = project_dir / track.midi_file
                if not midi_path.exists():
                    raise FileNotFoundError(f"MIDI file not found: {midi_path}")
            else:
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
                status = "muted" if track else "missing"
                self._emit("4_render", {"track": track_name, "status": status})
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
                max_len = max(
                    max(len(a.flatten()) for a in returns.values())
                    for returns in all_returns
                    if returns
                )
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
        """Render A/B comparison versions."""
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

        for effect in project.master.effects:
            plugin = registry.get(effect.name)
            if plugin is None:
                continue
            mixed_a = plugin.process(mixed_a, effect.params, sr)

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

        track_names_b = list(rendered_b.keys())
        track_audios_b = [rendered_b[n] for n in track_names_b]
        track_levels_b = [project.master.levels.get(n, 1.0) for n in track_names_b]
        mixed_b = mixer.mix(track_audios_b, levels=track_levels_b)

        for effect in project.master.effects:
            plugin = registry.get(effect.name)
            if plugin is None:
                continue
            mixed_b = plugin.process(mixed_b, effect.params, sr)

        output_b = project_dir / original_output.with_name(
            original_output.stem + "_b" + original_output.suffix
        )
        write_audio(mixed_b, output_b, sr)
        self._emit("7ab_output_b", {"path": str(output_b)})

        # Diff analysis
        if self.ab_diff:
            analyzer = Analyzer(sample_rate=sr)
            diff_report = analyzer.compare(mixed_a, mixed_b)

            min_len = min(len(mixed_a.flatten()), len(mixed_b.flatten()))
            a_flat = mixed_a.flatten()[:min_len].astype(np.float64)
            b_flat = mixed_b.flatten()[:min_len].astype(np.float64)
            diff_audio = a_flat - b_flat

            diff_rms = float(np.sqrt(np.mean(diff_audio ** 2)))
            diff_peak = float(np.max(np.abs(diff_audio)))
            diff_rms_db = round(
                20 * np.log10(diff_rms) if diff_rms > 0 else -120.0, 2
            )
            diff_report["diff_rms_db"] = diff_rms_db
            diff_peak_db = round(
                20 * np.log10(diff_peak) if diff_peak > 0 else -120.0, 2
            )
            diff_report["diff_peak_db"] = diff_peak_db

            self._emit("7ab_diff", diff_report)

    def _resolve_render_order(self, project: Any) -> list[str]:
        """Resolve track rendering order based on sidechain dependencies."""
        track_names = [t.name for t in project.tracks]
        deps: dict[str, set[str]] = {name: set() for name in track_names}

        for track in project.tracks:
            for effect in track.effects:
                if effect.sidechain is not None and effect.sidechain in track_names:
                    deps[track.name].add(effect.sidechain)

        in_degree = {name: 0 for name in track_names}
        for name, dep_set in deps.items():
            in_degree[name] = len(dep_set)

        queue = [name for name in track_names if in_degree[name] == 0]
        order: list[str] = []

        while queue:
            current = queue.pop(0)
            order.append(current)
            for name in track_names:
                if current in deps.get(name, set()):
                    deps[name].discard(current)
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)

        remaining = [name for name in track_names if name not in order]
        order.extend(remaining)

        return order

    def get_stream_events(self) -> list[Any]:
        """Get all accumulated DataStream events (for format='dict')."""
        return self.data_stream.get_events()
