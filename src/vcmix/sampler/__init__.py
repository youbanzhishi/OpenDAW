"""
sampler — Sample-based instrument module for VCMix.

Loads WAV/AIFF sample files, maps them to MIDI key/velocity ranges,
and renders audio with pitch shifting, looping, and trigger modes.

Usage:
    from vcmix.sampler import SamplerEngine, SampleZone

    zone = SampleZone(file="piano_C4.wav", root_key=60, key_low=48, key_high=72)
    engine = SamplerEngine(sample_rate=44100)
    engine.load_zone(zone)
    engine.note_on(60, 100)
    audio = engine.render(44100)
    engine.note_off(60)
"""

from vcmix.sampler.sample_zone import SampleZone
from vcmix.sampler.sampler_engine import ActiveVoice, SamplerEngine
from vcmix.sampler.sampler_track import SamplerTrack

__all__ = ["SampleZone", "SamplerEngine", "ActiveVoice", "SamplerTrack"]
