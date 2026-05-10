//! 项目模板系统 — 预置模板快速创建DAW工程
//!
//! - ProjectTemplate: 模板定义与项目生成
//! - 预置模板：Empty/Band/Podcast/EDM/Orchestral
//! - 模板包含轨道配置/BPM/拍号/默认插件

use serde::{Deserialize, Serialize};

use crate::project::{Project, ProjectConfig, TrackConfig};
use crate::timeline::TimeSignature;

/// 轨道类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TrackType {
    /// 音频轨道
    Audio,
    /// MIDI/乐器轨道
    Midi,
    /// 辅助总线
    Aux,
}

/// 模板中的轨道配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TemplateTrack {
    /// 轨道名称
    pub name: String,
    /// 轨道类型
    pub track_type: TrackType,
    /// 音量 (0.0 - 1.0)
    pub volume: f64,
    /// 声像 (-1.0 - 1.0)
    pub pan: f64,
    /// FX插件链
    pub fx_chain: Vec<String>,
}

impl TemplateTrack {
    /// 创建新模板轨道
    pub fn new(name: &str, track_type: TrackType) -> Self {
        Self {
            name: name.to_string(),
            track_type,
            volume: 1.0,
            pan: 0.0,
            fx_chain: Vec::new(),
        }
    }

    /// 设置音量
    pub fn with_volume(mut self, volume: f64) -> Self {
        self.volume = volume.clamp(0.0, 2.0);
        self
    }

    /// 设置声像
    pub fn with_pan(mut self, pan: f64) -> Self {
        self.pan = pan.clamp(-1.0, 1.0);
        self
    }

    /// 添加FX插件
    pub fn with_fx(mut self, plugin: &str) -> Self {
        self.fx_chain.push(plugin.to_string());
        self
    }
}

/// 预置模板名称
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PresetName {
    Empty,
    Band,
    Podcast,
    EDM,
    Orchestral,
}

impl std::fmt::Display for PresetName {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PresetName::Empty => write!(f, "Empty"),
            PresetName::Band => write!(f, "Band"),
            PresetName::Podcast => write!(f, "Podcast"),
            PresetName::EDM => write!(f, "EDM"),
            PresetName::Orchestral => write!(f, "Orchestral"),
        }
    }
}

/// 项目模板
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectTemplate {
    /// 模板名称
    pub name: String,
    /// 模板描述
    pub description: String,
    /// BPM
    pub bpm: f64,
    /// 拍号
    pub time_signature: TimeSignature,
    /// 轨道配置列表
    pub tracks: Vec<TemplateTrack>,
    /// 默认采样率
    pub sample_rate: f64,
    /// 默认缓冲区大小
    pub buffer_size: usize,
}

impl ProjectTemplate {
    /// 创建新模板
    pub fn new(name: &str, bpm: f64) -> Self {
        Self {
            name: name.to_string(),
            description: String::new(),
            bpm,
            time_signature: TimeSignature::four_four(),
            tracks: Vec::new(),
            sample_rate: 44100.0,
            buffer_size: 256,
        }
    }

    /// 设置描述
    pub fn with_description(mut self, desc: &str) -> Self {
        self.description = desc.to_string();
        self
    }

    /// 设置拍号
    pub fn with_time_signature(mut self, ts: TimeSignature) -> Self {
        self.time_signature = ts;
        self
    }

    /// 设置采样率
    pub fn with_sample_rate(mut self, rate: f64) -> Self {
        self.sample_rate = rate;
        self
    }

    /// 添加轨道
    pub fn add_track(&mut self, track: TemplateTrack) {
        self.tracks.push(track);
    }

    /// 从预置名创建模板
    pub fn from_preset(preset: PresetName) -> Self {
        match preset {
            PresetName::Empty => Self::empty(),
            PresetName::Band => Self::band(),
            PresetName::Podcast => Self::podcast(),
            PresetName::EDM => Self::edm(),
            PresetName::Orchestral => Self::orchestral(),
        }
    }

    /// 列出所有可用预置
    pub fn list_presets() -> Vec<(&'static str, &'static str)> {
        vec![
            ("Empty", "空项目 — 从零开始"),
            ("Band", "乐队4轨 — 鼓/贝斯/吉他/人声"),
            ("Podcast", "播客3轨 — 主持/嘉宾/音效"),
            ("EDM", "电子7轨 — Kick/Snare/HiHat/Bass/Lead/Pad/FX"),
            ("Orchestral", "管弦乐12轨 — 弦乐/木管/铜管/打击乐/合唱"),
        ]
    }

