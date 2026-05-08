//! Model Bus — AI模型扩展接口
//!
//! 第三根柱子：统一AI模型推理接口
//! 支持本地模型(ONNX/PyTorch)和远程API后端

use std::path::Path;

use crate::error::ModelError;
use crate::types::{ModelInput, ModelOutput};

/// 模型后端trait — 不同推理后端实现此接口
///
/// 内置后端：LocalBackend(ONNX)、ApiBackend(HTTP)
/// 第三方可注册自定义后端
pub trait ModelBackend: Send + Sync {
    /// 后端唯一标识（如 "local-onnx", "api-openai"）
    fn backend_id(&self) -> &str;

    /// 后端版本
    fn backend_version(&self) -> &str { "unknown" }

    /// 单次推理
    fn predict(&mut self, input: &ModelInput) -> Result<ModelOutput, ModelError>;

    /// 批量推理
    fn batch_predict(&mut self, inputs: &[ModelInput]) -> Result<Vec<ModelOutput>, ModelError>;

    /// 检查是否支持指定任务
    fn supports_task(&self, task: &str) -> bool;

    /// 加载模型
    fn load_model(&mut self, path: &Path) -> Result<(), ModelError>;

    /// 卸载模型，释放资源
    fn unload(&mut self);

    /// 后端是否已就绪（模型已加载）
    fn is_ready(&self) -> bool;
}

/// 本地模型后端 — 模拟实现
/// 生产环境可替换为 ONNX Runtime 或 PyTorch 绑定
pub struct LocalBackend {
    model_path: Option<String>,
    loaded: bool,
    supported_tasks: Vec<String>,
}

impl LocalBackend {
    pub fn new(supported_tasks: Vec<String>) -> Self {
        Self {
            model_path: None,
            loaded: false,
            supported_tasks,
        }
    }

    /// 创建带默认任务列表的本地后端
    pub fn default_tasks() -> Self {
        Self::new(vec![
            "auto_mix".into(),
            "separate".into(),
            "transcribe".into(),
        ])
    }
}

impl ModelBackend for LocalBackend {
    fn backend_id(&self) -> &str { "local" }

    fn backend_version(&self) -> &str { "0.1.0" }

    fn predict(&mut self, input: &ModelInput) -> Result<ModelOutput, ModelError> {
        if !self.loaded {
            return Err(ModelError::BackendUnavailable("模型未加载".into()));
        }
        // 模拟推理：简单返回输入特征的缩放
        let output_features: Vec<f64> = input.features.iter().map(|f| f * 0.5).collect();
        Ok(ModelOutput::from_features(output_features))
    }

    fn batch_predict(&mut self, inputs: &[ModelInput]) -> Result<Vec<ModelOutput>, ModelError> {
        if !self.loaded {
            return Err(ModelError::BackendUnavailable("模型未加载".into()));
        }
        inputs.iter().map(|input| self.predict(input)).collect()
    }

    fn supports_task(&self, task: &str) -> bool {
        self.supported_tasks.contains(&task.to_string())
    }

    fn load_model(&mut self, path: &Path) -> Result<(), ModelError> {
        if !path.exists() {
            return Err(ModelError::LoadFailed(
                format!("模型文件不存在: {}", path.display())
            ));
        }
        self.model_path = Some(path.display().to_string());
        self.loaded = true;
        Ok(())
    }

    fn unload(&mut self) {
        self.model_path = None;
        self.loaded = false;
    }

    fn is_ready(&self) -> bool {
        self.loaded
    }
}

/// API模型后端 — 通过HTTP调用远程模型服务
pub struct ApiBackend {
    endpoint: String,
    api_key: Option<String>,
    loaded: bool,
    supported_tasks: Vec<String>,
}

impl ApiBackend {
    pub fn new(endpoint: &str, supported_tasks: Vec<String>) -> Self {
        Self {
            endpoint: endpoint.to_string(),
            api_key: None,
            loaded: false,
            supported_tasks,
        }
    }

    pub fn with_api_key(mut self, key: &str) -> Self {
        self.api_key = Some(key.to_string());
        self
    }
}

impl ModelBackend for ApiBackend {
    fn backend_id(&self) -> &str { "api" }

    fn backend_version(&self) -> &str { "0.1.0" }

    fn predict(&mut self, input: &ModelInput) -> Result<ModelOutput, ModelError> {
        if !self.loaded {
            return Err(ModelError::BackendUnavailable("API后端未初始化".into()));
        }
        // 模拟API调用：返回基于输入的响应
        let prompt = input.prompt.as_deref().unwrap_or("(无提示)");
        Ok(ModelOutput::from_text(format!("[API响应] {}", prompt)))
    }

    fn batch_predict(&mut self, inputs: &[ModelInput]) -> Result<Vec<ModelOutput>, ModelError> {
        inputs.iter().map(|input| self.predict(input)).collect()
    }

    fn supports_task(&self, task: &str) -> bool {
        self.supported_tasks.contains(&task.to_string())
    }

    fn load_model(&mut self, _path: &Path) -> Result<(), ModelError> {
        // API后端不需要加载本地模型，标记为就绪即可
        self.loaded = true;
        Ok(())
    }

    fn unload(&mut self) {
        self.loaded = false;
    }

    fn is_ready(&self) -> bool {
        self.loaded
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_local_backend() {
        let mut backend = LocalBackend::default_tasks();

        // 未加载时应该报错
        assert!(!backend.is_ready());
        assert!(backend.predict(&ModelInput::from_features(vec![1.0])).is_err());

        // 模拟加载（使用临时文件）
        let tmp = std::env::temp_dir().join("test_model.onnx");
        std::fs::write(&tmp, b"fake").ok();
        backend.load_model(&tmp).unwrap();
        assert!(backend.is_ready());

        // 推理
        let input = ModelInput::from_features(vec![2.0, 4.0]);
        let output = backend.predict(&input).unwrap();
        assert_eq!(output.features, vec![1.0, 2.0]);

        // 任务支持检查
        assert!(backend.supports_task("auto_mix"));
        assert!(!backend.supports_task("unknown_task"));

        backend.unload();
        assert!(!backend.is_ready());
    }

    #[test]
    fn test_api_backend() {
        let mut backend = ApiBackend::new(
            "https://api.example.com/v1",
            vec!["compose".into(), "arrange".into()],
        );

        assert!(backend.supports_task("compose"));
        assert!(!backend.supports_task("auto_mix"));

        // 初始化
        backend.load_model(Path::new(".")).unwrap();
        assert!(backend.is_ready());

        let input = ModelInput::from_features(vec![]).with_prompt("生成一段C大调旋律");
        let output = backend.predict(&input).unwrap();
        assert!(output.text.unwrap().contains("API响应"));
    }
}
