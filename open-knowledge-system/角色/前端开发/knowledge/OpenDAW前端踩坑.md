# OpenDAW 前端踩坑经验

> 沉淀日期：2026-05-12
> 来源：专业 DAW 界面重做实践

## Tauri 2.0 前端要点

### 前端文件位置
- Tauri 2.0 的 `frontendDist` 配置指向 `./frontend`，所以前端文件放在 `desktop/src-tauri/frontend/` 目录
- 不是 `desktop/src/` — 这个路径不存在于 Tauri 2.0 项目中
- `tauri.conf.json` 的 `build.frontendDist` 决定静态文件服务目录

### JS 模块加载顺序
- 非 ES module 模式：`<script src>` 按顺序加载，后面的依赖前面的
- 加载顺序：utils → canvas → components → app.js
- 所有模块用 IIFE 模式（`const Name = (() => { ... })()`）暴露全局对象

### Tauri 调用方式
- Tauri 2.0 检测：`typeof window.__TAURI_INTERNALS__ !== 'undefined'`
- invoke 调用：`window.__TAURI_INTERNALS__.invoke(cmd, args)`
- 不是 `window.__TAURI_INVOKE__`（旧版写法）
- 文件对话框：`window.__TAURI_DIALOG__` 需要安装 `@tauri-apps/plugin-dialog`

## Canvas 渲染

### DPR 处理
- 必须处理 `window.devicePixelRatio`，否则在高分屏模糊
- Canvas 物理像素 = CSS 像素 × DPR
- `ctx.scale(dpr, dpr)` 后用 CSS 像素坐标绘制
- resize 时重新设置 canvas.width/height 并重新 scale

### 波形渲染性能
- 大波形不要每像素一个 fillRect，用 `step = peaks.length / canvasWidth` 采样
- 500+ 音轨时避免逐轨道 DOM 操作，Canvas 是唯一选择

## 触控支持

### Pointer Events vs Touch Events
- 用 Pointer Events API 统一鼠标/触摸/笔，不要分别监听 mouse 和 touch
- `setPointerCapture` 确保指针离开元素后仍能接收 move/up 事件
- `touch-action: none` 防止浏览器默认手势（滚动/缩放）
- 多指追踪：用 `e.pointerId` 和 Map 存储

### 双指缩放
- 记录初始两指距离 `initialPinchDist`
- 每次移动计算新距离比例 `scale = dist / initialPinchDist`
- 乘以初始 zoom 值，避免累积误差

### 长按检测
- pointerdown 时设 setTimeout(500ms)
- 如果 pointermove 距离 > 8px，取消长按
- 如果 pointerup 在 500ms 内，取消长按
- 双指触摸时取消长按

## 响应式布局

### CSS Grid vs Flexbox
- 整体布局用 CSS Grid（`grid-template-rows` 四行：传输/主区/混音/状态栏）
- 主区内部用 Flexbox（轨道/编曲/检视器三栏）
- 避免嵌套过深，body 直接 grid

### 移动端适配
- `@media (max-width: 768px)` 隐藏轨道列表和检视器
- `@media (orientation: landscape)` 横屏手机恢复轨道列表
- 混音台默认折叠，点击展开
- 虚拟钢琴键盘按需弹出

## 设计风格踩坑

### 用户偏好总结
- **禁止描边/外发光**：不用 `border`、`box-shadow`、`text-shadow`
- **字号大胆**：标题 20px 800 weight，标签 10px 800 weight uppercase
- **颜色不暧昧**：纯黑底 #121218，明确蓝色 #4a9eff，不搞渐变过渡
- **padding 充足**：用 16/24px 间距，不要 4px 挤在一起
- **输入左/输出右**：轨道列表（输入源）在左，混音台（输出）在底

### 按钮 SVG 图标
- 不用 emoji（跨平台不一致）
- 不用图标字体（加载慢）
- 内联 SVG：`<svg width="18" height="18" viewBox="0 0 18 18">`
- `fill="currentColor"` 跟随文本色

## 构建环境

### Linux 缺系统依赖
- Tauri on Linux 需要 webkit2gtk-4.1, glib-2.0 等
- `sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev libglib2.0-dev`
- 云电脑环境缺这些，Rust check 会失败，但前端代码本身没问题

### cargo check vs 实际运行
- `cargo check -p opendaw-desktop` 可验证 Rust 编译
- 前端语法用 `node --check` 验证
- 完整构建需要系统依赖
