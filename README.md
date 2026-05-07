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

# A/B comparison rendering (Phase 2)
vcmix render project.yaml --ab
vcmix render project.yaml --ab --diff
```

### Example YAML

```yaml
name: "九万字"
bpm: 62
sample_rate: 44100

sends:
  - name: reverb_bus
    effects:
      - name: vc-reverb
        params: { room: 30, decay: 35, damping: 50, mix: 100, predelay: 50, wetlpf: 5000 }
    return_level: 0.15

  - name: delay_bus
    effects:
      - name: vc-delay
        params: { time: "1/8d", feedback: 12, mix: 100 }
    return_level: 0.08

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
    sends:
      reverb_bus: 0.12
      delay_bus: 0.05

  - name: kick
    file: "kick.wav"
    effects: []

  - name: bass
    file: "bass.wav"
    effects:
      - name: vc-comp
        params: { threshold: -20, ratio: 4 }
        sidechain: kick    # Sidechain: kick drives bass compression

  - name: accomp
    file: "accomp.wav"
    effects: []

master:
  levels: { vocal: 0.8, kick: 0.9, bass: 0.7, accomp: 0.35 }
  output: "jiuwanzi_mix.wav"
```

### A/B Comparison YAML

```yaml
name: "Vocal A/B Test"
bpm: 120
sample_rate: 44100

tracks:
  - name: vocal
    file: "vocal.wav"
    effects_a:
      - name: vc-reverb
        params: { room: 30, decay: 35, mix: 10 }
    effects_b:
      - name: vc-reverb
        params: { room: 50, decay: 60, mix: 20 }

master:
  levels: { vocal: 1.0 }
  output: "output.wav"
```

Render both versions:
```bash
vcmix render project.yaml --ab          # → output_a.wav + output_b.wav
vcmix render project.yaml --ab --diff   # + diff analysis report
```

### BPM Note Value Auto-Conversion

| Note Value | Meaning | @BPM62 | @BPM120 |
|-----------|---------|--------|---------|
| `"1/4"` | Quarter note | 967.7ms | 500.0ms |
| `"1/8"` | Eighth note | 483.9ms | 250.0ms |
| `"1/8d"` | Dotted eighth | 725.8ms | 375.0ms |
| `"1/8t"` | Eighth triplet | 322.6ms | 166.7ms |
| `"1/16"` | Sixteenth | 241.9ms | 125.0ms |

### Rendering Pipeline

```
1. Parse YAML → ProjectConfig
2. Validate config & check audio files
3. Build signal routing DAG (tracks → inserts → sends → master)
4. Render each track through insert chain (sidechain routing)
5. Process Send/Return buses
6. Mix tracks with master level balancing + bus returns
7. Apply master insert chain
8. Write output + optional A/B versions + analysis report
```

### Phase 2 Features

#### Send/Return Buses
- Define shared effect buses (reverb, delay) in the `sends` section
- Each track can send to multiple buses at different levels
- Bus returns are mixed back into the master output
- Supports BPM note-value auto-conversion in bus effects

#### Sidechain Routing
- Any effect can specify a `sidechain` source track
- The sidechain track is rendered first, then its output drives the effect
- Currently simulated via gain envelope analysis (full CLI --sidechain support pending)
- Render order is automatically resolved via topological sort

#### A/B Comparison
- Define `effects_a` and `effects_b` on any track
- `--ab` flag renders both versions to `output_a.wav` and `output_b.wav`
- `--ab --diff` adds difference analysis (RMS delta, peak delta, diff spectrum)

#### AutoFix Gain Staging (v2)
- Per-effect input/output level analysis
- Gain accumulation detection (consecutive boost → clip risk, consecutive cut → SNR risk)
- Automatic gain node insertion at problematic points
- Rules: input ≤ -6dBFS, output ≥ -24dBFS, final output ≤ -1dBFS

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
│   │   ├── renderer.py     # Rendering pipeline (insert+sends+sidechain+AB)
│   │   ├── analyzer.py     # RMS/Peak/spectrum/sibilance/RT60
│   │   ├── autofix.py      # Gain staging auto-correction (v2: chain analysis)
│   │   └── bus.py          # Send/Return bus system
│   ├── plugins/
│   │   ├── adapter.py      # PluginAdapter base + sidechain support
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
| Phase 2 | Send/Return + Sidechain + A/B Compare + AutoFix v2 | ✅ Complete |
| Phase 3 | AI Reference Analysis (stem separation + reverse engineering) | 📋 Planned |
| Phase 4 | Smart Arrangement + Arrange-Mix Integration | 📋 Planned |
| Phase 5 | Full DAW (GUI + VST3 Hosting + MIDI + AI Agent API) | 🔮 Future |

## Related Projects

- [AudioFX](https://github.com/youbanzhishi/AudioFX) — VC Plugin Series (VST3 effects + CLI tools)

## License

MIT
