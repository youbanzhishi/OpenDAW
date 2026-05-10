//! WebSocket 消息协议

use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// WebSocket消息枚举
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum WsMessage {
    /// 项目更新通知
    ProjectUpdate {
        project_id: Uuid,
        change: String,
        payload: serde_json::Value,
    },

    /// 渲染进度推送
    RenderProgress {
        project_id: Uuid,
        progress: f32,
        status: String,
        estimated_seconds: Option<f64>,
    },

    /// AI决策过程实时展示
    AiDecision {
        project_id: Uuid,
        decision_type: String,
        reasoning: String,
        confidence: f32,
        action: serde_json::Value,
    },

    /// 电平表数据推送
    LevelMeter {
        project_id: Uuid,
        track_id: Uuid,
        peak_db: f32,
        rms_db: f32,
        channels: Vec<f32>,
    },

    /// 频谱数据推送
    Spectrum {
        project_id: Uuid,
        track_id: Uuid,
        bands: Vec<SpectrumBand>,
    },

    /// 协作操作
    CollabOperation {
        room_id: Uuid,
        user_id: String,
        operation: CollabOp,
    },

    /// 用户加入/离开
    CollabPresence {
        room_id: Uuid,
        user_id: String,
        action: PresenceAction,
    },

    /// 心跳/Ping
    Ping,

    /// 心跳/Pong
    Pong,
}

/// 频谱频段
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SpectrumBand {
    pub frequency: f32,
    pub magnitude: f32,
}

/// 协作操作
#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum CollabOp {
    Insert {
        position: usize,
        content: String,
        op_id: Uuid,
    },
    Delete {
        position: usize,
        length: usize,
        op_id: Uuid,
    },
    Replace {
        position: usize,
        length: usize,
        content: String,
        op_id: Uuid,
    },
    SetParam {
        track_id: Uuid,
        param: String,
        value: f32,
        op_id: Uuid,
    },
}

/// 在线状态动作
#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum PresenceAction {
    Join,
    Leave,
    CursorMove { x: f64, y: f64 },
}

impl WsMessage {
    /// 从JSON字符串解析
    pub fn from_json(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }

    /// 序列化为JSON字符串
    pub fn to_json(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self)
    }

    /// 获取消息类型名
    pub fn type_name(&self) -> &'static str {
        match self {
            WsMessage::ProjectUpdate { .. } => "ProjectUpdate",
            WsMessage::RenderProgress { .. } => "RenderProgress",
            WsMessage::AiDecision { .. } => "AiDecision",
            WsMessage::LevelMeter { .. } => "LevelMeter",
            WsMessage::Spectrum { .. } => "Spectrum",
            WsMessage::CollabOperation { .. } => "CollabOperation",
            WsMessage::CollabPresence { .. } => "CollabPresence",
            WsMessage::Ping => "Ping",
            WsMessage::Pong => "Pong",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_render_progress_roundtrip() {
        let msg = WsMessage::RenderProgress {
            project_id: Uuid::new_v4(),
            progress: 0.5,
            status: "running".into(),
            estimated_seconds: Some(30.0),
        };
        let json = msg.to_json().unwrap();
        let parsed = WsMessage::from_json(&json).unwrap();
        assert_eq!(parsed.type_name(), "RenderProgress");
    }

    #[test]
    fn test_ai_decision_roundtrip() {
        let msg = WsMessage::AiDecision {
            project_id: Uuid::new_v4(),
            decision_type: "eq_adjust".into(),
            reasoning: "Masking detected".into(),
            confidence: 0.85,
            action: serde_json::json!({"track": "vocals", "gain_db": -3.0}),
        };
        let json = msg.to_json().unwrap();
        let parsed = WsMessage::from_json(&json).unwrap();
        assert_eq!(parsed.type_name(), "AiDecision");
    }

    #[test]
    fn test_level_meter_roundtrip() {
        let msg = WsMessage::LevelMeter {
            project_id: Uuid::new_v4(),
            track_id: Uuid::new_v4(),
            peak_db: -3.2,
            rms_db: -12.5,
            channels: vec![-3.5, -3.1],
        };
        let json = msg.to_json().unwrap();
        let parsed = WsMessage::from_json(&json).unwrap();
        assert_eq!(parsed.type_name(), "LevelMeter");
    }

    #[test]
    fn test_spectrum_roundtrip() {
        let msg = WsMessage::Spectrum {
            project_id: Uuid::new_v4(),
            track_id: Uuid::new_v4(),
            bands: vec![
                SpectrumBand { frequency: 100.0, magnitude: 0.5 },
                SpectrumBand { frequency: 1000.0, magnitude: 0.3 },
            ],
        };
        let json = msg.to_json().unwrap();
        let parsed = WsMessage::from_json(&json).unwrap();
        assert_eq!(parsed.type_name(), "Spectrum");
    }

    #[test]
    fn test_collab_operation_roundtrip() {
        let msg = WsMessage::CollabOperation {
            room_id: Uuid::new_v4(),
            user_id: "user1".into(),
            operation: CollabOp::Insert {
                position: 10,
                content: "hello".into(),
                op_id: Uuid::new_v4(),
            },
        };
        let json = msg.to_json().unwrap();
        let parsed = WsMessage::from_json(&json).unwrap();
        assert_eq!(parsed.type_name(), "CollabOperation");
    }

    #[test]
    fn test_ping_pong() {
        let ping = WsMessage::Ping;
        let json = ping.to_json().unwrap();
        let parsed = WsMessage::from_json(&json).unwrap();
        assert_eq!(parsed.type_name(), "Ping");

        let pong = WsMessage::Pong;
        let json = pong.to_json().unwrap();
        let parsed = WsMessage::from_json(&json).unwrap();
        assert_eq!(parsed.type_name(), "Pong");
    }

    #[test]
    fn test_collab_presence() {
        let msg = WsMessage::CollabPresence {
            room_id: Uuid::new_v4(),
            user_id: "user1".into(),
            action: PresenceAction::CursorMove { x: 100.0, y: 200.0 },
        };
        let json = msg.to_json().unwrap();
        let parsed = WsMessage::from_json(&json).unwrap();
        assert_eq!(parsed.type_name(), "CollabPresence");
    }

    #[test]
    fn test_project_update() {
        let msg = WsMessage::ProjectUpdate {
            project_id: Uuid::new_v4(),
            change: "track_added".into(),
            payload: serde_json::json!({"name": "Guitar"}),
        };
        assert_eq!(msg.type_name(), "ProjectUpdate");
    }

    #[test]
    fn test_invalid_json() {
        let result = WsMessage::from_json("not valid json");
        assert!(result.is_err());
    }

    #[test]
    fn test_set_param_collab_op() {
        let op = CollabOp::SetParam {
            track_id: Uuid::new_v4(),
            param: "volume".into(),
            value: 0.8,
            op_id: Uuid::new_v4(),
        };
        let msg = WsMessage::CollabOperation {
            room_id: Uuid::new_v4(),
            user_id: "u".into(),
            operation: op,
        };
        let json = msg.to_json().unwrap();
        assert!(json.contains("SetParam"));
    }
}
