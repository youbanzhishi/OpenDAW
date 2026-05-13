# ADR-005: JSFX兼容作为杀手级差异化

## 状态
已采纳

## 背景
Reaper生态有大量JSFX自定义效果器脚本，其他DAW无法运行这些脚本。这是Reaper用户的强依赖。

## 决策
实现EEL2虚拟机，让OpenDAW能原生运行JSFX脚本。

## 理由
- 兼容JSFX=直接继承Reaper生态，其他DAW做不到
- 这是Reaper用户迁移到OpenDAW的核心动力
- JSFX脚本社区活跃，大量高质量免费效果器
- 实现EEL2 VM是技术可行的（jsfx-engine 5073行，37个测试全绿）

## 后果
- 正面：独特的生态兼容性，Reaper用户零迁移成本
- 负面：EEL2是动态类型，与Rust的类型安全有张力
- 维护成本：EEL2规范需要持续跟进Reaper的更新
- 测试策略：需要持续收集JSFX脚本做兼容性测试
