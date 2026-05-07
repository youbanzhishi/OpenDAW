# VCMix 示例项目

本目录包含 VCMix 的 YAML 示例配置文件，展示不同复杂度的混音项目。

## 文件说明

| 文件 | 说明 | 轨道数 | 效果器数 |
|------|------|--------|----------|
| `test-simple.yaml` | 最简测试：1轨+1效果器 | 1 | 1 |
| `jiuwanzi.yaml` | 标准贴唱：人声全链路+伴奏直通 | 2 | 8 |
| `jiuwanzi-full.yaml` | 完整混音：含Master处理链 | 2 | 10 |

## 使用方法

```bash
# 验证配置
vcmix validate examples/jiuwanzi.yaml

# 查看信号路由图
vcmix graph examples/jiuwanzi.yaml

# 渲染混音
vcmix render examples/jiuwanzi.yaml

# 带分析报告渲染
vcmix render examples/jiuwanzi.yaml --report

# JSON格式输出
vcmix render examples/jiuwanzi.yaml --stream json
```

## YAML 结构说明

```yaml
name: "项目名称"       # 项目名
bpm: 62                # BPM（影响音符时值换算）
sample_rate: 44100     # 采样率

tracks:                 # 轨道列表
  - name: vocal        # 轨道名
    file: vocal.wav    # 音频文件路径
    volume: 1.0        # 轨道音量（线性）
    effects:           # 插入效果链（顺序执行）
      - name: vc-eq    # 插件名
        params:        # 插件参数
          low_cut: 80

master:                 # 母线配置
  levels:              # 各轨电平
    vocal: 0.8
    accomp: 0.35
  effects: []          # 母线效果链
  output: output.wav   # 输出文件
```

## BPM 音符时值

效果器参数支持音符时值自动换算为毫秒：

| 写法 | 含义 | @BPM62 | @BPM120 |
|------|------|--------|---------|
| `"1/4"` | 四分音符 | 967.7ms | 500.0ms |
| `"1/8"` | 八分音符 | 483.9ms | 250.0ms |
| `"1/8d"` | 附点八分 | 725.8ms | 375.0ms |
| `"1/8t"` | 八分三连音 | 322.6ms | 166.7ms |
| `"1/16"` | 十六分 | 241.9ms | 125.0ms |

公式：`delay_ms = 60000 / BPM × (4/denominator) × modifier`
