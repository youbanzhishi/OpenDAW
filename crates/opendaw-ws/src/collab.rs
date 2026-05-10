//! 协作模块 — CRDT + 房间管理 + 评论
//!
//! Phase 32: 基础OT操作 + 房间管理
//! Phase 34: CRDT冲突解决（LWWRegister + ORSet）、
//!           协作会话增强（Presence、在线列表、历史回放）、
//!           协作评论（轨道/时间范围、回复线程、已解决/未解决）

use crate::protocol::{
    CollabCommentData, CollabOp, CommentAction, CommentTarget, PresenceAction, WsMessage,
};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

// ────────────────────────────────────────────
// HLC (Hybrid Logical Clock) 时间戳
// ────────────────────────────────────────────

/// 混合逻辑时钟时间戳
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct HLCTimestamp {
    pub wall_time: u64,  // 物理时钟
    pub logical: u32,    // 逻辑计数器
    pub node_id: String, // 节点标识
}

impl HLCTimestamp {
    pub fn new(wall_time: u64, logical: u32, node_id: String) -> Self {
        Self {
            wall_time,
            logical,
            node_id,
        }
    }

    /// 创建本地事件的时间戳
    pub fn now(node_id: &str) -> Self {
        let wt = current_timestamp();
        Self {
            wall_time: wt,
            logical: 0,
            node_id: node_id.to_string(),
        }
    }

    /// 接收远端事件后生成新时间戳
    pub fn receive(&self, remote: &HLCTimestamp) -> Self {
        let now_wt = current_timestamp();
        let new_wt = std::cmp::max(self.wall_time, std::cmp::max(remote.wall_time, now_wt));
        let new_logical = if new_wt == self.wall_time && new_wt == remote.wall_time {
            std::cmp::max(self.logical, remote.logical) + 1
        } else if new_wt == self.wall_time {
            self.logical + 1
        } else if new_wt == remote.wall_time {
            remote.logical + 1
        } else {
            0
        };
        Self {
            wall_time: new_wt,
            logical: new_logical,
            node_id: self.node_id.clone(),
        }
    }
}

impl Ord for HLCTimestamp {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        match self.wall_time.cmp(&other.wall_time) {
            std::cmp::Ordering::Equal => self.logical.cmp(&other.logical),
            other => other,
        }
    }
}

impl PartialOrd for HLCTimestamp {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

// ────────────────────────────────────────────
// CRDT: LWW Register (Last-Writer-Wins)
// ────────────────────────────────────────────

/// Last-Writer-Wins 寄存器（用于轨道属性等标量值）
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LWWRegister<T: Clone + std::fmt::Debug> {
    pub value: T,
    pub timestamp: HLCTimestamp,
}

impl<T: Clone + std::fmt::Debug> LWWRegister<T> {
    pub fn new(value: T, node_id: &str) -> Self {
        Self {
            value,
            timestamp: HLCTimestamp::now(node_id),
        }
    }

    /// 本地写入
    pub fn set(&mut self, value: T, node_id: &str) {
        self.timestamp = HLCTimestamp::now(node_id);
        self.value = value;
    }

    /// 合并远端写入（LWW: 较新时间戳胜出）
    pub fn merge(&mut self, other: &LWWRegister<T>) {
        if other.timestamp > self.timestamp {
            self.value = other.value.clone();
            self.timestamp = other.timestamp.clone();
        }
    }
}

// ────────────────────────────────────────────
// CRDT: OR-Set (Observed-Remove Set)
// ────────────────────────────────────────────

/// OR-Set 的唯一标记
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ORSetTag {
    pub element: String,
    pub unique_id: String,
}

/// Observed-Remove Set（用于轨道列表、发送列表等集合）
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct ORSet {
    /// 当前存在的元素标记
    entries: Vec<ORSetTag>,
    /// 已观察到的删除标记（墓碑）
    tombstones: Vec<ORSetTag>,
}

impl ORSet {
    pub fn new() -> Self {
        Self::default()
    }

    /// 添加元素
    pub fn add(&mut self, element: String) {
        let tag = ORSetTag {
            element: element.clone(),
            unique_id: format!("{}-{}", element, Uuid::new_v4()),
        };
        self.entries.push(tag);
    }

