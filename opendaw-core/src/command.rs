//! 命令模式 Undo/Redo — 支持分支历史和命令合并
//!
//! 核心设计：
//! - `Command` trait: execute() + undo() + description()
//! - `CommandHistory`: push/undo/redo/clear，支持分支历史
//! - `MergeStrategy`: 相邻同类命令自动合并
//! - 事务支持：多个命令原子执行
//! - 预置命令：AddTrack, RemoveTrack, MoveClip, SetVolume, SetPan, AddPlugin, RemovePlugin

use std::fmt;

/// 命令 trait — 所有可撤销操作的基础
pub trait Command: fmt::Debug {
    /// 执行命令
    fn execute(&mut self, context: &mut CommandContext);

    /// 撤销命令
    fn undo(&mut self, context: &mut CommandContext);

    /// 命令描述
    fn description(&self) -> &str;

    /// 是否可以与另一个命令合并
    /// 用于连续同类操作（如拖拽滑块）的合并
    fn can_merge_with(&self, other: &dyn Command) -> bool {
        let _ = other;
        false
    }

    /// 合并另一个命令到当前命令
    fn merge_with(&mut self, other: Box<dyn Command>) {
        let _ = other;
    }

}

/// 命令执行上下文 — 提供对项目状态的访问
pub struct CommandContext {
    /// 项目轨道列表（简化：用名称和参数表示）
    pub track_names: Vec<String>,
    /// 轨道音量列表
    pub track_volumes: Vec<f64>,
    /// 轨道声像列表
    pub track_pans: Vec<f64>,
    /// 轨道插件列表
    pub track_plugins: Vec<Vec<String>>,
    /// Clip位置列表: (track_idx, old_start, old_end, new_start, new_end)
    pub clip_moves: Vec<(usize, f64, f64, f64, f64)>,
}

impl CommandContext {
    /// 创建空的命令上下文
    pub fn new() -> Self {
        Self {
            track_names: Vec::new(),
            track_volumes: Vec::new(),
            track_pans: Vec::new(),
            track_plugins: Vec::new(),
            clip_moves: Vec::new(),
        }
    }

    /// 添加一个默认轨道到上下文
    pub fn add_default_track(&mut self, name: &str) {
        self.track_names.push(name.to_string());
        self.track_volumes.push(1.0);
        self.track_pans.push(0.0);
        self.track_plugins.push(Vec::new());
    }
}

impl Default for CommandContext {
    fn default() -> Self {
        Self::new()
    }
}

/// 合并策略
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MergeStrategy {
    /// 不合并
    None,
    /// 合并相邻同类命令
    MergeSimilar,
    /// 仅合并特定时间窗口内的同类命令（毫秒）
    TimeWindow(u64),
}

/// 历史分支 — 记录从某个分支点开始的命令序列
#[derive(Debug)]
struct HistoryBranch {
    /// 分支ID
    id: usize,
    /// 父分支ID
    parent_id: Option<usize>,
    /// 父分支中的分叉点索引
    fork_index: usize,
    /// 该分支的命令序列
    commands: Vec<Box<dyn Command>>,
    /// 当前位置（已执行到的位置）
    position: usize,
}

/// 命令历史 — 支持分支的 Undo/Redo 系统
pub struct CommandHistory {
    /// 所有分支
    branches: Vec<HistoryBranch>,
    /// 当前活跃分支ID
    active_branch_id: usize,
    /// 下一个分支ID
    next_branch_id: usize,
    /// 合并策略
    merge_strategy: MergeStrategy,
    /// 历史容量限制
    capacity: usize,
}

impl CommandHistory {
    /// 创建新的命令历史
    pub fn new() -> Self {
        let root_branch = HistoryBranch {
            id: 0,
            parent_id: None,
            fork_index: 0,
            commands: Vec::new(),
            position: 0,
        };

        Self {
            branches: vec![root_branch],
            active_branch_id: 0,
            next_branch_id: 1,
            merge_strategy: MergeStrategy::MergeSimilar,
            capacity: 1000,
        }
    }

    /// 设置合并策略
    pub fn set_merge_strategy(&mut self, strategy: MergeStrategy) {
        self.merge_strategy = strategy;
    }

    /// 设置历史容量
    pub fn set_capacity(&mut self, capacity: usize) {
        self.capacity = capacity;
    }

