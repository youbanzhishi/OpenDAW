//! Plugin Host 集成测试
//!
//! 测试多插件串行处理、信号链 bypass、参数管理、预设等端到端场景

use plugin_host::{
    PluginHost, PluginChain, ParamManager, PresetManager,
    VcPlugin, PluginType, AudioBuffer, ParamInfo, PluginError,
};

// ── 测试用插件 ─────────────────────────────────────────────────────────

/// 增益插件：将所有采样乘以固定增益值
struct GainPlugin {
    gain: f64,
    initialized: bool,
}

impl GainPlugin {
    fn new(gain: f64) -> Self {
        Self { gain, initialized: false }
    }
}

impl VcPlugin for GainPlugin {
    fn plugin_id(&self) -> &str { "gain" }
    fn plugin_name(&self) -> &str { "Gain" }
    fn plugin_type(&self) -> PluginType { PluginType::Effect }
    fn version(&self) -> &str { "1.0.0" }
    fn init(&mut self, _sr: f64, _bs: usize) -> Result<(), PluginError> {
        self.initialized = true;
        Ok(())
    }
    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        for (i, &s) in input.data.iter().enumerate() {
            if i < output.data.len() {
                output.data[i] = s * self.gain;
            }
        }
    }
    fn get_params(&self) -> Vec<ParamInfo> {
        vec![ParamInfo::new("gain", "Gain", 0.0, 10.0, self.gain, "x")]
    }
    fn set_param(&mut self, id: &str, value: f64) -> Result<(), PluginError> {
        if id == "gain" {
            self.gain = value.clamp(0.0, 10.0);
            Ok(())
        } else {
            Err(PluginError::ParamNotFound(id.to_string()))
        }
    }
    fn get_param(&self, id: &str) -> Option<f64> {
        if id == "gain" { Some(self.gain) } else { None }
    }
    fn destroy(&mut self) {
        self.initialized = false;
    }
}

/// 延迟插件（简化版）：对输出添加一个采样的延迟
struct DelayPlugin {
    initialized: bool,
    prev: (f64, f64), // (L, R) 上一帧
}

impl DelayPlugin {
    fn new() -> Self {
        Self { initialized: false, prev: (0.0, 0.0) }
    }
}

impl VcPlugin for DelayPlugin {
    fn plugin_id(&self) -> &str { "delay" }
    fn plugin_name(&self) -> &str { "Delay" }
    fn plugin_type(&self) -> PluginType { PluginType::Effect }
    fn version(&self) -> &str { "1.0.0" }
    fn init(&mut self, _sr: f64, _bs: usize) -> Result<(), PluginError> {
        self.initialized = true;
        Ok(())
    }
    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        // 简化延迟：第一帧输出上次的prev，后续帧直接传
        output.copy_from(input);
        if input.channels >= 2 && input.frames >= 1 {
            let old_prev = self.prev;
            output.set_sample(0, 0, old_prev.0);
            output.set_sample(1, 0, old_prev.1);
            self.prev = (input.sample(0, input.frames - 1), input.sample(1, input.frames - 1));
        }
    }
    fn get_params(&self) -> Vec<ParamInfo> { vec![] }
    fn set_param(&mut self, _id: &str, _v: f64) -> Result<(), PluginError> { Ok(()) }
    fn get_param(&self, _id: &str) -> Option<f64> { None }
    fn destroy(&mut self) { self.initialized = false; }
}

/// 静音插件：将所有输出设为0
struct MutePlugin;

impl VcPlugin for MutePlugin {
    fn plugin_id(&self) -> &str { "mute" }
    fn plugin_name(&self) -> &str { "Mute" }
    fn plugin_type(&self) -> PluginType { PluginType::Effect }
    fn version(&self) -> &str { "1.0.0" }
    fn init(&mut self, _sr: f64, _bs: usize) -> Result<(), PluginError> { Ok(()) }
    fn process(&mut self, _input: &AudioBuffer, output: &mut AudioBuffer) {
        output.clear();
    }
    fn get_params(&self) -> Vec<ParamInfo> { vec![] }
    fn set_param(&mut self, _id: &str, _v: f64) -> Result<(), PluginError> { Ok(()) }
    fn get_param(&self, _id: &str) -> Option<f64> { None }
    fn destroy(&mut self) {}
}