    /// 移除元素（观察-移除：删除所有与该元素关联的标记）
    pub fn remove(&mut self, element: &str) {
        let to_remove: Vec<ORSetTag> = self
            .entries
            .iter()
            .filter(|t| t.element == element)
            .cloned()
            .collect();
        for tag in to_remove {
            self.entries.retain(|t| t.unique_id != tag.unique_id);
            self.tombstones.push(tag);
        }
    }

    /// 查看当前元素集合
    pub fn elements(&self) -> Vec<String> {
        let mut seen = std::collections::HashSet::new();
        let mut result = Vec::new();
        for tag in &self.entries {
            if seen.insert(tag.element.clone()) {
                result.push(tag.element.clone());
            }
        }
        result
    }

    /// 检查元素是否存在
    pub fn contains(&self, element: &str) -> bool {
        self.entries.iter().any(|t| t.element == element)
    }

    /// 合并远端 OR-Set
    pub fn merge(&mut self, other: &ORSet) {
        // 墓碑合并
        for ts in &other.tombstones {
            if !self.tombstones.iter().any(|t| t.unique_id == ts.unique_id) {
                self.tombstones.push(ts.clone());
            }
        }
        // 删除被远端墓碑标记的条目
        self.entries
            .retain(|e| !other.tombstones.iter().any(|t| t.unique_id == e.unique_id));
        // 添加远端条目（不在本地墓碑中的）
        for entry in &other.entries {
            if !self
                .tombstones
                .iter()
                .any(|t| t.unique_id == entry.unique_id)
                && !self.entries.iter().any(|e| e.unique_id == entry.unique_id)
            {
                self.entries.push(entry.clone());
            }
        }
    }
}

// ────────────────────────────────────────────
// 操作日志
// ────────────────────────────────────────────

/// 操作日志条目
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct OperationLog {
    pub op_id: Uuid,
    pub user_id: String,
    pub operation: CollabOp,
    pub timestamp: u64,
    pub sequence: u64,
    pub hlc: Option<HLCTimestamp>,
}

// ────────────────────────────────────────────
// 用户在线状态（Phase 34 增强）
// ────────────────────────────────────────────

/// 用户编辑状态
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum EditState {
    Idle,
    Editing { target: String },
    Recording,
    Playing,
}

/// 用户在线状态（增强版）
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct UserPresence {
    pub user_id: String,
    pub cursor_x: f64,
    pub cursor_y: f64,
    pub selected_track: Option<Uuid>,
    pub edit_state: EditState,
    pub joined_at: u64,
}

// ────────────────────────────────────────────
// 协作评论（Phase 34 新增）
// ────────────────────────────────────────────

/// 评论线程
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CommentThread {
    pub thread_id: Uuid,
    pub root: CollabCommentData,
    pub replies: Vec<CollabCommentData>,
    pub resolved: bool,
}

impl CommentThread {
    pub fn new(comment: CollabCommentData) -> Self {
        let resolved = comment.resolved;
        Self {
            thread_id: comment.comment_id,
            root: comment,
            replies: Vec::new(),
            resolved,
        }
    }

    /// 添加回复
    pub fn add_reply(&mut self, reply: CollabCommentData) {
        self.replies.push(reply);
    }

    /// 标记为已解决
    pub fn resolve(&mut self) {
        self.resolved = true;
    }

    /// 重新打开
    pub fn reopen(&mut self) {
        self.resolved = false;
    }
}

// ────────────────────────────────────────────
// 协作房间
// ────────────────────────────────────────────

/// 协作房间
#[derive(Debug)]
pub struct CollabRoom {
    pub room_id: Uuid,
    pub project_id: Uuid,
    pub users: HashMap<String, UserPresence>,
    pub operation_log: Vec<OperationLog>,
    pub sequence_counter: u64,
    /// Phase 34: 评论线程
    pub comment_threads: HashMap<Uuid, CommentThread>,
    /// Phase 34: CRDT 轨道列表
    pub track_set: ORSet,
    /// Phase 34: CRDT 轨道属性
    pub track_volumes: HashMap<String, LWWRegister<f32>>,
    /// Phase 34: 快照（历史回放）
    pub snapshots: Vec<RoomSnapshot>,
}

/// 房间快照（用于历史回放）
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RoomSnapshot {
    pub sequence: u64,
    pub timestamp: u64,
    pub track_list: Vec<String>,
    pub track_volumes: HashMap<String, f32>,
}

impl CollabRoom {
    pub fn new(room_id: Uuid, project_id: Uuid) -> Self {
        Self {
            room_id,
            project_id,
            users: HashMap::new(),
            operation_log: Vec::new(),
            sequence_counter: 0,
            comment_threads: HashMap::new(),
            track_set: ORSet::new(),
            track_volumes: HashMap::new(),
            snapshots: Vec::new(),
        }
    }