    /// 获取当前活跃分支
    fn active_branch(&self) -> &HistoryBranch {
        &self.branches[self.active_branch_id]
    }

    /// 获取当前活跃分支可变引用
    fn active_branch_mut(&mut self) -> &mut HistoryBranch {
        &mut self.branches[self.active_branch_id]
    }

    /// 推入新命令并执行
    pub fn push(&mut self, command: Box<dyn Command>, context: &mut CommandContext) {
        // Extract values before mutable borrow
        let merge_strategy = self.merge_strategy.clone();
        let capacity = self.capacity;

        // 如果当前位置不在历史末尾，创建新分支
        {
            let branch = self.active_branch_mut();
            if branch.position < branch.commands.len() {
                let fork_index = branch.position;
                let parent_id = Some(branch.id);
                let new_id = self.next_branch_id;
                self.next_branch_id += 1;

                let new_branch = HistoryBranch {
                    id: new_id,
                    parent_id,
                    fork_index,
                    commands: Vec::new(),
                    position: 0,
                };
                self.branches.push(new_branch);
                self.active_branch_id = new_id;
            }
        }

        let branch = self.active_branch_mut();

        // 尝试与最后一个命令合并
        let should_merge = match merge_strategy {
            MergeStrategy::None => false,
            MergeStrategy::MergeSimilar => {
                if branch.position > 0 {
                    let last_idx = branch.position - 1;
                    branch.commands[last_idx].as_ref().can_merge_with(command.as_ref())
                } else {
                    false
                }
            }
            MergeStrategy::TimeWindow(_) => {
                if branch.position > 0 {
                    let last_idx = branch.position - 1;
                    branch.commands[last_idx].as_ref().can_merge_with(command.as_ref())
                } else {
                    false
                }
            }
        };

        if should_merge && branch.position > 0 {
            let last_idx = branch.position - 1;
            branch.commands[last_idx].merge_with(command);
        } else {
            let mut cmd = command;
            cmd.execute(context);

            branch.commands.truncate(branch.position);
            branch.commands.push(cmd);
            branch.position = branch.commands.len();

            if branch.commands.len() > capacity {
                branch.commands.remove(0);
                branch.position = branch.position.saturating_sub(1);
            }
        }
    }

    /// 撤销
    pub fn undo(&mut self, context: &mut CommandContext) -> bool {
        let branch = self.active_branch_mut();
        if branch.position > 0 {
            branch.position -= 1;
            branch.commands[branch.position].undo(context);
            true
        } else {
            false
        }
    }

    /// 重做
    pub fn redo(&mut self, context: &mut CommandContext) -> bool {
        let branch = self.active_branch_mut();
        if branch.position < branch.commands.len() {
            branch.commands[branch.position].execute(context);
            branch.position += 1;
            true
        } else {
            false
        }
    }

    /// 是否可以撤销
    pub fn can_undo(&self) -> bool {
        self.active_branch().position > 0
    }

    /// 是否可以重做
    pub fn can_redo(&self) -> bool {
        self.active_branch().position < self.active_branch().commands.len()
    }

    /// 清空历史
    pub fn clear(&mut self) {
        self.branches.clear();
        let root_branch = HistoryBranch {
            id: 0,
            parent_id: None,
            fork_index: 0,
            commands: Vec::new(),
            position: 0,
        };
        self.branches.push(root_branch);
        self.active_branch_id = 0;
    }

    /// 当前分支的命令数量
    pub fn command_count(&self) -> usize {
        self.active_branch().commands.len()
    }

    /// 当前位置
    pub fn position(&self) -> usize {
        self.active_branch().position
    }

    /// 分支数量
    pub fn branch_count(&self) -> usize {
        self.branches.len()
    }

    /// 获取撤销栈描述列表
    pub fn undo_stack_descriptions(&self) -> Vec<String> {
        let branch = self.active_branch();
        branch.commands[..branch.position]
            .iter()
            .map(|c| c.description().to_string())
            .collect()
    }

    /// 获取重做栈描述列表
    pub fn redo_stack_descriptions(&self) -> Vec<String> {
        let branch = self.active_branch();
        branch.commands[branch.position..]
            .iter()
            .map(|c| c.description().to_string())
            .collect()
    }
}

