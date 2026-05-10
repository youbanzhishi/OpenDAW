//! 项目管理 — 加载YAML、组织Track/Plugin

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use audio_engine::Track;

/// 项目配置（YAML格式）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectConfig {
    pub name: String,
    pub sample_rate: f64,
    pub buffer_size: usize,
    #[serde(default)]
    pub tracks: Vec<TrackConfig>,
    #[serde(default)]
    pub master_volume: f64,
}

/// 轨道配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackConfig {
    pub name: String,
    pub channels: usize,
    #[serde(default = "default_volume")]
    pub volume: f64,
    #[serde(default)]
    pub pan: f64,
    #[serde(default)]
    pub muted: bool,
    #[serde(default)]
    pub plugins: Vec<String>,
}

fn default_volume() -> f64 {
    1.0
}

/// 项目 — DAW工程的核心数据结构
pub struct Project {
    /// 项目名称
    pub name: String,
    /// 采样率
    pub sample_rate: f64,
    /// 缓冲区大小
    pub buffer_size: usize,
    /// 轨道列表
    pub tracks: Vec<Track>,
    /// 主音量
    pub master_volume: f64,
    /// 项目文件路径
    pub path: Option<String>,
    /// 是否已修改
    pub dirty: bool,
    /// 元数据
    pub metadata: HashMap<String, String>,
}

impl Project {
    /// 创建空白项目
    pub fn new(name: &str, sample_rate: f64, buffer_size: usize) -> Self {
        Self {
            name: name.to_string(),
            sample_rate,
            buffer_size,
            tracks: Vec::new(),
            master_volume: 1.0,
            path: None,
            dirty: false,
            metadata: HashMap::new(),
        }
    }

    /// 从YAML配置创建项目
    pub fn from_config(config: &ProjectConfig) -> Self {
        let mut project = Self::new(&config.name, config.sample_rate, config.buffer_size);

        for tc in &config.tracks {
            let mut track = Track::new(&tc.name);
            track.set_volume(tc.volume);
            track.set_pan(tc.pan);
            if tc.muted {
                track.toggle_mute();
            }
            project.tracks.push(track);
        }

        project.master_volume = config.master_volume;
        project
    }

    /// 从YAML文件加载项目
    pub fn from_file(path: &Path) -> Result<Self, ProjectError> {
        let content = std::fs::read_to_string(path)
            .map_err(|e| ProjectError::IoError(format!("读取文件失败: {}", e)))?;
        let config: ProjectConfig = serde_yaml::from_str(&content)
            .map_err(|e| ProjectError::ParseError(format!("YAML解析失败: {}", e)))?;
        let mut project = Self::from_config(&config);
        project.path = Some(path.display().to_string());
        Ok(project)
    }

    /// 保存项目到文件
    pub fn save(&self, path: &Path) -> Result<(), ProjectError> {
        let config = ProjectConfig {
            name: self.name.clone(),
            sample_rate: self.sample_rate,
            buffer_size: self.buffer_size,
            tracks: self
                .tracks
                .iter()
                .map(|t| TrackConfig {
                    name: t.name.clone(),
                    channels: t.channels,
                    volume: t.volume,
                    pan: t.pan,
                    muted: t.muted,
                    plugins: vec![],
                })
                .collect(),
            master_volume: self.master_volume,
        };
        let yaml = serde_yaml::to_string(&config)
            .map_err(|e| ProjectError::SerializeError(format!("YAML序列化失败: {}", e)))?;
        std::fs::write(path, yaml)
            .map_err(|e| ProjectError::IoError(format!("写入文件失败: {}", e)))
    }

    /// 添加轨道
    pub fn add_track(&mut self, track: Track) {
        self.tracks.push(track);
        self.dirty = true;
    }

    /// 移除轨道
    pub fn remove_track(&mut self, index: usize) -> Option<Track> {
        if index < self.tracks.len() {
            self.dirty = true;
            Some(self.tracks.remove(index))
        } else {
            None
        }
    }

    /// 获取轨道
    pub fn get_track(&self, index: usize) -> Option<&Track> {
        self.tracks.get(index)
    }

    /// 获取轨道可变引用
    pub fn get_track_mut(&mut self, index: usize) -> Option<&mut Track> {
        self.tracks.get_mut(index)
    }

    /// 轨道数量
    pub fn track_count(&self) -> usize {
        self.tracks.len()
    }

    /// 项目时长（基于轨道数和当前状态，简化实现）
    pub fn duration_info(&self) -> String {
        format!(
            "项目: {} | {} 轨道 | {}Hz | {}帧缓冲",
            self.name,
            self.tracks.len(),
            self.sample_rate,
            self.buffer_size
        )
    }

    /// 生成示例项目配置
    pub fn example_config() -> ProjectConfig {
        ProjectConfig {
            name: "示例项目".into(),
            sample_rate: 44100.0,
            buffer_size: 256,
            tracks: vec![
                TrackConfig {
                    name: "人声".into(),
                    channels: 2,
                    volume: 0.8,
                    pan: 0.0,
                    muted: false,
                    plugins: vec!["vc-eq".into(), "vc-compressor".into()],
                },
                TrackConfig {
                    name: "吉他".into(),
                    channels: 2,
                    volume: 0.6,
                    pan: -0.3,
                    muted: false,
                    plugins: vec!["vc-reverb".into()],
                },
            ],
            master_volume: 1.0,
        }
    }

    // === Phase 26: 项目格式升级需要的方法 ===

    /// 将项目导出为ProjectConfig
    pub fn to_config(&self) -> ProjectConfig {
        ProjectConfig {
            name: self.name.clone(),
            sample_rate: self.sample_rate,
            buffer_size: self.buffer_size,
            tracks: self
                .tracks
                .iter()
                .map(|t| TrackConfig {
                    name: t.name.clone(),
                    channels: t.channels,
                    volume: t.volume,
                    pan: t.pan,
                    muted: t.muted,
                    plugins: vec![],
                })
                .collect(),
            master_volume: self.master_volume,
        }
    }
}

/// 项目错误
#[derive(Debug, thiserror::Error)]
pub enum ProjectError {
    #[error("IO错误: {0}")]
    IoError(String),
    #[error("解析错误: {0}")]
    ParseError(String),
    #[error("序列化错误: {0}")]
    SerializeError(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_project_creation() {
        let project = Project::new("测试", 44100.0, 256);
        assert_eq!(project.name, "测试");
        assert_eq!(project.track_count(), 0);
    }

    #[test]
    fn test_project_add_track() {
        let mut project = Project::new("测试", 44100.0, 256);
        project.add_track(Track::stereo("人声"));
        project.add_track(Track::mono("贝斯"));
        assert_eq!(project.track_count(), 2);
        assert_eq!(project.get_track(0).unwrap().name, "人声");
    }

    #[test]
    fn test_project_config() {
        let config = Project::example_config();
        let project = Project::from_config(&config);
        assert_eq!(project.name, "示例项目");
        assert_eq!(project.track_count(), 2);
    }

    #[test]
    fn test_project_save_load() {
        let mut project = Project::new("保存测试", 48000.0, 512);
        project.add_track(Track::stereo("主轨道"));

        let tmp = std::env::temp_dir().join("test_project.yaml");
        project.save(&tmp).unwrap();

        let loaded = Project::from_file(&tmp).unwrap();
        assert_eq!(loaded.name, "保存测试");
        assert_eq!(loaded.sample_rate, 48000.0);
        assert_eq!(loaded.track_count(), 1);

        let _ = std::fs::remove_file(&tmp);
    }
}
