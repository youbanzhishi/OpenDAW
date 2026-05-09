//! 混音器 — Track -> PluginChain -> Bus -> Master

use audio_engine::{AudioEngine, EngineAudioBuffer, Track, EngineState};
use opendaw_extension::{AudioBuffer, VcPlugin};
use plugin_host::PluginChain;

/// 总线类型
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BusType {
    /// 主输出总线
    Master,
    /// 辅助发送总线
    Aux,
    /// 编组总线
    Group,
}

/// 总线
pub struct Bus {
    /// 总线名称
    pub name: String,
    /// 总线类型
    pub bus_type: BusType,
    /// 声道数
    pub channels: usize,
    /// 音量
    pub volume: f64,
    /// 静音
    pub muted: bool,
}

impl Bus {
    pub fn new(name: &str, bus_type: BusType, channels: usize) -> Self {
        Self {
            name: name.to_string(),
            bus_type,
            channels,
            volume: 1.0,
            muted: false,
        }
    }

    pub fn master(channels: usize) -> Self {
        Self::new("Master", BusType::Master, channels)
    }
}

/// 混音器 — 管理所有轨道的混音过程
///
/// 信号流：
/// Track1 -> [PluginChain] -> Bus1 ─┐
/// Track2 -> [PluginChain] -> Bus2 ─┤-> Master Bus -> 输出
/// Track3 -> [PluginChain] -> Bus3 ─┘
pub struct Mixer {
    /// 主输出总线
    master_bus: Bus,
    /// 辅助总线
    aux_buses: Vec<Bus>,
    /// 轨道到总线的路由
    routing: Vec<usize>, // track_index -> bus_index (0 = master)
    /// 采样率
    sample_rate: f64,
    /// 缓冲区大小
    buffer_size: usize,
}

impl Mixer {
    /// 创建新的混音器
    pub fn new(sample_rate: f64, buffer_size: usize, channels: usize) -> Self {
        Self {
            master_bus: Bus::master(channels),
            aux_buses: Vec::new(),
            routing: Vec::new(),
            sample_rate,
            buffer_size,
        }
    }

    /// 添加辅助总线
    pub fn add_aux_bus(&mut self, name: &str, channels: usize) -> usize {
        let index = self.aux_buses.len() + 1; // 0号是master
        self.aux_buses.push(Bus::new(name, BusType::Aux, channels));
        index
    }

    /// 设置轨道路由
    pub fn set_routing(&mut self, track_index: usize, bus_index: usize) {
        // 确保routing数组足够大
        while self.routing.len() <= track_index {
            self.routing.push(0); // 默认路由到master
        }
        self.routing[track_index] = bus_index;
    }

    /// 混音：将多个轨道的音频混合到输出
    ///
    /// tracks: (轨道信息, 音频数据) 的列表
    /// output: 混音后的输出
    pub fn mix(
        &self,
        track_buffers: &[(f64, f64, bool, &EngineAudioBuffer)], // (volume, pan, muted, buffer)
        output: &mut EngineAudioBuffer,
    ) {
        output.clear();

        for (volume, pan, muted, buffer) in track_buffers {
            if *muted {
                continue;
            }

            // 计算立体声增益
            let theta = (pan + 1.0) / 2.0 * std::f64::consts::FRAC_PI_2;
            let left_gain = volume * theta.cos();
            let right_gain = volume * theta.sin();

            // 混合到输出
            if buffer.channels >= 2 && output.channels >= 2 {
                let in_left = buffer.channel_slice(0);
                let in_right = buffer.channel_slice(1);
                let out_left = output.channel_slice_mut(0);
                let out_right = output.channel_slice_mut(1);

                let len = in_left.len().min(out_left.len());
                for i in 0..len {
                    out_left[i] += in_left[i] * left_gain;
                    out_right[i] += in_right[i] * right_gain;
                }
            } else if buffer.channels == 1 && output.channels >= 2 {
                // 单声道到立体声
                let in_mono = buffer.channel_slice(0);
                let out_left = output.channel_slice_mut(0);
                let out_right = output.channel_slice_mut(1);
                let len = in_mono.len().min(out_left.len());
                for i in 0..len {
                    out_left[i] += in_mono[i] * left_gain;
                    out_right[i] += in_mono[i] * right_gain;
                }
            }
        }

        // 应用master音量
        output.apply_gain(self.master_bus.volume);
    }

    /// 设置主音量
    pub fn set_master_volume(&mut self, vol: f64) {
        self.master_bus.volume = vol.clamp(0.0, 2.0);
    }

    /// 主音量
    pub fn master_volume(&self) -> f64 {
        self.master_bus.volume
    }

    /// 总线数量
    pub fn bus_count(&self) -> usize {
        1 + self.aux_buses.len() // master + aux
    }

    /// 采样率
    pub fn sample_rate(&self) -> f64 {
        self.sample_rate
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mixer_basic() {
        let mixer = Mixer::new(44100.0, 256, 2);

        // 两个轨道混合
        let buf1 = EngineAudioBuffer::new(2, 256, 44100.0);
        let mut buf2 = EngineAudioBuffer::new(2, 256, 44100.0);
        buf2.data[0] = 0.5; // 左声道
        buf2.data[256] = 0.5; // 右声道

        let mut output = EngineAudioBuffer::new(2, 256, 44100.0);
        mixer.mix(
            &[
                (1.0, 0.0, false, &buf1),
                (1.0, 0.0, false, &buf2),
            ],
            &mut output,
        );

        // 应该有来自buf2的信号
        assert!(output.data[0].abs() > 0.0);
    }

    #[test]
    fn test_mixer_mute() {
        let mixer = Mixer::new(44100.0, 256, 2);
        let mut buf = EngineAudioBuffer::new(2, 256, 44100.0);
        buf.data[0] = 1.0;

        let mut output = EngineAudioBuffer::new(2, 256, 44100.0);
        mixer.mix(
            &[(1.0, 0.0, true, &buf)], // 静音
            &mut output,
        );

        // 静音轨道不应输出
        assert!(output.data[0].abs() < 1e-10);
    }

    #[test]
    fn test_mixer_master_volume() {
        let mut mixer = Mixer::new(44100.0, 256, 2);
        mixer.set_master_volume(0.5);

        let mut buf = EngineAudioBuffer::new(2, 256, 44100.0);
        buf.data[0] = 1.0;

        let mut output = EngineAudioBuffer::new(2, 256, 44100.0);
        mixer.mix(
            &[(1.0, 0.0, false, &buf)],
            &mut output,
        );

        // master音量0.5
        assert!((output.data[0] - 0.5).abs() < 0.01);
    }
}