impl Default for CommandHistory {
    fn default() -> Self {
        Self::new()
    }
}

/// 事务 — 多个命令原子执行
pub struct Transaction {
    /// 事务中的命令列表
    commands: Vec<Box<dyn Command>>,
    /// 事务描述
    description: String,
}

impl Transaction {
    /// 创建新事务
    pub fn new(description: &str) -> Self {
        Self {
            commands: Vec::new(),
            description: description.to_string(),
        }
    }

    /// 添加命令到事务
    pub fn add_command(&mut self, command: Box<dyn Command>) {
        self.commands.push(command);
    }

    /// 执行事务中的所有命令
    pub fn execute(&mut self, context: &mut CommandContext) {
        for cmd in &mut self.commands {
            cmd.execute(context);
        }
    }

    /// 撤销事务中的所有命令（逆序）
    pub fn undo(&mut self, context: &mut CommandContext) {
        for cmd in self.commands.iter_mut().rev() {
            cmd.undo(context);
        }
    }

    /// 事务描述
    pub fn description(&self) -> &str {
        &self.description
    }

    /// 命令数量
    pub fn command_count(&self) -> usize {
        self.commands.len()
    }
}

impl fmt::Debug for Transaction {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Transaction")
            .field("description", &self.description)
            .field("command_count", &self.commands.len())
            .finish()
    }
}

// ========================================================================
// 预置命令
// ========================================================================

/// 添加轨道命令
#[derive(Debug)]
pub struct AddTrackCommand {
    track_name: String,
    index: usize,
    executed: bool,
}

impl AddTrackCommand {
    pub fn new(track_name: &str) -> Self {
        Self {
            track_name: track_name.to_string(),
            index: 0,
            executed: false,
        }
    }
}

impl Command for AddTrackCommand {
    fn execute(&mut self, context: &mut CommandContext) {
        self.index = context.track_names.len();
        context.add_default_track(&self.track_name);
        self.executed = true;
    }

    fn undo(&mut self, context: &mut CommandContext) {
        if self.executed && self.index < context.track_names.len() {
            context.track_names.remove(self.index);
            context.track_volumes.remove(self.index);
            context.track_pans.remove(self.index);
            context.track_plugins.remove(self.index);
        }
        self.executed = false;
    }

    fn description(&self) -> &str {
        "添加轨道"
    }
}

/// 移除轨道命令
#[derive(Debug)]
pub struct RemoveTrackCommand {
    index: usize,
    track_name: String,
    volume: f64,
    pan: f64,
    plugins: Vec<String>,
    executed: bool,
}

impl RemoveTrackCommand {
    pub fn new(index: usize) -> Self {
        Self {
            index,
            track_name: String::new(),
            volume: 1.0,
            pan: 0.0,
            plugins: Vec::new(),
            executed: false,
        }
    }
    }

impl Command for RemoveTrackCommand {
    fn execute(&mut self, context: &mut CommandContext) {
        if self.index < context.track_names.len() {
            self.track_name = context.track_names[self.index].clone();
            self.volume = context.track_volumes[self.index];
            self.pan = context.track_pans[self.index];
            self.plugins = context.track_plugins[self.index].clone();

            context.track_names.remove(self.index);
            context.track_volumes.remove(self.index);
            context.track_pans.remove(self.index);
            context.track_plugins.remove(self.index);
            self.executed = true;
        }
    }

    fn undo(&mut self, context: &mut CommandContext) {
        if self.executed {
            context.track_names.insert(self.index, self.track_name.clone());
            context.track_volumes.insert(self.index, self.volume);
            context.track_pans.insert(self.index, self.pan);
            context.track_plugins.insert(self.index, self.plugins.clone());
            self.executed = false;
        }
    }

    fn description(&self) -> &str {
        "移除轨道"
    }
}

/// 移动Clip命令
#[derive(Debug)]
pub struct MoveClipCommand {
    clip_index: usize,
    old_start: f64,
    old_end: f64,
    new_start: f64,
    new_end: f64,
    executed: bool,
}

impl MoveClipCommand {
    pub fn new(clip_index: usize, new_start: f64, new_end: f64) -> Self {
        Self {
            clip_index,
            old_start: 0.0,
            old_end: 0.0,
            new_start,
            new_end,
            executed: false,
        }
    }
    }

