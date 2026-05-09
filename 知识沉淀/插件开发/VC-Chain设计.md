# VC-Chain 设计文档

> 兼容 Waves StudioRack 的混音链系统
> 版本：1.0 | 作者：OpenDAW Bot | 日期：2025-01

---

## 1. 核心理念

Waves StudioRack 是业界最流行的混音链插件，但其链文件 `.xps` 是闭源私有格式，社区分享（StudioVerse）也是封闭生态。VC-Chain 的目标是：

1. **用 YAML 定义链** — 跟 VCMix 项目文件风格一致，开源友好，Git 可追踪
2. **导入 .xps 文件** — 逆向解析 Waves 格式，让已有 Waves 用户无缝迁移
3. **导出为 .xps** — 让 Waves 用户也能用 VC-Chain 创建的链
4. **社区分享用 YAML** — ChainVerse（类似 StudioVerse），基于标签+AI搜索+评分
5. **8个 Macro 控制** — 兼容 StudioRack 的 8-Macro 设计

### 与现有 chain_presets.py 的关系

现有的 \`vcmix/presets/chain_presets.py\` 是 Phase 9 的简易链预设系统：
- 仅支持 serial 路由
- 没有 Macro 控制
- 没有并行/多频段处理
- 没有 .xps 兼容
- 没有社区分享

VC-Chain 是 chain_presets 的**超集升级**，但保持向后兼容：
- 旧 \`ChainPreset\` YAML 文件仍可被 VC-Chain 读取（自动升级）
- VC-Chain YAML 新增 \`macro\`、\`parallel\`、\`multiband\` 字段
- 旧 API 端点 (\`/api/presets/chains\`) 保留，新端点 (\`/api/v1/chains\`) 并行存在

---

## 2. 链定义格式（YAML）

### 2.1 完整格式

\`\`\`yaml
name: "CLA人声链"
author: "小龙"
version: "1.0"
tags: [vocal, pop, bright]
description: "Chris Lord-Alge 风格人声处理链"

macro:
  - name: "亮度"
    mapping:
      - plugin: vc-eq
        param: high_gain
        range: [0, 6]
      - plugin: vc-eq
        param: high_freq
        range: [8000, 16000]
  - name: "压缩感"
    mapping:
      - plugin: vc-comp
        param: ratio
        range: [2, 8]
  - name: "空间感"
    mapping:
      - plugin: vc-reverb
        param: wet
        range: [0.05, 0.4]
  - name: "齿音控制"
    mapping:
      - plugin: vc-deesser
        param: threshold
        range: [-40, -20]
    inverse: true

chain:
  serial:
    - plugin: vc-deesser
      params:
        threshold: -30
        frequency: 6000
    - plugin: vc-eq
      params:
        low_gain: -2
        high_gain: 3
        high_freq: 12000
    - plugin: vc-comp
      params:
        threshold: -18
        ratio: 4
        attack: 5
        release: 50
    - plugin: vc-reverb
      params:
        room_size: 0.3
        wet: 0.15
  parallel:
    - mix: 0.3
      chain:
        - plugin: vc-saturator
          params:
            drive: 3
\`\`\`

### 2.2 最小格式（兼容旧 ChainPreset）

\`\`\`yaml
name: "简单人声链"
description: "基础人声处理"
routing: serial
tags: [vocal]
effects:
  - name: vc-deesser
    params:
      threshold: -35
  - name: vc-comp
    params:
      threshold: -20
      ratio: 3
\`\`\`

### 2.3 格式升级规则

| 旧字段 | 新字段 | 说明 |
|--------|--------|------|
| \`routing: serial\` | \`chain.serial: [...]\` | serial 下的 effect 列表 |
| \`effects: [...]\` | \`chain.serial: [...]\` | 无 routing 时默认 serial |
| - | \`chain.parallel: [...]\` | 新增并行处理 |
| - | \`chain.multiband: {...}\` | 新增多频段处理 |
| - | \`macro: [...]\` | 新增 Macro 控制 |
| - | \`author\` | 新增作者信息 |
| - | \`version\` | 新增版本号 |

---

## 3. .xps 兼容层

### 3.1 .xps 文件结构

Waves .xps 文件结构：二进制头部(~128 bytes) + XML Body(UTF-8)

XML 结构：
- WavesPreset > PresetInfo (Name, Author)
- WavesPreset > PluginChain > Plugin (slot, name, Parameter)
- WavesPreset > Macros > Macro (index, name, Mapping)

### 3.2 导入流程

.xps → 跳过二进制头 → 解析 XML → 映射插件名/参数名 → 提取 Macro → 生成 YAML

### 3.3 插件名映射表

| Waves 插件 | VC 插件 | 说明 |
|-----------|---------|------|
| CLA-76 | vc-comp | 光学压缩器 |
| CLA-2A | vc-comp | 电子管压缩器 |
| R-EQ | vc-eq | 参量均衡 |
| R-Vox | vc-comp | 人声压缩 |
| DeEsser | vc-deesser | 去齿音 |
| L2 | vc-limiter | 限制器 |
| H-Delay | vc-delay | 延迟 |
| H-Reverb | vc-reverb | 混响 |
| Vitamin | vc-saturator | 增强器 |
| C1 Comp | vc-comp | 通用压缩 |
| C4 | vc-multiband | 多段动态 |
| Q10 | vc-eq | 10段参量EQ |

### 3.4 参数名映射

Waves: PascalCase → VC: snake_case（自动转换 + 硬编码映射表）

---

## 4. ChainVerse 社区分享

### 4.1 架构

用户浏览器 ←→ ChainVerse API ←→ GitHub Repo / 本地存储 + AI 搜索引擎

### 4.2 AI 推荐

用户音频 → 特征提取 → 标签匹配 → Top-N 推荐链列表

### 4.3 评分系统

综合评分 = rating * log(downloads + 1) / log(max_downloads + 1)

---

## 5. 8个 Macro 控制

- Macro 旋钮范围：0.0 ~ 1.0（归一化）
- 映射公式：param_value = min + macro_value * (max - min)
- 反向映射：param_value = max - macro_value * (max - min)
- 一个 Macro 可同时控制多个参数
- 最多 8 个 Macro（兼容 StudioRack）

---

## 6. 并行 + 多频段处理

### 6.1 并行处理

输入信号复制两份，一份走效果链，一份直通，按 mix 比例混合。

### 6.2 多频段处理

使用分频滤波器，信号按频率分最多5段，每段独立处理后求和。

### 6.3 执行顺序

Serial → Parallel → Multiband

---

## 7. API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/chains | 列出所有链 |
| POST | /api/v1/chains | 创建链 |
| GET | /api/v1/chains/{name} | 获取链详情 |
| PUT | /api/v1/chains/{name} | 更新链 |
| DELETE | /api/v1/chains/{name} | 删除链 |
| POST | /api/v1/chains/{name}/apply | 应用链到轨道 |
| POST | /api/v1/chains/import/xps | 导入 .xps 文件 |
| POST | /api/v1/chains/{name}/export/xps | 导出为 .xps |
| GET | /api/v1/chainverse/search | 社区搜索 |
| POST | /api/v1/chainverse/upload | 上传到社区 |

---

## 8. 模块结构

\`\`\`
src/vcmix/chain/
├── __init__.py       # 模块导出
├── models.py         # 数据模型
├── engine.py         # ChainEngine 链执行引擎
├── xps_import.py     # .xps 导入
├── xps_export.py     # .xps 导出
├── macro.py          # Macro 控制器
├── presets.py        # 内置预设链
└── community.py      # ChainVerse 社区接口
\`\`\`

---

## 9. 技术决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 链定义格式 | YAML | 与 VCMix 项目文件风格一致 |
| .xps 兼容 | 基础版 | 先做 XML 部分，跳过二进制头 |
| Macro 数量 | 8 | 兼容 StudioRack |
| 多频段最大频段 | 5 | 兼容 StudioRack |
| 社区存储 | 本地 YAML | 先做本地，后续扩展 |
| AI 推荐 | 标签匹配 | 先做简单版 |
| 并行处理 | 信号复制 + 混合 | 简单可靠 |

---

## 10. 兼容性矩阵

| 功能 | VC-Chain YAML | Waves .xps | 旧 ChainPreset YAML |
|------|---------------|------------|---------------------|
| Serial 链 | ✅ | ✅ | ✅ |
| Parallel 链 | ✅ | ⚠️ 基础 | ❌ |
| Multiband 链 | ✅ | ⚠️ 基础 | ❌ |
| Macro 控制 | ✅ | ✅ 读取 | ❌ |
| 社区分享 | ✅ | ❌ | ❌ |
| AI 推荐 | ✅ | ❌ | ❌ |
