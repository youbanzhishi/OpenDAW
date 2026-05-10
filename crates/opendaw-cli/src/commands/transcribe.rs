//! 扒带子命令

use crate::output::OutputFormat;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum TranscribeAction {
    /// 音频扒带 (音频→MIDI)
    Transcribe {
        /// 音频文件路径
        input: String,
        /// 输出MIDI文件路径
        #[arg(long)]
        output: Option<String>,
        /// 灵敏度 (0.0-1.0)
        #[arg(long, default_value = "0.5")]
        sensitivity: f32,
    },
}

#[derive(Debug, serde::Serialize)]
struct TranscribeResult {
    action: String,
    input: String,
    output: Option<String>,
    status: String,
}

pub fn run(action: TranscribeAction, format: &OutputFormat) -> Result<(), Box<dyn std::error::Error>> {
    match action {
        TranscribeAction::Transcribe { input, output, sensitivity } => {
            let result = TranscribeResult {
                action: "transcribe".into(),
                input: input.clone(),
                output: output.clone(),
                status: format!("transcribing (sensitivity: {})", sensitivity).into(),
            };
            format.print(&result);
            format.print_success(&format!("Transcription started: {}", input));
        }
    }
    Ok(())
}
