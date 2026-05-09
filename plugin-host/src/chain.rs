//! PluginChain — 信号链
//!
//! input -> plugin1 -> plugin2 -> ... -> output

use opendaw_extension::{AudioBuffer as ExtAudioBuffer, VcPlugin, PluginError};
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
    temp_buffer: ExtAudioBuffer,
    /// 引擎临时缓冲区（用于 process_engine）
    engine_temp_buffer: EngineAudioBuffer,
    /// 通道数
    channels: usize,
    /// 缓冲区大小
    buffer_size: usize,
}

impl PluginChain {
    /// 创建空信号链
    pub fn new(channels: usize, buffer_size: usize) -> Self {
        Self {
            nodes: Vec::new(),
            temp_buffer: ExtAudioBuffer::new(channels, buffer_size),
            engine_temp_buffer: EngineAudioBuffer::new(channels, buffer_size, 44100.0),
            channels,
            buffer_size,
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
        if index < self.nodes.len() {
            Some(self.nodes.remove(index).plugin)
        } else {
            None
        }
    }

    /// 调整缓冲区大小（当处理的缓冲区大小改变时调用）
    pub fn resize(&mut self, channels: usize, buffer_size: usize) {
        self.channels = channels;
        self.buffer_size = buffer_size;
        self.temp_buffer = ExtAudioBuffer::new(channels, buffer_size);
        self.engine_temp_buffer = EngineAudioBuffer::new(channels, buffer_size, 44100.0);
    }

    /// 处理信号链（使用 Extension AudioBuffer f64）
    ///
    /// 输入通过所有启用的插件，最终写入输出
    pub fn process(&mut self, input: &ExtAudioBuffer, output: &mut ExtAudioBuffer) {
        // 调整缓冲区大小如果需要
        if input.channels != self.channels || input.frames != self.buffer_size {
            self.resize(input.channels, input.frames);
        }

        if self.nodes.is_empty() {
            // 空链：直通
            output.channels = input.channels;
            output.frames = input.frames;
            if output.data.len() != input.data.len() {
                output.data.resize(input.data.len(), 0.0);
            }
            output.data.copy_from_slice(&input.data);
            return;
        }

        // 第一个插件从input读取，写入temp_buffer
        let mut src_data = input.data.clone();

        for node in &mut self.nodes {
            if !node.enabled {
                continue; // 旁路
            }

            let src = ExtAudioBuffer {
                channels: input.channels,
                frames: input.frames,
                data: src_data,
            };

            // 确保 temp_buffer 大小匹配
            if self.temp_buffer.data.len() != src.data.len() {
                self.temp_buffer.data.resize(src.data.len(), 0.0);
                self.temp_buffer.channels = src.channels;
                self.temp_buffer.frames = src.frames;
            }

            node.plugin.process(&src, &mut self.temp_buffer);
            src_data = self.temp_buffer.data.clone();
        }

        output.channels = input.channels;
        output.frames = input.frames;
        if output.data.len() != src_data.len() {
            output.data.resize(src_data.len(), 0.0);
        }
        output.data.copy_from_slice(&src_data);
    }

    /// 使用 audio-engine AudioBuffer 处理信号链（f32）
    ///
    /// 将 engine AudioBuffer (f32 planar) 转换为 extension AudioBuffer (f64)，
    /// 通过链中所有插件处理后，再转换回 engine AudioBuffer。
    pub fn process_engine(
        &mut self,
        input: &EngineAudioBuffer,
        output: &mut EngineAudioBuffer,
    ) {
        // 调整缓冲区大小如果需要
        if input.channels != self.channels || input.frames != self.buffer_size {
            self.resize(input.channels, input.frames);
        }

        // engine f32 → extension f64
        let mut ext_input = ExtAudioBuffer {
            channels: input.channels,
            frames: input.frames,
            data: input.as_slice().iter().map(|&s| s as f64).collect(),
        };
        let mut ext_output = ExtAudioBuffer::new(input.channels, input.frames);

        // 通过插件链处理
        self.process(&ext_input, &mut ext_output);

        // 确保 output 大小匹配 — 用公开API（EngineAudioBuffer.data是私有字段）
        if output.len() != input.len() {
            // 重新创建output（EngineAudioBuffer没有公开resize方法，通过赋值替换）
            *output = EngineAudioBuffer::zeros(input.channels, input.frames, input.sample_rate);
        }

        // extension f64 → engine f32
        let out_slice = output.as_mut_slice();
        for (i, &v) in ext_output.data.iter().enumerate() {
            if i < out_slice.len() {
                out_slice[i] = v as f32;
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

    /// 获取指定位置插件是否启用
    pub fn is_enabled(&self, index: usize) -> Option<bool> {
        self.nodes.get(index).map(|n| n.enabled)
    }

    /// 获取指定位置插件的ID
    pub fn plugin_id(&self, index: usize) -> Option<&str> {
        self.nodes.get(index).map(|n| n.plugin.plugin_id())
    }

    /// 获取指定位置插件的可变引用
    pub fn get_plugin_mut(&mut self, index: usize) -> Option<&mut (dyn VcPlugin + 'static)> {
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

    /// 清空所有插件
    pub fn clear(&mut self) {
        self.nodes.clear();
    }

    /// 交换两个位置插件的位置
    pub fn swap(&mut self, a: usize, b: usize) -> Result<(), PluginError> {
        if a >= self.nodes.len() || b >= self.nodes.len() {
            return Err(PluginError::ProcessFailed("索引越界".to_string()));
        }
        self.nodes.swap(a, b);
        Ok(())
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
        fn process(&mut self, input: &ExtAudioBuffer, output: &mut ExtAudioBuffer) {
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

        let mut input = ExtAudioBuffer::new(2, 256);
        input.data[0] = 0.5;
        let mut output = ExtAudioBuffer::new(2, 256);

        chain.process(&input, &mut output);
        // 0.5 * 2.0 * 0.5 = 0.5
        assert!((output.data[0] - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_chain_bypass() {
        let mut chain = PluginChain::new(2, 256);
        chain.push(Box::new(TestGain { gain: 10.0 }));
        chain.set_enabled(0, false).unwrap(); // 旁路

        let mut input = ExtAudioBuffer::new(2, 256);
        input.data[0] = 0.5;
        let mut output = ExtAudioBuffer::new(2, 256);

        chain.process(&input, &mut output);
        assert!((output.data[0] - 0.5).abs() < 1e-10); // 直通
    }

    #[test]
    fn test_chain_insert_remove() {
        let mut chain = PluginChain::new(2, 256);
        chain.push(Box::new(TestGain { gain: 2.0 }));
        chain.push(Box::new(TestGain { gain: 3.0 }));

        assert_eq!(chain.len(), 2);

        // 插入中间
        chain.insert(1, Box::new(TestGain { gain: 0.5 }));
        assert_eq!(chain.len(), 3);

        // 移除中间
        let removed = chain.remove(1);
        assert!(removed.is_some());
        assert_eq!(chain.len(), 2);
    }

    #[test]
    fn test_chain_swap() {
        let mut chain = PluginChain::new(2, 256);
        chain.push(Box::new(TestGain { gain: 2.0 }));
        chain.push(Box::new(TestGain { gain: 3.0 }));

        chain.swap(0, 1).unwrap();

        let mut input = ExtAudioBuffer::new(2, 4);
        input.data[0] = 1.0;
        let mut output = ExtAudioBuffer::new(2, 4);

        chain.process(&input, &mut output);
        // 3.0 * 2.0 = 6.0 (顺序已交换)
        assert!((output.data[0] - 6.0).abs() < 1e-10);
    }

    #[test]
    fn test_chain_resize() {
        let mut chain = PluginChain::new(2, 256);
        chain.push(Box::new(TestGain { gain: 2.0 }));

        // 改变缓冲区大小
        chain.resize(2, 512);

        let mut input = ExtAudioBuffer::new(2, 512);
        input.data[0] = 0.5;
        let mut output = ExtAudioBuffer::new(2, 512);

        chain.process(&input, &mut output);
        assert!((output.data[0] - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_chain_engine_process() {
        let mut chain = PluginChain::new(2, 256);
        chain.push(Box::new(TestGain { gain: 2.0 }));

        let mut input = EngineAudioBuffer::new(2, 256, 44100.0);
        input.as_mut_slice()[0] = 0.5;
        let mut output = EngineAudioBuffer::new(2, 256, 44100.0);

        chain.process_engine(&input, &mut output);
        assert!((output.as_slice()[0] - 1.0).abs() < 1e-6);
    }
}
