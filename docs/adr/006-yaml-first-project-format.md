# ADR-006: YAML优先的项目格式

## 状态
已采纳

## 背景
传统DAW的项目文件是二进制格式（.rpp/.als/.ptx），不透明、不可diff、AI Agent无法直接读写。

## 决策
YAML作为主要项目格式，同时支持JSON和Binary互转。

## 理由
- AI Agent可直接读写YAML，无需API中转
- 人类可审查和手动编辑
- git友好（可diff、可merge）
- 调试方便（出问题直接看项目文件）

## 后果
- 大型项目文件可能较大，但换来可调试性和Agent友好性
- 需要严格的schema验证（opendaw-core的Project结构体）
- 格式互转工具：`opendaw convert project.yaml project.json`
