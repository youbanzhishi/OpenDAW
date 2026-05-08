//! VCMix Desktop — Binary entry point
//!
//! Tauri v2 requires a separate binary target for desktop builds.
//! The actual logic lives in lib.rs → vcmix_desktop_lib::run().

fn main() {
    vcmix_desktop_lib::run()
}
