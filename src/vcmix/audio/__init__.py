"""
vcmix.audio — Audio I/O, mixing, and metering utilities.

This subpackage provides:
    - io: Audio file reading and writing (WAV, FLAC, OGG)
    - mixer: Multi-track mixing with gain and pan
    - meter: RMS/Peak/spectrum calculation for metering

Usage:
    from vcmix.audio import read_audio, write_audio, Mixer, Meter

Dependencies: numpy, soundfile
"""

from vcmix.audio.io import read_audio, write_audio
from vcmix.audio.mixer import Mixer
from vcmix.audio.meter import Meter

__all__ = ["read_audio", "write_audio", "Mixer", "Meter"]
