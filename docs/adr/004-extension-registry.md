# ADR-004: Extension Registry四柱架构

## 状态
已采纳

## 背景
DAW需要无限扩展性——新效果器、新乐器、新AI功能、新协议支持不断出现。如果每次加功能都要改核心架构，代码会越来越脆弱。

## 决策
Extension Registry四柱架构，新功能=注册扩展，架构本身永远不需要改：
1. **Plugin API** — 效果器和乐器通过统一接口注册
2. **Script Runtime** — JSFX/EEL2脚本运行时，兼容Reaper生态
3. **Model Bus** — AI模型推理总线，插件可调用AI能力
4. **Hook System** — 生命周期钩子，插件可拦截任何阶段

## 理由
- 参考VSCode Extension和Reaper JSFX的成功模式
- 核心层零业务逻辑铁律：不管什么功能，核心只做抽象调度
- 扩展之间解耦，一个扩展崩溃不影响其他

## 后果
- 所有新功能必须走Extension路径
- JSFX兼容成为杀手级差异化（ADR-005）
- 核心层代码量可控，不会随功能增长膨胀
