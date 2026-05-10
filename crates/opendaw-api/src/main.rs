//! OpenDAW REST API 服务器入口

mod api;
mod error;
mod models;
mod state;

use axum::Router;
use std::net::SocketAddr;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;
use tracing_subscriber::{fmt, EnvFilter};

#[tokio::main]
async fn main() {
    // 初始化日志
    fmt()
        .with_env_filter(
            EnvFilter::from_default_env().add_directive("opendaw_api=debug".parse().unwrap()),
        )
        .init();

    let app_state = state::AppState::new();
    let app = Router::new()
        .merge(api::routes(app_state.clone()))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(app_state);

    let addr = SocketAddr::from(([0, 0, 0, 0], 3000));
    tracing::info!("🚀 OpenDAW API server listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
