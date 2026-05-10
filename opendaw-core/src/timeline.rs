//! 时间线管理 — 多拍号/多速度/时间位置转换
//!
//! - Timeline: 全局时间线
//! - TimeSignatureChange: 拍号变化点
//! - TempoChange: 速度变化点
//! - TimelineCursor: 时间位置 ↔ 拍/小节/帧 互转

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

/// 拍号
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct TimeSignature {
    /// 每小节拍数
    pub numerator: u8,
    /// 拍值（4 = 四分音符, 8 = 八分音符）
    pub denominator: u8,
}

impl TimeSignature {
    /// 创建新的拍号
    pub fn new(numerator: u8, denominator: u8) -> Self {
        Self { numerator, denominator }
    }

    /// 4/4拍
    pub fn four_four() -> Self {
        Self::new(4, 4)
    }

    /// 3/4拍
    pub fn three_four() -> Self {
        Self::new(3, 4)
    }

    /// 6/8拍
    pub fn six_eight() -> Self {
        Self::new(6, 8)
    }

    /// 7/8拍
    pub fn seven_eight() -> Self {
        Self::new(7, 8)
    }

    /// 转换为文本表示
    pub fn to_string_display(&self) -> String {
        format!("{}/{}", self.numerator, self.denominator)
    }

    /// 每小节的四分音符拍数（考虑拍值）
    pub fn beats_per_bar(&self) -> f64 {
        (self.numerator as f64 * 4.0) / self.denominator as f64
    }
}

impl Default for TimeSignature {
    fn default() -> Self {
        Self::four_four()
    }
}

/// 拍号变化点
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimeSignatureChange {
    /// 变化发生的小节位置
    pub bar: u32,
    /// 新拍号
    pub time_signature: TimeSignature,
}

impl TimeSignatureChange {
    /// 创建新的拍号变化
    pub fn new(bar: u32, time_signature: TimeSignature) -> Self {
        Self { bar, time_signature }
    }
}

/// 速度变化类型
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum TempoChangeType {
    /// 线性渐变
    Linear,
    /// 阶梯式（立即切换）
    Step,
}

/// 速度变化点
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TempoChange {
    /// 变化发生的拍位置
    pub beat: f64,
    /// 目标BPM
    pub bpm: f64,
    /// 变化类型
    pub change_type: TempoChangeType,
}

impl TempoChange {
    /// 创建线性速度变化
    pub fn linear(beat: f64, bpm: f64) -> Self {
        Self {
            beat,
            bpm,
            change_type: TempoChangeType::Linear,
        }
    }

    /// 创建阶梯式速度变化
    pub fn step(beat: f64, bpm: f64) -> Self {
        Self {
            beat,
            bpm,
            change_type: TempoChangeType::Step,
        }
    }
}

/// 时间位置 — 表示时间线上的精确位置
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct TimePosition {
    /// 小节（从1开始）
    pub bar: u32,
    /// 拍（从1开始，支持小数）
    pub beat: f64,
    /// Tick（细粒度位置，1拍=480ticks）
    pub tick: u32,
}

impl TimePosition {
    /// 创建时间位置
    pub fn new(bar: u32, beat: f64, tick: u32) -> Self {
        Self { bar, beat, tick }
    }

    /// 从小节和拍创建
    pub fn from_bar_beat(bar: u32, beat: f64) -> Self {
        Self { bar, beat, tick: 0 }
    }

    /// 起点
    pub fn zero() -> Self {
        Self::new(1, 1.0, 0)
    }

    /// 转换为总拍数（从第1小节第1拍开始计数）
    pub fn to_total_beats(&self) -> f64 {
        ((self.bar - 1) as f64) + (self.beat - 1.0) + self.tick as f64 / 480.0
    }

    /// 从总拍数创建时间位置
    pub fn from_total_beats(total_beats: f64) -> Self {
        let bar = (total_beats / 4.0).floor() as u32 + 1;
        let remaining = total_beats - ((bar - 1) as f64 * 4.0);
        let beat = remaining.floor() + 1.0;
        let tick_remaining = (remaining - remaining.floor()) * 480.0;
        Self {
            bar,
            beat,
            tick: tick_remaining.round() as u32,
        }
    }
}

