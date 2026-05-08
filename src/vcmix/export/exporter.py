"""
exporter.py — Multi-format audio export and stem export for VCMix (Phase 18).

Supports export to WAV, MP3, FLAC, OGG, and MIDI formats.
Provides per-track (stem) export and per-bus export capabilities.

Architecture:
    - AudioExporter: Main exporter class
    - Uses soundfile for WAV/FLAC/OGG
    - Uses ffmpeg subprocess for MP3 (via pydub or direct)
    - Uses mido for MIDI export
    - Stem export renders each track independently
    - Bus export groups tracks by their bus assignment

Usage:
    from vcmix.export.exporter import AudioExporter
    exporter = AudioExporter()
    exporter.export("input.wav", "output.mp3", "mp3", {"bitrate": "320k"})
    stems = exporter.export_stems("project.yaml", "stems/", "wav")
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import yaml


class AudioExporter:
    """Multi-format audio exporter.

    Supports:
        - WAV (PCM 16/24/32bit float via soundfile)
        - MP3 (via ffmpeg subprocess)
        - FLAC (via soundfile)
        - OGG (via soundfile if libogg available)
        - MIDI (via mido)
    """

    # Supported formats
    SUPPORTED_FORMATS = {"wav", "mp3", "flac", "ogg", "midi"}

    # Default quality settings per format
    DEFAULT_QUALITY: dict[str, dict[str, Any]] = {
        "wav": {"sample_rate": 44100, "bit_depth": 24, "subtype": "PCM_24"},
        "mp3": {"bitrate": "320k", "sample_rate": 44100},
        "flac": {"sample_rate": 44100, "bit_depth": 24, "subtype": "PCM_24"},
        "ogg": {"sample_rate": 44100, "bit_depth": 16, "subtype": "VORBIS"},
    }

    def export(
        self,
        input_wav: str | Path,
        output_path: str | Path,
        format: str,
        quality: dict[str, Any] | None = None,
    ) -> str:
        """Export audio to specified format.

        Args:
            input_wav: Path to input WAV file.
            output_path: Path for output file.
            format: Target format (wav/mp3/flac/ogg).
            quality: Quality settings dict. Keys depend on format:
                - wav: {sample_rate, bit_depth, subtype}
                - mp3: {bitrate, sample_rate}
                - flac: {sample_rate, bit_depth, subtype}
                - ogg: {sample_rate, subtype}

        Returns:
            Path to the exported file.

        Raises:
            ValueError: If format is not supported.
            FileNotFoundError: If input file doesn't exist.
            RuntimeError: If export fails.
        """
        format = format.lower()
        if format not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format: {format}. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_FORMATS))}"
            )

        input_path = Path(input_wav)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_wav}")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        # Merge with defaults
        q = {**self.DEFAULT_QUALITY.get(format, {}), **(quality or {})}

        if format == "wav":
            return self._export_wav(input_path, output, q)
        elif format == "mp3":
            return self._export_mp3(input_path, output, q)
        elif format == "flac":
            return self._export_flac(input_path, output, q)
        elif format == "ogg":
            return self._export_ogg(input_path, output, q)
        else:
            raise ValueError(f"Format not handled: {format}")

    def _export_wav(self, input_path: Path, output: Path, quality: dict) -> str:
        """Export to WAV format."""
        data, sr = sf.read(str(input_path), dtype="float32", always_2d=False)

        # Resample if needed
        target_sr = quality.get("sample_rate", sr)
        if target_sr != sr:
            data = self._resample(data, sr, target_sr)
            sr = target_sr

        # Ensure (samples, channels) for soundfile
        if data.ndim == 2:
            write_data = data.T if data.shape[0] < data.shape[1] else data
        else:
            write_data = data

        subtype = quality.get("subtype", "PCM_24")
        sf.write(str(output), write_data, sr, format="WAV", subtype=subtype)
        return str(output)

    def _export_mp3(self, input_path: Path, output: Path, quality: dict) -> str:
        """Export to MP3 format via ffmpeg."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError(
                "ffmpeg not found. Install ffmpeg for MP3 export. "
                "On Ubuntu: apt install ffmpeg. On macOS: brew install ffmpeg."
            )

        bitrate = quality.get("bitrate", "320k")
        target_sr = quality.get("sample_rate", 44100)

        cmd = [
            ffmpeg, "-y",
            "-i", str(input_path),
            "-codec:a", "libmp3lame",
            "-b:a", bitrate,
            "-ar", str(target_sr),
            str(output),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg MP3 export failed: {result.stderr[:500]}")
        return str(output)

    def _export_flac(self, input_path: Path, output: Path, quality: dict) -> str:
        """Export to FLAC format."""
        data, sr = sf.read(str(input_path), dtype="float32", always_2d=False)

        target_sr = quality.get("sample_rate", sr)
        if target_sr != sr:
            data = self._resample(data, sr, target_sr)
            sr = target_sr

        if data.ndim == 2:
            write_data = data.T if data.shape[0] < data.shape[1] else data
        else:
            write_data = data

        subtype = quality.get("subtype", "PCM_24")
        sf.write(str(output), write_data, sr, format="FLAC", subtype=subtype)
        return str(output)

    def _export_ogg(self, input_path: Path, output: Path, quality: dict) -> str:
        """Export to OGG Vorbis format."""
        try:
            data, sr = sf.read(str(input_path), dtype="float32", always_2d=False)
        except Exception as e:
            raise RuntimeError(f"Cannot read input for OGG export: {e}")

        target_sr = quality.get("sample_rate", sr)
        if target_sr != sr:
            data = self._resample(data, sr, target_sr)
            sr = target_sr

        if data.ndim == 2:
            write_data = data.T if data.shape[0] < data.shape[1] else data
        else:
            write_data = data

        try:
            sf.write(str(output), write_data, sr, format="OGG", subtype="VORBIS")
            return str(output)
        except Exception as e:
            # OGG might not be available; fall back to ffmpeg
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg is None:
                raise RuntimeError(
                    f"OGG export via soundfile failed ({e}) and ffmpeg not available."
                )
            cmd = [
                ffmpeg, "-y",
                "-i", str(input_path),
                "-codec:a", "libvorbis",
                "-q:a", "6",
                str(output),
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8"
            )
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg OGG export failed: {result.stderr[:500]}")
            return str(output)

    def _resample(self, data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Simple resample by linear interpolation.

        For production use, consider scipy.signal.resample for better quality.
        """
        if orig_sr == target_sr:
            return data

        if data.ndim == 1:
            ratio = target_sr / orig_sr
            new_len = int(len(data) * ratio)
            indices = np.linspace(0, len(data) - 1, new_len)
            return np.interp(indices, np.arange(len(data)), data).astype(np.float32)
        else:
            # Multi-channel: resample each channel
            ratio = target_sr / orig_sr
            new_len = int(data.shape[1] * ratio) if data.shape[0] < data.shape[1] else int(data.shape[0] * ratio)
            # Determine layout
            if data.shape[0] < data.shape[1]:
                # (channels, samples)
                result = np.zeros((data.shape[0], new_len), dtype=np.float32)
                for ch in range(data.shape[0]):
                    indices = np.linspace(0, data.shape[1] - 1, new_len)
                    result[ch] = np.interp(indices, np.arange(data.shape[1]), data[ch])
                return result
            else:
                # (samples, channels)
                result = np.zeros((new_len, data.shape[1]), dtype=np.float32)
                for ch in range(data.shape[1]):
                    indices = np.linspace(0, data.shape[0] - 1, new_len)
                    result[:, ch] = np.interp(indices, np.arange(data.shape[0]), data[:, ch])
                return result

    def export_stems(
        self,
        project_yaml: str | Path,
        output_dir: str | Path,
        format: str = "wav",
        quality: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Export each track as a separate stem file.

        Renders each track independently (solo mode) and exports
        to the specified format.

        Args:
            project_yaml: Path to VCMix project YAML.
            output_dir: Directory for stem output files.
            format: Output format (wav/mp3/flac/ogg).
            quality: Quality settings per format.

        Returns:
            Dict mapping track_name -> output_file_path.
        """
        project_path = Path(project_yaml)
        if not project_path.exists():
            raise FileNotFoundError(f"Project not found: {project_yaml}")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Parse project
        content = project_path.read_text(encoding="utf-8")
        config = yaml.safe_load(content)

        tracks = config.get("tracks", [])
        results: dict[str, str] = {}

        # Try to use the renderer for proper stem rendering
        try:
            from vcmix.config.parser import parse_project
            from vcmix.engine.renderer import Renderer

            cfg = parse_project(project_path)
            cfg.__dict__["_project_dir"] = project_path.parent.resolve()

            for track in tracks:
                track_name = track.get("name", "unknown")
                # Create a copy with only this track (solo mode)
                solo_cfg = _solo_project(cfg, track_name)
                if solo_cfg is None:
                    continue

                try:
                    engine = Renderer(solo_cfg, stream="none")
                    wav_output = engine.run()
                    # Export to target format
                    ext = format if format != "wav" else "wav"
                    stem_path = out_dir / f"{track_name}.{ext}"
                    if format == "wav" and wav_output:
                        # Just copy/move the rendered output
                        import shutil as sh
                        if Path(wav_output) != stem_path:
                            sh.copy2(str(wav_output), str(stem_path))
                        results[track_name] = str(stem_path)
                    elif wav_output:
                        self.export(wav_output, str(stem_path), format, quality)
                        results[track_name] = str(stem_path)
                except Exception:
                    # Fall back to direct file copy for raw tracks
                    self._export_raw_stem(track, out_dir, format, quality, results)

        except (ImportError, Exception):
            # Direct file-based stem export without rendering
            for track in tracks:
                self._export_raw_stem(track, out_dir, format, quality, results)

        return results

    def _export_raw_stem(
        self,
        track: dict,
        out_dir: Path,
        format: str,
        quality: dict | None,
        results: dict[str, str],
    ) -> None:
        """Export a single track's raw audio file as a stem."""
        track_name = track.get("name", "unknown")
        track_file = track.get("file", "")
        if not track_file:
            return

        track_path = Path(track_file)
        if not track_path.exists():
            return

        ext = format if format != "wav" else "wav"
        stem_path = out_dir / f"{track_name}.{ext}"
        try:
            if format == "wav":
                import shutil as sh
                sh.copy2(str(track_path), str(stem_path))
            else:
                self.export(str(track_path), str(stem_path), format, quality)
            results[track_name] = str(stem_path)
        except Exception:
            pass

    def export_stems_by_bus(
        self,
        project_yaml: str | Path,
        output_dir: str | Path,
        format: str = "wav",
        quality: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Export stems grouped by bus assignment.

        Tracks assigned to the same bus are rendered together
        into a single stem file named after the bus.

        Args:
            project_yaml: Path to VCMix project YAML.
            output_dir: Directory for bus stem output files.
            format: Output format.
            quality: Quality settings.

        Returns:
            Dict mapping bus_name -> output_file_path.
        """
        project_path = Path(project_yaml)
        if not project_path.exists():
            raise FileNotFoundError(f"Project not found: {project_yaml}")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        content = project_path.read_text(encoding="utf-8")
        config = yaml.safe_load(content)

        tracks = config.get("tracks", [])
        config.get("sends", [])

        # Build bus -> tracks mapping
        bus_tracks: dict[str, list[dict]] = {}
        unassigned: list[dict] = []

        for track in tracks:
            sends = track.get("sends", {})
            if isinstance(sends, dict) and sends:
                # Track belongs to first bus in sends
                first_bus = next(iter(sends.keys()))
                bus_tracks.setdefault(first_bus, []).append(track)
            else:
                unassigned.append(track)

        # Add unassigned tracks as "direct" bus
        if unassigned:
            bus_tracks["direct"] = unassigned

        results: dict[str, str] = {}

        for bus_name, bus_track_list in bus_tracks.items():
            ext = format if format != "wav" else "wav"
            stem_path = out_dir / f"{bus_name}.{ext}"

            # Mix all bus tracks together
            mixed_audio = None
            sample_rate = 44100

            for track in bus_track_list:
                track_file = track.get("file", "")
                if not track_file:
                    continue
                track_path = Path(track_file)
                if not track_path.exists():
                    continue

                try:
                    from vcmix.audio.io import read_audio
                    audio, sr = read_audio(track_path)
                    sample_rate = sr

                    # Apply track volume
                    volume = track.get("volume", 1.0)
                    audio = audio * volume

                    if mixed_audio is None:
                        mixed_audio = audio.copy()
                    else:
                        # Align lengths and sum
                        if mixed_audio.ndim == 1 and audio.ndim == 1:
                            max_len = max(len(mixed_audio), len(audio))
                            padded_mixed = np.zeros(max_len, dtype=np.float32)
                            padded_audio = np.zeros(max_len, dtype=np.float32)
                            padded_mixed[:len(mixed_audio)] = mixed_audio
                            padded_audio[:len(audio)] = audio
                            mixed_audio = padded_mixed + padded_audio
                        else:
                            # Handle stereo
                            a1 = mixed_audio.flatten()
                            a2 = audio.flatten()
                            max_len = max(len(a1), len(a2))
                            padded1 = np.zeros(max_len, dtype=np.float32)
                            padded2 = np.zeros(max_len, dtype=np.float32)
                            padded1[:len(a1)] = a1
                            padded2[:len(a2)] = a2
                            mixed_audio = (padded1 + padded2)
                except Exception:
                    continue

            if mixed_audio is not None:
                try:
                    # Write intermediate WAV then convert
                    tmp_wav = out_dir / f"_tmp_{bus_name}.wav"
                    from vcmix.audio.io import write_audio
                    write_audio(mixed_audio.astype(np.float32), tmp_wav, sample_rate)

                    if format == "wav":
                        import shutil as sh
                        sh.move(str(tmp_wav), str(stem_path))
                    else:
                        self.export(str(tmp_wav), str(stem_path), format, quality)
                        tmp_wav.unlink(missing_ok=True)

                    results[bus_name] = str(stem_path)
                except Exception:
                    pass

        return results

    def export_midi(
        self,
        project_yaml: str | Path,
        output_path: str | Path,
    ) -> str:
        """Export MIDI data from project as a MIDI file.

        Reads MIDI tracks from the project YAML and creates a
        standard MIDI file using mido.

        Args:
            project_yaml: Path to VCMix project YAML.
            output_path: Output MIDI file path.

        Returns:
            Path to the exported MIDI file.
        """
        try:
            import mido
        except ImportError:
            raise RuntimeError("mido not installed. Install with: pip install mido")

        project_path = Path(project_yaml)
        if not project_path.exists():
            raise FileNotFoundError(f"Project not found: {project_yaml}")

        content = project_path.read_text(encoding="utf-8")
        config = yaml.safe_load(content)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        bpm = config.get("bpm", 120)
        tracks = config.get("tracks", [])

        mid = mido.MidiFile()
        # Tempo track
        tempo_track = mido.MidiTrack()
        tempo_track.name = "Tempo"
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
        tempo_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
        mid.tracks.append(tempo_track)

        for track_cfg in tracks:
            track_type = track_cfg.get("type", "audio")
            midi_file = track_cfg.get("midi_file", None)

            if track_type == "midi" and midi_file and Path(midi_file).exists():
                # Re-encode existing MIDI file
                try:
                    src_mid = mido.MidiFile(str(midi_file))
                    for t in src_mid.tracks:
                        mid.tracks.append(t)
                except Exception:
                    pass
            elif track_type == "sampler":
                # Create basic track from zones
                track_obj = mido.MidiTrack()
                track_obj.name = track_cfg.get("name", "Sampler")
                zones = track_cfg.get("zones", [])
                for zone in zones:
                    note = zone.get("root_note", 60)
                    vel = int(zone.get("velocity", 100))
                    duration = int(zone.get("duration", 480))
                    track_obj.append(mido.Message("note_on", note=note, velocity=vel, time=0))
                    track_obj.append(mido.Message("note_off", note=note, velocity=0, time=duration))
                if zones:
                    mid.tracks.append(track_obj)

        mid.save(str(output))
        return str(output)


def _solo_project(cfg, track_name: str):
    """Create a copy of the project config with only one track active.

    Returns a modified config object or None if track not found.
    """
    found = False
    for track in cfg.tracks:
        if track.name == track_name:
            found = True
            break

    if not found:
        return None

    # Create solo copy by muting all other tracks
    import copy
    solo_cfg = copy.deepcopy(cfg)
    for track in solo_cfg.tracks:
        if track.name != track_name:
            track.mute = True
    return solo_cfg
