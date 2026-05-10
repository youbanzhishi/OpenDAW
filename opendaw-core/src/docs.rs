//! SDK文档生成支持 — OpenAPI 3.1规范自动生成
//!
//! - ApiEndpoint: 描述单个API端点
//! - ApiDocGenerator: 收集所有端点，生成OpenAPI 3.1 YAML
//! - 覆盖opendaw-api中的所有REST端点

use serde::{Deserialize, Serialize};

/// HTTP方法
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum HttpMethod {
    GET,
    POST,
    PUT,
    DELETE,
    PATCH,
}

impl std::fmt::Display for HttpMethod {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            HttpMethod::GET => write!(f, "GET"),
            HttpMethod::POST => write!(f, "POST"),
            HttpMethod::PUT => write!(f, "PUT"),
            HttpMethod::DELETE => write!(f, "DELETE"),
            HttpMethod::PATCH => write!(f, "PATCH"),
        }
    }
}

/// API端点描述
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiEndpoint {
    /// HTTP方法
    pub method: HttpMethod,
    /// URL路径 (如 "/api/v1/projects")
    pub path: String,
    /// 端点描述
    pub description: String,
    /// 请求体类型描述
    pub request_type: Option<String>,
    /// 响应体类型描述
    pub response_type: Option<String>,
    /// 是否需要认证
    pub requires_auth: bool,
    /// 标签（分组）
    pub tags: Vec<String>,
}

impl ApiEndpoint {
    /// 创建新的API端点
    pub fn new(method: HttpMethod, path: &str, description: &str) -> Self {
        Self {
            method,
            path: path.to_string(),
            description: description.to_string(),
            request_type: None,
            response_type: None,
            requires_auth: false,
            tags: Vec::new(),
        }
    }

    /// 设置请求体类型
    pub fn with_request_type(mut self, request_type: &str) -> Self {
        self.request_type = Some(request_type.to_string());
        self
    }

    /// 设置响应体类型
    pub fn with_response_type(mut self, response_type: &str) -> Self {
        self.response_type = Some(response_type.to_string());
        self
    }

    /// 设置是否需要认证
    pub fn with_auth(mut self, requires: bool) -> Self {
        self.requires_auth = requires;
        self
    }

    /// 添加标签
    pub fn with_tag(mut self, tag: &str) -> Self {
        self.tags.push(tag.to_string());
        self
    }

    /// 生成端点的operationId
    pub fn operation_id(&self) -> String {
        let method_str = match self.method {
            HttpMethod::GET => "get",
            HttpMethod::POST => "create",
            HttpMethod::PUT => "update",
            HttpMethod::DELETE => "delete",
            HttpMethod::PATCH => "patch",
        };
        let path_part = self
            .path
            .trim_start_matches("/api/v1/")
            .replace('/', "_")
            .replace('{', "")
            .replace('}', "");
        format!("{}_{}", method_str, path_part)
    }
}

/// API文档生成器
#[derive(Debug, Clone)]
pub struct ApiDocGenerator {
    /// 端点列表
    endpoints: Vec<ApiEndpoint>,
    /// API标题
    title: String,
    /// API版本
    version: String,
    /// 服务器基础URL
    server_url: String,
}

impl ApiDocGenerator {
    /// 创建新的文档生成器
    pub fn new(title: &str, version: &str) -> Self {
        Self {
            endpoints: Vec::new(),
            title: title.to_string(),
            version: version.to_string(),
            server_url: "http://localhost:3000".to_string(),
        }
    }

    /// 设置服务器URL
    pub fn with_server_url(mut self, url: &str) -> Self {
        self.server_url = url.to_string();
        self
    }

    /// 添加端点
    pub fn add_endpoint(&mut self, endpoint: ApiEndpoint) {
        self.endpoints.push(endpoint);
    }

    /// 获取所有端点
    pub fn endpoints(&self) -> &[ApiEndpoint] {
        &self.endpoints
    }

    /// 按标签获取端点
    pub fn endpoints_by_tag(&self, tag: &str) -> Vec<&ApiEndpoint> {
        self.endpoints
            .iter()
            .filter(|e| e.tags.contains(&tag.to_string()))
            .collect()
    }

    /// 生成OpenAPI 3.1 YAML规范
    pub fn to_openapi_yaml(&self) -> Result<String, serde_yaml::Error> {
        let spec = self.build_openapi_spec();
        serde_yaml::to_string(&spec)
    }

    /// 生成OpenAPI 3.1 JSON规范
    pub fn to_openapi_json(&self) -> Result<String, serde_json::Error> {
        let spec = self.build_openapi_spec();
        serde_json::to_string_pretty(&spec)
    }

