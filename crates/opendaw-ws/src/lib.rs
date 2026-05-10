//! OpenDAW WebSocket 实时通信层
//!
//! 提供：
//! - 渲染进度推送
//! - AI决策过程实时展示
//! - 仪表盘数据推送（电平表/频谱）
//! - 多人协作（CRDT + 房间管理 + 评论）

pub mod collab;
pub mod protocol;
pub mod server;

pub use collab::{
    CollabManager,
    CollabRoom,
    CommentThread,
    EditState,
    // Phase 34 CRDT
    HLCTimestamp,
    LWWRegister,
    ORSet,
    ORSetTag,
    OperationLog,
    RoomSnapshot,
    // Phase 34 Presence & Comments
    UserPresence,
};
pub use protocol::WsMessage;
pub use protocol::{CollabCommentData, CommentAction, CommentTarget};
pub use server::WsServer;
