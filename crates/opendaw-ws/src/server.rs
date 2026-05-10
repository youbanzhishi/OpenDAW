//! WebSocket 服务器

use crate::protocol::WsMessage;
use futures_util::{SinkExt, StreamExt};
use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio::sync::{broadcast, RwLock};
use tokio_tungstenite::tungstenite::Message;

/// WebSocket服务器
#[derive(Debug)]
pub struct WsServer {
    /// 频道: 项目ID -> broadcast sender
    channels: Arc<RwLock<HashMap<uuid::Uuid, broadcast::Sender<WsMessage>>>>,
    /// 连接计数
    connection_count: Arc<RwLock<usize>>,
}

impl WsServer {
    pub fn new() -> Self {
        Self {
            channels: Arc::new(RwLock::new(HashMap::new())),
            connection_count: Arc::new(RwLock::new(0)),
        }
    }

    /// 获取或创建项目的广播频道
    pub async fn get_channel(&self, project_id: uuid::Uuid) -> broadcast::Sender<WsMessage> {
        let mut channels = self.channels.write().await;
        channels
            .entry(project_id)
            .or_insert_with(|| broadcast::channel(256).0)
            .clone()
    }

    /// 向项目频道广播消息
    pub async fn broadcast(&self, project_id: uuid::Uuid, msg: WsMessage) {
        let channels = self.channels.read().await;
        if let Some(sender) = channels.get(&project_id) {
            let _ = sender.send(msg);
        }
    }

    /// 获取当前连接数
    pub async fn connection_count(&self) -> usize {
        *self.connection_count.read().await
    }

    /// 启动WebSocket服务器
    pub async fn serve(
        self: Arc<Self>,
        addr: SocketAddr,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let listener = TcpListener::bind(addr).await?;
        tracing::info!("🔌 OpenDAW WebSocket server listening on {}", addr);

        while let Ok((stream, _addr)) = listener.accept().await {
            let server = self.clone();
            tokio::spawn(async move {
                let ws_stream = tokio_tungstenite::accept_async(stream).await;
                if let Ok(ws_stream) = ws_stream {
                    let (mut write, mut read) = ws_stream.split();

                    // 增加连接计数
                    {
                        let mut count = server.connection_count.write().await;
                        *count += 1;
                    }

                    // 读取消息
                    while let Some(msg_result) = read.next().await {
                        match msg_result {
                            Ok(Message::Text(text)) => {
                                if let Ok(ws_msg) = WsMessage::from_json(&text) {
                                    match ws_msg {
                                        WsMessage::Ping => {
                                            let pong = WsMessage::Pong;
                                            if let Ok(json) = pong.to_json() {
                                                let _ = write.send(Message::Text(json)).await;
                                            }
                                        }
                                        WsMessage::CollabOperation { room_id, .. } => {
                                            server.broadcast(room_id, ws_msg).await;
                                        }
                                        _ => {
                                            // 其他消息的处理
                                            if let Ok(json) = ws_msg.to_json() {
                                                let _ = write.send(Message::Text(json)).await;
                                            }
                                        }
                                    }
                                }
                            }
                            Ok(Message::Close(_)) => break,
                            Err(_) => break,
                            _ => {}
                        }
                    }

                    // 减少连接计数
                    {
                        let mut count = server.connection_count.write().await;
                        *count = count.saturating_sub(1);
                    }
                }
            });
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn test_ws_server_new() {
        let server = WsServer::new();
        // Just ensure construction works
        assert!(true);
    }

    #[tokio::test]
    async fn test_get_channel() {
        let server = WsServer::new();
        let project_id = Uuid::new_v4();
        let sender = server.get_channel(project_id).await;
        // Subscribe to verify
        let mut rx = sender.subscribe();
        let _ = sender.send(WsMessage::Ping);
        let msg = rx.recv().await.unwrap();
        assert_eq!(msg.type_name(), "Ping");
    }

    #[tokio::test]
    async fn test_broadcast() {
        let server = WsServer::new();
        let project_id = Uuid::new_v4();
        let sender = server.get_channel(project_id).await;
        let mut rx = sender.subscribe();

        server
            .broadcast(
                project_id,
                WsMessage::RenderProgress {
                    project_id,
                    progress: 0.5,
                    status: "running".into(),
                    estimated_seconds: None,
                },
            )
            .await;

        let msg = rx.recv().await.unwrap();
        assert_eq!(msg.type_name(), "RenderProgress");
    }

    #[tokio::test]
    async fn test_connection_count_initial() {
        let server = WsServer::new();
        assert_eq!(server.connection_count().await, 0);
    }

    #[tokio::test]
    async fn test_broadcast_nonexistent_channel() {
        let server = WsServer::new();
        // Should not panic
        server.broadcast(Uuid::new_v4(), WsMessage::Pong).await;
    }

    #[tokio::test]
    async fn test_multiple_channels() {
        let server = WsServer::new();
        let id1 = Uuid::new_v4();
        let id2 = Uuid::new_v4();
        let s1 = server.get_channel(id1).await;
        let s2 = server.get_channel(id2).await;
        let mut rx1 = s1.subscribe();
        let mut rx2 = s2.subscribe();

        let _ = s1.send(WsMessage::Ping);
        let _ = s2.send(WsMessage::Pong);

        let m1 = rx1.recv().await.unwrap();
        let m2 = rx2.recv().await.unwrap();
        assert_eq!(m1.type_name(), "Ping");
        assert_eq!(m2.type_name(), "Pong");
    }
}