    /// 构建OpenAPI规范对象
    fn build_openapi_spec(&self) -> serde_json::Value {
        let mut paths = serde_json::Map::new();

        for endpoint in &self.endpoints {
            let path_key = endpoint.path.clone();
            let method_key = endpoint.method.to_string().to_lowercase();

            let mut operation = serde_json::Map::new();
            operation.insert(
                "summary".to_string(),
                serde_json::Value::String(endpoint.description.clone()),
            );
            operation.insert(
                "operationId".to_string(),
                serde_json::Value::String(endpoint.operation_id()),
            );

            if !endpoint.tags.is_empty() {
                let tags: serde_json::Value = endpoint
                    .tags
                    .iter()
                    .map(|t| serde_json::Value::String(t.clone()))
                    .collect();
                operation.insert("tags".to_string(), tags);
            }

            let mut responses = serde_json::Map::new();
            let mut ok_response = serde_json::Map::new();
            ok_response.insert(
                "description".to_string(),
                serde_json::Value::String("Success".to_string()),
            );
            if let Some(ref rt) = endpoint.response_type {
                let mut content = serde_json::Map::new();
                let mut json_content = serde_json::Map::new();
                json_content.insert(
                    "schema".to_string(),
                    serde_json::json!({
                        "type": rt
                    }),
                );
                content.insert(
                    "application/json".to_string(),
                    serde_json::Value::Object(json_content),
                );
                ok_response.insert("content".to_string(), serde_json::Value::Object(content));
            }
            responses.insert("200".to_string(), serde_json::Value::Object(ok_response));
            operation.insert(
                "responses".to_string(),
                serde_json::Value::Object(responses),
            );

            if let Some(ref req_t) = endpoint.request_type {
                let mut content = serde_json::Map::new();
                let mut json_content = serde_json::Map::new();
                json_content.insert(
                    "schema".to_string(),
                    serde_json::json!({
                        "type": req_t
                    }),
                );
                content.insert(
                    "application/json".to_string(),
                    serde_json::Value::Object(json_content),
                );
                operation.insert(
                    "requestBody".to_string(),
                    serde_json::json!({
                        "content": serde_json::Value::Object(content),
                        "required": true
                    }),
                );
            }

            if paths.contains_key(&path_key) {
                if let Some(serde_json::Value::Object(path_obj)) = paths.get_mut(&path_key) {
                    path_obj.insert(method_key, serde_json::Value::Object(operation));
                }
            } else {
                let mut path_obj = serde_json::Map::new();
                path_obj.insert(method_key, serde_json::Value::Object(operation));
                paths.insert(path_key, serde_json::Value::Object(path_obj));
            }
        }

        serde_json::json!({
            "openapi": "3.1.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": format!("{} API Documentation", self.title),
            },
            "servers": [
                {
                    "url": self.server_url,
                    "description": "OpenDAW API Server"
                }
            ],
            "paths": serde_json::Value::Object(paths),
        })
    }

    /// 从opendaw-api路由自动收集所有端点
    pub fn collect_opendaw_endpoints() -> Self {
        let mut gen = Self::new("OpenDAW API", "1.0.0");

        // 项目CRUD
        gen.add_endpoint(
            ApiEndpoint::new(HttpMethod::GET, "/api/v1/projects", "列出所有项目")
                .with_response_type("array")
                .with_tag("projects"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(HttpMethod::POST, "/api/v1/projects", "创建项目")
                .with_request_type("CreateProjectRequest")
                .with_response_type("Project")
                .with_tag("projects"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(HttpMethod::GET, "/api/v1/projects/{id}", "获取项目详情")
                .with_response_type("Project")
                .with_tag("projects"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(HttpMethod::PUT, "/api/v1/projects/{id}", "更新项目")
                .with_request_type("UpdateProjectRequest")
                .with_response_type("Project")
                .with_tag("projects"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(HttpMethod::DELETE, "/api/v1/projects/{id}", "删除项目")
                .with_tag("projects"),
        );

        // 渲染 & AI
        gen.add_endpoint(
            ApiEndpoint::new(HttpMethod::POST, "/api/v1/projects/{id}/render", "触发渲染")
                .with_request_type("RenderRequest")
                .with_response_type("RenderResponse")
                .with_tag("render"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(
                HttpMethod::POST,
                "/api/v1/projects/{id}/automix",
                "AI自动混音",
            )
            .with_request_type("AutoMixRequest")
            .with_response_type("AutoMixResponse")
            .with_tag("ai"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(
                HttpMethod::POST,
                "/api/v1/projects/{id}/transcribe",
                "音频扒带",
            )
            .with_request_type("TranscribeRequest")
            .with_response_type("TranscribeResponse")
            .with_tag("ai"),
        );

        // 插件 & 混音
        gen.add_endpoint(
            ApiEndpoint::new(HttpMethod::GET, "/api/v1/plugins", "列出可用插件")
                .with_response_type("array")
                .with_tag("plugins"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(
                HttpMethod::GET,
                "/api/v1/mixer/{id}/suggestions",
                "混音建议",
            )
            .with_response_type("MixerSuggestionsResponse")
            .with_tag("mixer"),
        );

        // Marketplace
        gen.add_endpoint(
            ApiEndpoint::new(
                HttpMethod::GET,
                "/api/v1/marketplace/search",
                "搜索市场插件",
            )
            .with_response_type("array")
            .with_tag("marketplace"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(
                HttpMethod::GET,
                "/api/v1/marketplace/categories",
                "获取分类列表",
            )
            .with_response_type("array")
            .with_tag("marketplace"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(HttpMethod::GET, "/api/v1/marketplace/{id}", "获取插件详情")
                .with_response_type("PluginDetailResponse")
                .with_tag("marketplace"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(
                HttpMethod::POST,
                "/api/v1/marketplace/{id}/install",
                "一键安装插件",
            )
            .with_response_type("InstallResponse")
            .with_tag("marketplace"),
        );
        gen.add_endpoint(
            ApiEndpoint::new(
                HttpMethod::POST,
                "/api/v1/marketplace/{id}/review",
                "提交评价",
            )
            .with_request_type("SubmitReviewRequest")
            .with_response_type("ReviewResponse")
            .with_tag("marketplace"),
        );

        gen
    }

    /// 统计端点数量
    pub fn endpoint_count(&self) -> usize {
        self.endpoints.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_api_endpoint_creation() {
        let ep = ApiEndpoint::new(HttpMethod::GET, "/api/v1/projects", "列出所有项目");
        assert_eq!(ep.method, HttpMethod::GET);
        assert_eq!(ep.path, "/api/v1/projects");
        assert_eq!(ep.description, "列出所有项目");
        assert!(ep.request_type.is_none());
        assert!(ep.response_type.is_none());
    }

    #[test]
    fn test_api_endpoint_builder() {
        let ep = ApiEndpoint::new(HttpMethod::POST, "/api/v1/projects", "创建项目")
            .with_request_type("CreateProjectRequest")
            .with_response_type("Project")
            .with_auth(true)
            .with_tag("projects");
        assert_eq!(ep.request_type, Some("CreateProjectRequest".to_string()));
        assert_eq!(ep.response_type, Some("Project".to_string()));
        assert!(ep.requires_auth);
        assert!(ep.tags.contains(&"projects".to_string()));
    }

    #[test]
    fn test_api_endpoint_operation_id() {
        let ep = ApiEndpoint::new(HttpMethod::GET, "/api/v1/projects/{id}", "获取项目");
        assert_eq!(ep.operation_id(), "get_projects_id");
    }

    #[test]
    fn test_doc_generator_yaml_output() {
        let mut gen = ApiDocGenerator::new("Test API", "1.0.0");
        gen.add_endpoint(ApiEndpoint::new(
            HttpMethod::GET,
            "/api/v1/test",
            "Test endpoint",
        ));
        let yaml = gen.to_openapi_yaml().unwrap();
        assert!(yaml.contains("openapi"));
        assert!(yaml.contains("3.1.0"));
        assert!(yaml.contains("/api/v1/test"));
    }

    #[test]
    fn test_doc_generator_json_output() {
        let mut gen = ApiDocGenerator::new("Test API", "1.0.0");
        gen.add_endpoint(ApiEndpoint::new(
            HttpMethod::GET,
            "/api/v1/test",
            "Test endpoint",
        ));
        let json = gen.to_openapi_json().unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["openapi"], "3.1.0");
    }

    #[test]
    fn test_collect_opendaw_endpoints() {
        let gen = ApiDocGenerator::collect_opendaw_endpoints();
        // Should have all the endpoints from opendaw-api
        assert!(gen.endpoint_count() >= 14);
        let yaml = gen.to_openapi_yaml().unwrap();
        assert!(yaml.contains("/api/v1/projects"));
        assert!(yaml.contains("/api/v1/marketplace"));
    }

    #[test]
    fn test_endpoints_by_tag() {
        let gen = ApiDocGenerator::collect_opendaw_endpoints();
        let project_eps = gen.endpoints_by_tag("projects");
        assert!(
            project_eps.len() >= 4,
            "Should have at least 4 project endpoints"
        );
        let marketplace_eps = gen.endpoints_by_tag("marketplace");
        assert!(
            marketplace_eps.len() >= 3,
            "Should have at least 3 marketplace endpoints"
        );
    }
}
