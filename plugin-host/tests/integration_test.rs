//! Plugin Host 集成测试
//!
//! 测试多插件串行处理、信号链 bypass、参数管理、预设等端到端场景

use plugin_host::{
    PluginHost, PluginChain, ParamManager, PresetManager, PluginLoader,
    VcPlugin, PluginType, AudioBuffer, ParamInfo, PluginError,
    PluginParameter, ParameterValue, ParameterType,
    PluginFormat, ScannedPlugin,
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

/// 带开关的增益插件（测试bool参数推断）
struct BypassableGainPlugin {
    gain: f64,
    bypass: bool,
}

impl BypassableGainPlugin {
    fn new(gain: f64) -> Self {
        Self { gain, bypass: false }
    }
}

impl VcPlugin for BypassableGainPlugin {
    fn plugin_id(&self) -> &str { "bypass-gain" }
    fn plugin_name(&self) -> &str { "Bypassable Gain" }
    fn plugin_type(&self) -> PluginType { PluginType::Effect }
    fn version(&self) -> &str { "1.0.0" }
    fn init(&mut self, _sr: f64, _bs: usize) -> Result<(), PluginError> { Ok(()) }
    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        if self.bypass {
            output.copy_from(input);
        } else {
            for (i, &s) in input.data.iter().enumerate() {
                if i < output.data.len() {
                    output.data[i] = s * self.gain;
                }
            }
        }
    }
    fn get_params(&self) -> Vec<ParamInfo> {
        vec![
            ParamInfo::new("gain", "Gain", 0.0, 10.0, self.gain, "x"),
            ParamInfo::with_step("bypass", "Bypass", 0.0, 1.0, 0.0, 1.0, ""),
        ]
    }
    fn set_param(&mut self, id: &str, value: f64) -> Result<(), PluginError> {
        match id {
            "gain" => { self.gain = value.clamp(0.0, 10.0); Ok(()) }
            "bypass" => { self.bypass = value >= 0.5; Ok(()) }
            _ => Err(PluginError::ParamNotFound(id.to_string()))
        }
    }
    fn get_param(&self, id: &str) -> Option<f64> {
        match id {
            "gain" => Some(self.gain),
            "bypass" => Some(if self.bypass { 1.0 } else { 0.0 }),
            _ => None,
        }
    }
    fn destroy(&mut self) {}
}

/// 延迟插件（简化版）：对输出添加一个采样的延迟
struct DelayPlugin {
    initialized: bool,
    prev: (f64, f64), // (L, R) 上一帧
}

