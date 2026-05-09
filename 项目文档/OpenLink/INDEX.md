# OpenLink 项目知识索引

> 最后更新：2026-05-09 | 更新人：主对话
> 用途：任何智能体接手OpenLink相关任务时，先读本文件了解项目全貌

## 共享规范
→ ./共享知识/项目规范/（宪法层，改一次全局生效）
- 目录结构规范：最后同步 2026-05-09
- 协作规范：最后同步 2026-05-09
- 热规则规范：最后同步 2026-05-09
本项目已对齐：全部（INDEX.md+justfile+.github/workflows+规划/+assets/+output/+feedback/+docs/ 已建，中文目录已迁移）

## 热规则
→ 规划/hot-rules.md（派发任务时必须注入，防重复踩坑）

## 目录自愈

此项目按开发类目录结构规范，执行任何操作前运行：
```bash
mkdir -p ./回收站 && mkdir -p ./项目文档/OpenLink/{
  规划,src,tests/{integration,fixtures},
  docs/{dev-log,knowledge},
  assets/{images,templates,data},
  output,config,scripts,feedback
}
```

⚠️ 文件安全铁律：删除→mv到./回收站/OpenLink-$(date +%m%d)/，禁止rm

## 项目定位

**OpenLink不是短链服务，是智能体互联网的基础协议层。**

- 当下：短链重定向（入口功能）
- 近未来：Agent间的发现、握手、协作
- 远未来：智能体互联网的DNS + 路由 + 编排

一句话：**URL是人类互联网的入口协议，OpenLink是智能体互联网的入口协议。**

→ 完整规划：[项目规划-旧.md](规划/项目规划-旧.md)

## 核心知识

### 产品特性（开发↔运营 共享）