    /// 将模板转换为Project实例
    pub fn to_project(&self) -> Project {
        let config = ProjectConfig {
            name: self.name.clone(),
            sample_rate: self.sample_rate,
            buffer_size: self.buffer_size,
            tracks: self.tracks.iter().map(|t| TrackConfig {
                name: t.name.clone(),
                channels: 2,
                volume: t.volume,
                pan: t.pan,
                muted: false,
                plugins: t.fx_chain.clone(),
            }).collect(),
            master_volume: 1.0,
        };
        Project::from_config(&config)
    }

    // ── 预置模板 ─────────────────────────────

    /// 空项目
    fn empty() -> Self {
        Self::new("Empty Project", 120.0)
            .with_description("空项目 — 从零开始创建")
    }

    /// 乐队4轨
    fn band() -> Self {
        let mut tmpl = Self::new("Band Project", 120.0)
            .with_description("乐队4轨 — 鼓/贝斯/吉他/人声");
        tmpl.add_track(TemplateTrack::new("Drums", TrackType::Midi)
            .with_volume(0.8).with_pan(0.0)
            .with_fx("vc-eq").with_fx("vc-compressor"));
        tmpl.add_track(TemplateTrack::new("Bass", TrackType::Midi)
            .with_volume(0.7).with_pan(0.0)
            .with_fx("vc-eq").with_fx("vc-compressor"));
        tmpl.add_track(TemplateTrack::new("Guitar", TrackType::Audio)
            .with_volume(0.65).with_pan(-0.3)
            .with_fx("vc-eq").with_fx("vc-reverb"));
        tmpl.add_track(TemplateTrack::new("Vocals", TrackType::Audio)
            .with_volume(0.75).with_pan(0.0)
            .with_fx("vc-eq").with_fx("vc-compressor").with_fx("vc-reverb"));
        tmpl
    }

    /// 播客3轨
    fn podcast() -> Self {
        let mut tmpl = Self::new("Podcast Project", 120.0)
            .with_description("播客3轨 — 主持/嘉宾/音效");
        tmpl.add_track(TemplateTrack::new("Host", TrackType::Audio)
            .with_volume(0.8).with_pan(-0.2)
            .with_fx("vc-eq").with_fx("vc-compressor"));
        tmpl.add_track(TemplateTrack::new("Guest", TrackType::Audio)
            .with_volume(0.8).with_pan(0.2)
            .with_fx("vc-eq").with_fx("vc-compressor"));
        tmpl.add_track(TemplateTrack::new("SFX", TrackType::Audio)
            .with_volume(0.5).with_pan(0.0));
        tmpl
    }

    /// 电子7轨
    fn edm() -> Self {
        let mut tmpl = Self::new("EDM Project", 128.0)
            .with_description("电子7轨 — Kick/Snare/HiHat/Bass/Lead/Pad/FX");
        tmpl.add_track(TemplateTrack::new("Kick", TrackType::Midi)
            .with_volume(0.9).with_pan(0.0)
            .with_fx("vc-eq").with_fx("vc-compressor"));
        tmpl.add_track(TemplateTrack::new("Snare", TrackType::Midi)
            .with_volume(0.7).with_pan(0.0)
            .with_fx("vc-eq").with_fx("vc-reverb"));
        tmpl.add_track(TemplateTrack::new("HiHat", TrackType::Midi)
            .with_volume(0.5).with_pan(0.1));
        tmpl.add_track(TemplateTrack::new("Bass", TrackType::Midi)
            .with_volume(0.75).with_pan(0.0)
            .with_fx("vc-eq").with_fx("vc-compressor"));
        tmpl.add_track(TemplateTrack::new("Lead", TrackType::Midi)
            .with_volume(0.6).with_pan(0.0)
            .with_fx("vc-reverb").with_fx("vc-delay"));
        tmpl.add_track(TemplateTrack::new("Pad", TrackType::Midi)
            .with_volume(0.4).with_pan(0.0)
            .with_fx("vc-reverb"));
        tmpl.add_track(TemplateTrack::new("FX", TrackType::Midi)
            .with_volume(0.3).with_pan(0.0));
        tmpl
    }