impl DelayPlugin {
    #[allow(dead_code)]
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

// ── 基础集成测试 ──────────────────────────────────────────────────────

#[test]
fn test_host_load_and_chain() {
    let mut host = PluginHost::new(44100.0, 256, 2);

    let id1 = host.load_plugin(Box::new(GainPlugin::new(2.0))).unwrap();
    let id2 = host.load_plugin(Box::new(GainPlugin::new(0.5))).unwrap();

    assert_eq!(id1, "gain");
    assert_eq!(id2, "gain"); // 同ID会覆盖

    host.add_to_chain("gain").unwrap();
    assert_eq!(host.chain_length(), 1);
}

#[test]
fn test_host_process_chain() {
    let mut host = PluginHost::new(44100.0, 256, 2);

    host.load_plugin(Box::new(GainPlugin::new(3.0))).unwrap();
    host.add_to_chain("gain").unwrap();

    let mut input = AudioBuffer::new(2, 64);
    input.data[0] = 1.0;
    input.data[64] = 0.5;

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

    chain.push(Box::new(GainPlugin::new(2.0)));
    chain.push(Box::new(MutePlugin));
    chain.push(Box::new(GainPlugin::new(3.0)));

    let mut input = AudioBuffer::new(2, 64);
    input.data[0] = 1.0;
    let mut output = AudioBuffer::new(2, 64);

    chain.process(&input, &mut output);
    assert!(output.data.iter().all(|&v| v.abs() < 1e-10));
}

#[test]
fn test_chain_bypass_mute() {
    let mut chain = PluginChain::new(2, 64);

    chain.push(Box::new(GainPlugin::new(2.0)));
    chain.push(Box::new(MutePlugin));
    chain.push(Box::new(GainPlugin::new(3.0)));

    chain.set_enabled(1, false).unwrap();

    let mut input = AudioBuffer::new(2, 64);
    input.data[0] = 1.0;
    let mut output = AudioBuffer::new(2, 64);

    chain.process(&input, &mut output);
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

    pm.add_automation_point("test-plugin", "gain", 0.0, 0.0);
    pm.add_automation_point("test-plugin", "gain", 1.0, 10.0);
    pm.add_automation_point("test-plugin", "gain", 2.0, 5.0);

    assert!((pm.get_automation_value("test-plugin", "gain", 0.5).unwrap() - 5.0).abs() < 0.01);
    assert!((pm.get_automation_value("test-plugin", "gain", 1.5).unwrap() - 7.5).abs() < 0.01);
    assert!((pm.get_automation_value("test-plugin", "gain", 2.0).unwrap() - 5.0).abs() < 0.01);
}

#[test]
fn test_preset_manager_roundtrip() {
    let mut pm = PresetManager::new();

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

    for i in 0..8 {
        buf.data[i] = (i + 1) as f64;
        buf.data[8 + i] = (i + 1) as f64 * 10.0;
    }

    let ch0 = buf.channel_slice(0);
    assert_eq!(ch0, &[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]);

    let ch1 = buf.channel_slice(1);
    assert_eq!(ch1, &[10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]);

    buf.channel_slice_mut(0)[0] = 99.0;
    assert_eq!(buf.sample(0, 0), 99.0);

    let mut buf2 = AudioBuffer::new(2, 4);
    buf2.copy_from(&buf);
    assert_eq!(buf2.channels, 2);
    assert_eq!(buf2.frames, 8);
    assert_eq!(buf2.data[0], 99.0);
}

#[test]
fn test_audio_buffer_interleaved_roundtrip() {
    let mut buf = AudioBuffer::new(2, 3);
    buf.data = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0];

    let interleaved = buf.to_interleaved();
    assert_eq!(interleaved, vec![1.0, 4.0, 2.0, 5.0, 3.0, 6.0]);

    let roundtrip = AudioBuffer::from_interleaved(&interleaved, 2);
    assert_eq!(roundtrip.data, buf.data);
}

// ── Phase 23: PluginParameter 统一参数模型测试 ──────────────────────────

#[test]
fn test_enhanced_params_loaded() {
    let mut host = PluginHost::new(44100.0, 256, 2);
    host.load_plugin(Box::new(GainPlugin::new(1.5))).unwrap();

    // 应该推断出增强参数
    let params = host.get_plugin_params("gain").unwrap();
    assert_eq!(params.len(), 1);
    assert_eq!(params[0].id, "gain");
    assert_eq!(params[0].name, "Gain");
    // gain参数是连续的 [0,10] → 应推断为Float
    assert_eq!(params[0].param_type, ParameterType::Float);
}

#[test]
fn test_bool_param_inference() {
    let mut host = PluginHost::new(44100.0, 256, 2);
    host.load_plugin(Box::new(BypassableGainPlugin::new(1.0))).unwrap();

    let params = host.get_plugin_params("bypass-gain").unwrap();
    assert_eq!(params.len(), 2);

    // 第一个参数 gain 是连续 float
    assert_eq!(params[0].id, "gain");
    assert_eq!(params[0].param_type, ParameterType::Float);

    // 第二个参数 bypass: step=1, min=0, max=1 → 应推断为Bool
    assert_eq!(params[1].id, "bypass");
    assert_eq!(params[1].param_type, ParameterType::Bool);
}

#[test]
fn test_set_enhanced_param() {
    let mut host = PluginHost::new(44100.0, 256, 2);
    host.load_plugin(Box::new(GainPlugin::new(1.0))).unwrap();

    // 使用增强参数接口设置
    host.set_enhanced_param("gain", "gain", &ParameterValue::Float(3.5)).unwrap();

    // 传统接口也应该反映变更
    assert!((host.get_plugin_param("gain", "gain").unwrap() - 3.5).abs() < 1e-10);

    // 增强参数也应该更新
    let params = host.get_plugin_params("gain").unwrap();
    assert!((params[0].as_f64() - 3.5).abs() < 1e-10);
}

