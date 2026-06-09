//! 导出模块
//!
//! - midi_export: Standard MIDI File导出
//! - audio_export: 多格式音频导出（WAV/FLAC/MP3-stub/OGG-stub）
//! - mix_report: 编曲混音报告导出（.omr.md格式）

pub mod audio_export;
pub mod midi_export;
pub mod mix_report;

pub use audio_export::{
    AudioExporter, AudioFormat, BitDepth, ExportConfig, ExportError, ExportProgress, ExportResult,
    RenderPipeline,
};
pub use midi_export::{MidiEvent, MidiExportConfig, MidiExporter, MidiTrack};
pub use mix_report::{
    ArrangementAnalysis, ArrangementTechnique, AutomationInfo, AutomationSidechainSection,
    BusProcessingInfo, DesignIntentSection, DynamicChange, EffectChainInfo, EffectInfo, EffectType,
    InstrumentInfo, InstrumentType, KnowledgeLinks, MixReport, MixReportGenerator, MixingAnalysis,
    ProjectOverview, SectionInfo, SectionIntent, SendInfo, SidechainInfo, TrackMixParams,
};