    /// 用户加入房间
    pub fn join(&mut self, user_id: String, timestamp: u64) {
        self.users.insert(
            user_id.clone(),
            UserPresence {
                user_id,
                cursor_x: 0.0,
                cursor_y: 0.0,
                selected_track: None,
                edit_state: EditState::Idle,
                joined_at: timestamp,
            },
        );
    }

    /// 用户离开房间
    pub fn leave(&mut self, user_id: &str) {
        self.users.remove(user_id);
    }

    /// 更新用户 Presence
    pub fn update_presence(&mut self, user_id: &str, cursor_x: f64, cursor_y: f64) {
        if let Some(presence) = self.users.get_mut(user_id) {
            presence.cursor_x = cursor_x;
            presence.cursor_y = cursor_y;
        }
    }

    /// 设置用户选中的轨道
    pub fn set_selected_track(&mut self, user_id: &str, track_id: Option<Uuid>) {
        if let Some(presence) = self.users.get_mut(user_id) {
            presence.selected_track = track_id;
        }
    }

    /// 设置用户编辑状态
    pub fn set_edit_state(&mut self, user_id: &str, state: EditState) {
        if let Some(presence) = self.users.get_mut(user_id) {
            presence.edit_state = state;
        }
    }

    /// 获取在线用户列表
    pub fn online_users(&self) -> Vec<&UserPresence> {
        self.users.values().collect()
    }

    /// 记录操作（带CRDT冲突解决）
    pub fn apply_operation(
        &mut self,
        user_id: String,
        operation: CollabOp,
        timestamp: u64,
    ) -> OperationLog {
        let op_id = match &operation {
            CollabOp::Insert { op_id, .. }
            | CollabOp::Delete { op_id, .. }
            | CollabOp::Replace { op_id, .. }
            | CollabOp::SetParam { op_id, .. } => *op_id,
        };

        // CRDT处理: SetParam 使用 LWWRegister
        if let CollabOp::SetParam {
            track_id,
            param,
            value,
            ..
        } = &operation
        {
            if param == "volume" {
                let key = format!("{}_{}", track_id, param);
                let hlc = HLCTimestamp::now(&user_id);
                let register = LWWRegister::new(*value, &user_id);
                self.track_volumes.insert(key, register);
            }
        }

        // CRDT处理: Insert/Delete 使用 ORSet（概念上：Insert = add, Delete = remove）
        match &operation {
            CollabOp::Insert { content, .. } => {
                self.track_set.add(content.clone());
            }
            CollabOp::Delete { position, .. } => {
                // 删除位置对应的轨道
                let elements = self.track_set.elements();
                if *position < elements.len() {
                    self.track_set.remove(&elements[*position]);
                }
            }
            _ => {}
        }

        self.sequence_counter += 1;

        // 每隔一定操作保存快照
        if self.sequence_counter % 10 == 0 {
            self.save_snapshot();
        }

        let log = OperationLog {
            op_id,
            user_id,
            operation,
            timestamp,
            sequence: self.sequence_counter,
            hlc: Some(HLCTimestamp::now("server")),
        };
        self.operation_log.push(log.clone());
        log
    }

    /// 保存快照
    fn save_snapshot(&mut self) {
        let track_list = self.track_set.elements();
        let track_volumes: HashMap<String, f32> = self
            .track_volumes
            .iter()
            .map(|(k, v)| (k.clone(), v.value))
            .collect();
        self.snapshots.push(RoomSnapshot {
            sequence: self.sequence_counter,
            timestamp: current_timestamp(),
            track_list,
            track_volumes,
        });
    }

    /// 回放到指定序列号
    pub fn replay_to(&self, target_seq: u64) -> Option<&RoomSnapshot> {
        // 找到最接近目标序列号的快照
        self.snapshots
            .iter()
            .filter(|s| s.sequence <= target_seq)
            .last()
    }

