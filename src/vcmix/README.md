# VCMix 源码目录

VCMix — VocalChain 无界面混音宿主，AI原生开源DAW核心组件。

## 模块结构

```
src/vcmix/
├── __init__.py          # 包入口 + 标准化错误码
├── __main__.py          # python -m vcmix 支持
├── cli.py               # CLI入口（render/validate/graph/analyze）
├── config/
│   ├── __init__.py      # 导出 parse_project, ProjectConfig 等
│   └── parser.py        # YAML解析 + Pydantic校验 + BPM换算
├── engine/
│   ├── __init__.py      # 导出 Renderer, Analyzer, AutoFix
│   ├── renderer.py      # 7步渲染管线
│   ├── analyzer.py      # 音频分析（RMS/Peak/频谱/齿音/RT60）
│   └── autofix.py       # 增益自动修正
├── plugins/
│   ├── __init__.py      # 导出 PluginAdapter, PluginRegistry
│   ├── adapter.py       # PluginAdapter 抽象基类
│   ├── vc_plugins.py    # VC插件CLI适配器（subprocess调用）
│   └── registry.py      # 插件注册表
├── audio/
│   ├── __init__.py      # 导出 read_audio, write_audio, Mixer, Meter
│   ├── io.py            # 音频读写（WAV/FLAC/MP3 via soundfile+ffmpeg）
│   ├── mixer.py         # 多轨混合（numpy向量化）
│   └── meter.py         # 电平测量（RMS/Peak/TruePeak/LUFS）
└── bpm/
    ├── __init__.py      # 导出 note_to_ms, resolve_bpm_times
    ├── detector.py      # BPM检测（librosa.beat）
    └── sync.py          # BPM音符时值换算
```

## 三大设计原则

1. **跨平台** — pathlib.Path, soundfile, ffmpeg三平台兼容, UTF-8统一编码
2. **轻量高性能** — numpy向量化, 流式处理, 增量缓存
3. **AI Agent友好** — YAML配置驱动 + CLI零GUI + 结构化JSON输出

## 标准化错误码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 配置错误 |
| 2 | 插件CLI错误 |
| 3 | 音频I/O错误 |
| 4 | 渲染错误 |
| 5 | 缓存错误 |
| 6 | 缺少依赖 |
