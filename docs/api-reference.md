# OpenDAW API 参考

## 基础信息

- **Base URL**: `http://localhost:3000`
- **Content-Type**: `application/json`
- **API版本**: v1

## 项目管理

### 列出所有项目

```
GET /api/v1/projects
```

**响应**:

```json
[
  {
    "id": "uuid",
    "name": "My Project",
    "description": "",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

### 创建项目

```
POST /api/v1/projects
```

**请求体**:

```json
{
  "name": "My New Project",
  "description": "A new project"
}
```

**响应** (201 Created):

```json
{
  "id": "uuid",
  "name": "My New Project",
  "description": "A new project",
  "tracks": [],
  "created_at": "2024-01-01T00:00:00Z"
}
```

### 获取项目详情

```
GET /api/v1/projects/{id}
```

**路径参数**:
- `id` — 项目UUID

**响应** (200 OK):

```json
{
  "id": "uuid",
  "name": "My Project",
  "description": "",
  "tracks": [
    {
      "name": "Vocals",
      "volume": 0.8,
      "pan": 0.0,
      "muted": false
    }
  ],
  "created_at": "2024-01-01T00:00:00Z"
}
```

### 更新项目

```
PUT /api/v1/projects/{id}
```

**请求体**:

```json
{
  "name": "Updated Name",
  "description": "Updated description"
}
```

### 删除项目

```
DELETE /api/v1/projects/{id}
```

**响应**: 204 No Content

---

## 渲染 & AI

### 触发渲染

```
POST /api/v1/projects/{id}/render
```

**请求体**:

```json
{
  "format": "wav",
  "sample_rate": 44100,
  "bit_depth": 16,
  "normalize": false
}
```

**响应** (200 OK):

```json
{
  "task_id": "uuid",
  "project_id": "uuid",
  "status": "pending",
  "message": "Render task created"
}
```

### AI自动混音

```
POST /api/v1/projects/{id}/automix
```

**请求体**:

```json
{
  "style": "pop",
  "apply": false
}
```

**响应** (200 OK):

```json
{
  "project_id": "uuid",
  "suggestions": [
    {
      "track_name": "Vocals",
      "action": "adjust_volume",
      "current_value": 0.8,
      "suggested_value": 0.72,
      "reason": "Auto-mix volume adjustment"
    }
  ],
  "applied": false
}
```

### 音频扒带

```
POST /api/v1/projects/{id}/transcribe
```

**请求体**:

```json
{
  "source_track": "uuid",
  "options": {
    "detect_pitch": true,
    "detect_beats": true
  }
}
```

**响应** (200 OK):

```json
{
  "project_id": "uuid",
  "notes_detected": 0,
  "tracks_created": 0,
  "key_estimate": null
}
```

---

## 插件

### 列出可用插件

```
GET /api/v1/plugins
```

**响应** (200 OK):

```json
[]
```

---

## 混音

### 获取混音建议

```
GET /api/v1/mixer/{id}/suggestions
```

**路径参数**:
- `id` — 项目UUID

**响应** (200 OK):

```json
{
  "project_id": "uuid",
  "suggestions": [
    {
      "track_name": "Vocals",
      "action": "eq_adjust",
      "current_value": 0.8,
      "suggested_value": 0.68,
      "reason": "Frequency masking detected"
    }
  ],
  "overall_score": 75.0
}
```

---

## 插件市场

### 搜索插件

```
GET /api/v1/marketplace/search?q=eq&category=effect
```

**查询参数**:
- `q` (可选) — 搜索关键词
- `category` (可选) — 分类筛选

**响应** (200 OK):

```json
[
  {
    "id": "plugin-id",
    "name": "VC Equalizer",
    "version": "1.0.0",
    "author": "OpenDAW",
    "description": "Parametric EQ",
    "category": "Effect",
    "tags": ["eq", "equalizer"],
    "average_rating": 4.5,
    "review_count": 10,
    "compatible": true
  }
]
```

### 获取分类列表

```
GET /api/v1/marketplace/categories
```

**响应** (200 OK):

```json
[
  {
    "name": "Effect",
    "count": 0
  },
  {
    "name": "Instrument",
    "count": 0
  }
]
```

### 获取插件详情

```
GET /api/v1/marketplace/{id}
```

**响应** (200 OK):

```json
{
  "id": "plugin-id",
  "name": "VC Equalizer",
  "version": "1.0.0",
  "author": "OpenDAW",
  "description": "Parametric EQ",
  "category": "Effect",
  "average_rating": 4.5,
  "review_count": 10,
  "rating_distribution": [0, 1, 2, 3, 4],
  "compatible": true,
  "compatibility_issues": []
}
```

### 安装插件

```
POST /api/v1/marketplace/{id}/install
```

**响应** (200 OK):

```json
{
  "plugin_id": "plugin-id",
  "version": "1.0.0",
  "status": "installed",
  "message": "Plugin installed successfully"
}
```

### 提交评价

```
POST /api/v1/marketplace/{id}/review
```

**请求体**:

```json
{
  "user_id": "user-uuid",
  "rating": 5,
  "comment": "Great plugin!"
}
```

**响应** (200 OK):

```json
{
  "review_id": "review-uuid",
  "plugin_id": "plugin-id",
  "rating": 5,
  "comment": "Great plugin!"
}
```

---

## 错误响应

所有端点在出错时返回统一格式：

```json
{
  "error": "Error type",
  "message": "Detailed error message"
}
```

| 状态码 | 含义 |
|--------|------|
| 400 | Bad Request — 请求参数错误 |
| 404 | Not Found — 资源不存在 |
| 500 | Internal Server Error — 服务器内部错误 |