impl std::fmt::Display for TimePosition {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}:{}:{}", self.bar, self.beat as u32, self.tick)
    }
}

/// 时间线 — 全局时间线管理
pub struct Timeline {
    /// 默认拍号
    default_time_signature: TimeSignature,
    /// 默认BPM
    default_bpm: f64,
    /// 采样率
    sample_rate: f64,
    /// 拍号变化列表（按小节排序）
    time_signature_changes: BTreeMap<u32, TimeSignature>,
    /// 速度变化列表（按拍排序）
    tempo_changes: BTreeMap<u64, TempoChange>, // key: beat * 1000 for precision
    /// 循环起始（拍，None表示不循环）
    loop_start: Option<f64>,
    /// 循环结束（拍）
    loop_end: Option<f64>,
}

impl Timeline {
    /// 创建新的时间线
    pub fn new(bpm: f64, time_signature: TimeSignature, sample_rate: f64) -> Self {
        let mut ts_changes = BTreeMap::new();
        ts_changes.insert(1, time_signature);

        let mut tempo_changes = BTreeMap::new();
        tempo_changes.insert(0, TempoChange::step(0.0, bpm));

        Self {
            default_time_signature: time_signature,
            default_bpm: bpm,
            sample_rate,
            time_signature_changes: ts_changes,
            tempo_changes,
            loop_start: None,
            loop_end: None,
        }
    }

    /// 创建默认4/4拍120BPM时间线
    pub fn default_120bpm(sample_rate: f64) -> Self {
        Self::new(120.0, TimeSignature::four_four(), sample_rate)
    }

    /// 添加拍号变化
    pub fn add_time_signature_change(&mut self, bar: u32, ts: TimeSignature) {
        self.time_signature_changes.insert(bar, ts);
    }

    /// 移除拍号变化
    pub fn remove_time_signature_change(&mut self, bar: u32) {
        if bar != 1 { // 不允许移除初始拍号
            self.time_signature_changes.remove(&bar);
        }
    }

    /// 添加速度变化
    pub fn add_tempo_change(&mut self, change: TempoChange) {
        let key = (change.beat * 1000.0) as u64;
        self.tempo_changes.insert(key, change);
    }

    /// 移除速度变化
    pub fn remove_tempo_change(&mut self, beat: f64) {
        let key = (beat * 1000.0) as u64;
        if key != 0 { // 不允许移除初始速度
            self.tempo_changes.remove(&key);
        }
    }

    /// 获取指定小节的拍号
    pub fn time_signature_at_bar(&self, bar: u32) -> TimeSignature {
        self.time_signature_changes
            .range(..=bar)
            .next_back()
            .map(|(_, ts)| *ts)
            .unwrap_or(self.default_time_signature)
    }

    /// 获取指定拍位置的BPM
    pub fn bpm_at_beat(&self, beat: f64) -> f64 {
        let key = (beat * 1000.0) as u64;
        self.tempo_changes
            .range(..=key)
            .next_back()
            .map(|(_, change)| change.bpm)
            .unwrap_or(self.default_bpm)
    }

    /// 拍 → 帧数（考虑速度变化）
    pub fn beat_to_frame(&self, beat: f64) -> u64 {
        let bpm = self.bpm_at_beat(beat);
        let beats_per_sec = bpm / 60.0;
        let secs = beat / beats_per_sec;
        (secs * self.sample_rate) as u64
    }

    /// 帧数 → 拍（简化实现，使用当前BPM）
    pub fn frame_to_beat(&self, frame: u64) -> f64 {
        let secs = frame as f64 / self.sample_rate;
        let bpm = self.default_bpm; // 简化：使用默认BPM
        let beats_per_sec = bpm / 60.0;
        secs * beats_per_sec
    }

    /// 拍 → 秒
    pub fn beat_to_seconds(&self, beat: f64) -> f64 {
        let bpm = self.bpm_at_beat(beat);
        beat / (bpm / 60.0)
    }