// ── 集成测试 ──────────────────────────────────────────────────────────

#[test]
fn test_host_load_and_chain() {
    let mut host = PluginHost::new(44100.0, 256, 2);

    // 加载两个增益插件
    let id1 = host.load_plugin(Box::new(GainPlugin::new(2.0))).unwrap();
    let id2 = host.load_plugin(Box::new(GainPlugin::new(0.5))).unwrap();

    assert_eq!(id1, "gain");
    assert_eq!(id2, "gain"); // 同ID会覆盖

    // 添加到链
    host.add_to_chain("gain").unwrap();
    assert_eq!(host.chain_length(), 1);
}

#[test]
fn test_host_process_chain() {
    let mut host = PluginHost::new(44100.0, 256, 2);

    // 加载增益为3x的插件
    host.load_plugin(Box::new(GainPlugin::new(3.0))).unwrap();
    host.add_to_chain("gain").unwrap();

    let mut input = AudioBuffer::new(2, 64);
    input.data[0] = 1.0;  // ch0, frame0
    input.data[64] = 0.5; // ch1, frame0

    let mut output = AudioBuffer::new(2, 64);
    host.process(&input, &mut output);

    assert!((output.data[0] - 3.0).abs() < 1e-10);
    assert!((output.data[64] - 1.5).abs() < 1e-10);
}

#[test]
fn test_host_unload_plugin() {
    let mut host = PluginHost::new(44100.0, 256, 2);
    host.load_plugin(Box::new(GainPlugin::new(1.0))).unwrap();
    assert_eq!(host.plugin_count(), 1);

    host.unload_plugin("gain").unwrap();
    assert_eq!(host.plugin_count(), 0);
}

#[test]
fn test_chain_serial_processing() {
    let mut chain = PluginChain::new(2, 64);

    // 增益2x → 静音 → 增益3x
    // 结果应该被静音，因为静音在中间
    chain.push(Box::new(GainPlugin::new(2.0)));
    chain.push(Box::new(MutePlugin));
    chain.push(Box::new(GainPlugin::new(3.0)));

    let mut input = AudioBuffer::new(2, 64);
    input.data[0] = 1.0;
    let mut output = AudioBuffer::new(2, 64);

    chain.process(&input, &mut output);

    // 静音插件将所有数据归零，后续的3x增益也不会改变0
    assert!(output.data.iter().all(|&v| v.abs() < 1e-10));
}

#[test]
fn test_chain_bypass_mute() {
    let mut chain = PluginChain::new(2, 64);

    // 增益2x → 静音(将bypass) → 增益3x
    chain.push(Box::new(GainPlugin::new(2.0)));
    chain.push(Box::new(MutePlugin));
    chain.push(Box::new(GainPlugin::new(3.0)));

    // Bypass 静音插件
    chain.set_enabled(1, false).unwrap();

    let mut input = AudioBuffer::new(2, 64);
    input.data[0] = 1.0;
    let mut output = AudioBuffer::new(2, 64);

    chain.process(&input, &mut output);

    // 1.0 * 2.0 * 3.0 = 6.0 (静音被bypass)
    assert!((output.data[0] - 6.0).abs() < 1e-10);
}

#[test]
fn test_chain_all_bypass() {
    let mut chain = PluginChain::new(2, 64);
    chain.push(Box::new(GainPlugin::new(100.0)));
    chain.push(Box::new(MutePlugin));

    chain.set_enabled(0, false).unwrap();
    chain.set_enabled(1, false).unwrap();

    let mut input = AudioBuffer::new(2, 64);
    input.data[0] = 0.75;
    let mut output = AudioBuffer::new(2, 64);

    chain.process(&input, &mut output);
    assert!((output.data[0] - 0.75).abs() < 1e-10);
}