#[test]
fn test_normalized_param_roundtrip() {
    let mut host = PluginHost::new(44100.0, 256, 2);
    host.load_plugin(Box::new(GainPlugin::new(1.0))).unwrap();

    // gain range [0, 10], default 1.0 → normalized = 0.1
    let norm = host.get_param_normalized("gain", "gain").unwrap();
    assert!((norm - 0.1).abs() < 1e-10);

    // 设置归一化值
    host.set_param_normalized("gain", "gain", 0.5).unwrap();
    assert!((host.get_plugin_param("gain", "gain").unwrap() - 5.0).abs() < 1e-10);

    host.set_param_normalized("gain", "gain", 0.0).unwrap();
    assert!((host.get_plugin_param("gain", "gain").unwrap() - 0.0).abs() < 1e-10);

    host.set_param_normalized("gain", "gain", 1.0).unwrap();
    assert!((host.get_plugin_param("gain", "gain").unwrap() - 10.0).abs() < 1e-10);
}

#[test]
fn test_list_all_params() {
    let mut host = PluginHost::new(44100.0, 256, 2);
    host.load_plugin(Box::new(GainPlugin::new(1.0))).unwrap();
    host.load_plugin(Box::new(MutePlugin)).unwrap();

    let all = host.list_all_params();
    // GainPlugin has 1 param, MutePlugin has 0
    assert_eq!(all.len(), 1);
    assert_eq!(all[0].1, "gain");
    assert_eq!(all[0].2, ParameterType::Float);
}

// ── Phase 23: PluginLoader 工厂模式测试 ──────────────────────────────────

#[test]
fn test_loader_new() {
    let loader = PluginLoader::new();
    // 默认有 /tmp/AudioFX 搜索目录
}

#[test]
fn test_loader_detect_format_nonexistent() {
    let result = PluginLoader::detect_format(std::path::Path::new("/nonexistent/path.vst3"));
    assert!(result.is_err());
}

#[test]
fn test_loader_supported_formats() {
    let formats = PluginLoader::supported_formats();
    assert!(formats.contains(&PluginFormat::Vst3));
    assert!(formats.contains(&PluginFormat::Clap));
    assert!(formats.contains(&PluginFormat::VcCli));
    assert!(formats.contains(&PluginFormat::Jsfx));
    assert!(formats.contains(&PluginFormat::Lv2));
}

#[test]
fn test_loader_load_nonexistent() {
    let loader = PluginLoader::new();
    let result = loader.load_from_path(std::path::Path::new("/nonexistent.vst3"));
    assert!(result.is_err());
}

#[test]
fn test_loader_load_vc_by_id_nonexistent() {
    let loader = PluginLoader::new();
    let result = loader.load_vc_by_id("vc-nonexistent-xyz");
    assert!(result.is_err());
}

#[test]
fn test_loader_lv2_unsupported() {
    let loader = PluginLoader::new();
    let result = loader.load_with_format(
        std::path::Path::new("/tmp/test.lv2"),
        &PluginFormat::Lv2,
    );
    assert!(result.is_err());
}

#[test]
fn test_host_load_from_path_nonexistent() {
    let mut host = PluginHost::new(44100.0, 256, 2);
    let result = host.load_plugin_from_path(std::path::Path::new("/nonexistent.vst3"));
    assert!(result.is_err());
}

#[test]
fn test_host_load_from_scanned() {
    let mut host = PluginHost::new(44100.0, 256, 2);
    let scanned = ScannedPlugin::new(
        "test-lv2",
        "Test LV2",
        PluginFormat::Lv2,
        std::path::PathBuf::from("/tmp/test.lv2"),
    );
    let result = host.load_plugin_from_scanned(&scanned);
    assert!(result.is_err()); // LV2 not supported yet
}

// ── Phase 23: PluginParameter 独立功能测试 ──────────────────────────────

#[test]
fn test_plugin_parameter_float() {
    let mut p = PluginParameter::float("gain", "增益", -60.0, 60.0, 0.0, "dB");
    assert_eq!(p.id, "gain");
    assert_eq!(p.param_type, ParameterType::Float);
    assert!((p.as_f64() - 0.0).abs() < 1e-10);

    p.set_from_f64(6.0);
    assert!((p.as_f64() - 6.0).abs() < 1e-10);

    p.set_from_f64(100.0); // 超出范围 → clamp
    assert!((p.as_f64() - 60.0).abs() < 1e-10);

    p.reset();
    assert!((p.as_f64() - 0.0).abs() < 1e-10);
}

