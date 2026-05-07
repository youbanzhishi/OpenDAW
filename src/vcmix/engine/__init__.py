"""
vcmix.engine — Core rendering, analysis, auto-fix, bus, and auto-mix engines.

This subpackage provides:
    - Renderer: 7-step audio rendering pipeline with DataStream integration
    - Analyzer: Audio data analysis (RMS, Peak, spectrum, sibilance, RT60)
    - AutoFix: Adaptive gain staging and headroom correction
    - BusManager / SendReturnBus: Send/Return bus routing (Phase 2)
    - AutoMixer: Intelligent auto-mixing from dry vocal analysis (Phase 4)
                  + DataStream closed-loop control (Phase 6)
    - ReferenceMatcher: Reference track spectral/dynamic matching (Phase 6)
    - AudioCache: LRU audio file cache for performance optimization (Phase 10)
    - IncrementalRenderer: Incremental rendering with cache (Phase 10)
    - RealtimeEngine: Real-time audio playback and recording engine (Phase 14)
    - AudioDriver: Abstract audio driver interface (Phase 14)
    - Transport: Transport control and time management (Phase 14)

Usage:
    from vcmix.engine import Renderer, Analyzer, AutoFix, AutoMixer
    from vcmix.engine import ReferenceMatcher, AudioCache
    from vcmix.engine import RealtimeEngine, Transport

Dependencies: numpy, soundfile
"""

from vcmix.engine.analyzer import Analyzer
from vcmix.engine.audio_cache import AudioCache
from vcmix.engine.audio_driver import (
    AudioDriverBase,
    DriverConfig,
    DriverInfo,
    DriverType,
    MockDriver,
    SoundDeviceDriver,
    create_driver,
)
from vcmix.engine.autofix import AutoFix
from vcmix.engine.automix import (
    AdjustmentSuggestion,
    AutoMixer,
    MasterMixState,
    MixingState,
    TrackMixState,
)
from vcmix.engine.bus import BusManager, SendReturnBus
from vcmix.engine.incremental import IncrementalRenderer
from vcmix.engine.realtime_engine import (
    EngineState,
    RealtimeEngine,
    RealtimeTrack,
    TrackClip,
)
from vcmix.engine.reference_matcher import (
    MatchDiff,
    ReferenceAdjustment,
    ReferenceMatcher,
    SpectralFeatures,
)
from vcmix.engine.renderer import Renderer
from vcmix.engine.transport import (
    TempoEvent,
    TempoTrack,
    TimeSignature,
    Transport,
    TransportState,
)

__all__ = [
    "Renderer",
    "Analyzer",
    "AutoFix",
    "AutoMixer",
    "AdjustmentSuggestion",
    "MasterMixState",
    "MixingState",
    "TrackMixState",
    "BusManager",
    "SendReturnBus",
    "ReferenceMatcher",
    "MatchDiff",
    "ReferenceAdjustment",
    "SpectralFeatures",
    "AudioCache",
    "IncrementalRenderer",
    # Phase 14
    "RealtimeEngine",
    "RealtimeTrack",
    "TrackClip",
    "EngineState",
    "Transport",
    "TransportState",
    "TimeSignature",
    "TempoTrack",
    "TempoEvent",
    "AudioDriverBase",
    "SoundDeviceDriver",
    "MockDriver",
    "DriverConfig",
    "DriverInfo",
    "DriverType",
    "create_driver",
]
