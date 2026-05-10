//! API 错误处理

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;

/// API错误类型
#[derive(Debug, thiserror::Error)]
pub enum ApiError {
    #[error("Project not found: {0}")]
    NotFound(String),

    #[error("Bad request: {0}")]
    BadRequest(String),

    #[error("Internal error: {0}")]
    Internal(String),

    #[error("Render failed: {0}")]
    RenderFailed(String),

    #[error("Plugin error: {0}")]
    PluginError(String),
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, message) = match &self {
            ApiError::NotFound(msg) => (StatusCode::NOT_FOUND, msg.clone()),
            ApiError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg.clone()),
            ApiError::Internal(msg) => (StatusCode::INTERNAL_SERVER_ERROR, msg.clone()),
            ApiError::RenderFailed(msg) => (StatusCode::INTERNAL_SERVER_ERROR, msg.clone()),
            ApiError::PluginError(msg) => (StatusCode::INTERNAL_SERVER_ERROR, msg.clone()),
        };

        let body = json!({
            "success": false,
            "error": message,
        });

        (status, Json(body)).into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_not_found_error() {
        let err = ApiError::NotFound("project 123".into());
        assert!(err.to_string().contains("project 123"));
    }

    #[test]
    fn test_bad_request_error() {
        let err = ApiError::BadRequest("missing name".into());
        assert!(err.to_string().contains("missing name"));
    }

    #[test]
    fn test_internal_error() {
        let err = ApiError::Internal("db fail".into());
        assert!(err.to_string().contains("db fail"));
    }

    #[test]
    fn test_render_failed_error() {
        let err = ApiError::RenderFailed("timeout".into());
        assert!(err.to_string().contains("timeout"));
    }

    #[test]
    fn test_plugin_error() {
        let err = ApiError::PluginError("load failed".into());
        assert!(err.to_string().contains("load failed"));
    }

    #[test]
    fn test_error_into_response() {
        let err = ApiError::NotFound("test".into());
        let response = err.into_response();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[test]
    fn test_bad_request_into_response() {
        let err = ApiError::BadRequest("invalid".into());
        let response = err.into_response();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[test]
    fn test_internal_into_response() {
        let err = ApiError::Internal("oops".into());
        let response = err.into_response();
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
    }

    #[test]
    fn test_error_display() {
        let err = ApiError::NotFound("x".into());
        let s = format!("{}", err);
        assert!(!s.is_empty());
    }

    #[test]
    fn test_error_debug() {
        let err = ApiError::BadRequest("y".into());
        let s = format!("{:?}", err);
        assert!(s.contains("BadRequest"));
    }
}
