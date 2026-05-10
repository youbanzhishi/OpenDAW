//! JSFX运行时环境
//!
//! 管理JSFX虚拟机的状态：变量、内存、音频通道、参数等
//! 兼容Reaper JSFX运行时语义

/// 默认内存大小（JSFX标准为8192槽，可扩展）
const DEFAULT_MEMORY_SIZE: usize = 8192;
/// 最大内存扩展上限
const MAX_MEMORY_SIZE: usize = 1_048_576;
/// 最大通道数
const MAX_CHANNELS: usize = 64;
/// 最大slider数
const MAX_SLIDERS: usize = 256;

/// JSFX运行时环境
pub struct JsfxRuntime {
    /// 命名变量存储（变量名已转小写）
    pub vars: std::collections::HashMap<String, f64>,
    /// memory[]数组 — JSFX的共享内存空间
    pub memory: Vec<f64>,
    /// 音频通道 — spl0=0, spl1=1, spl(2)...spl(63)
    pub spl: [f64; MAX_CHANNELS],
    /// slider参数值 slider1=sliders[0], slider256=sliders[255]
    pub sliders: [f64; MAX_SLIDERS],
    /// 采样率
    pub srate: f64,
    /// 当前block大小
    pub samplesblock: usize,
    /// 当前采样在block中的位置
    pub sample_index: usize,
    /// tempo（BPM）
    pub tempo: f64,
    /// 播放位置（采样数）
    pub play_position: f64,
    /// 是否已初始化
    pub initialized: bool,
    /// 预处理器定义的常量（$pi等通过变量系统解析）
    /// 随机数种子
    rand_seed: u64,
    /// pdc延迟值（插件延迟补偿）
    pub pdc: usize,
}

impl JsfxRuntime {
    /// 创建新的运行时环境
    pub fn new() -> Self {
        let mut runtime = Self {
            vars: std::collections::HashMap::new(),
            memory: vec![0.0; DEFAULT_MEMORY_SIZE],
            spl: [0.0; MAX_CHANNELS],
            sliders: [0.0; MAX_SLIDERS],
            srate: 44100.0,
            samplesblock: 256,
            sample_index: 0,
            tempo: 120.0,
            play_position: 0.0,
            initialized: false,
            rand_seed: 12345,
            pdc: 0,
        };

        // 初始化内置变量
        runtime.vars.insert("srate".to_string(), 44100.0);
        runtime.vars.insert("samplesblock".to_string(), 256.0);
        runtime.vars.insert("tempo".to_string(), 120.0);
        runtime.vars.insert("play_position".to_string(), 0.0);
        runtime.vars.insert("beat_position".to_string(), 0.0);
        runtime.vars.insert("ts_num".to_string(), 4.0);
        runtime.vars.insert("ts_denom".to_string(), 4.0);

        // EEL2数学常量
        runtime.vars.insert("$pi".to_string(), std::f64::consts::PI);
        runtime.vars.insert("$e".to_string(), std::f64::consts::E);
        runtime.vars.insert("$phi".to_string(), 1.618033988749895); // 黄金比例

        runtime
    }

    /// 设置采样率并初始化
    pub fn init(&mut self, sample_rate: f64, buffer_size: usize) {
        self.srate = sample_rate;
        self.samplesblock = buffer_size;
        self.vars.insert("srate".to_string(), sample_rate);
        self.vars.insert("samplesblock".to_string(), buffer_size as f64);
        self.sample_index = 0;
        self.play_position = 0.0;
        self.initialized = true;
    }

    /// 获取变量值
    pub fn get_var(&self, name: &str) -> f64 {
        let name_lower = name.to_lowercase();

        // 特殊变量：spl0, spl1
        if name_lower == "spl0" { return self.spl[0]; }
        if name_lower == "spl1" { return self.spl[1]; }

        // slider变量
        if name_lower.starts_with("slider") && name_lower.len() > 6 {
            if let Ok(idx) = name_lower[6..].parse::<usize>() {
                if idx >= 1 && idx <= MAX_SLIDERS {
                    return self.sliders[idx - 1];
                }
            }
        }

        // 系统变量
        if name_lower == "srate" { return self.srate; }
        if name_lower == "samplesblock" { return self.samplesblock as f64; }
        if name_lower == "tempo" { return self.tempo; }
        if name_lower == "pdc" { return self.pdc as f64; }

        // $常量（$pi, $e, $phi）- 变量名中包含$前缀
        if name_lower.starts_with("$") {
            // 尝试从vars中查找
            if let Some(&v) = self.vars.get(&name_lower) {
                return v;
            }
            // 尝试标准常量
            match name_lower.as_str() {
                "$pi" => return std::f64::consts::PI,
                "$e" => return std::f64::consts::E,
                "$phi" => return 1.618033988749895,
                _ => return 0.0,
            }
        }

        // 通用变量
        self.vars.get(&name_lower).copied().unwrap_or(0.0)
    }

