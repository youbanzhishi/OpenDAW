# OpenDAW AI智能体内置指南

> 本文档面向AI Agent，提供结构化的OpenDAW功能参考。
> Agent阅读本文档后应能理解OpenDAW是什么、能调什么API、怎么帮用户做音乐。

---

## 1. OpenDAW是什么

OpenDAW是AI原生的数字音频工作站（DAW）。

**核心特征**：
- Rust原生引擎，高性能实时音频处理
- 支持CLI/API/WebUI/Desktop四种交互方式
- 内置AI Agent能力：ReAct循环 + 工具执行，最多5轮
- 声明式YAML项目配置，AI可直接读写理解
- 插件市场：搜索/安装/评价

**交互接口**：
| 接口 | 入口 | 说明 |
|------|------|------|
| CLI | `opendaw` 命令 | 命令行，零GUI |
| API | `http://localhost:3000/api/v1` | REST API |
| WebUI | `http://localhost:3000/` | Web界面 |
| Desktop | Tauri桌面应用 | 原生桌面 |
| Agent | `/api/v1/agent/chat` | AI Agent对话 |

**发现协议**：`GET /.well-known/agent.json` 返回完整能力声明。

---

## 2. API速查表

### 2.1 项目CRUD

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/api/v1/projects` | 列出所有项目 | — | `ProjectInfo[]` |
| POST | `/api/v1/projects` | 创建项目 | `{name, description?, bpm?, sample_rate?}` | `Project` (201) |
| GET | `/api/v1/projects/{id}` | 获取项目详情 | — | `Project` |
| PUT | `/api/v1/projects/{id}` | 更新项目 | `{name?, description?, bpm?}` | `Project` |
| DELETE | `/api/v1/projects/{id}` | 删除项目 | — | 204 |

### 2.2 渲染与AI

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/v1/projects/{id}/render` | 触发渲染 | `{format?, sample_rate?, bit_depth?, normalize?}` | `RenderResponse` |
| POST | `/api/v1/projects/{id}/automix` | AI自动混音 | `{style?, target_loudness?}` | `AutoMixResponse` |
| POST | `/api/v1/projects/{id}/transcribe` | 音频扒带 | `{audio_path, sensitivity?}` | `TranscribeResponse` |

### 2.3 Agent对话

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/v1/agent/chat` | Agent对话 | `{message, project_id?}` | `AgentChatResponse` |

### 2.4 插件与混音

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/api/v1/plugins` | 列出可用插件 | — | `PluginInfo[]` |
| GET | `/api/v1/mixer/{id}/suggestions` | 获取混音建议 | — | `MixerSuggestionsResponse` |

### 2.5 插件市场

| 方法 | 路径 | 说明 | 参数 | 响应 |
|------|------|------|------|------|
| GET | `/api/v1/marketplace/search` | 搜索插件 | `?q=xxx&category=xxx` | `MarketplacePlugin[]` |
| GET | `/api/v1/marketplace/categories` | 分类列表 | — | `CategoryItem[]` |
| GET | `/api/v1/marketplace/{id}` | 插件详情 | — | `PluginDetailResponse` |
| POST | `/api/v1/marketplace/{id}/install` | 安装插件 | — | `InstallResponse` |
| POST | `/api/v1/marketplace/{id}/review` | 提交评价 | `{user_id, rating, comment}` | `ReviewResponse` |

### 2.6 数据模型

