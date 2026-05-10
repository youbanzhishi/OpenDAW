# Changelog

## [0.25.0] - 2025-05-10

### Added
- **JSFX文件加载器 (loader.rs)** - 新增专门的加载模块
  - `load_jsfx_file()` - 从文件加载JSFX
  - `load_jsfx_source()` - 从源码字符串加载
  - `scan_jsfx_directory()` - 扫描目录中的JSFX文件
  - `JsfxMeta` - JSFX元信息快速扫描结构
- **示例JSFX插件 (examples/)** - 新增3个示例
  - `gain.jsfx` - 简单增益效果器
  - `lowpass.jsfx` - 二阶低通滤波器
  - `distortion.jsfx` - 软clip失真效果
- **端到端集成测试** - 新增7个测试用例
  - gain.jsfx E2E测试
  - @init块测试
  - slider动态更新测试
  - 立体声处理测试
  - 参数接口测试
  - loader模块测试
  - 元信息解析测试

### Changed
- `lib.rs` - 导出loader模块和公共函数
- `plugin-host/Cargo.toml` - 新增jsfx_e2e示例

### Fixed
- `loader.rs` - 添加VcPlugin trait导入

## [0.24.0] - 2025-05-10

### Added
- JSFX解释器核心实现
- EEL2 parser + VM
- JsfxPlugin适配VcPlugin trait
- 内置60+数学函数
