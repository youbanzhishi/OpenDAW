//! 导出模块
//!
//! - midi_export: Standard MIDI File导出
//! - audio_export: 多格式音频导出（WAV/FLAC/MP3-stub/OGG-stub）
//! - mix_report: 编曲混音报告导出（.omr.md格式）
//! - technique_template: 技巧模板导出（.omt.yaml格式）
//! - style_profile: 风格画像导出（.omp.yaml格式）
//! - technique_package: 技巧包导出（.omx.zip跨DAW格式）

pub mod audio_export;
pub mod midi_export;
pub mod mix_report;
pub mod style_profile;
pub mod technique_package;
pub mod technique_template;

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
pub use style_profile::{
    ArrangementPreference, AutomationHabits, ConfidenceScore, FrequencyItem, InstrumentCombo,
    MixingPreference, ParamPreference, ProfileAggregator, ProfileMeta, StyleProfile,
    TempoPreference,
};
pub use technique_package::{
    DAW, DAWEffectInstance, DAWMapper, DAWParamMap, DAWPreset, PackageError, PackageManifest,
    TechniquePackage,
};
pub use technique_template::{
    ArrangementTechniqueTemplate, ParamRange, ProcessingChainTemplate, ProcessingStep,
    TechniqueExtractor, TechniqueLibrary, TechniqueTemplate, TemplateCategory, TemplateMeta,
    TemplateStats, TemplateTip, TipType, UsageConditions,
};
