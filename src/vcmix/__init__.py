"""
VCMix — AI-native open-source DAW core library
================================================

YAML-driven, headless mixing host for the VocalChain plugin ecosystem.
Parses declarative mix project files into signal routing graphs,
auto-schedules VC plugin CLI for offline rendering.

Three Core Design Principles:
    1. Cross-platform — pathlib.Path, soundfile, ffmpeg; UTF-8 everywhere
    2. Lightweight & Fast — numpy vectorized, streaming, incremental cache
    3. AI Agent Friendly — YAML config + CLI zero-GUI + structured JSON output

Usage (CLI):
    vcmix render project.yaml              # render mix
    vcmix render project.yaml --report     # with analysis report
    vcmix render project.yaml --stream json # JSON structured output
    vcmix render project.yaml --ab         # A/B comparison rendering
    vcmix render project.yaml --ab --diff  # A/B with diff analysis
    vcmix render project.yaml --auto-fix   # with gain staging auto-fix
    vcmix validate project.yaml            # validate config
    vcmix graph project.yaml               # signal routing graph
    vcmix analyze track.wav                # audio analysis

Usage (Python API):
    from vcmix.config.parser import parse_project
    from vcmix.engine.renderer import Renderer

    cfg = parse_project("project.yaml")
    engine = Renderer(cfg, report=True)
    engine.run()

Module Map:
    config/parser.py   — YAML parsing + pydantic validation + BPM note conversion
    engine/renderer.py — Rendering pipeline (insert+sends+sidechain+AB)
    engine/analyzer.py — RMS/Peak/spectrum/sibilance/RT60 analysis
    engine/autofix.py  — Gain staging auto-correction (v2: chain analysis)
    engine/bus.py      — Send/Return bus system
    plugins/adapter.py — PluginAdapter base class + sidechain support
    plugins/vc_plugins.py — VC plugin CLI subprocess adapter
    plugins/registry.py  — Plugin registry by name
    audio/io.py        — WAV/FLAC/MP3 read/write (soundfile + ffmpeg)
    audio/mixer.py     — Multi-track mixing (numpy vectorized)
    audio/meter.py     — Level metering (RMS/Peak/TruePeak/LUFS)
    bpm/detector.py    — BPM detection via librosa
    bpm/sync.py        — BPM note-value to ms conversion
    cli.py             — CLI entry point (render/validate/graph/analyze)

Standardized Exit Codes (AI Agent processable):
    0  OK
    1  Config error
    2  Plugin CLI error
    3  Audio I/O error
    4  Render error
    5  Cache error
    6  Missing dependency

Dependencies: numpy, soundfile, pyyaml, pydantic, click, rich, librosa
Version: 0.2.0 (Phase 2)
"""

__version__ = "0.2.0"
__author__ = "youbanzhishi"

# ── Standardized exit codes for AI Agent programmatic handling ──
EXIT_OK            = 0
EXIT_CONFIG_ERROR  = 1
EXIT_PLUGIN_ERROR  = 2
EXIT_IO_ERROR      = 3
EXIT_RENDER_ERROR  = 4
EXIT_CACHE_ERROR   = 5
EXIT_MISSING_DEP   = 6