    /// 秒 → 拍
    pub fn seconds_to_beat(&self, seconds: f64) -> f64 {
        let beats_per_sec = self.default_bpm / 60.0;
        seconds * beats_per_sec
    }

    /// 小节 → 起始拍
    pub fn bar_to_beat(&self, bar: u32) -> f64 {
        if bar <= 1 {
            return 0.0;
        }

        let mut beat = 0.0;
        let mut current_bar = 1;
        let mut current_ts = self.time_signature_at_bar(1);

        while current_bar < bar as usize {
            beat += current_ts.beats_per_bar();
            current_bar += 1;
            current_ts = self.time_signature_at_bar(current_bar as u32);
        }

        beat
    }

    /// 拍 → 小节和拍
    pub fn beat_to_bar_beat(&self, beat: f64) -> (u32, f64) {
        let mut remaining = beat;
        let mut current_bar = 1u32;
        let mut current_ts = self.time_signature_at_bar(1);

        loop {
            let bar_beats = current_ts.beats_per_bar();
            if remaining < bar_beats {
                return (current_bar, remaining + 1.0);
            }
            remaining -= bar_beats;
            current_bar += 1;
            current_ts = self.time_signature_at_bar(current_bar);

            // 安全检查
            if current_bar > 100000 {
                return (current_bar, 1.0);
            }
        }
    }

    /// 设置循环区域
    pub fn set_loop(&mut self, start_beat: f64, end_beat: f64) {
        self.loop_start = Some(start_beat);
        self.loop_end = Some(end_beat);
    }

    /// 清除循环
    pub fn clear_loop(&mut self) {
        self.loop_start = None;
        self.loop_end = None;
    }

    /// 是否有循环
    pub fn has_loop(&self) -> bool {
        self.loop_start.is_some()
    }

    /// 获取循环区域
    pub fn get_loop(&self) -> Option<(f64, f64)> {
        match (self.loop_start, self.loop_end) {
            (Some(s), Some(e)) => Some((s, e)),
            _ => None,
        }
    }

    /// 应用循环 — 如果超出循环终点则回到循环起点
    pub fn apply_loop(&self, beat: f64) -> f64 {
        if let (Some(start), Some(end)) = (self.loop_start, self.loop_end) {
            if beat >= end {
                let loop_length = end - start;
                if loop_length > 0.0 {
                    return start + ((beat - start) % loop_length);
                }
            }
        }
        beat
    }

    /// 获取小节数量（基于拍号变化计算）
    pub fn bar_count(&self, total_beats: f64) -> u32 {
        let (bar, _) = self.beat_to_bar_beat(total_beats);
        bar
    }

    /// 默认BPM
    pub fn default_bpm(&self) -> f64 {
        self.default_bpm
    }

    /// 默认拍号
    pub fn default_time_signature(&self) -> TimeSignature {
        self.default_time_signature
    }

    /// 采样率
    pub fn sample_rate(&self) -> f64 {
        self.sample_rate
    }

    /// 设置默认BPM
    pub fn set_bpm(&mut self, bpm: f64) {
        self.default_bpm = bpm;
        // 更新初始速度变化
        self.tempo_changes.insert(0, TempoChange::step(0.0, bpm));
    }

    /// 获取所有拍号变化
    pub fn time_signature_changes(&self) -> &BTreeMap<u32, TimeSignature> {
        &self.time_signature_changes
    }

    /// 获取所有速度变化
    pub fn tempo_changes(&self) -> &BTreeMap<u64, TempoChange> {
        &self.tempo_changes
    }
}

/// 时间线光标 — 在时间线上导航的辅助工具
pub struct TimelineCursor {
    /// 当前拍位置
    current_beat: f64,
    /// 时间线引用
    timeline: Timeline,
}

impl TimelineCursor {
    /// 创建新的时间线光标
    pub fn new(timeline: Timeline) -> Self {
        Self {
            current_beat: 0.0,
            timeline,
        }
    }

    /// 获取当前拍
    pub fn beat(&self) -> f64 {
        self.current_beat
    }

    /// 设置当前拍
    pub fn set_beat(&mut self, beat: f64) {
        self.current_beat = beat.max(0.0);
    }