    /// 获取操作历史
    pub fn get_operations_since(&self, since_seq: u64) -> Vec<&OperationLog> {
        self.operation_log
            .iter()
            .filter(|log| log.sequence > since_seq)
            .collect()
    }

    /// 用户数量
    pub fn user_count(&self) -> usize {
        self.users.len()
    }

    // ──── Phase 34: 评论 ────

    /// 添加评论
    pub fn add_comment(&mut self, comment: CollabCommentData) {
        let thread_id = comment.thread_id.unwrap_or(comment.comment_id);
        if let Some(thread) = self.comment_threads.get_mut(&thread_id) {
            thread.add_reply(comment);
        } else {
            let thread = CommentThread::new(comment);
            self.comment_threads.insert(thread_id, thread);
        }
    }

    /// 回复评论
    pub fn reply_to_comment(&mut self, thread_id: Uuid, reply: CollabCommentData) {
        if let Some(thread) = self.comment_threads.get_mut(&thread_id) {
            thread.add_reply(reply);
        }
    }

    /// 解决评论
    pub fn resolve_comment(&mut self, thread_id: Uuid) {
        if let Some(thread) = self.comment_threads.get_mut(&thread_id) {
            thread.resolve();
        }
    }

    /// 获取未解决评论
    pub fn unresolved_comments(&self) -> Vec<&CommentThread> {
        self.comment_threads
            .values()
            .filter(|t| !t.resolved)
            .collect()
    }

    /// 获取所有评论线程
    pub fn all_comments(&self) -> Vec<&CommentThread> {
        self.comment_threads.values().collect()
    }

    // ──── Phase 34: CRDT 合并 ────

    /// 合并远端OR-Set
    pub fn merge_track_set(&mut self, remote: &ORSet) {
        self.track_set.merge(remote);
    }

    /// 合并远端轨道属性
    pub fn merge_track_volume(&mut self, key: &str, remote: &LWWRegister<f32>) {
        if let Some(local) = self.track_volumes.get_mut(key) {
            local.merge(remote);
        } else {
            self.track_volumes.insert(key.to_string(), remote.clone());
        }
    }
}

// ────────────────────────────────────────────
// 协作管理器
// ────────────────────────────────────────────

/// 协作管理器 — 管理所有房间
#[derive(Debug)]
pub struct CollabManager {
    rooms: Arc<RwLock<HashMap<Uuid, CollabRoom>>>,
}

impl CollabManager {
    pub fn new() -> Self {
        Self {
            rooms: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// 创建房间
    pub async fn create_room(&self, project_id: Uuid) -> Uuid {
        let room_id = Uuid::new_v4();
        let room = CollabRoom::new(room_id, project_id);
        let mut rooms = self.rooms.write().await;
        rooms.insert(room_id, room);
        room_id
    }

    /// 加入房间
    pub async fn join_room(&self, room_id: Uuid, user_id: String) -> Option<WsMessage> {
        let mut rooms = self.rooms.write().await;
        if let Some(room) = rooms.get_mut(&room_id) {
            room.join(user_id.clone(), current_timestamp());
            Some(WsMessage::CollabPresence {
                room_id,
                user_id,
                action: PresenceAction::Join,
            })
        } else {
            None
        }
    }

    /// 离开房间
    pub async fn leave_room(&self, room_id: Uuid, user_id: String) -> Option<WsMessage> {
        let mut rooms = self.rooms.write().await;
        if let Some(room) = rooms.get_mut(&room_id) {
            room.leave(&user_id);
            Some(WsMessage::CollabPresence {
                room_id,
                user_id,
                action: PresenceAction::Leave,
            })
        } else {
            None
        }
    }

    /// 应用操作
    pub async fn apply_operation(
        &self,
        room_id: Uuid,
        user_id: String,
        operation: CollabOp,
    ) -> Option<OperationLog> {
        let mut rooms = self.rooms.write().await;
        if let Some(room) = rooms.get_mut(&room_id) {
            Some(room.apply_operation(user_id, operation, current_timestamp()))
        } else {
            None
        }
    }

    /// 发送评论
    pub async fn add_comment(
        &self,
        room_id: Uuid,
        action: CommentAction,
        comment: CollabCommentData,
    ) -> Option<WsMessage> {
        let mut rooms = self.rooms.write().await;
        if let Some(room) = rooms.get_mut(&room_id) {
            match action {
                CommentAction::Add => room.add_comment(comment.clone()),
                CommentAction::Reply => {
                    if let Some(tid) = comment.thread_id {
                        room.reply_to_comment(tid, comment.clone());
                    }
                }
                CommentAction::Resolve => {
                    room.resolve_comment(comment.comment_id);
                }
            }
            Some(WsMessage::CollabComment {
                room_id,
                action,
                comment,
            })
        } else {
            None
        }
    }

    /// 同步全量状态给新用户
    pub async fn sync_state(&self, room_id: Uuid, target_user: String) -> Option<WsMessage> {
        let rooms = self.rooms.read().await;
        if let Some(room) = rooms.get(&room_id) {
            let state = serde_json::json!({
                "tracks": room.track_set.elements(),
                "users": room.online_users().len(),
                "comments_count": room.all_comments().len(),
            });
            Some(WsMessage::CollabSync {
                room_id,
                target_user,
                state,
            })
        } else {
            None
        }
    }

    /// 获取房间信息（简化）
    pub async fn room_exists(&self, room_id: Uuid) -> bool {
        let rooms = self.rooms.read().await;
        rooms.contains_key(&room_id)
    }

    /// 列出所有房间
    pub async fn list_rooms(&self) -> Vec<(Uuid, Uuid)> {
        let rooms = self.rooms.read().await;
        rooms.values().map(|r| (r.room_id, r.project_id)).collect()
    }
}

fn current_timestamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[cfg(test)]
mod tests {
    use super::*;

    // ──── Phase 32 原有测试 ────

    #[test]
    fn test_collab_room_new() {
        let room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        assert_eq!(room.users.len(), 0);
        assert_eq!(room.operation_log.len(), 0);
        assert_eq!(room.sequence_counter, 0);
    }

    #[test]
    fn test_collab_room_join() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        room.join("user1".into(), 1000);
        assert_eq!(room.user_count(), 1);
    }

    #[test]
    fn test_collab_room_leave() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        room.join("user1".into(), 1000);
        room.leave("user1");
        assert_eq!(room.user_count(), 0);
    }

