//! OpenDAW WebSocket 实时通信层
//!
//! 提供：
//! - 渲染进度推送
//! - AI决策过程实时展示
//! - 仪表盘数据推送（电平表/频谱）
//! - 多人协作（OT操作 + 房间管理）

pub mod collab;
pub mod protocol;
pub mod server;

pub use protocol::WsMessage;
pub use server::WsServer;
pub use collab::{CollabRoom, CollabManager, OperationLog};
