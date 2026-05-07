# OpenDAW 🎵

**AI-native open-source DAW** — YAML-driven, cross-platform, AI Agent friendly.

> Reaper有的我们要有，Reaper没有的我们也要有。

## Three Core Principles

1. **Cross-platform** — Windows / macOS / Linux
2. **Lightweight & Fast** — Streaming + numpy + incremental rendering
3. **AI Agent Friendly** — YAML config + CLI + zero-GUI operation

## Quick Start

```bash
pip install vcmix

# Render a mix project
vcmix render project.yaml

# Validate config
vcmix validate project.yaml

# View signal routing graph
vcmix graph project.yaml

# Render with real-time analysis report
vcmix render project.yaml --report

# Render with auto-fix
vcmix render project.yaml --auto-fix --stream log
```

## Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 1 | Insert chain + Master + Multi-track + BPM sync | 🔄 In Progress |
| Phase 2 | Send/Return + Sidechain + A/B Compare + Auto-fix | 📋 Planned |
| Phase 3 | AI Reference Analysis (stem separation + reverse engineering) | 📋 Planned |
| Phase 4 | Smart Arrangement + Arrange-Mix Integration | 📋 Planned |
| Phase 5 | Full DAW (GUI + VST3 Hosting + MIDI + AI Agent API) | 🔮 Future |

## Related Projects

- [AudioFX](https://github.com/youbanzhishi/AudioFX) — VC Plugin Series (VST3 effects + instruments)

## License

MIT
