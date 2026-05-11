//! OpenDAW Desktop — Binary entry point
//!
//! Tauri v2 requires a separate binary target for desktop builds.
//! The actual logic lives in lib.rs → opendaw_desktop_lib::run().

fn main() {
    opendaw_desktop_lib::run()
}
