//! 示例：用 Plugin API 写一个简单的 Gain 插件
//!
//! 演示：
//! 1. 实现 VcPlugin trait
//! 2. 创建 ExtensionRegistry 注册插件
//! 3. 初始化、处理音频、调整参数
//! 4. 触发钩子事件

use opendaw_extension::{
    AudioBuffer, ExtensionRegistry, HookContext, ModelInput, ParamInfo, PluginType,
    ScriptValue, SimpleScriptEngine, VcPlugin, LocalBackend, ModelBackend,
};
use std::path::Path;

// ===== Gain 插件实现 =====

/// 增益插件 — 调整音频音量
struct GainPlugin {
    gain: f64,          // 增益倍数
    sample_rate: f64,
    buffer_size: usize,
    initialized: bool,
}

impl GainPlugin {
    fn new(gain: f64) -> Self {
        Self {
            gain,
            sample_rate: 0.0,
            buffer_size: 0,
            initialized: false,
        }
    }
}

impl VcPlugin for GainPlugin {
    fn plugin_id(&self) -> &str {
        "gain"
    }

    fn plugin_name(&self) -> &str {
        "增益插件"
    }

    fn plugin_type(&self) -> PluginType {
        PluginType::Effect
    }

    fn version(&self) -> &str {
        "1.0.0"
    }

    fn init(&mut self, sample_rate: f64, buffer_size: usize) -> Result<(), opendaw_extension::PluginError> {
        self.sample_rate = sample_rate;
        self.buffer_size = buffer_size;
        self.initialized = true;
        println!("[Gain] 初始化完成: sr={}, bs={}", sample_rate, buffer_size);
        Ok(())
    }

    fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        if !self.initialized {
            return;
        }
        // 核心DSP：每个采样乘以增益系数
        for (i, &sample) in input.data.iter().enumerate() {
            output.data[i] = sample * self.gain;
        }
    }

    fn get_params(&self) -> Vec<ParamInfo> {
        vec![ParamInfo::new("gain", "增益", 0.0, 10.0, 1.0, "x")]
    }

    fn set_param(&mut self, id: &str, value: f64) -> Result<(), opendaw_extension::PluginError> {
        match id {
            "gain" => {
                self.gain = value.clamp(0.0, 10.0);
                println!("[Gain] 增益设置为: {:.2}", self.gain);
                Ok(())
            }
            _ => Err(opendaw_extension::PluginError::ParamNotFound(id.to_string())),
        }
    }

    fn get_param(&self, id: &str) -> Option<f64> {
        match id {
            "gain" => Some(self.gain),
            _ => None,
        }
    }

    fn destroy(&mut self) {
        self.initialized = false;
        println!("[Gain] 已销毁");
    }
}

// ===== 主函数 =====

fn main() {
    println!("=== OpenDAW Extension Registry 示例 ===
");

    // 1. 创建注册中心
    let mut registry = ExtensionRegistry::new();
    println!("[Registry] 创建扩展注册中心");

    // 2. 注册 Gain 插件
    let gain_plugin = GainPlugin::new(1.0);
    registry.register_plugin(Box::new(gain_plugin)).unwrap();
    println!("[Registry] 注册插件: {}", registry.list_plugins().join(", "));

    // 3. 注册脚本引擎
    let mut script = SimpleScriptEngine::new();
    script.register_api("get_gain", Box::new(|args| {
        if args.is_empty() {
            return Ok(ScriptValue::Float(1.0));
        }
        Ok(ScriptValue::Float(args[0].as_float().unwrap_or(1.0)))
    }));
    registry.register_script(Box::new(script)).unwrap();
    println!("[Registry] 注册脚本引擎: {}", registry.list_scripts().join(", "));

    // 4. 注册模型后端
    let model = LocalBackend::default_tasks();
    registry.register_model(Box::new(model)).unwrap();
    println!("[Registry] 注册模型后端: {}", registry.list_models().join(", "));

    // 5. 注册钩子
    let handler_id = registry.register_hook(
        "render_start",
        Box::new(|ctx| {
            println!("[Hook] render_start 触发! 事件={}", ctx.event);
            Ok(())
        }),
        10,
    );
    println!("[Registry] 注册钩子处理器: {}", handler_id);

    // 6. 初始化并使用插件
    let plugin = registry.get_plugin_mut("gain").unwrap();
    plugin.init(44100.0, 256).unwrap();

    // 7. 创建测试音频缓冲区
    let mut input = AudioBuffer::new(2, 256);
    // 填充正弦波测试信号
    for frame in 0..256 {
        let value = (2.0 * std::f64::consts::PI * 440.0 * frame as f64 / 44100.0).sin() * 0.5;
        input.set_sample(0, frame, value); // 左声道
        input.set_sample(1, frame, value); // 右声道
    }
    let mut output = AudioBuffer::new(2, 256);

    // 8. 处理音频（增益1.0 = 无变化）
    {
        let plugin = registry.get_plugin_mut("gain").unwrap();
        plugin.process(&input, &mut output);
    }
    println!("
[Process] 增益=1.0: 输入[0]={:.4}, 输出[0]={:.4}",
        input.sample(0, 0), output.sample(0, 0));

    // 9. 修改增益参数
    {
        let plugin = registry.get_plugin_mut("gain").unwrap();
        plugin.set_param("gain", 2.0).unwrap();
    }

    // 10. 再次处理（增益2.0 = 音量翻倍）
    {
        let plugin = registry.get_plugin_mut("gain").unwrap();
        plugin.process(&input, &mut output);
    }
    println!("[Process] 增益=2.0: 输入[0]={:.4}, 输出[0]={:.4}",
        input.sample(0, 0), output.sample(0, 0));

    // 11. 触发钩子事件
    let mut ctx = HookContext::new("render_start");
    ctx.insert("project", "test-project");
    registry.emit_hook("render_start", &mut ctx).unwrap();

    // 12. 模型推理
    let model_input = ModelInput::from_features(vec![1.0, 2.0, 3.0]);
    // 先加载模型（用临时文件模拟）
    {
        let tmp = std::env::temp_dir().join("test_model.onnx");
        std::fs::write(&tmp, b"fake").ok();
        let model = registry.get_model_mut("local").unwrap();
        model.load_model(&tmp).unwrap();
    }
    let result = registry.predict("local", &model_input).unwrap();
    println!("
[Model] 输入: {:?}", model_input.features);
    println!("[Model] 输出: {:?}", result.features);

    // 13. 脚本执行
    {
        let script = registry.get_script_mut("simple-0").unwrap();
        let val = script.eval("volume = 0.8").unwrap();
        println!("
[Script] 执行赋值: volume = {}", val);
        let result = script.call_function("get_gain", &[ScriptValue::Float(0.8)]).unwrap();
        println!("[Script] 调用 get_gain(0.8) = {}", result);
    }

    // 14. 销毁插件
    {
        let plugin = registry.get_plugin_mut("gain").unwrap();
        plugin.destroy();
    }

    println!("
=== 示例完成 ===");
}