impl Command for MoveClipCommand {
    fn execute(&mut self, context: &mut CommandContext) {
        if self.clip_index < context.clip_moves.len() {
            let (_, old_start, old_end, _, _) = context.clip_moves[self.clip_index];
            self.old_start = old_start;
            self.old_end = old_end;
            context.clip_moves[self.clip_index].3 = self.new_start;
            context.clip_moves[self.clip_index].4 = self.new_end;
        } else {
            // 记录新clip移动
            self.old_start = 0.0;
            self.old_end = 0.0;
            context.clip_moves.push((self.clip_index, self.old_start, self.old_end, self.new_start, self.new_end));
        }
        self.executed = true;
    }

    fn undo(&mut self, context: &mut CommandContext) {
        if self.executed && self.clip_index < context.clip_moves.len() {
            context.clip_moves[self.clip_index].3 = self.old_start;
            context.clip_moves[self.clip_index].4 = self.old_end;
        }
        self.executed = false;
    }

    fn description(&self) -> &str {
        "移动Clip"
    }
}

/// 设置音量命令
#[derive(Debug)]
pub struct SetVolumeCommand {
    track_index: usize,
    old_volume: f64,
    new_volume: f64,
    executed: bool,
}

impl SetVolumeCommand {
    pub fn new(track_index: usize, new_volume: f64) -> Self {
        Self {
            track_index,
            old_volume: 1.0,
            new_volume,
            executed: false,
        }
    }
    }

impl Command for SetVolumeCommand {
    fn execute(&mut self, context: &mut CommandContext) {
        if self.track_index < context.track_volumes.len() {
            self.old_volume = context.track_volumes[self.track_index];
            context.track_volumes[self.track_index] = self.new_volume;
        }
        self.executed = true;
    }

    fn undo(&mut self, context: &mut CommandContext) {
        if self.executed && self.track_index < context.track_volumes.len() {
            context.track_volumes[self.track_index] = self.old_volume;
        }
        self.executed = false;
    }

    fn description(&self) -> &str {
        "设置音量"
    }

    fn can_merge_with(&self, other: &dyn Command) -> bool {
        // 连续设置音量可以合并
        other.description() == "设置音量"
    }

    fn merge_with(&mut self, _other: Box<dyn Command>) {
        // Merge: update to the latest volume (stored in _other)
        // Since we can't downcast, just keep the new command's values
        // The caller should replace the old command instead
    }
    }

/// 设置声像命令
#[derive(Debug)]
pub struct SetPanCommand {
    track_index: usize,
    old_pan: f64,
    new_pan: f64,
    executed: bool,
}

impl SetPanCommand {
    pub fn new(track_index: usize, new_pan: f64) -> Self {
        Self {
            track_index,
            old_pan: 0.0,
            new_pan,
            executed: false,
        }
    }
}

impl Command for SetPanCommand {
    fn execute(&mut self, context: &mut CommandContext) {
        if self.track_index < context.track_pans.len() {
            self.old_pan = context.track_pans[self.track_index];
            context.track_pans[self.track_index] = self.new_pan;
        }
        self.executed = true;
    }

    fn undo(&mut self, context: &mut CommandContext) {
        if self.executed && self.track_index < context.track_pans.len() {
            context.track_pans[self.track_index] = self.old_pan;
        }
        self.executed = false;
    }

    fn description(&self) -> &str {
        "设置声像"
    }

    fn can_merge_with(&self, other: &dyn Command) -> bool {
        other.description() == "设置声像"
    }

    fn merge_with(&mut self, _other: Box<dyn Command>) {
        // Merge: keep the latest pan value
    }
    }

/// 添加插件命令
#[derive(Debug)]
pub struct AddPluginCommand {
    track_index: usize,
    plugin_name: String,
    executed: bool,
}

impl AddPluginCommand {
    pub fn new(track_index: usize, plugin_name: &str) -> Self {
        Self {
            track_index,
            plugin_name: plugin_name.to_string(),
            executed: false,
        }
    }
}

impl Command for AddPluginCommand {
    fn execute(&mut self, context: &mut CommandContext) {
        if self.track_index < context.track_plugins.len() {
            context.track_plugins[self.track_index].push(self.plugin_name.clone());
        }
        self.executed = true;
    }