    /// 移动到指定小节
    pub fn go_to_bar(&mut self, bar: u32) {
        self.current_beat = self.timeline.bar_to_beat(bar);
    }

    /// 移动到指定小节和拍
    pub fn go_to_bar_beat(&mut self, bar: u32, beat: f64) {
        let bar_start = self.timeline.bar_to_beat(bar);
        self.current_beat = bar_start + beat - 1.0;
    }

    /// 前进N拍
    pub fn advance_beats(&mut self, beats: f64) {
        self.current_beat += beats;
        self.current_beat = self.timeline.apply_loop(self.current_beat);
    }

    /// 前进N小节
    pub fn advance_bars(&mut self, bars: u32) {
        let current_bar = self.bar();
        let target_bar = current_bar + bars;
        self.current_beat = self.timeline.bar_to_beat(target_bar);
        self.current_beat = self.timeline.apply_loop(self.current_beat);
    }

    /// 后退N拍
    pub fn retreat_beats(&mut self, beats: f64) {
        self.current_beat = (self.current_beat - beats).max(0.0);
    }

    /// 回到起点
    pub fn reset(&mut self) {
        self.current_beat = 0.0;
    }

    /// 当前小节
    pub fn bar(&self) -> u32 {
        self.timeline.beat_to_bar_beat(self.current_beat).0
    }

    /// 当前小节内的拍
    pub fn beat_in_bar(&self) -> f64 {
        self.timeline.beat_to_bar_beat(self.current_beat).1
    }

    /// 当前帧
    pub fn frame(&self) -> u64 {
        self.timeline.beat_to_frame(self.current_beat)
    }

    /// 当前秒
    pub fn seconds(&self) -> f64 {
        self.timeline.beat_to_seconds(self.current_beat)
    }

    /// 当前BPM
    pub fn bpm(&self) -> f64 {
        self.timeline.bpm_at_beat(self.current_beat)
    }

    /// 当前拍号
    pub fn time_signature(&self) -> TimeSignature {
        self.timeline.time_signature_at_bar(self.bar())
    }

    /// 当前时间位置
    pub fn position(&self) -> TimePosition {
        let (bar, beat) = self.timeline.beat_to_bar_beat(self.current_beat);
        TimePosition::from_bar_beat(bar, beat)
    }

    /// 获取时间线引用
    pub fn timeline(&self) -> &Timeline {
        &self.timeline
    }

    /// 获取时间线可变引用
    pub fn timeline_mut(&mut self) -> &mut Timeline {
        &mut self.timeline
    }