#[test]
fn test_plugin_parameter_int() {
    let mut p = PluginParameter::int("voices", "声部数", 1, 64, 8, "");
    assert_eq!(p.param_type, ParameterType::Int);
    assert_eq!(p.value.as_int(), Some(8));

    p.set_from_f64(16.0);
    assert_eq!(p.value.as_int(), Some(16));
}

#[test]
fn test_plugin_parameter_bool() {
    let mut p = PluginParameter::bool_param("bypass", "旁路", false);
    assert_eq!(p.param_type, ParameterType::Bool);
    assert_eq!(p.value.as_bool(), Some(false));

    p.set_from_f64(1.0);
    assert_eq!(p.value.as_bool(), Some(true));

    p.set_from_f64(0.3);
    assert_eq!(p.value.as_bool(), Some(false));
}

#[test]
fn test_plugin_parameter_enum() {
    let mut p = PluginParameter::enum_param("filter", "滤波器", &["LPF", "HPF", "BPF", "Notch"], 0);
    assert_eq!(p.param_type, ParameterType::Enum);
    assert_eq!(p.value.as_enum(), Some(0));
    assert_eq!(p.current_enum_label(), Some("LPF"));

    p.set_from_f64(2.0);
    assert_eq!(p.value.as_enum(), Some(2));
    assert_eq!(p.current_enum_label(), Some("BPF"));
}

#[test]
fn test_plugin_parameter_normalized() {
    let mut p = PluginParameter::float("gain", "增益", -60.0, 60.0, 0.0, "dB");
    // 0.0 is midpoint → normalized = 0.5
    assert!((p.normalized() - 0.5).abs() < 1e-10);

    p.set_normalized(0.25);
    let expected = -60.0 + 0.25 * 120.0; // = -30.0
    assert!((p.as_f64() - expected).abs() < 1e-10);
}

#[test]
fn test_plugin_parameter_display() {
    let p1 = PluginParameter::float("gain", "增益", 0.0, 10.0, 5.5, "dB");
    assert!(p1.display_value().contains("5.50"));

    let p2 = PluginParameter::bool_param("on", "开关", true);
    assert_eq!(p2.display_value(), "On");

    let p3 = PluginParameter::int("count", "数量", 1, 10, 3, "个");
    assert!(p3.display_value().contains("3"));
}

#[test]
fn test_plugin_parameter_param_info_roundtrip() {
    let original = ParamInfo::new("gain", "增益", -60.0, 60.0, 0.0, "dB");
    let param = PluginParameter::from_param_info(&original);
    let back = param.to_param_info();

    assert_eq!(back.id, original.id);
    assert_eq!(back.min, original.min);
    assert_eq!(back.max, original.max);
}

#[test]
fn test_parameter_value_conversions() {
    // Float → f64
    let v = ParameterValue::Float(3.14);
    assert!((v.to_f64() - 3.14).abs() < 1e-10);
    assert_eq!(v.as_float(), Some(3.14));
    assert_eq!(v.as_int(), None);

    // Int → f64
    let v = ParameterValue::Int(42);
    assert!((v.to_f64() - 42.0).abs() < 1e-10);
    assert_eq!(v.as_int(), Some(42));

    // Bool → f64
    let v = ParameterValue::Bool(true);
    assert!((v.to_f64() - 1.0).abs() < 1e-10);
    assert_eq!(v.as_bool(), Some(true));

    // Enum → f64
    let v = ParameterValue::Enum(2);
    assert!((v.to_f64() - 2.0).abs() < 1e-10);
    assert_eq!(v.as_enum(), Some(2));

    // from_f64 with type
    let v = ParameterValue::from_f64(3.7, &ParameterType::Int);
    assert_eq!(v.as_int(), Some(4)); // rounds

    let v = ParameterValue::from_f64(0.8, &ParameterType::Bool);
    assert_eq!(v.as_bool(), Some(true));
}