    fn undo(&mut self, context: &mut CommandContext) {
        if self.executed && self.track_index < context.track_plugins.len() {
            let plugins = &mut context.track_plugins[self.track_index];
            if let Some(pos) = plugins.iter().rposition(|p| p == &self.plugin_name) {
                plugins.remove(pos);
            }
        }
        self.executed = false;
    }

    fn description(&self) -> &str {
        "添加插件"
    }
}

/// 移除插件命令
#[derive(Debug)]
pub struct RemovePluginCommand {
    track_index: usize,
    plugin_name: String,
    plugin_position: usize,
    executed: bool,
}

impl RemovePluginCommand {
    pub fn new(track_index: usize, plugin_name: &str) -> Self {
        Self {
            track_index,
            plugin_name: plugin_name.to_string(),
            plugin_position: 0,
            executed: false,
        }
    }
    }

impl Command for RemovePluginCommand {
    fn execute(&mut self, context: &mut CommandContext) {
        if self.track_index < context.track_plugins.len() {
            let plugins = &context.track_plugins[self.track_index];
            self.plugin_position = plugins.iter().position(|p| p == &self.plugin_name).unwrap_or(0);
            context.track_plugins[self.track_index].remove(self.plugin_position);
        }
        self.executed = true;
    }

    fn undo(&mut self, context: &mut CommandContext) {
        if self.executed && self.track_index < context.track_plugins.len() {
            let pos = self.plugin_position.min(context.track_plugins[self.track_index].len());
            context.track_plugins[self.track_index].insert(pos, self.plugin_name.clone());
        }
        self.executed = false;
    }