#[test]
fn test_param_manager_automation() {
    let mut pm = ParamManager::new();
    let param = ParamInfo::new("gain", "Gain", 0.0, 10.0, 1.0, "x");
    pm.register_plugin_params("test-plugin", vec![param]);

    // 添加自动化点
    pm.add_automation_point("test-plugin", "gain", 0.0, 0.0);
    pm.add_automation_point("test-plugin", "gain", 1.0, 10.0);
    pm.add_automation_point("test-plugin", "gain", 2.0, 5.0);

    // 线性插值验证
    assert!((pm.get_automation_value("test-plugin", "gain", 0.5).unwrap() - 5.0).abs() < 0.01);
    assert!((pm.get_automation_value("test-plugin", "gain", 1.5).unwrap() - 7.5).abs() < 0.01);
    assert!((pm.get_automation_value("test-plugin", "gain", 2.0).unwrap() - 5.0).abs() < 0.01);
}

#[test]
fn test_preset_manager_roundtrip() {
    let mut pm = PresetManager::new();

    // Create a Preset and test save/load
    use opendaw_extension as _;
    let mut p = plugin_host::preset::Preset::new("warm", "vc-eq");
    p.set_param("low_shelf", 3.0);
    p.set_param("high_shelf", -2.0);
    p.add_tag("vocal");
    p.add_tag("warm");

    pm.save(p);

    let loaded = pm.load("vc-eq", "warm").unwrap();
    assert_eq!(loaded.get_param("low_shelf"), Some(3.0));
    assert_eq!(loaded.get_param("high_shelf"), Some(-2.0));
    assert!(loaded.tags.contains(&"vocal".to_string()));
    assert!(loaded.tags.contains(&"warm".to_string()));

    // Export/Import roundtrip
    let json = pm.export_json("vc-eq", "warm").unwrap();
    let mut pm2 = PresetManager::new();
    pm2.import_json(&json).unwrap();
    let loaded2 = pm2.load("vc-eq", "warm").unwrap();
    assert_eq!(loaded2.get_param("low_shelf"), Some(3.0));
}

#[test]
fn test_plugin_info() {
    let plugin = GainPlugin::new(2.0);
    let info = plugin.get_info();

    assert_eq!(info.id, "gain");
    assert_eq!(info.name, "Gain");
    assert_eq!(info.plugin_type, PluginType::Effect);
    assert_eq!(info.version, "1.0.0");
    assert_eq!(info.parameters.len(), 1);
    assert_eq!(info.parameters[0].id, "gain");
}

#[test]
fn test_audio_buffer_zero_copy_methods() {
    let mut buf = AudioBuffer::new(2, 8);

    // 填充数据：channel 0 = [1,2,3,4,5,6,7,8], channel 1 = [10,20,30,40,50,60,70,80]
    for i in 0..8 {
        buf.data[i] = (i + 1) as f64;
        buf.data[8 + i] = (i + 1) as f64 * 10.0;
    }

    // 零拷贝切片读取
    let ch0 = buf.channel_slice(0);
    assert_eq!(ch0, &[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]);

    let ch1 = buf.channel_slice(1);
    assert_eq!(ch1, &[10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]);

    // 零拷贝切片写入
    buf.channel_slice_mut(0)[0] = 99.0;
    assert_eq!(buf.sample(0, 0), 99.0);

    // copy_from 测试
    let mut buf2 = AudioBuffer::new(2, 4);
    buf2.copy_from(&buf);
    assert_eq!(buf2.channels, 2);
    assert_eq!(buf2.frames, 8);
    assert_eq!(buf2.data[0], 99.0);
}

#[test]
fn test_audio_buffer_interleaved_roundtrip() {
    let mut buf = AudioBuffer::new(2, 3);
    buf.data = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0]; // ch0=[1,2,3] ch1=[4,5,6]

    let interleaved = buf.to_interleaved();
    assert_eq!(interleaved, vec![1.0, 4.0, 2.0, 5.0, 3.0, 6.0]);

    let roundtrip = AudioBuffer::from_interleaved(&interleaved, 2);
    assert_eq!(roundtrip.data, buf.data);
}