**Project**：
```json
{
  "id": "uuid",
  "name": "string",
  "description": "string|null",
  "tracks": ["TrackInfo"],
  "sample_rate": 44100,
  "bpm": 120.0,
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

**TrackInfo**：
```json
{
  "id": "uuid",
  "name": "string",
  "volume": 0.8,
  "pan": 0.0,
  "muted": false,
  "solo": false,
  "plugin_count": 2
}
```

**AutoMixResponse**：
```json
{
  "project_id": "uuid",
  "suggestions": [
    {
      "track_name": "string",
      "action": "string",
      "current_value": 0.8,
      "suggested_value": 0.72,
      "reason": "string"
    }
  ],
  "applied": false
}
```

**RenderResponse**：
```json
{
  "task_id": "uuid",
  "project_id": "uuid",
  "status": "pending|running|completed|failed",
  "message": "string"
}
```

**MixerSuggestionsResponse**：
```json
{
  "project_id": "uuid",
  "suggestions": ["MixSuggestionItem"],
  "overall_score": 75.0
}
```

**错误响应**：
```json
{
  "error": "Error type",
  "message": "Detailed error message"
}
```
状态码：400（参数错误）、404（资源不存在）、500（内部错误）

---

## 3. 核心工作流

### 3.1 完整流程：创建项目 → 添加轨道 → 添加插件 → 混音 → 导出

**步骤1：创建项目**

```bash
curl -X POST http://localhost:3000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "My Song", "bpm": 120, "sample_rate": 44100}'
```

响应中获取 `id`（UUID），后续步骤使用。

**步骤2：添加轨道**

```bash
# 通过Agent对话
curl -X POST http://localhost:3000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "添加一个人声轨道和一个吉他轨道", "project_id": "<UUID>"}'
```

**步骤3：添加效果器**

```bash
# 通过Agent对话
curl -X POST http://localhost:3000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "给人声加EQ和压缩器", "project_id": "<UUID>"}'
```

**步骤4：混音**

```bash
# AI自动混音
curl -X POST http://localhost:3000/api/v1/projects/<UUID>/automix \
  -H "Content-Type: application/json" \
  -d '{"style": "pop", "apply": true}'
```

**步骤5：导出**

```bash
# 触发渲染
curl -X POST http://localhost:3000/api/v1/projects/<UUID>/render \
  -H "Content-Type: application/json" \
  -d '{"format": "wav", "sample_rate": 44100, "bit_depth": 24}'
```

### 3.2 快速路径：AI一键混音

```bash
# 一步完成分析和混音
curl -X POST http://localhost:3000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我自动混音，风格pop，然后导出wav", "project_id": "<UUID>"}'
```

---

## 4. Agent对话协议

### 4.1 请求格式

`POST /api/v1/agent/chat`

```json
{
  "message": "用户自然语言消息",
  "project_id": "可选，绑定到特定项目"
}
```

### 4.2 响应格式

```json
{
  "message": "Agent的最终文本回复",
  "actions": [
    {
      "tool": "工具名称",
      "arguments": {"key": "value"},
      "result": {"key": "value"},
      "explanation": "操作说明",
      "timestamp": 1234567890.0
    }
  ],
  "thinking": "Agent的思考过程（工具调用日志）",
  "requires_confirmation": false
}
```

**字段说明**：
- `message`：最终回复文本，展示给用户
- `actions`：执行的工具调用列表
- `thinking`：思考链，包含 `🔧 调用工具` 和 `📊 工具结果` 日志
- `requires_confirmation`：`confirm` 模式下有操作时为 `true`，需用户确认

### 4.3 Persona选择

| persona_id | 名称 | 特点 | 默认执行模式 |
|------------|------|------|-------------|
| `mix-engineer` | 混音工程师 | 专业混音，EQ/压缩/空间处理 | confirm |
| `vocal-expert` | 人声专家 | 人声处理专精 | confirm |
| `beginner-coach` | 新手教练 | 简单语言，逐步教学 | suggest |

### 4.4 执行模式

| 模式 | 行为 |
|------|------|
| `auto` | 自动执行，无需确认 |
| `confirm` | 执行前请求确认（默认） |
| `suggest` | 仅建议，不执行 |

### 4.5 ReAct循环

Agent使用 ReAct (Reason + Act) 循环：

1. 接收用户消息，构建上下文（Persona + 项目状态 + 对话历史）
2. 调用LLM，传入工具定义
3. 如果LLM返回 `tool_calls` → 执行工具 → 将结果追加到上下文 → 回到步骤2
4. 如果LLM返回文本 → 返回最终 `AgentResponse`
5. 最多5轮工具调用（`MAX_TOOL_ROUNDS = 5`）

---

## 5. YAML项目格式参考

```yaml
# 项目基本信息
name: "项目名称"          # 必需
bpm: 120                  # 必需，速度
sample_rate: 44100        # 必需，采样率