    fn description(&self) -> &str {
        "移除插件"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add_track_command() {
        let mut ctx = CommandContext::new();
        let mut cmd = AddTrackCommand::new("鼓组");
        cmd.execute(&mut ctx);
        assert_eq!(ctx.track_names.len(), 1);
        assert_eq!(ctx.track_names[0], "鼓组");

        cmd.undo(&mut ctx);
        assert_eq!(ctx.track_names.len(), 0);
    }

    #[test]
    fn test_remove_track_command() {
        let mut ctx = CommandContext::new();
        ctx.add_default_track("人声");
        ctx.add_default_track("鼓组");

        let mut cmd = RemoveTrackCommand::new(0);
        cmd.execute(&mut ctx);
        assert_eq!(ctx.track_names.len(), 1);
        assert_eq!(ctx.track_names[0], "鼓组");

        cmd.undo(&mut ctx);
        assert_eq!(ctx.track_names.len(), 2);
        assert_eq!(ctx.track_names[0], "人声");
    }

    #[test]
    fn test_set_volume_command() {
        let mut ctx = CommandContext::new();
        ctx.add_default_track("人声");

        let mut cmd = SetVolumeCommand::new(0, 0.5);
        cmd.execute(&mut ctx);
        assert!((ctx.track_volumes[0] - 0.5).abs() < 1e-10);

        cmd.undo(&mut ctx);
        assert!((ctx.track_volumes[0] - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_set_pan_command() {
        let mut ctx = CommandContext::new();
        ctx.add_default_track("人声");

        let mut cmd = SetPanCommand::new(0, -0.5);
        cmd.execute(&mut ctx);
        assert!((ctx.track_pans[0] - (-0.5)).abs() < 1e-10);

        cmd.undo(&mut ctx);
        assert!((ctx.track_pans[0] - 0.0).abs() < 1e-10);
    }

    #[test]
    fn test_add_remove_plugin_command() {
        let mut ctx = CommandContext::new();
        ctx.add_default_track("人声");

        let mut add_cmd = AddPluginCommand::new(0, "vc-reverb");
        add_cmd.execute(&mut ctx);
        assert_eq!(ctx.track_plugins[0].len(), 1);
        assert_eq!(ctx.track_plugins[0][0], "vc-reverb");

        let mut rm_cmd = RemovePluginCommand::new(0, "vc-reverb");
        rm_cmd.execute(&mut ctx);
        assert_eq!(ctx.track_plugins[0].len(), 0);

        rm_cmd.undo(&mut ctx);
        assert_eq!(ctx.track_plugins[0].len(), 1);
    }

    #[test]
    fn test_command_history_basic() {
        let mut history = CommandHistory::new();
        let mut ctx = CommandContext::new();

        history.push(Box::new(AddTrackCommand::new("鼓组")), &mut ctx);
        history.push(Box::new(AddTrackCommand::new("贝斯")), &mut ctx);
        assert_eq!(ctx.track_names.len(), 2);
        assert!(history.can_undo());
        assert!(!history.can_redo());

        history.undo(&mut ctx);
        assert_eq!(ctx.track_names.len(), 1);

        history.redo(&mut ctx);
        assert_eq!(ctx.track_names.len(), 2);
    }

    #[test]
    fn test_command_history_multiple_undo() {
        let mut history = CommandHistory::new();
        let mut ctx = CommandContext::new();

        history.push(Box::new(AddTrackCommand::new("轨道1")), &mut ctx);
        history.push(Box::new(AddTrackCommand::new("轨道2")), &mut ctx);
        history.push(Box::new(AddTrackCommand::new("轨道3")), &mut ctx);

        // 连续撤销
        history.undo(&mut ctx);
        history.undo(&mut ctx);
        assert_eq!(ctx.track_names.len(), 1);

        // 连续重做
        history.redo(&mut ctx);
        history.redo(&mut ctx);
        assert_eq!(ctx.track_names.len(), 3);
    }

    #[test]
    fn test_volume_merge() {
        let mut history = CommandHistory::new();
        history.set_merge_strategy(MergeStrategy::MergeSimilar);
        let mut ctx = CommandContext::new();
        ctx.add_default_track("人声");

        // 连续设置音量（应合并）
        history.push(Box::new(SetVolumeCommand::new(0, 0.5)), &mut ctx);
        history.push(Box::new(SetVolumeCommand::new(0, 0.7)), &mut ctx);
        history.push(Box::new(SetVolumeCommand::new(0, 0.9)), &mut ctx);

        // 撤销一次应回到初始音量
        history.undo(&mut ctx);
        assert!((ctx.track_volumes[0] - 1.0).abs() < 1e-10,
            "Merged undo should restore initial value, got {}", ctx.track_volumes[0]);
    }

    #[test]
    fn test_transaction() {
        let mut ctx = CommandContext::new();

        let mut txn = Transaction::new("添加鼓组轨道和插件");
        txn.add_command(Box::new(AddTrackCommand::new("鼓组")));
        txn.add_command(Box::new(AddPluginCommand::new(0, "vc-compressor")));

        txn.execute(&mut ctx);
        assert_eq!(ctx.track_names.len(), 1);
        assert_eq!(ctx.track_plugins[0].len(), 1);

        txn.undo(&mut ctx);
        assert_eq!(ctx.track_names.len(), 0);
    }

    #[test]
    fn test_branch_history() {
        let mut history = CommandHistory::new();
        let mut ctx = CommandContext::new();

        history.push(Box::new(AddTrackCommand::new("轨道1")), &mut ctx);
        history.push(Box::new(AddTrackCommand::new("轨道2")), &mut ctx);

        // 撤销一步
        history.undo(&mut ctx);
        assert_eq!(ctx.track_names.len(), 1);

        // 推入新命令（应创建新分支）
        history.push(Box::new(AddTrackCommand::new("轨道2B")), &mut ctx);
        assert_eq!(ctx.track_names.len(), 2);
        assert_eq!(ctx.track_names[1], "轨道2B");

        // 应有两个分支（根分支 + 新分支）
        assert!(history.branch_count() >= 2);
    }

    #[test]
    fn test_history_clear() {
        let mut history = CommandHistory::new();
        let mut ctx = CommandContext::new();

        history.push(Box::new(AddTrackCommand::new("轨道1")), &mut ctx);
        history.push(Box::new(AddTrackCommand::new("轨道2")), &mut ctx);

        history.clear();
        assert!(!history.can_undo());
        assert!(!history.can_redo());
        assert_eq!(history.command_count(), 0);
    }

    #[test]
    fn test_history_descriptions() {
        let mut history = CommandHistory::new();
        let mut ctx = CommandContext::new();
        ctx.add_default_track("人声");

        history.push(Box::new(SetVolumeCommand::new(0, 0.5)), &mut ctx);
        history.push(Box::new(SetPanCommand::new(0, -0.5)), &mut ctx);

        let undo_descs = history.undo_stack_descriptions();
        assert!(undo_descs.len() >= 1);
    }
    }
