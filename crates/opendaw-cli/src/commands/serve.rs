//! 服务器启动子命令
//!
//! 启动 OpenDAW API 服务器（opendaw-api 二进制）。
//! 支持后台守护模式（--daemon）和前台运行模式。

use crate::output::OutputFormat;
use clap::Args;
use std::process::Command;

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
    /// 后台守护模式
    #[arg(long)]
    daemon: bool,
}

#[derive(Debug, serde::Serialize)]
struct ServeResult {
    host: String,
    port: u16,
    ws_port: u16,
    daemon: bool,
    status: String,
}

/// 查找 opendaw-api 二进制
fn find_opendaw_api() -> Option<std::path::PathBuf> {
    // 1. PATH 查找
    if let Ok(path) = which::which("opendaw-api") {
        return Some(path);
    }
    // 2. 相对路径 release
    let release = std::path::PathBuf::from("target/release/opendaw-api");
    if release.exists() {
        return Some(release);
    }
    // 3. 相对路径 debug
    let debug = std::path::PathBuf::from("target/debug/opendaw-api");
    if debug.exists() {
        return Some(debug);
    }
    None
}

pub fn run(args: ServeArgs, format: &OutputFormat) -> Result<(), Box<dyn std::error::Error>> {
    let binary_path = match find_opendaw_api() {
        Some(p) => p,
        None => {
            let result = ServeResult {
                host: args.host.clone(),
                port: args.port,
                ws_port: args.ws_port,
                daemon: args.daemon,
                status: "error: opendaw-api binary not found".into(),
            };
            format.print(&result);
            format.print_error(
                "opendaw-api binary not found. Run `cargo build --release` first.",
            );
            return Err("opendaw-api binary not found".into());
        }
    };

    let result = ServeResult {
        host: args.host.clone(),
        port: args.port,
        ws_port: args.ws_port,
        daemon: args.daemon,
        status: "starting".into(),
    };
    format.print(&result);

    // 构建命令
    let mut cmd = Command::new(&binary_path);
    cmd.env("OPENDAW_HOST", &args.host);
    cmd.env("OPENDAW_PORT", args.port.to_string());
    cmd.env("OPENDAW_WS_PORT", args.ws_port.to_string());
    cmd.env("RUST_LOG", "opendaw_api=debug,opendaw_ws=debug");

    if args.daemon {
        // 守护模式：启动子进程并detach
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            cmd.process_group(0);
            cmd.stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .stdin(std::process::Stdio::null());
        }

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NEW_PROCESS_GROUP: u32 = 0x00000200;
            cmd.creation_flags(CREATE_NEW_PROCESS_GROUP);
            cmd.stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .stdin(std::process::Stdio::null());
        }

        let child = cmd.spawn()?;
        format.print_success(&format!(
            "OpenDAW server started in daemon mode (PID: {})",
            child.id()
        ));
        format.print_success(&format!(
            "  API: http://{}:{}",
            args.host, args.port
        ));
        format.print_success(&format!(
            "  WebSocket: http://{}:{}",
            args.host, args.ws_port
        ));
    } else {
        // 前台模式：启动子进程并等待
        format.print_success(&format!(
            "OpenDAW server starting at {}:{} (WS: {})",
            args.host, args.port, args.ws_port
        ));

        let mut child = cmd.spawn()?;
        let status = child.wait()?;
        if !status.success() {
            return Err(format!("opendaw-api exited with status: {}", status).into());
        }
    }

    Ok(())
}