| 特性 | 说明 | 详见 |
|------|------|------|
| 5大核心原语 | Link/Route/Action/Context/Hook | [项目规划-旧.md#二](规划/项目规划-旧.md) |
| Extension Registry | 四柱模型：Action/Condition/Hook/Protocol | [项目规划-旧.md#四](规划/项目规划-旧.md) |
| 动态路由 | 同一短链根据访问者路由到不同目标 | [docs/knowledge/设计哲学与决策依据.md#一](docs/knowledge/设计哲学与决策依据.md) |
| 公私分治 | 公开内容过审，私密内容端到端加密不过审 | [docs/knowledge/设计哲学与决策依据.md#十一](docs/knowledge/设计哲学与决策依据.md) |
| 人形机器人对接 | 机器人=PhysicalAgent，注册扩展即可 | [docs/knowledge/设计哲学与决策依据.md#十三](docs/knowledge/设计哲学与决策依据.md) |
| PPS模式 | 人越多越快但不断流，云端保底 | [docs/knowledge/设计哲学与决策依据.md#十](docs/knowledge/设计哲学与决策依据.md) |
| 存储路由 | 跟Link路由引擎同构，文件走不同后端 | [项目规划-旧.md#三-Phase3](规划/项目规划-旧.md) |
| 传输路由 | LAN直传/P2P穿透/云中转自动切换 | [项目规划-旧.md#三-Phase4](规划/项目规划-旧.md) |
| 安全防火墙 | 三道防线（仅公开内容） | [项目规划-旧.md#十三](规划/项目规划-旧.md) |

### 技术架构（开发关注）

| 维度 | 选择 | 详见 |
|------|------|------|
| 语言 | Rust（与OpenDAW统一技术栈） | [docs/knowledge/设计哲学与决策依据.md#二](docs/knowledge/设计哲学与决策依据.md) |
| 框架 | Axum + SQLite→PG | [项目规划-旧.md#七](规划/项目规划-旧.md) |
| 核心哲学 | 新功能=注册扩展，架构永远不改 | [项目规划-旧.md#十一](规划/项目规划-旧.md) |
| 与OpenDAW同构 | Extension Registry + 共享crate可能 | [项目规划-旧.md#十](规划/项目规划-旧.md) |
| CI | GitHub Actions（check→clippy→test→fmt→docker） | [docs/knowledge/设计哲学与决策依据.md#十四](docs/knowledge/设计哲学与决策依据.md) |
| 编译环境 | 云电脑开发 / Actions编译 / ECS部署 | [docs/knowledge/设计哲学与决策依据.md#十四](docs/knowledge/设计哲学与决策依据.md) |

### 运营卖点（运营关注）

- **核心差异化**：传统短链是静态映射，OpenLink是动态路由引擎
- **目标用户**：AI开发者 / 智能体运营者 / 开源社区 / 独立开发者
- **一句话定位**：URL是人类互联网的入口协议，OpenLink是智能体互联网的入口协议
- **核心类比**：PPS播放器进化版——人越多越快但不断流
- **安全背书**：三道防线 + 公私分治 → 国内合规无忧
- **开放生态**：Extension Registry让任何人都能扩展能力

### 内容素材（内容关注）

- **教程方向**：短链入门 → 动态路由 → Agent协作 → 文件中转 → DAW集成 → 人形机器人
- **核心类比**：PPS播放器进化版 / Extension Registry像App Store / 短链是Agent的URL
- **与OpenDAW的关系**：同架构不同领域，Rust统一技术栈，共享crate
- **与OpenVault的关系**：OpenLink管"到得了"，OpenVault管"丢不了"

## 项目状态

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 1：核心原语+基础短链 | ✅ 已完成 | 3270行/36文件/30测试通过 |
| Phase 2：动态路由+Hook | ✅ 已完成 | 5237行/43文件/72测试/5扩展 |
| Phase 3：Agent接入+文件中转 | ✅ 已完成 | SDK+FileTransfer+Workflow+Conditions(3049行/23文件/114测试通过) |
| Phase 4：局域网直传+DAW | ✅ 已完成 | openlink-node + ext-direct-transfer + ext-daw-distribute (3127行/17文件/38测试通过) |
| Phase 5：P2P穿透+边缘化 | 📋 规划中 | Tailscale+WASM+规模化 |
| Phase 6：协议层 | 📋 规划中 | MCP/A2A/Agent发现 |

- GitHub仓库：https://github.com/youbanzhishi/OpenLink
- CI：已上线（push自动触发）

## 联盟项目
| 项目 | 路径 | 关系 | 共享知识 |
|------|------|------|----------|
| OpenDAW | ./项目文档/OpenDAW/ | DAW核心+插件宿主 | 音频引擎/信号链/扩展注册 |
| AudioFX | ./项目文档/AudioFX/ | VC插件基础(C++/JUCE) | DSP/插件设计/混音经验 |
| OpenLink | ./项目文档/OpenLink/ | 同架构不同领域 | Extension Registry/架构模式 |
| OpenVault | ./项目文档/OpenVault/ | 保险层 | 存储引擎/备份策略 |
| open-dev-tools | ./项目文档/open-dev-tools/ | 共享构建工具链 | CI模板/构建脚本 |

## 关联项目

| 项目 | 关系 | 详见 |
|------|------|------|
| OpenVault | 保险层，调用OpenLink做运输 | [../OpenVault/规划/项目规划-旧.md](../OpenVault/规划/项目规划-旧.md) |
| open-dev-tools | 共享构建工具链 | [../open-dev-tools/INDEX.md](../open-dev-tools/INDEX.md) |
| AudioFX | VC插件基础(C++/JUCE) | [../AudioFX/INDEX.md](../AudioFX/INDEX.md) |
| OpenDAW | 架构同构，共享Extension Registry模式 | [../../共享知识/设计模式/extension-registry.md](../../共享知识/设计模式/extension-registry.md) |

## 职能分工

| 职能 | 负责人 | 关注点 | 产出目录 |
|------|--------|--------|---------|
| 开发 | 主对话+sub-agent | 代码/架构/CI | openlink/ + docs/knowledge/ |
| 运营 | 待定 | 文案/推广/用户 | 运营/ |
| 内容 | 待定 | 教程/FAQ/科普 | 内容/ |

## 最近变更（2026-05-09）

- Phase 1代码完成（3270行/36文件/30测试通过）→ [docs/dev-log/2026-05-09.md](docs/dev-log/2026-05-09.md)
- GitHub Actions CI上线（ci.yml + release.yml）
- 新增人形机器人对接设计 → [docs/knowledge/设计哲学与决策依据.md#十三](docs/knowledge/设计哲学与决策依据.md)
- 新增公私分治：公开内容过审，私密内容端到端加密 → [docs/knowledge/设计哲学与决策依据.md#十一](docs/knowledge/设计哲学与决策依据.md)
- open-dev-tools升级为跨语言工具链
- 共享知识库建立 `./共享知识/` → [../../共享知识/README.md](../../共享知识/README.md)

## 最近变更（2026-05-10）

- **Phase 4代码完成**（3127行/17文件/38测试通过）
  - openlink-node: 设备端守护进程（mDNS发现+HTTP文件服务+心跳）
  - ext-direct-transfer: LAN P2P直传Action（11测试通过）
  - ext-daw-distribute: DAW插件分发Action（13测试通过）
  - openlink-node测试：14测试通过
- 踩坑记录更新 → [规划/hot-rules.md](规划/hot-rules.md)

## 最近变更（2026-05-10）

- **Phase 4代码完成**（3127行/17文件/38测试通过）
  - openlink-node: 设备端守护进程（mDNS发现+HTTP文件服务+心跳）
  - ext-direct-transfer: LAN P2P直传Action（11测试通过）
  - ext-daw-distribute: DAW插件分发Action（13测试通过）
  - openlink-node测试：14测试通过
- 踩坑记录更新 → [规划/hot-rules.md](规划/hot-rules.md)
