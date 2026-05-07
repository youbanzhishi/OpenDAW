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

# Render with real-time analysis report
vcmix render examples/jiuwanzi.yaml --report

# Render with auto-fix gain staging
vcmix render examples/jiuwanzi.yaml --auto-fix --stream log

# JSON structured output (AI Agent friendly)
vcmix render examples/jiuwanzi.yaml --stream json

# A/B comparison rendering
vcmix render project.yaml --ab
vcmix render project.yaml --ab --diff

# Auto-mix: analyze + suggest + apply
vcmix automix project.yaml
vcmix automix project.yaml --dry-run
vcmix automix project.yaml --reference ref.wav

# View arrangement analysis
vcmix arrangement project.yaml --strategy

# List built-in presets
vcmix presets
```

### Rendering Pipeline

```
1. Parse YAML → ProjectConfig
2. Validate config & check audio files
3. Build signal routing DAG (tracks → inserts → sends → master)
4. Render each track through insert chain (sidechain routing)
5. Process Send/Return buses
6. Mix tracks with master level balancing + bus returns
7. Apply master insert chain + DataStream events
8. Write output + optional A/B versions + analysis report
```

## Feature Overview

| Feature | Phase | Status |
|---------|-------|--------|
| YAML-driven rendering | 1 | ✅ |
| Insert chain processing | 1 | ✅ |
| Multi-track mixing | 1 | ✅ |
| BPM note value sync | 1 | ✅ |
| Send/Return buses | 2 | ✅ |
| Sidechain routing | 2 | ✅ |
| A/B comparison | 2 | ✅ |
| AutoFix gain staging v2 | 2 | ✅ |
| Built-in presets (7) | 3 | ✅ |
| DataStream closed-loop | 4 | ✅ |
| Source separation | 5 | ✅ |
| Arrangement extraction | 5 | ✅ |
| AutoMix engine | 6 | ✅ |
| Reference matching | 6 | ✅ |
| Arrangement-aware mixing | 7 | ✅ |
| Web UI (FastAPI) | 8 | 🏃 In Progress |
| Native GUI | 9 | 🔮 Future |
| Full DAW | 10 | 🔮 Ultimate Goal |

## Supported VC Plugins (20)

### Gen 1 (16 plugins)
| Plugin | Key Parameters |
|--------|---------------|
| VC-EQ | low_cut, high_shelf, peak_freq, peak_gain |
| VC-Comp | threshold, ratio, attack, release, makeup |
| VC-Smooth | amount |
| VC-DeEsser | threshold, reduction, frequency |
| VC-Gain | gain |
| VC-Saturator | drive, mix |
| VC-Limiter | ceiling, release |
| VC-Delay | time, feedback, mix |
| VC-Reverb | room, decay, damping, mix, predelay, wetlpf |
| VC-DynamicEQ | frequency, threshold, q, attack, release |
| VC-Distortion | drive, tone, mix |
| VC-Noise | threshold, reduction |
| VC-SurgicalDeEsser | threshold, frequency, reduction |
| VC-Tune | speed, scale, transpose, autokey |
| VC-Gate | threshold, ratio, attack, hold, release, range |
| VC-Chorus | rate, depth, voices, mix, width |

### Gen 2 (4 plugins)
| Plugin | Type | Key Parameters |
|--------|------|---------------|
| VC-Stereo | 🆕 New | width, pan, mono_bass, bass_freq |
| VC-PitchShift | 🆕 New | semitones, cents, formant |
| VC-Reverb | ⬆️ FDN升级 | room, decay, damping, mix, predelay, wetlpf (8-delay FDN) |
| VC-Comp | ⬆️ 多段升级 | threshold, ratio, --multiband, --band-threshold, --band-ratio |



## DataStream Events (AI Agent API)

| Event | Data | Use Case |
|-------|------|----------|
| track_level | rms_db, peak_db, true_peak_db | Monitor per-track levels |
| effect_delta | before_rms, after_rms, delta_db | Track effect impact |
| master_level | rms_db, peak_db, true_peak_db | Master bus monitoring |
| warning | type (clipping/low_snr/sibilance), message | Problem detection |
| decision | action, params, reason | Auto-fix logging |

## Standardized Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Config error |
| 2 | Plugin CLI error |
| 3 | Audio I/O error |
| 4 | Render error |
| 5 | Cache error |
| 6 | Missing dependency |

## Related Projects

- [AudioFX](https://github.com/youbanzhishi/AudioFX) — VC Plugin Series (VST3 effects + CLI tools)

## License

MIT
