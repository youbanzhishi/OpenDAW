//! 服务器启动子命令

use crate::output::OutputFormat;
use clap::Args;

#[derive(Args)]
pub struct ServeArgs {
    /// 监听地址
    #[arg(long, default_value = "0.0.0.0")]
    host: String,
    /// API端口
    #[arg(long, default_value = "3000")]
    port: u16,
    /// WebSocket端口
    #[arg(long, default_value = "3001")]
    ws_port: u16,
}

#[derive(Debug, serde::Serialize)]
struct ServeResult {
    host: String,
    port: u16,
    ws_port: u16,
    status: String,
}

pub fn run(args: ServeArgs, format: &OutputFormat) -> Result<(), Box<dyn std::error::Error>> {
    let result = ServeResult {
        host: args.host.clone(),
        port: args.port,
        ws_port: args.ws_port,
        status: "starting".into(),
    };
    format.print(&result);
    format.print_success(&format!(
        "OpenDAW server starting at {}:{} (WS: {})",
        args.host, args.port, args.ws_port
    ));

    // 占位: 实际启动 opendaw-api + opendaw-ws 服务器
    // 这里只是打印信息，实际集成时需要调用对应crate的serve方法
    println!("Note: Full server integration requires running opendaw-api and opendaw-ws binaries");

    Ok(())
}
