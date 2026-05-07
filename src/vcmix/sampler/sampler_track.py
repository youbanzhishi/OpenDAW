"""
sampler_track.py — SamplerTrack integration for VCMix renderer.

Provides a high-level interface for rendering sampler tracks within
the VCMix project pipeline. Integrates with the YAML config parser
and the main Renderer class.

Usage:
    from vcmix.sampler.sampler_track import SamplerTrack

    track = SamplerTrack.from_config(track_config, project_dir, sample_rate=44100)
    midi_events = track.parse_midi(midi_path)
    audio = track.render_from_midi(midi_events, total_samples, bpm=120)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from vcmix.midi.midi_parser import MidiNote, MidiParser
from vcmix.sampler.sample_zone import SampleZone
from vcmix.sampler.sampler_engine import SamplerEngine


class SamplerTrack:
    """High-level sampler track for the VCMix rendering pipeline.

    Manages a SamplerEngine with zones loaded from YAML config,
    and provides methods to render audio from MIDI events.

    Args:
        name: Track name.
        sample_rate: Output sample rate.
        zones: List of SampleZone instances.
        midi_file: Optional path to MIDI file.
        bpm: Beats per minute for MIDI timing.
    """

    def __init__(
        self,
        name: str = "sampler",
        sample_rate: int = 44100,
        zones: list[SampleZone] | None = None,
        midi_file: str | None = None,
        bpm: float = 120.0,
    ) -> None:
        """Initialize a SamplerTrack.

        Args:
            name: Track name.
            sample_rate: Output sample rate.
            zones: List of SampleZone instances.
            midi_file: Path to MIDI file.
            bpm: Beats per minute.
        """
        self.name = name
        self.sample_rate = sample_rate
        self.midi_file = midi_file
        self.bpm = bpm

        # Build the sampler engine
        self.engine = SamplerEngine(sample_rate=sample_rate)
        if zones:
            for zone in zones:
                self.engine.load_zone(zone)

    @classmethod
    def from_config(
        cls,
        track_config: Any,
        project_dir: Path,
        sample_rate: int = 44100,
    ) -> SamplerTrack:
        """Create a SamplerTrack from a YAML track config.

        Args:
            track_config: TrackConfig with type='sampler' and zones list.
            project_dir: Project directory for resolving file paths.
            sample_rate: Output sample rate.

        Returns:
            SamplerTrack instance with loaded zones.
        """
        zones: list[SampleZone] = []

        # Get zones from track config
        raw_zones = getattr(track_config, "zones", None)
        if raw_zones is None:
            # Try dict-style access (from YAML)
            if isinstance(track_config, dict):
                raw_zones = track_config.get("zones", [])
            else:
                raw_zones = []

        if raw_zones:
            for zone_data in raw_zones:
                if isinstance(zone_data, SampleZone):
                    zones.append(zone_data)
                elif hasattr(zone_data, "model_dump"):
                    # Pydantic model (SampleZoneConfig) — serialize to dict first
                    zone_dict = zone_data.model_dump()
                    file_path = zone_dict.get("file", "")
                    if file_path and not Path(file_path).is_absolute():
                        zone_dict["file"] = str(project_dir / file_path)
                    zones.append(SampleZone.from_dict(zone_dict))
                elif isinstance(zone_data, dict):
                    # Resolve relative file paths against project_dir
                    file_path = zone_data.get("file", "")
                    if file_path and not Path(file_path).is_absolute():
                        zone_data["file"] = str(project_dir / file_path)
                    zones.append(SampleZone.from_dict(zone_data))

        midi_file = getattr(track_config, "midi_file", None)
        if midi_file and not Path(midi_file).is_absolute():
            midi_file = str(project_dir / midi_file)

        bpm = getattr(track_config, "bpm", None) or 120.0

        return cls(
            name=getattr(track_config, "name", "sampler"),
            sample_rate=sample_rate,
            zones=zones,
            midi_file=midi_file,
            bpm=bpm,
        )

    def parse_midi(self, midi_path: str | None = None) -> list[MidiNote]:
        """Parse a MIDI file and extract note events.

        Args:
            midi_path: Path to MIDI file. Uses self.midi_file if None.

        Returns:
            List of MidiNote events sorted by start_beat.
        """
        path = midi_path or self.midi_file
        if not path:
            return []

        parser = MidiParser()
        midi_tracks, midi_info = parser.parse(path)

        # Use MIDI file BPM if available
        if midi_info.bpm > 0:
            self.bpm = midi_info.bpm

        # Merge all MIDI tracks' notes
        all_notes: list[MidiNote] = []
        for mt in midi_tracks:
            all_notes.extend(mt.notes)

        return sorted(all_notes, key=lambda n: (n.start_beat, n.note))

    def render_from_midi(
        self,
        notes: list[MidiNote],
        total_samples: int,
        bpm: float | None = None,
    ) -> np.ndarray:
        """Render audio from MIDI note events.

        Schedules note_on/note_off events on a sample-based timeline,
        then renders the sampler engine for the full duration.

        Args:
            notes: List of MidiNote events.
            total_samples: Total number of output samples to render.
            bpm: Beats per minute. Uses self.bpm if None.

        Returns:
            1D float32 audio array.
        """
        if not notes:
            return np.zeros(total_samples, dtype=np.float32)

        bpm = bpm or self.bpm
        if bpm <= 0:
            bpm = 120.0

        samples_per_beat = (60.0 / bpm) * self.sample_rate

        # Build event timeline: (sample_position, event_type, note, velocity)
        events: list[tuple[int, str, int, int]] = []
        for note in notes:
            start_sample = int(note.start_beat * samples_per_beat)
            end_sample = int((note.start_beat + note.duration_beats) * samples_per_beat)
            events.append((start_sample, "note_on", note.note, note.velocity))
            events.append((end_sample, "note_off", note.note, 0))

        # Sort by sample position (note_off before note_on at same position)
        events.sort(key=lambda e: (e[0], e[1] == "note_on"))

        # Render block-by-block, processing events at each sample position
        output = np.zeros(total_samples, dtype=np.float32)
        event_idx = 0
        current_sample = 0

        while current_sample < total_samples:
            # Process all events at the current position
            while event_idx < len(events) and events[event_idx][0] <= current_sample:
                _, event_type, note, velocity = events[event_idx]
                if event_type == "note_on":
                    self.engine.note_on(note, velocity)
                elif event_type == "note_off":
                    self.engine.note_off(note)
                event_idx += 1

            # Determine block size: render until next event or end
            next_event_sample = total_samples
            if event_idx < len(events):
                next_event_sample = events[event_idx][0]

            block_size = min(next_event_sample - current_sample, total_samples - current_sample)
            if block_size <= 0:
                block_size = min(256, total_samples - current_sample)
                if block_size <= 0:
                    break

            # Render this block
            block = self.engine.render(block_size)
            end = min(current_sample + len(block), total_samples)
            length = end - current_sample
            if length > 0:
                output[current_sample:end] = block[:length]

            current_sample += block_size

        return output

    def render_full(self) -> np.ndarray:
        """Render the full track from MIDI file.

        Convenience method that parses MIDI and renders.

        Returns:
            1D float32 audio array.
        """
        notes = self.parse_midi()
        if not notes:
            return np.zeros(1, dtype=np.float32)

        # Compute total duration from notes
        bpm = self.bpm
        samples_per_beat = (60.0 / bpm) * self.sample_rate if bpm > 0 else (
            0.5 * self.sample_rate
        )
        max_end_beat = max(n.start_beat + n.duration_beats for n in notes)
        total_samples = int(max_end_beat * samples_per_beat) + self.sample_rate  # +1s tail

        return self.render_from_midi(notes, total_samples, bpm)

    @property
    def zone_count(self) -> int:
        """Number of loaded zones."""
        return len(self.engine.zones)

    @property
    def info(self) -> dict:
        """Track information summary."""
        return {
            "name": self.name,
            "sample_rate": self.sample_rate,
            "bpm": self.bpm,
            "zone_count": self.zone_count,
            "zones": self.engine.get_zone_info(),
            "midi_file": self.midi_file,
        }
