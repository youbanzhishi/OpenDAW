# VC-EQ Gen2 升级设计文档

## 当前状态 (Gen1)
- 5段参量均衡器
- 滤波器类型：Low Shelf / Peak / High Shelf / Low Pass / High Pass
- IIR Biquad实现
- ⚠️ 已知Bug：IIR系数计算在某些极端Q值下不稳定

## Gen2 升级目标

### P1: 动态EQ升级
每个频段可绑定动态检测：
- 检测源：自身频段 / 侧链输入 / 全频段能量
- 检测→增益调制：频段增益随信号动态变化
- 应用场景：人声De-Essing(高频动态)、低频控制(踢鼓侧链)

### P2: 频谱分析器
- 实时FFT频谱显示（给Web UI用）
- 1/3倍频程平滑
- 峰值+RMS双模式
- DataStream输出频谱数据

### P3: 匹配EQ
- 参考轨道频谱分析
- 自动生成EQ曲线匹配参考
- 与reference_matcher.py联动

## 技术架构

### 动态EQ核心
```
struct DynamicBand {
    // 基础EQ参数（继承Gen1）
    float freq, gain, q;
    FilterType type;
    
    // 动态参数（Gen2新增）
    bool dynamic;           // 启用动态模式
    float threshold;        // 检测阈值 dB
    float range;            // 动态范围 dB（正=向上扩展，负=向下压缩）
    float attack, release;  // 包络时间 ms
    int detectSource;       // 0=self, 1=sidechain, 2=fullband
    float knee;             // 软拐点 dB
};
```

### 信号流
```
Input → [Band1 Static/Dynamic] → [Band2] → ... → [Band5] → Output
              ↑ sidechain (optional)
              │
         [EnvelopeFollower] → gain modulation
```

### 频谱分析器
```python
# DataStream事件
class SpectrumEvent:
    frequencies: List[float]  # 1/3 octave centers
    magnitudes_db: List[float]  # dB values
    peak: List[float]
    rms: List[float]
```

## 参数兼容性
- Gen1参数100%兼容，新增参数有默认值不改变行为
- `--dynamic` 启用动态EQ模式
- `--band-dynamic 1,0,0,1,0` 按频段启用
- `--band-threshold -20,-30,-30,-15,-30` 按频段阈值

## 升级优先级
1. **P0**: 修复IIR系数Bug → 稳定性基础
2. **P1**: 动态EQ → 最实用功能
3. **P2**: 频谱分析器 → Web UI可视化
4. **P3**: 匹配EQ → AI混音闭环
