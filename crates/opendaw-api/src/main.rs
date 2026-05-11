//! OpenDAW REST API 服务器入口
//!
//! 同时提供 API 端点和 Web UI 静态文件服务。
//! 浏览器访问 http://host:port/ → Web UI
//! API 端点 http://host:port/api/v1/* → JSON API

mod api;
mod error;
mod models;
mod state;

use axum::Router;
use std::net::SocketAddr;
use tower_http::cors::CorsLayer;
use tower_http::services::{ServeDir, ServeFile};
use tower_http::trace::TraceLayer;
use tracing_subscriber::{fmt, EnvFilter};

/// Web UI 静态文件目录
///
/// 优先级：
/// 1. 环境变量 OPENDAW_WEB_DIR（开发热更新用）
/// 2. 相对路径 ./desktop/src-tauri/frontend/（项目内）
/// 3. 相对路径 ./static/（部署时拷贝到此目录）
const DEFAULT_WEB_DIRS: &[&str] = &[
    "./desktop/src-tauri/frontend",
    "./static",
    "../desktop/src-tauri/frontend",
];

fn find_web_dir() -> Option<String> {
    // 1. 环境变量优先
    if let Ok(dir) = std::env::var("OPENDAW_WEB_DIR") {
        if std::path::Path::new(&dir).exists() {
            tracing::info!("Using OPENDAW_WEB_DIR: {}", dir);
            return Some(dir);
        }
    }

    // 2. 按默认路径查找
    for dir in DEFAULT_WEB_DIRS {
        if std::path::Path::new(dir).exists() {
            tracing::info!("Found Web UI at: {}", dir);
            return Some(dir.to_string());
        }
    }

    None
}

#[tokio::main]
async fn main() {
    // 初始化日志
    fmt()
        .with_env_filter(
            EnvFilter::from_default_env().add_directive("opendaw_api=debug".parse().unwrap()),
        )
        .init();

    let app_state = state::AppState::new();

    let mut app = Router::new()
        .merge(api::routes(app_state.clone()))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(app_state);

    // 挂载 Web UI 静态文件
    if let Some(web_dir) = find_web_dir() {
        let index_path = format!("{}/index.html", web_dir);
        if std::path::Path::new(&index_path).exists() {
            tracing::info!("🌐 Serving Web UI from: {}", web_dir);

            // 静态文件服务：/ → index.html, 其他文件按路径匹配
            // SPA fallback: 任何未匹配的路径返回 index.html
            let serve_dir = ServeDir::new(&web_dir).fallback(ServeFile::new(&index_path));
            app = app.fallback_service(serve_dir);
        } else {
            tracing::warn!("Web UI directory found but no index.html: {}", web_dir);
            tracing::info!("💡 Running in API-only mode");
        }
    } else {
        tracing::info!("💡 No Web UI found, running in API-only mode");
        tracing::info!("   Set OPENDAW_WEB_DIR or place files in ./static/");
    }

    let addr = SocketAddr::from(([0, 0, 0, 0], 8080));
    tracing::info!("🚀 OpenDAW server listening on {}", addr);
    tracing::info!("   API:  http://{}/api/v1/", addr);
    if find_web_dir().is_some() {
        tracing::info!("   Web:  http://{}/", addr);
    }

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
