//! JSFX运行时环境
//!
//! 管理JSFX虚拟机的状态：变量、内存、音频通道、参数等

/// JSFX运行时环境
pub struct JsfxRuntime {
    /// 命名变量存储（变量名已转小写）
    pub vars: std::collections::HashMap<String, f64>,
    /// memory[]数组 — JSFX的共享内存空间
    pub memory: Vec<f64>,
    /// 音频通道 — spl0=0, spl1=1, spl(2)...spl(63)
    pub spl: [f64; 64],
    /// slider参数值 slider1=sliders[0], slider256=sliders[255]
    pub sliders: [f64; 256],
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
}

impl JsfxRuntime {
    /// 创建新的运行时环境
    pub fn new() -> Self {
        let mut runtime = Self {
            vars: std::collections::HashMap::new(),
            memory: vec![0.0; 1048576], // 默认1M个f64槽位
            spl: [0.0; 64],
            sliders: [0.0; 256],
            srate: 44100.0,
            samplesblock: 256,
            sample_index: 0,
            tempo: 120.0,
            play_position: 0.0,
            initialized: false,
        };

        // 初始化内置变量
        runtime.vars.insert("srate".to_string(), 44100.0);
        runtime.vars.insert("samplesblock".to_string(), 256.0);
        runtime.vars.insert("tempo".to_string(), 120.0);
        runtime.vars.insert("play_position".to_string(), 0.0);
        runtime.vars.insert("beat_position".to_string(), 0.0);
        runtime.vars.insert("ts_num".to_string(), 4.0);
        runtime.vars.insert("ts_denom".to_string(), 4.0);

        runtime
    }

    /// 设置采样率并初始化
    pub fn init(&mut self, sample_rate: f64, buffer_size: usize) {
        self.srate = sample_rate;
        self.samplesblock = buffer_size;
        self.vars.insert("srate".to_string(), sample_rate);
        self.vars.insert("samplesblock".to_string(), buffer_size as f64);
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
                if idx >= 1 && idx <= 256 {
                    return self.sliders[idx - 1];
                }
            }
        }

        // srate, samplesblock等
        if name_lower == "srate" { return self.srate; }
        if name_lower == "samplesblock" { return self.samplesblock as f64; }
        if name_lower == "tempo" { return self.tempo; }

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

        // srate等系统变量
        if name_lower == "srate" { self.srate = value; return; }
        if name_lower == "samplesblock" { self.samplesblock = value as usize; return; }
        if name_lower == "tempo" { self.tempo = value; return; }

        // 通用变量
        self.vars.insert(name_lower, value);
    }

    /// 获取spl通道值
    pub fn get_spl(&self, channel: usize) -> f64 {
        if channel < 64 { self.spl[channel] } else { 0.0 }
    }

    /// 设置spl通道值
    pub fn set_spl(&mut self, channel: usize, value: f64) {
        if channel < 64 { self.spl[channel] = value; }
    }

    /// 设置slider参数值
    pub fn set_slider(&mut self, index: usize, value: f64) {
        if index >= 1 && index <= 256 {
            self.sliders[index - 1] = value;
        }
    }

    /// 获取slider参数值
    pub fn get_slider(&self, index: usize) -> f64 {
        if index >= 1 && index <= 256 {
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
        }
    }

    /// 分配内存（memory()函数）
    /// 返回分配的起始索引
    pub fn mem_alloc(&mut self, start: usize, size: usize) -> usize {
        // 确保内存足够大
        let needed = start + size;
        if needed > self.memory.len() {
            self.memory.resize(needed, 0.0);
        }
        start
    }
}

impl Default for JsfxRuntime {
    fn default() -> Self {
        Self::new()
    }
}