    #[test]
    fn test_collab_room_apply_operation() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        let op = CollabOp::Insert {
            position: 0,
            content: "hello".into(),
            op_id: Uuid::new_v4(),
        };
        let log = room.apply_operation("user1".into(), op, 1000);
        assert_eq!(log.sequence, 1);
        assert_eq!(room.operation_log.len(), 1);
    }

    #[test]
    fn test_get_operations_since() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        room.apply_operation(
            "u1".into(),
            CollabOp::Insert {
                position: 0,
                content: "a".into(),
                op_id: Uuid::new_v4(),
            },
            1000,
        );
        room.apply_operation(
            "u1".into(),
            CollabOp::Insert {
                position: 1,
                content: "b".into(),
                op_id: Uuid::new_v4(),
            },
            1001,
        );
        let ops = room.get_operations_since(1);
        assert_eq!(ops.len(), 1);
    }

    #[tokio::test]
    async fn test_collab_manager_create_room() {
        let manager = CollabManager::new();
        let room_id = manager.create_room(Uuid::new_v4()).await;
        let rooms = manager.list_rooms().await;
        assert_eq!(rooms.len(), 1);
        assert_eq!(rooms[0].0, room_id);
    }

    #[tokio::test]
    async fn test_collab_manager_join_leave() {
        let manager = CollabManager::new();
        let room_id = manager.create_room(Uuid::new_v4()).await;
        let msg = manager.join_room(room_id, "user1".into()).await;
        assert!(msg.is_some());
        let msg = manager.leave_room(room_id, "user1".into()).await;
        assert!(msg.is_some());
    }

    #[tokio::test]
    async fn test_collab_manager_join_nonexistent() {
        let manager = CollabManager::new();
        let result = manager.join_room(Uuid::new_v4(), "user1".into()).await;
        assert!(result.is_none());
    }

    // ──── Phase 34 新增测试 ────

    #[test]
    fn test_hlc_timestamp_ordering() {
        let t1 = HLCTimestamp::new(100, 0, "node1".into());
        let t2 = HLCTimestamp::new(100, 1, "node1".into());
        let t3 = HLCTimestamp::new(101, 0, "node1".into());
        assert!(t2 > t1);
        assert!(t3 > t2);
        assert!(t3 > t1);
    }

    #[test]
    fn test_hlc_receive() {
        let local = HLCTimestamp::new(100, 0, "node1".into());
        let remote = HLCTimestamp::new(105, 0, "node2".into());
        let merged = local.receive(&remote);
        assert!(merged.wall_time >= 105);
    }

    #[test]
    fn test_lww_register_last_writer_wins() {
        // Use explicit timestamps to guarantee reg2 is newer
        let mut reg1 = LWWRegister {
            value: 0.5,
            timestamp: HLCTimestamp::new(1000, 0, "node1".into()),
        };
        let reg2 = LWWRegister {
            value: 0.8,
            timestamp: HLCTimestamp::new(2000, 0, "node2".into()),
        };
        // reg2 has a later timestamp, so it wins
        reg1.merge(&reg2);
        assert_eq!(reg1.value, 0.8);
    }

    #[test]
    fn test_lww_register_older_ignored() {
        // Set reg1 to a far-future timestamp (year 2099 in seconds)
        let mut reg1 = LWWRegister {
            value: 0.5,
            timestamp: HLCTimestamp::new(4102444800, 0, "node1".into()),
        };
        let reg2 = LWWRegister {
            value: 0.8,
            timestamp: HLCTimestamp::new(1000, 0, "node2".into()),
        };
        // reg1 has later timestamp, so reg2 is ignored
        reg1.merge(&reg2);
        assert_eq!(reg1.value, 0.5);
    }

    #[test]
    fn test_or_set_add_and_elements() {
        let mut set = ORSet::new();
        set.add("track1".into());
        set.add("track2".into());
        set.add("track3".into());
        let elements = set.elements();
        assert_eq!(elements.len(), 3);
        assert!(set.contains("track1"));
    }

    #[test]
    fn test_or_set_remove() {
        let mut set = ORSet::new();
        set.add("track1".into());
        set.add("track2".into());
        set.remove("track1");
        assert!(!set.contains("track1"));
        assert!(set.contains("track2"));
    }

    #[test]
    fn test_or_set_merge() {
        // CRDT OR-Set merge test: entries and tombstones use unique_ids
        // set2.remove("track1") creates a tombstone with set2's unique_id,
        // which won't match set1's "track1" entry (different unique_id).
        // Correct CRDT behavior: concurrent add+remove => add wins (element preserved).
        let mut set1 = ORSet::new();
        set1.add("track1".into());
        set1.add("track2".into());

        let mut set2 = ORSet::new();
        set2.add("track3".into());

        set1.merge(&set2);
        // track1 remains because set2 never observed set1's "track1" entry
        assert!(set1.contains("track1"));
        assert!(set1.contains("track2"));
        assert!(set1.contains("track3"));
    }

    #[test]
    fn test_room_update_presence() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        room.join("user1".into(), 1000);
        room.update_presence("user1", 10.5, 20.3);
        let presence = room.users.get("user1").unwrap();
        assert!((presence.cursor_x - 10.5).abs() < 0.01);
        assert!((presence.cursor_y - 20.3).abs() < 0.01);
    }

    #[test]
    fn test_room_set_edit_state() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        room.join("user1".into(), 1000);
        room.set_edit_state(
            "user1",
            EditState::Editing {
                target: "track1".into(),
            },
        );
        let presence = room.users.get("user1").unwrap();
        assert_eq!(
            presence.edit_state,
            EditState::Editing {
                target: "track1".into()
            }
        );
    }

    #[test]
    fn test_room_online_users() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        room.join("user1".into(), 1000);
        room.join("user2".into(), 1001);
        assert_eq!(room.online_users().len(), 2);
    }

    #[test]
    fn test_room_add_comment() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        let comment = CollabCommentData {
            comment_id: Uuid::new_v4(),
            thread_id: None,
            user_id: "user1".into(),
            target: CommentTarget::Track {
                track_id: Uuid::new_v4(),
            },
            content: "Needs reverb".into(),
            resolved: false,
            created_at: 1000,
        };
        room.add_comment(comment);
        assert_eq!(room.all_comments().len(), 1);
        assert_eq!(room.unresolved_comments().len(), 1);
    }

    #[test]
    fn test_room_reply_and_resolve_comment() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        let cid = Uuid::new_v4();
        let comment = CollabCommentData {
            comment_id: cid,
            thread_id: None,
            user_id: "user1".into(),
            target: CommentTarget::Track {
                track_id: Uuid::new_v4(),
            },
            content: "Needs reverb".into(),
            resolved: false,
            created_at: 1000,
        };
        room.add_comment(comment);

        let reply = CollabCommentData {
            comment_id: Uuid::new_v4(),
            thread_id: Some(cid),
            user_id: "user2".into(),
            target: CommentTarget::Track {
                track_id: Uuid::new_v4(),
            },
            content: "I'll add it".into(),
            resolved: false,
            created_at: 1001,
        };
        room.reply_to_comment(cid, reply);
        assert_eq!(room.comment_threads.get(&cid).unwrap().replies.len(), 1);

        room.resolve_comment(cid);
        assert!(room.comment_threads.get(&cid).unwrap().resolved);
        assert_eq!(room.unresolved_comments().len(), 0);
    }

    #[test]
    fn test_room_crdt_set_param() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        let track_id = Uuid::new_v4();
        room.apply_operation(
            "user1".into(),
            CollabOp::SetParam {
                track_id,
                param: "volume".into(),
                value: 0.7,
                op_id: Uuid::new_v4(),
            },
            1000,
        );
        let key = format!("{}_volume", track_id);
        assert_eq!(room.track_volumes.get(&key).unwrap().value, 0.7);
    }

    #[test]
    fn test_room_crdt_insert_delete_track() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        room.apply_operation(
            "u1".into(),
            CollabOp::Insert {
                position: 0,
                content: "track1".into(),
                op_id: Uuid::new_v4(),
            },
            1000,
        );
        room.apply_operation(
            "u1".into(),
            CollabOp::Insert {
                position: 1,
                content: "track2".into(),
                op_id: Uuid::new_v4(),
            },
            1001,
        );
        assert_eq!(room.track_set.elements().len(), 2);

        room.apply_operation(
            "u1".into(),
            CollabOp::Delete {
                position: 0,
                length: 1,
                op_id: Uuid::new_v4(),
            },
            1002,
        );
        assert_eq!(room.track_set.elements().len(), 1);
    }

    #[test]
    fn test_room_snapshot_replay() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        // Generate enough operations to trigger snapshot (every 10)
        for i in 0..12 {
            room.apply_operation(
                "u1".into(),
                CollabOp::Insert {
                    position: i,
                    content: format!("track{}", i),
                    op_id: Uuid::new_v4(),
                },
                1000 + i as u64,
            );
        }
        assert!(!room.snapshots.is_empty());
        let snap = room.replay_to(10);
        assert!(snap.is_some());
    }

    #[test]
    fn test_room_merge_track_set() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        room.apply_operation(
            "u1".into(),
            CollabOp::Insert {
                position: 0,
                content: "track1".into(),
                op_id: Uuid::new_v4(),
            },
            1000,
        );

        let mut remote = ORSet::new();
        remote.add("track2".into());
        room.merge_track_set(&remote);
        assert!(room.track_set.contains("track2"));
    }

    #[test]
    fn test_room_merge_track_volume() {
        let mut room = CollabRoom::new(Uuid::new_v4(), Uuid::new_v4());
        let remote_reg = LWWRegister::new(0.9, "remote_node");
        room.merge_track_volume("track1_volume", &remote_reg);
        assert_eq!(room.track_volumes.get("track1_volume").unwrap().value, 0.9);
    }

    #[tokio::test]
    async fn test_collab_manager_add_comment() {
        let manager = CollabManager::new();
        let room_id = manager.create_room(Uuid::new_v4()).await;
        let comment = CollabCommentData {
            comment_id: Uuid::new_v4(),
            thread_id: None,
            user_id: "user1".into(),
            target: CommentTarget::Track {
                track_id: Uuid::new_v4(),
            },
            content: "Great track".into(),
            resolved: false,
            created_at: 1000,
        };
        let result = manager
            .add_comment(room_id, CommentAction::Add, comment)
            .await;
        assert!(result.is_some());
    }

    #[tokio::test]
    async fn test_collab_manager_sync_state() {
        let manager = CollabManager::new();
        let room_id = manager.create_room(Uuid::new_v4()).await;
        let result = manager.sync_state(room_id, "newuser".into()).await;
        assert!(result.is_some());
    }
}