    /// 格式化当前位置
    pub fn display_position(&self) -> String {
        let (bar, beat) = self.timeline.beat_to_bar_beat(self.current_beat);
        format!("{}:{} @ {:.1}BPM", bar, beat as u32, self.bpm())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_time_signature() {
        let ts = TimeSignature::four_four();
        assert_eq!(ts.numerator, 4);
        assert_eq!(ts.denominator, 4);
        assert!((ts.beats_per_bar() - 4.0).abs() < 1e-10);

        let ts = TimeSignature::six_eight();
        assert!((ts.beats_per_bar() - 3.0).abs() < 1e-10);
    }

    #[test]
    fn test_time_signature_display() {
        assert_eq!(TimeSignature::four_four().to_string_display(), "4/4");
        assert_eq!(TimeSignature::three_four().to_string_display(), "3/4");
        assert_eq!(TimeSignature::six_eight().to_string_display(), "6/8");
    }

    #[test]
    fn test_time_position() {
        let pos = TimePosition::from_bar_beat(3, 2.0);
        assert_eq!(pos.bar, 3);
        assert!((pos.beat - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_time_position_to_total_beats() {
        let pos = TimePosition::from_bar_beat(1, 1.0);
        assert!((pos.to_total_beats() - 0.0).abs() < 1e-10);

        let pos = TimePosition::from_bar_beat(2, 1.0);
        assert!((pos.to_total_beats() - 4.0).abs() < 1e-10);

        let pos = TimePosition::from_bar_beat(3, 3.0);
        assert!((pos.to_total_beats() - 10.0).abs() < 1e-10);
    }

    #[test]
    fn test_time_position_display() {
        let pos = TimePosition::new(5, 3.0, 120);
        assert_eq!(format!("{}", pos), "5:3:120");
    }

    #[test]
    fn test_timeline_basic() {
        let timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        assert!((timeline.default_bpm() - 120.0).abs() < 1e-10);
        assert_eq!(timeline.default_time_signature(), TimeSignature::four_four());
    }

    #[test]
    fn test_timeline_beat_to_seconds() {
        let timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        // 120BPM = 2 beats/sec
        assert!((timeline.beat_to_seconds(2.0) - 1.0).abs() < 1e-10);
        assert!((timeline.beat_to_seconds(4.0) - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_seconds_to_beat() {
        let timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        assert!((timeline.seconds_to_beat(1.0) - 2.0).abs() < 1e-10);
        assert!((timeline.seconds_to_beat(2.0) - 4.0).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_beat_to_frame() {
        let timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        // 120BPM = 2 beats/sec = 1 beat = 22050 frames
        let frame = timeline.beat_to_frame(1.0);
        assert_eq!(frame, 22050);
    }

    #[test]
    fn test_timeline_bar_to_beat() {
        let timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        assert!((timeline.bar_to_beat(1) - 0.0).abs() < 1e-10);
        assert!((timeline.bar_to_beat(2) - 4.0).abs() < 1e-10);
        assert!((timeline.bar_to_beat(3) - 8.0).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_beat_to_bar_beat() {
        let timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        let (bar, beat) = timeline.beat_to_bar_beat(0.0);
        assert_eq!(bar, 1);
        assert!((beat - 1.0).abs() < 1e-10);

        let (bar, beat) = timeline.beat_to_bar_beat(4.0);
        assert_eq!(bar, 2);
        assert!((beat - 1.0).abs() < 1e-10);

        let (bar, beat) = timeline.beat_to_bar_beat(5.5);
        assert_eq!(bar, 2);
        assert!((beat - 2.5).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_time_signature_change() {
        let mut timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        timeline.add_time_signature_change(3, TimeSignature::three_four());

        // 第1-2小节是4/4，第3小节起是3/4
        assert_eq!(timeline.time_signature_at_bar(1), TimeSignature::four_four());
        assert_eq!(timeline.time_signature_at_bar(2), TimeSignature::four_four());
        assert_eq!(timeline.time_signature_at_bar(3), TimeSignature::three_four());
        assert_eq!(timeline.time_signature_at_bar(5), TimeSignature::three_four());
    }

    #[test]
    fn test_timeline_tempo_change() {
        let mut timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        assert!((timeline.bpm_at_beat(0.0) - 120.0).abs() < 1e-10);

        timeline.add_tempo_change(TempoChange::step(4.0, 140.0));
        assert!((timeline.bpm_at_beat(3.0) - 120.0).abs() < 1e-10);
        assert!((timeline.bpm_at_beat(4.0) - 140.0).abs() < 1e-10);
        assert!((timeline.bpm_at_beat(8.0) - 140.0).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_set_bpm() {
        let mut timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        timeline.set_bpm(140.0);
        assert!((timeline.default_bpm() - 140.0).abs() < 1e-10);
        assert!((timeline.bpm_at_beat(0.0) - 140.0).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_loop() {
        let mut timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);

        assert!(!timeline.has_loop());

        timeline.set_loop(4.0, 12.0);
        assert!(timeline.has_loop());

        let looped = timeline.apply_loop(12.0);
        assert!((looped - 4.0).abs() < 1e-10);

        let looped = timeline.apply_loop(15.0);
        assert!((looped - 7.0).abs() < 1e-10);

        timeline.clear_loop();
        assert!(!timeline.has_loop());
    }

    #[test]
    fn test_timeline_cursor_basic() {
        let timeline = Timeline::default_120bpm(44100.0);
        let mut cursor = TimelineCursor::new(timeline);

        assert!((cursor.beat() - 0.0).abs() < 1e-10);
        assert_eq!(cursor.bar(), 1);

        cursor.advance_beats(4.0);
        assert_eq!(cursor.bar(), 2);

        cursor.advance_bars(1);
        assert_eq!(cursor.bar(), 3);
    }

    #[test]
    fn test_timeline_cursor_go_to() {
        let timeline = Timeline::default_120bpm(44100.0);
        let mut cursor = TimelineCursor::new(timeline);

        cursor.go_to_bar(5);
        assert_eq!(cursor.bar(), 5);

        cursor.go_to_bar_beat(3, 2.0);
        assert_eq!(cursor.bar(), 3);
    }

    #[test]
    fn test_timeline_cursor_retreat() {
        let timeline = Timeline::default_120bpm(44100.0);
        let mut cursor = TimelineCursor::new(timeline);

        cursor.advance_beats(10.0);
        cursor.retreat_beats(3.0);
        assert!((cursor.beat() - 7.0).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_cursor_reset() {
        let timeline = Timeline::default_120bpm(44100.0);
        let mut cursor = TimelineCursor::new(timeline);

        cursor.advance_beats(20.0);
        cursor.reset();
        assert!((cursor.beat() - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_cursor_display() {
        let timeline = Timeline::default_120bpm(44100.0);
        let mut cursor = TimelineCursor::new(timeline);

        cursor.go_to_bar(5);
        let display = cursor.display_position();
        assert!(display.contains("5"));
        assert!(display.contains("120"));
    }

    #[test]
    fn test_timeline_cursor_seconds() {
        let timeline = Timeline::default_120bpm(44100.0);
        let mut cursor = TimelineCursor::new(timeline);

        cursor.advance_beats(2.0);
        assert!((cursor.seconds() - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_cursor_with_loop() {
        let timeline = Timeline::default_120bpm(44100.0);
        let mut cursor = TimelineCursor::new(timeline);
        cursor.timeline_mut().set_loop(4.0, 12.0);

        cursor.set_beat(0.0);
        cursor.advance_beats(14.0);
        // 14 beats with loop 4-12: 14 > 12, should wrap
        let beat = cursor.beat();
        assert!(beat >= 4.0 && beat < 12.0, "Beat should be in loop range, got {}", beat);
    }

    #[test]
    fn test_3_4_time_signature() {
        let timeline = Timeline::new(120.0, TimeSignature::three_four(), 44100.0);
        // 3/4拍：每小节3拍
        assert!((timeline.bar_to_beat(2) - 3.0).abs() < 1e-10);
        assert!((timeline.bar_to_beat(3) - 6.0).abs() < 1e-10);
    }

    #[test]
    fn test_mixed_time_signatures() {
        let mut timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        // 第1-2小节 4/4，第3-4小节 3/4
        timeline.add_time_signature_change(3, TimeSignature::three_four());

        // 小节1: 0-4拍, 小节2: 4-8拍, 小节3: 8-11拍(3/4), 小节4: 11-14拍(3/4)
        assert!((timeline.bar_to_beat(1) - 0.0).abs() < 1e-10);
        assert!((timeline.bar_to_beat(2) - 4.0).abs() < 1e-10);
        assert!((timeline.bar_to_beat(3) - 8.0).abs() < 1e-10);
        assert!((timeline.bar_to_beat(4) - 11.0).abs() < 1e-10);
        assert!((timeline.bar_to_beat(5) - 14.0).abs() < 1e-10);
    }

    #[test]
    fn test_timeline_bar_count() {
        let timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        assert_eq!(timeline.bar_count(4.0), 1);
        assert_eq!(timeline.bar_count(8.0), 2);
        assert_eq!(timeline.bar_count(16.0), 4);
    }

    #[test]
    fn test_timeline_remove_time_signature_change() {
        let mut timeline = Timeline::new(120.0, TimeSignature::four_four(), 44100.0);
        timeline.add_time_signature_change(3, TimeSignature::three_four());
        timeline.remove_time_signature_change(3);
        assert_eq!(timeline.time_signature_at_bar(3), TimeSignature::four_four());
    }
}
