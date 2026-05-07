# VST3 Host — C++ VST3 Plugin Hosting Engine

Part of **OpenDAW (VCMix)** Phase 9: Third-party VST3 plugin support.

## Architecture

```
┌─────────────────┐     subprocess      ┌──────────────────┐
│  VCMix Python   │ ──────────────────▶ │  vst3_host CLI   │
│  VST3Proxy      │ ◀────────────────── │  (this program)  │
└─────────────────┘    WAV file I/O      └──────────────────┘
```

## Build

### Prerequisites
- CMake 3.22+
- C++17 compiler (GCC 9+, Clang 10+, MSVC 2019+)
- JUCE 7.0.9+ (auto-fetched by CMake)
- VST3 SDK 3.7.9+ (bundled with JUCE)

### Build Steps
```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . -j$(nproc)
```

### Install
```bash
cmake --install . --prefix /usr/local
```

## Usage

### List installed VST3 plugins
```bash
vst3_host list
```

### Export plugin parameters
```bash
vst3_host params --plugin "/usr/lib/vst3/Serum.vst3"
```

### Process audio through an effect plugin
```bash
vst3_host process \
  --plugin "/usr/lib/vst3/FabFilter Pro-Q 3.vst3" \
  --input input.wav \
  --output output.wav \
  --param 1=0.5 --param 2=0.8
```

### Render instrument with MIDI
```bash
vst3_host process \
  --plugin "/usr/lib/vst3/Serum.vst3" \
  --output output.wav \
  --duration 10.0 \
  --midi-file melody.mid \
  --bpm 120
```

### Load preset
```bash
vst3_host process \
  --plugin "/usr/lib/vst3/Serum.vst3" \
  --output output.wav \
  --preset-file "/presets/Serum/Pad.vstpreset" \
  --duration 8.0 \
  --midi-file chords.mid
```

## Source Structure

| File | Purpose |
|------|---------|
| `main.cpp` | CLI entry point, argument parsing, command dispatch |
| `VST3Host.cpp/h` | JUCE AudioPluginFormatManager wrapper, plugin scanning/loading |
| `PluginWrapper.cpp/h` | Plugin instance wrapper: params, MIDI, rendering |
| `AudioFileIO.cpp/h` | WAV read/write via dr_wav |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing args, plugin load failed, I/O error) |

## Notes

- Each invocation loads and releases the plugin — no persistent state.
- For better performance, use the gRPC daemon mode (Phase 9.2).
- VST3 plugin crashes are isolated to this process; VCMix Python layer
  detects non-zero exit codes and reports the error.
