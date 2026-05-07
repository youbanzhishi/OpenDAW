# OpenDAW 🎵

**AI-native open-source DAW** — YAML-driven, cross-platform, AI Agent friendly.

> Reaper有的我们要有，Reaper没有的我们也要有。

## Three Core Principles

1. **Cross-platform** — Windows / macOS / Linux (pathlib, soundfile, ffmpeg, UTF-8)
2. **Lightweight & Fast** — Streaming + numpy vectorized + incremental rendering cache
3. **AI Agent Friendly** — YAML config + CLI zero-GUI + structured JSON output + exit codes

## VCMix — VocalChain Headless Mixing Host

VCMix is the core component of OpenDAW. It is a YAML-driven headless mixing host that parses declarative mix project files into signal routing graphs and auto-schedules VC plugin CLI for offline rendering.

### Quick Start

```bash
pip install -e .

# Render a mix project
vcmix render examples/jiuwanzi.yaml

# Validate config
vcmix validate examples/jiuwanzi.yaml

# View signal routing graph
vcmix graph examples/jiuwanzi.yaml
vcmix graph examples/jiuwanzi.yaml -f mermaid

# Render with real-time analysis report
vcmix render examples/jiuwanzi.yaml --report

# Render with auto-fix gain staging
vcmix render examples/jiuwanzi.yaml --auto-fix --stream log

# JSON structured output (AI Agent friendly)
vcmix render examples/jiuwanzi.yaml --stream json
vcmix validate examples/jiuwanzi.yaml --json

# Analyze audio file
vcmix analyze vocal.wav
vcmix analyze vocal.wav --json
```

### Example YAML

```yaml
name: "九万字"
bpm: 62
sample_rate: 44100

tracks:
  - name: vocal
    file: "vocal_dry.wav"
    effects:
      - name: vc-deesser
        params: { threshold: -40, reduction: -6 }
      - name: vc-gain
        params: { gain: 6 }
      - name: vc-eq
        params: { low_cut: 80, high_shelf: 8000, peak_gain: -3 }
      - name: vc-comp
        params: { threshold: -30, ratio: 2.5 }
      - name: vc-reverb
        params: { room: 30, decay: 35, damping: 50, mix: 10, predelay: 50, wetlpf: 5000 }
      - name: vc-delay
        params: { time: "1/8d", feedback: 12, mix: 5 }  # "1/8d" → 725.8ms @BPM62
      - name: vc-limiter
        params: { ceiling: -1 }

  - name: accomp
    file: "accomp.wav"
    effects: []

master:
  levels: { vocal: 0.8, accomp: 0.35 }
  output: "jiuwanzi_mix.wav"
```

### BPM Note Value Auto-Conversion

| Note Value | Meaning | @BPM62 | @BPM120 |
|-----------|---------|--------|---------|
| `"1/4"` | Quarter note | 967.7ms | 500.0ms |
| `"1/8"` | Eighth note | 483.9ms | 250.0ms |
| `"1/8d"` | Dotted eighth | 725.8ms | 375.0ms |
| `"1/8t"` | Eighth triplet | 322.6ms | 166.7ms |
| `"1/16"` | Sixteenth | 241.9ms | 125.0ms |

### 7-Step Rendering Pipeline

```
1. Parse YAML → ProjectConfig
2. Validate config & check audio files
3. Build signal routing DAG
4. Render each track through insert chain
5. Mix tracks with master level balancing
6. Apply master insert chain
7. Write output + optional report
```

### Standardized Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Config error |
| 2 | Plugin CLI error |
| 3 | Audio I/O error |
| 4 | Render error |
| 5 | Cache error |
| 6 | Missing dependency |

## Project Structure

```
OpenDAW/
├── src/vcmix/              # VCMix source code
│   ├── cli.py              # CLI entry point
│   ├── config/parser.py    # YAML parsing + Pydantic validation
│   ├── engine/
│   │   ├── renderer.py     # 7-step rendering pipeline
│   │   ├── analyzer.py     # RMS/Peak/spectrum/sibilance/RT60
│   │   └── autofix.py      # Gain staging auto-correction
│   ├── plugins/
│   │   ├── adapter.py      # PluginAdapter base class
│   │   ├── vc_plugins.py   # VC CLI subprocess adapter
│   │   └── registry.py     # Plugin registry
│   ├── audio/
│   │   ├── io.py           # WAV/FLAC/MP3 read/write
│   │   ├── mixer.py        # Multi-track mixing
│   │   └── meter.py        # Level metering
│   └── bpm/
│       ├── detector.py     # BPM detection (librosa)
│       └── sync.py         # Note-value → ms conversion
├── examples/               # Example YAML projects
├── tests/                  # Test suite
└── pyproject.toml          # Package config
```

## Supported VC Plugins (10)

| Plugin | CLI Binary | Key Parameters |
|--------|-----------|---------------|
| VC-EQ | `VC-EQ-CLI-Standalone` | low_cut, high_shelf, peak_freq, peak_gain |
| VC-Comp | `VC-Comp-CLI-Standalone` | threshold, ratio, attack, release, makeup |
| VC-Gain | `VC-Gain-CLI-Standalone` | gain |
| VC-DeEsser | `VC-DeEsser-CLI-Standalone` | threshold, reduction, frequency |
| VC-Saturator | `VC-Saturator-CLI-Standalone` | drive, mix |
| VC-Limiter | `VC-Limiter-CLI-Standalone` | ceiling, release |
| VC-Delay | `VC-Delay-CLI-Standalone` | time, feedback, mix |
| VC-Reverb | `VC-Reverb-CLI-Standalone` | room, decay, damping, mix, predelay, wetlpf |
| VC-DynamicEQ | `VC-DynamicEQ-CLI-Standalone` | frequency, threshold, q, attack, release |
| VC-Smooth | `VC-Smooth-CLI-Standalone` | amount |

## Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 1 | Insert chain + Master + Multi-track + BPM sync | ✅ Complete |
| Phase 2 | Send/Return + Sidechain + A/B Compare + Cache | 📋 Planned |
| Phase 3 | AI Reference Analysis (stem separation + reverse engineering) | 📋 Planned |
| Phase 4 | Smart Arrangement + Arrange-Mix Integration | 📋 Planned |
| Phase 5 | Full DAW (GUI + VST3 Hosting + MIDI + AI Agent API) | 🔮 Future |

## Related Projects

- [AudioFX](https://github.com/youbanzhishi/AudioFX) — VC Plugin Series (VST3 effects + CLI tools)

## License

MIT