# 轨道列表
tracks:
  - name: "vocal"         # 轨道名称
    file: "vocal_dry.wav" # 音频文件路径
    volume: 1.0           # 音量 (0.0-2.0)
    effects:              # 效果器链（按顺序处理）
      - name: vc-deesser  # 插件名称
        params:           # 插件参数
          threshold: -40
          reduction: -6
      - name: vc-eq
        params:
          low_cut: 80
          high_shelf: 8000
          peak_gain: -3
      - name: vc-comp
        params:
          threshold: -30
          ratio: 2.5
          attack: 5
          release: 50
      - name: vc-reverb
        params:
          room: 30
          decay: 35
          damping: 50
          mix: 10
          predelay: 50
          wetlpf: 5000
      - name: vc-delay
        params:
          time: "1/8d"    # BPM同步音符值，自动换算毫秒
          feedback: 12
          mix: 5
      - name: vc-limiter
        params:
          ceiling: -1

  - name: "accomp"
    file: "accomp.wav"
    volume: 1.0
    effects: []            # 无效果器

# Master总线
master:
  levels:                  # 各轨在Master中的电平
    vocal: 0.8
    accomp: 0.35
  effects: []              # Master效果器链
  output: "output.wav"     # 输出文件名
```

**字段说明**：
- `name`：项目名称
- `bpm`：速度（节拍/分钟）
- `sample_rate`：采样率（44100/48000等）
- `tracks[]`：轨道数组
  - `name`：轨道名
  - `file`：音频文件路径
  - `volume`：音量 0.0-2.0
  - `effects[]`：效果器链，按顺序串行处理
    - `name`：插件名（vc-eq, vc-comp, vc-reverb等）
    - `params`：插件参数键值对
- `master`：Master总线
  - `levels`：各轨电平映射
  - `effects[]`：Master效果器链
  - `output`：输出文件名

**延迟时间格式**：`"1/8d"` 表示附点八分音符，系统自动根据BPM换算为毫秒。公式：`60000/BPM × 音符比例 × 1.5(附点)`。

---

## 6. 模型配置

### 6.1 ModelConfig字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | string | `"openai"` | LLM后端 |
| `model` | string | `"gpt-4o"` | 模型名称 |
| `api_key` | string | `""` | API密钥（本地模型可留空） |
| `base_url` | string | `"https://api.openai.com/v1"` | API地址 |
| `temperature` | float | `0.3` | 温度参数 0-1 |
| `max_tokens` | int | `2048` | 最大输出token数 |

### 6.2 各provider的base_url

| provider | base_url | 说明 |
|----------|----------|------|
| `openai` | `https://api.openai.com/v1` | OpenAI官方 |
| `anthropic` | `https://api.anthropic.com/v1` | Anthropic兼容层 |
| `ollama` | `http://localhost:11434/v1` | Ollama本地 |
| `vllm` | `http://localhost:8000/v1` | vLLM本地 |

### 6.3 各provider推荐模型