    /// 管弦乐12轨
    fn orchestral() -> Self {
        let mut tmpl = Self::new("Orchestral Project", 100.0)
            .with_description("管弦乐12轨 — 弦乐/木管/铜管/打击乐/合唱");
        // 弦乐
        tmpl.add_track(TemplateTrack::new("Violins I", TrackType::Midi)
            .with_volume(0.7).with_pan(-0.4)
            .with_fx("vc-eq").with_fx("vc-reverb"));
        tmpl.add_track(TemplateTrack::new("Violins II", TrackType::Midi)
            .with_volume(0.65).with_pan(-0.2)
            .with_fx("vc-eq").with_fx("vc-reverb"));
        tmpl.add_track(TemplateTrack::new("Violas", TrackType::Midi)
            .with_volume(0.6).with_pan(0.0)
            .with_fx("vc-eq").with_fx("vc-reverb"));
        tmpl.add_track(TemplateTrack::new("Cellos", TrackType::Midi)
            .with_volume(0.65).with_pan(0.2)
            .with_fx("vc-eq").with_fx("vc-reverb"));
        tmpl.add_track(TemplateTrack::new("Basses", TrackType::Midi)
            .with_volume(0.6).with_pan(0.4)
            .with_fx("vc-eq").with_fx("vc-reverb"));
        // 木管
        tmpl.add_track(TemplateTrack::new("Woodwinds", TrackType::Midi)
            .with_volume(0.55).with_pan(-0.1)
            .with_fx("vc-reverb"));
        // 铜管
        tmpl.add_track(TemplateTrack::new("Brass", TrackType::Midi)
            .with_volume(0.6).with_pan(0.1)
            .with_fx("vc-eq").with_fx("vc-reverb"));
        // 打击乐
        tmpl.add_track(TemplateTrack::new("Timpani", TrackType::Midi)
            .with_volume(0.7).with_pan(0.0)
            .with_fx("vc-compressor"));
        tmpl.add_track(TemplateTrack::new("Percussion", TrackType::Midi)
            .with_volume(0.5).with_pan(0.0));
        // 键盘
        tmpl.add_track(TemplateTrack::new("Piano", TrackType::Midi)
            .with_volume(0.55).with_pan(0.0)
            .with_fx("vc-reverb"));
        // 合唱
        tmpl.add_track(TemplateTrack::new("Choir", TrackType::Midi)
            .with_volume(0.5).with_pan(0.0)
            .with_fx("vc-reverb"));
        // 指挥
        tmpl.add_track(TemplateTrack::new("Conductor", TrackType::Audio)
            .with_volume(1.0).with_pan(0.0));
        tmpl
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_template_from_preset_empty() {
        let tmpl = ProjectTemplate::from_preset(PresetName::Empty);
        assert_eq!(tmpl.name, "Empty Project");
        assert_eq!(tmpl.tracks.len(), 0);
        assert!((tmpl.bpm - 120.0).abs() < 0.001);
    }

    #[test]
    fn test_template_from_preset_band() {
        let tmpl = ProjectTemplate::from_preset(PresetName::Band);
        assert_eq!(tmpl.tracks.len(), 4);
        assert_eq!(tmpl.tracks[0].name, "Drums");
        assert_eq!(tmpl.tracks[3].name, "Vocals");
    }

    #[test]
    fn test_template_to_project() {
        let tmpl = ProjectTemplate::from_preset(PresetName::Podcast);
        let project = tmpl.to_project();
        assert_eq!(project.name, "Podcast Project");
        assert_eq!(project.track_count(), 3);
        assert_eq!(project.get_track(0).unwrap().name, "Host");
    }

    #[test]
    fn test_template_list_presets() {
        let presets = ProjectTemplate::list_presets();
        assert_eq!(presets.len(), 5);
        assert_eq!(presets[0].0, "Empty");
        assert_eq!(presets[4].0, "Orchestral");
    }

    #[test]
    fn test_template_edm_tracks() {
        let tmpl = ProjectTemplate::from_preset(PresetName::EDM);
        assert_eq!(tmpl.tracks.len(), 7);
        assert!((tmpl.bpm - 128.0).abs() < 0.001);
        // Check kick has FX chain
        assert!(tmpl.tracks[0].fx_chain.contains(&"vc-eq".to_string()));
    }

    #[test]
    fn test_template_orchestral_tracks() {
        let tmpl = ProjectTemplate::from_preset(PresetName::Orchestral);
        assert_eq!(tmpl.tracks.len(), 12);
        assert_eq!(tmpl.tracks[0].name, "Violins I");
    }

    #[test]
    fn test_template_track_builder() {
        let track = TemplateTrack::new("Test", TrackType::Audio)
            .with_volume(0.8)
            .with_pan(-0.5)
            .with_fx("vc-eq")
            .with_fx("vc-reverb");
        assert!((track.volume - 0.8).abs() < 0.001);
        assert!((track.pan - (-0.5)).abs() < 0.001);
        assert_eq!(track.fx_chain.len(), 2);
    }

    #[test]
    fn test_template_volume_clamping() {
        let track = TemplateTrack::new("Test", TrackType::Audio).with_volume(3.0);
        assert!((track.volume - 2.0).abs() < 0.001); // Clamped to max 2.0
    }
}