    /// 设置变量值
    pub fn set_var(&mut self, name: &str, value: f64) {
        let name_lower = name.to_lowercase();

        // 特殊变量：spl0, spl1
        if name_lower == "spl0" { self.spl[0] = value; return; }
        if name_lower == "spl1" { self.spl[1] = value; return; }

        // slider变量只读（不能在脚本中赋值slider）
        if name_lower.starts_with("slider") && name_lower.len() > 6 {
            if name_lower[6..].parse::<usize>().is_ok() {
                // slider是只读的，忽略赋值
                return;
            }
        }

        // 系统变量
        if name_lower == "srate" { self.srate = value; return; }
        if name_lower == "samplesblock" { self.samplesblock = value as usize; return; }
        if name_lower == "tempo" { self.tempo = value; return; }
        if name_lower == "pdc" { self.pdc = value as usize; return; }

        // $常量不可赋值
        if name_lower.starts_with("$") {
            return;
        }

        // 通用变量
        self.vars.insert(name_lower, value);
    }

    /// 获取spl通道值
    pub fn get_spl(&self, channel: usize) -> f64 {
        if channel < MAX_CHANNELS { self.spl[channel] } else { 0.0 }
    }

    /// 设置spl通道值
    pub fn set_spl(&mut self, channel: usize, value: f64) {
        if channel < MAX_CHANNELS { self.spl[channel] = value; }
    }

    /// 设置slider参数值
    pub fn set_slider(&mut self, index: usize, value: f64) {
        if index >= 1 && index <= MAX_SLIDERS {
            self.sliders[index - 1] = value;
        }
    }

    /// 获取slider参数值
    pub fn get_slider(&self, index: usize) -> f64 {
        if index >= 1 && index <= MAX_SLIDERS {
            self.sliders[index - 1]
        } else {
            0.0
        }
    }

    /// 获取内存值
    pub fn mem_get(&self, index: usize) -> f64 {
        if index < self.memory.len() {
            self.memory[index]
        } else {
            0.0
        }
    }

    /// 设置内存值
    pub fn mem_set(&mut self, index: usize, value: f64) {
        if index < self.memory.len() {
            self.memory[index] = value;
        } else if index < MAX_MEMORY_SIZE {
            // 自动扩展内存
            self.memory.resize(index + 1, 0.0);
            self.memory[index] = value;
        }
    }

    /// 分配内存（memory()函数）
    /// 返回分配的起始索引
    pub fn mem_alloc(&mut self, start: usize, size: usize) -> usize {
        let needed = start + size;
        if needed > self.memory.len() {
            if needed <= MAX_MEMORY_SIZE {
                self.memory.resize(needed, 0.0);
            }
        }
        start
    }

    /// 获取下一个随机数 [0,1)
    pub fn rand_next(&mut self) -> f64 {
        // xorshift64
        self.rand_seed ^= self.rand_seed << 13;
        self.rand_seed ^= self.rand_seed >> 7;
        self.rand_seed ^= self.rand_seed << 17;
        (self.rand_seed >> 33) as f64 / 2147483648.0
    }

    /// 设置随机数种子
    pub fn srand(&mut self, seed: f64) {
        self.rand_seed = if seed == 0.0 {
            // 用时间作为种子（简化）
            use std::time::SystemTime;
            let t = SystemTime::now()
                .duration_since(SystemTime::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos() as u64;
            t
        } else {
            seed.to_bits()
        };
    }

    /// 内存拷贝
    pub fn mem_cpy(&mut self, dest: usize, src: usize, len: usize) {
        if src + len <= self.memory.len() && dest + len <= self.memory.len() {
            let tmp: Vec<f64> = self.memory[src..src + len].to_vec();
            self.memory[dest..dest + len].copy_from_slice(&tmp);
        }
    }

    /// 重置采样位置（每个block开始时调用）
    pub fn reset_block(&mut self) {
        self.sample_index = 0;
    }
}

impl Default for JsfxRuntime {
    fn default() -> Self {
        Self::new()
    }
}