| provider | 推荐模型 |
|----------|----------|
| `openai` | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo` |
| `anthropic` | `claude-3.5-sonnet`, `claude-3-opus` |
| `ollama` | `llama3.3:70b`, `qwen2.5:72b`, `deepseek-r1` |
| `vllm` | `custom-mix-engine-v1`（用户自部署模型） |

### 6.4 配置方式

**方式1：配置文件** `config/default.toml`
```toml
[model]
provider = "openai"
model = "gpt-4o"
api_key = "sk-xxx"
base_url = "https://api.openai.com/v1"
temperature = 0.3
max_tokens = 2048
```

**方式2：环境变量**（优先级高于配置文件）
```bash
OPENDAW_MODEL_PROVIDER=openai
OPENDAW_MODEL_MODEL=gpt-4o
OPENDAW_MODEL_API_KEY=sk-xxx
OPENDAW_MODEL_BASE_URL=https://api.openai.com/v1
OPENDAW_MODEL_TEMPERATURE=0.3
OPENDAW_MODEL_MAX_TOKENS=2048
```

### 6.5 API兼容性

所有provider通过 OpenAI SDK 兼容接口 `/chat/completions` 访问。ModelBus自动处理：
- 根据 `provider` 设置默认 `base_url`
- 统一请求/响应格式
- 支持 function calling（工具调用）

---

## 7. Agent工具完整列表

| 工具名 | API映射 | 说明 |
|--------|---------|------|
| `analyze_project` | GET `/projects/{id}/analysis` | 项目音频分析 |
| `list_plugins` | GET `/plugins` | 列出可用插件 |
| `add_effect` | POST `/projects/{id}/tracks/{name}/effects` | 添加效果器 |
| `update_effect` | PUT `/projects/{id}/tracks/{name}/effects/{idx}` | 更新效果器参数 |
| `remove_effect` | DELETE `/projects/{id}/tracks/{name}/effects/{idx}` | 移除效果器 |
| `get_project` | GET `/projects/{id}` | 获取项目详情 |
| `render_project` | POST `/projects/{id}/render` | 触发渲染 |
| `ai_auto_mix` | POST `/ai/mix` | AI自动混音 |
| `ai_master` | POST `/ai/master` | AI母带 |
| `get_waveform` | GET `/waveform/{id}/{track}` | 波形数据 |
| `get_spectrum` | GET `/spectrum/{id}/{track}` | 频谱数据 |
| `add_track` | POST `/projects/{id}/tracks` | 添加轨道 |
| `update_track` | PUT `/projects/{id}/tracks/{name}` | 更新轨道 |
| `remove_track` | DELETE `/projects/{id}/tracks/{name}` | 删除轨道 |
| `validate_project` | POST `/validate` | 验证项目 |
| `get_presets` | GET `/presets/chains` | 列出预设 |
| `apply_preset` | POST `/presets/chains/{name}/apply` | 应用预设 |
| `ai_compose` | POST `/ai/compose` | AI作曲 |
| `create_snapshot` | POST `/projects/{id}/snapshots` | 创建快照 |
| `export_stems` | POST `/projects/{id}/export-stems` | 导出Stem |

---

## 8. DataStream事件

Agent操作触发的实时事件（WebSocket广播）：

| 事件 | 数据 | 用途 |
|------|------|------|
| `track_level` | rms_db, peak_db, true_peak_db | 轨道电平监控 |
| `effect_delta` | before_rms, after_rms, delta_db | 效果器影响量化 |
| `master_level` | rms_db, peak_db, true_peak_db | Master总线监控 |
| `warning` | type(clipping/low_snr/sibilance), message | 问题检测 |
| `decision` | action, params, reason | 自动操作日志 |

---

## 9. MCP Server

OpenDAW同时暴露MCP Server，支持外部Agent通过MCP协议控制。

- **协议**：JSON-RPC 2.0 over SSE
- **支持方法**：`initialize`, `tools/list`, `tools/call`, `ping`
- **工具**：与Agent工具完全一致（20个）
- **版本**：MCP协议 `2024-11-05`

外部Agent流程：
1. 连接MCP SSE端点
2. `initialize` → 获取能力声明
3. `tools/list` → 获取可用工具
4. `tools/call` → 调用工具执行操作

---

## Agent Action Protocol v2 定义

> OpenDAW 的 agent.json v2 能力声明，遵循 [Agent Action Protocol](https://github.com/youbanzhishi/open-knowledge-system/blob/main/共享知识/设计模式/Agent-Action-Protocol.md)。

### agent.json v2

```json
{
  "schema_version": "2.0",
  "name": "opendaw",
  "description": "AI原生的数字音频工作站——混音、母带、音频分析一体化",
  "version": "1.0.1",
  "base_url": "http://localhost:3000",
  "auth": {
    "type": "bearer",
    "header": "Authorization"
  },
  "capabilities": [
    {
      "name": "open_project",
      "description": "打开指定工程文件，加载项目状态（轨道、效果器、配置）",
      "category": "search",
      "endpoint": "GET /api/v1/projects/{id}",
      "input": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "项目UUID"
          }
        },
        "required": ["id"]
      },
      "output": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "name": { "type": "string" },
          "tracks": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": { "type": "string" },
                "name": { "type": "string" },
                "volume": { "type": "number" },
                "pan": { "type": "number" },
                "muted": { "type": "boolean" },
                "solo": { "type": "boolean" },
                "plugin_count": { "type": "integer" }
              }
            }
          },
          "bpm": { "type": "number" },
          "sample_rate": { "type": "integer" }
        }
      },
      "examples": [
        {
          "input": { "id": "550e8400-e29b-41d4-a716-446655440000" },
          "output": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "name": "夏日之歌",
            "tracks": [
              { "id": "t1", "name": "vocal", "volume": 0.8, "pan": 0.0, "muted": false, "solo": false, "plugin_count": 3 }
            ],
            "bpm": 120.0,
            "sample_rate": 44100
          }
        }
      ]
    },
    {
      "name": "ai_mix",
      "description": "AI混音对话——通过自然语言描述混音需求，Agent自动调整EQ/压缩/空间等参数",
      "category": "execute",
      "endpoint": "POST /api/v1/agent/chat",
      "input": {
        "type": "object",
        "properties": {
          "message": {
            "type": "string",
            "description": "自然语言混音指令，如'让人声更亮更靠前'"
          },
          "project_id": {
            "type": "string",
            "description": "目标项目UUID"
          }
        },
        "required": ["message", "project_id"]
      },
      "output": {
        "type": "object",
        "properties": {
          "message": { "type": "string", "description": "Agent回复文本" },
          "actions": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "tool": { "type": "string" },
                "arguments": { "type": "object" },
                "result": { "type": "object" },
                "explanation": { "type": "string" }
              }
            }
          },
          "requires_confirmation": { "type": "boolean" }
        }
      },
      "examples": [
        {
          "input": { "message": "帮我自动混音，风格pop，然后导出wav", "project_id": "550e8400-e29b-41d4-a716-446655440000" },
          "output": {
            "message": "已应用Pop风格混音预设：人声EQ提升2kHz-5kHz，压缩比2.5:1，混响房间30%。准备导出WAV。",
            "actions": [
              { "tool": "ai_auto_mix", "arguments": { "style": "pop", "apply": true }, "result": { "applied": true }, "explanation": "应用Pop风格AI混音" }
            ],
            "requires_confirmation": false
          }
        }
      ]
    },
    {
      "name": "export",
      "description": "导出音频文件，支持WAV/FLAC/MP3格式，可指定采样率和位深",
      "category": "execute",
      "endpoint": "POST /api/v1/projects/{id}/render",
      "input": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "项目UUID"
          },
          "format": {
            "type": "string",
            "enum": ["wav", "flac", "mp3"],
            "description": "导出格式，默认wav"
          },
          "sample_rate": {
            "type": "integer",
            "enum": [44100, 48000, 96000],
            "description": "采样率，默认44100"
          },
          "bit_depth": {
            "type": "integer",
            "enum": [16, 24, 32],
            "description": "位深，默认24"
          },
          "normalize": {
            "type": "boolean",
            "description": "是否响度标准化，默认true"
          }
        },
        "required": ["id"]
      },
      "output": {
        "type": "object",
        "properties": {
          "task_id": { "type": "string", "description": "渲染任务UUID" },
          "project_id": { "type": "string" },
          "status": { "type": "string", "enum": ["pending", "running", "completed", "failed"] },
          "message": { "type": "string" }
        }
      },
      "examples": [
        {
          "input": { "id": "550e8400-e29b-41d4-a716-446655440000", "format": "wav", "sample_rate": 44100, "bit_depth": 24 },
          "output": {
            "task_id": "task-7f3a9c",
            "project_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "pending",
            "message": "渲染任务已创建"
          }
        }
      ]
    },
    {
      "name": "list_projects",
      "description": "列出所有工程文件，返回项目概览列表",
      "category": "search",
      "endpoint": "GET /api/v1/projects",
      "input": {
        "type": "object",
        "properties": {},
        "required": []
      },
      "output": {
        "type": "object",
        "properties": {
          "projects": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": { "type": "string" },
                "name": { "type": "string" },
                "description": { "type": "string" },
                "bpm": { "type": "number" },
                "updated_at": { "type": "string" }
              }
            }
          }
        }
      },
      "examples": [
        {
          "input": {},
          "output": {
            "projects": [
              { "id": "550e8400-e29b-41d4-a716-446655440000", "name": "夏日之歌", "description": "流行曲", "bpm": 120.0, "updated_at": "2024-06-15T10:30:00Z" },
              { "id": "660f9511-f30c-52e5-b827-557766551111", "name": "深夜爵士", "description": "爵士即兴", "bpm": 95.0, "updated_at": "2024-06-14T22:00:00Z" }
            ]
          }
        }
      ]
    },
    {
      "name": "get_analysis",
      "description": "获取项目音频分析结果，包含频谱、响度、动态范围等",
      "category": "search",
      "endpoint": "GET /api/v1/projects/{id}/analysis",
      "input": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "项目UUID"
          }
        },
        "required": ["id"]
      },
      "output": {
        "type": "object",
        "properties": {
          "project_id": { "type": "string" },
          "overall_score": { "type": "number", "description": "整体混音评分 0-100" },
          "loudness": {
            "type": "object",
            "properties": {
              "integrated_lufs": { "type": "number" },
              "true_peak_db": { "type": "number" }
            }
          },
          "suggestions": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "track_name": { "type": "string" },
                "action": { "type": "string" },
                "reason": { "type": "string" }
              }
            }
          }
        }
      },
      "examples": [
        {
          "input": { "id": "550e8400-e29b-41d4-a716-446655440000" },
          "output": {
            "project_id": "550e8400-e29b-41d4-a716-446655440000",
            "overall_score": 75.0,
            "loudness": { "integrated_lufs": -14.2, "true_peak_db": -1.0 },
            "suggestions": [
              { "track_name": "vocal", "action": "降低200Hz附近的箱体共鸣", "reason": "人声低频过多导致浑浊" }
            ]
          }
        }
      ]
    }
  ],
  "workflows": [
    {
      "name": "mix_and_publish",
      "description": "混音发布流：OpenMind找待办→OpenVault取音轨→OpenDAW混音导出→OpenLink发布",
      "steps": [
        { "project": "openmind", "action": "find_todos" },
        { "project": "openvault", "action": "retrieve" },
        { "project": "opendaw", "action": "open_project" },
        { "project": "opendaw", "action": "ai_mix" },
        { "project": "opendaw", "action": "export" },
        { "project": "openlink", "action": "create_link" }
      ]
    },
    {
      "name": "knowledge_archive",
      "description": "知识归档流：OpenDAW导出→OpenMind入库→OpenVault备份",
      "steps": [
        { "project": "opendaw", "action": "export" },
        { "project": "openmind", "action": "ingest" },
        { "project": "openvault", "action": "backup" }
      ]
    }
  ],
  "events": {
    "subscribe": "WS /ws/events",
    "types": ["render.completed", "render.failed", "mix.applied", "track.level", "warning.clipping"]
  },
  "links": {
    "docs": "https://github.com/youbanzhishi/OpenDAW/docs",
    "source": "https://github.com/youbanzhishi/OpenDAW",
    "health": "http://localhost:3000/health"
  }
}
```
