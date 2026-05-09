//! PluginChain — 信号链
//!
//! input -> plugin1 -> plugin2 -> ... -> output

use opendaw_extension::{AudioBuffer, VcPlugin, PluginError};
use audio_engine::buffer::AudioBuffer as EngineAudioBuffer;

/// 信号链节点
struct ChainNode {
    plugin: Box<dyn VcPlugin>,
    enabled: bool,
}

/// 插件信号链
///
/// 音频数据按顺序通过链中的每个插件
/// 禁用的插件会被旁路（直通）
pub struct PluginChain {
    nodes: Vec<ChainNode>,
    /// 临时缓冲区（用于插件间传递数据）
    temp_buffer: AudioBuffer,
}

impl PluginChain {
    /// 创建空信号链
    pub fn new(channels: usize, buffer_size: usize) -> Self {
        Self {
            nodes: Vec::new(),
            temp_buffer: AudioBuffer::new(channels, buffer_size),
        }
    }

    /// 添加插件到链尾
    pub fn push(&mut self, plugin: Box<dyn VcPlugin>) {
        self.nodes.push(ChainNode {
            plugin,
            enabled: true,
        });
    }

    /// 在指定位置插入插件
    pub fn insert(&mut self, index: usize, plugin: Box<dyn VcPlugin>) {
        self.nodes.insert(index, ChainNode {
            plugin,
            enabled: true,
        });
    }

    /// 移除指定位置的插件
    pub fn remove(&mut self, index: usize) -> Option<Box<dyn VcPlugin>> {
        self.nodes.remove(index).map(|n| n.plugin)
    }

    /// 处理信号链
    ///
    /// 输入通过所有启用的插件，最终写入输出
    pub fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
        if self.nodes.is_empty() {
            // 空链：直通
            output.data.copy_from_slice(&input.data);
            return;
        }

        // 第一个插件从input读取，写入temp_buffer
        let mut src_data = input.data.clone();

        for node in &mut self.nodes {
            if !node.enabled {
                continue; // 旁路
            }

            let src = AudioBuffer {
                channels: input.channels,
                frames: input.frames,
                data: src_data,
            };

            node.plugin.process(&src, &mut self.temp_buffer);
            src_data = self.temp_buffer.data.clone();
        }

        output.data.copy_from_slice(&src_data);
    }

    /// 使用audio-engine AudioBuffer处理信号链
    ///
    /// 将engine AudioBuffer(f32 planar)转换为extension AudioBuffer(f64)，
    /// 通过链中所有插件处理后，再转换回engine AudioBuffer。
    pub fn process_engine(
        &mut self,
        input: &EngineAudioBuffer,
        output: &mut EngineAudioBuffer,
    ) {
        // engine f32 → extension f64
        let ext_input = AudioBuffer {
            channels: input.channels,
            frames: input.frames,
            data: input.as_slice().iter().map(|&s| s as f64).collect(),
        };
        let mut ext_output = AudioBuffer::new(output.channels, output.frames);

        // 通过插件链处理
        self.process(&ext_input, &mut ext_output);

        // extension f64 → engine f32
        for (i, &v) in ext_output.data.iter().enumerate() {
            if i < output.as_mut_slice().len() {
                output.as_mut_slice()[i] = v as f32;
            }
        }
    }

    /// 获取链中插件数量
    pub fn len(&self) -> usize {
        self.nodes.len()
    }

    pub fn is_empty(&self) -> bool {
        self.nodes.is_empty()
    }

    /// 启用/禁用指定位置的插件
    pub fn set_enabled(&mut self, index: usize, enabled: bool) -> Result<(), PluginError> {
        self.nodes
            .get_mut(index)
            .map(|n| n.enabled = enabled)
            .ok_or_else(|| PluginError::ProcessFailed(format!("插件索引越界: {}", index)))
    }

    /// 获取指定位置插件的ID
    pub fn plugin_id(&self, index: usize) -> Option<&str> {
        self.nodes.get(index).map(|n| n.plugin.plugin_id())
    }

    /// 获取指定位置插件的可变引用
    pub fn get_plugin_mut(&mut self, index: usize) -> Option<&mut dyn VcPlugin> {
        self.nodes.get_mut(index).map(|n| n.plugin.as_mut())
    }

    /// 列出链中所有插件信息
    pub fn list_plugins(&self) -> Vec<ChainPluginInfo> {
        self.nodes
            .iter()
            .enumerate()
            .map(|(i, n)| ChainPluginInfo {
                index: i,
                id: n.plugin.plugin_id().to_string(),
                name: n.plugin.plugin_name().to_string(),
                enabled: n.enabled,
            })
            .collect()
    }
}

/// 链中插件信息
#[derive(Clone, Debug)]
pub struct ChainPluginInfo {
    pub index: usize,
    pub id: String,
    pub name: String,
    pub enabled: bool,
}

#[cfg(test)]
mod tests {
    use super::*;
    use opendaw_extension::PluginType;

    /// 测试用增益插件
    struct TestGain {
        gain: f64,
    }

    impl VcPlugin for TestGain {
        fn plugin_id(&self) -> &str { "test-gain" }
        fn plugin_name(&self) -> &str { "测试增益" }
        fn plugin_type(&self) -> PluginType { PluginType::Effect }
        fn version(&self) -> &str { "0.1.0" }
        fn init(&mut self, _sr: f64, _bs: usize) -> Result<(), PluginError> { Ok(()) }
        fn process(&mut self, input: &AudioBuffer, output: &mut AudioBuffer) {
            for (i, &s) in input.data.iter().enumerate() {
                output.data[i] = s * self.gain;
            }
        }
        fn get_params(&self) -> Vec<opendaw_extension::ParamInfo> { vec![] }
        fn set_param(&mut self, _id: &str, _v: f64) -> Result<(), PluginError> { Ok(()) }
        fn get_param(&self, _id: &str) -> Option<f64> { None }
        fn destroy(&mut self) {}
    }

    #[test]
    fn test_chain_process() {
        let mut chain = PluginChain::new(2, 256);
        chain.push(Box::new(TestGain { gain: 2.0 }));
        chain.push(Box::new(TestGain { gain: 0.5 })); // 2.0 * 0.5 = 1.0

        let mut input = AudioBuffer::new(2, 256);
        input.data[0] = 0.5;
        let mut output = AudioBuffer::new(2, 256);

        chain.process(&input, &mut output);
        // 0.5 * 2.0 * 0.5 = 0.5
        assert!((output.data[0] - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_chain_bypass() {
        let mut chain = PluginChain::new(2, 256);
        chain.push(Box::new(TestGain { gain: 10.0 }));
        chain.set_enabled(0, false).unwrap(); // 旁路

        let mut input = AudioBuffer::new(2, 256);
        input.data[0] = 0.5;
        let mut output = AudioBuffer::new(2, 256);

        chain.process(&input, &mut output);
        assert!((output.data[0] - 0.5).abs() < 1e-10); // 直通
    }
}
