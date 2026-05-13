# ADR-001: 从Python重写为Rust

## 状态
已采纳

## 背景
VCMix v1是Python实现（click+pydantic+numpy），在实时音频处理上遇到性能瓶颈和类型安全问题。Python的GIL限制了多线程音频处理，动态类型导致运行时错误频发。

## 决策
用Rust完全重写整个项目，形成9个crate的workspace架构。

## 理由
- 实时音频需要零成本抽象和确定性内存管理
- 跨平台需要单一二进制分发，不依赖Python运行时
- AI Agent友好需要结构化JSON输出，Rust的serde天然支持
- 类型安全在编译期捕获错误，而非运行时崩溃
- 跨平台（Windows/macOS/Linux）用同一套代码

## 后果
- 正面：9 crate workspace，499 tests全绿，CI全平台构建+Release
- 负面：学习曲线陡峭，贡献者门槛高于Python，编译时间较长
- 注意：architecture.md等旧文档仍引用Python架构，需逐步更新
