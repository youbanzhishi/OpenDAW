"""
vcmix.audio — Audio I/O, mixing, and metering.

This subpackage provides:
    - io:    WAV/FLAC/MP3 read/write via soundfile + ffmpeg
    - mixer: Multi-track mixing with level control
    - meter: Level metering (RMS/Peak/TruePeak/LUFS)

Usage:
    from vcmix.audio.io import read_audio, write_audio
    from vcmix.audio.mixer import Mixer
    from vcmix.audio.meter import Meter

Dependencies: numpy, soundfile, ffmpeg (system)
"""

__all__ = ["read_audio", "write_audio", "Mixer", "Meter"]
