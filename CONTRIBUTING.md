# 贡献指南

感谢你对OpenDAW的关注！本指南帮助你快速上手并有效贡献。

## 开发环境

### 必备
- **Rust 1.85+**（推荐1.86+，icu依赖需edition 2024）
- **系统音频驱动**：Linux需ALSA（`libasound2-dev`），macOS用CoreAudio，Windows用WASAPI

### 可选
- **Node.js 22+**（构建桌面端前端）
- **Tauri CLI**（桌面端开发）：`cargo install tauri-cli`

### 快速开始

```bash
git clone https://github.com/youbanzhishi/OpenDAW.git
cd OpenDAW

# 构建全部
cargo build

# 构建特定crate
cargo build -p opendaw-cli
cargo build -p opendaw-api

# 运行测试
cargo test

# 格式化
cargo fmt

# Lint
cargo clippy
```

## 项目结构

```
OpenDAW/
├── audio-engine/        # 实时音频引擎（采样率/缓冲区/零拷贝管道）
├── opendaw-core/        # 核心层（Project/Track/Plugin/Extension Registry）
├── opendaw-extension/   # 扩展接口定义（Plugin API/Script Runtime/Model Bus/Hook）
├── plugin-host/         # 插件加载/扫描/VC适配器
├── jsfx-engine/         # EEL2 VM（Reaper JSFX兼容）
├── crates/
│   ├── opendaw-api/     # REST API服务器（Axum，端口8080）
│   ├── opendaw-cli/     # 命令行工具（Clap）
│   └── opendaw-ws/      # WebSocket协作服务
├── desktop/             # Tauri桌面应用
└── docs/
    ├── adr/             # 架构决策记录
    ├── architecture.md  # 架构文档
    └── ...
```

### Crate依赖关系

```
opendaw-api ──→ opendaw-core ──→ audio-engine
opendaw-cli ──→ opendaw-core ──→ plugin-host ──→ jsfx-engine
                                ──→ opendaw-extension
opendaw-ws  ──→ opendaw-core
```

## 代码规范

1. **`cargo fmt` 必须通过** — 不讨论格式
2. **`cargo clippy` 零警告** — 警告当错误处理
3. **`cargo test` 全绿** — 没有测试的代码没有保证
4. **核心层零业务逻辑** — 新功能=注册Extension，不改核心
5. **文档即代码** — 每个public接口有文档注释

## PR流程

1. Fork → Branch → Commit → PR
2. PR必须使用[PR模板](.github/PULL_REQUEST_TEMPLATE.md)，填全所有字段
3. CI必须全绿（check + test + fmt）
4. 至少一人Review后合并
5. **交付物必须完整可用** — Docker镜像要包含前端，Release要包含所有平台包

## 架构决策记录（ADR）

关键决策必须写ADR，放在`docs/adr/`目录。

- 参考模板：`docs/adr/000-template.md`
- 编号递增：下一个可用编号看目录里最大编号+1
- 格式：背景 → 决策 → 理由 → 后果

**什么时候需要写ADR：**
- 选了某个技术方案而非另一个
- 做了影响架构的决策
- 决定不做什么（同样重要）
- 踩了坑并提炼出规则

## 踩坑反哺

新发现必须记录，不要让下一个人踩同样的坑：

| 发现类型 | 记录到 |
|---------|--------|
| 架构决策 | `docs/adr/` |
| 代码级踩坑 | 代码注释 + commit message |
| 依赖/兼容性问题 | `docs/adr/` 或相关crate的README |
| 部署问题 | `docs/deployment.md` |

## CHANGELOG规范

每条记录必须回答三个问题：
1. **做了什么**
2. **为什么做**
3. **下一步是什么**（没有写"无"）

格式示例：
```
### opendaw-api: 新增Marketplace搜索端点
- **为什么**: AI Agent需要按关键词搜索可用插件
- **下一步**: 实现插件一键安装端点
```

## 常见问题

**Q: opendaw-cli的serve命令为什么不启动服务？**
A: CLI的serve是占位代码，真正的HTTP服务由opendaw-api提供。详见ADR-003。

**Q: Docker镜像为什么包含前端？**
A: opendaw-api自动查找`./static/`目录挂载Web UI，镜像必须包含前端文件才能浏览器访问。Dockerfile中`COPY --from=builder /app/desktop/src-tauri/frontend /app/static`。

**Q: 怎么只构建特定crate？**
A: `cargo build -p opendaw-api` 或 `cargo test -p opendaw-core`，不需要构建整个workspace。

**Q: Linux上构建失败怎么办？**
A: 确保`libasound2-dev`和`pkg-config`已安装。桌面端还需`libwebkit2gtk-4.1-dev`等依赖。
