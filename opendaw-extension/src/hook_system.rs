//! Hook System — 事件钩子扩展
//!
//! 第四根柱子：所有核心事件可被Hook
//! Hook = 注册回调函数，按优先级执行
//! 脚本/插件/模型都可注册Hook

use std::collections::HashMap;

use crate::error::HookError;

/// 钩子上下文 — 传递给处理器的执行环境
#[derive(Clone, Debug)]
pub struct HookContext {
    /// 事件名称
    pub event: String,
    /// 事件数据（键值对）
    pub data: HashMap<String, String>,
    /// 是否阻止后续处理器执行（处理器可设置，使用 Cell 实现内部可变性）
    stop_propagation: std::cell::Cell<bool>,
}

impl HookContext {
    pub fn new(event: &str) -> Self {
        Self {
            event: event.to_string(),
            data: HashMap::new(),
            stop_propagation: std::cell::Cell::new(false),
        }
    }

    /// 插入数据
    pub fn insert(&mut self, key: &str, value: &str) -> &mut Self {
        self.data.insert(key.to_string(), value.to_string());
        self
    }

    /// 获取数据
    pub fn get(&self, key: &str) -> Option<&str> {
        self.data.get(key).map(|s| s.as_str())
    }

    /// 阻止后续处理器执行
    pub fn stop_propagation(&self) {
        self.stop_propagation.replace(true);
    }
}

/// 钩子处理器信息
#[derive(Clone, Debug)]
pub struct HookInfo {
    /// 处理器唯一ID
    pub id: String,
    /// 处理器名称（人类可读）
    pub name: String,
    /// 优先级（数值越小越先执行）
    pub priority: i32,
}

/// 内部处理器存储
struct HandlerEntry {
    id: String,
    name: String,
    priority: i32,
    handler: Box<dyn Fn(&HookContext) -> Result<(), HookError> + Send + Sync>,
}

/// Hook System — 事件注册/触发/优先级管理
pub struct HookSystem {
    /// 事件名 -> 处理器列表
    handlers: HashMap<String, Vec<HandlerEntry>>,
}

impl HookSystem {
    pub fn new() -> Self {
        Self {
            handlers: HashMap::new(),
        }
    }

    /// 注册钩子处理器
    ///
    /// 返回处理器ID，可用于后续注销
    /// priority: 优先级，数值越小越先执行
    pub fn register(
        &mut self,
        event: &str,
        handler: Box<dyn Fn(&HookContext) -> Result<(), HookError> + Send + Sync>,
        priority: i32,
    ) -> String {
        let id = uuid::Uuid::new_v4().to_string();
        let entry = HandlerEntry {
            id: id.clone(),
            name: format!("handler-{}", &id[..8]),
            priority,
            handler,
        };
        self.handlers
            .entry(event.to_string())
            .or_default()
            .push(entry);

        // 按优先级排序
        if let Some(list) = self.handlers.get_mut(event) {
            list.sort_by_key(|e| e.priority);
        }

        id
    }

    /// 注册带名称的钩子处理器
    pub fn register_named(
        &mut self,
        event: &str,
        name: &str,
        handler: Box<dyn Fn(&HookContext) -> Result<(), HookError> + Send + Sync>,
        priority: i32,
    ) -> String {
        let id = uuid::Uuid::new_v4().to_string();
        let entry = HandlerEntry {
            id: id.clone(),
            name: name.to_string(),
            priority,
            handler,
        };
        self.handlers
            .entry(event.to_string())
            .or_default()
            .push(entry);

        if let Some(list) = self.handlers.get_mut(event) {
            list.sort_by_key(|e| e.priority);
        }

        id
    }

    /// 注销钩子处理器
    pub fn unregister(&mut self, handler_id: &str) -> Result<(), HookError> {
        let mut found = false;
        for (_event, list) in self.handlers.iter_mut() {
            let before = list.len();
            list.retain(|e| e.id != handler_id);
            if list.len() < before {
                found = true;
            }
        }
        if found {
            Ok(())
        } else {
            Err(HookError::HandlerNotFound(handler_id.to_string()))
        }
    }

    /// 触发事件，按优先级执行所有处理器
    ///
    /// 如果某个处理器设置了 stop_propagation，后续处理器不会执行
    pub fn emit(&self, event: &str, context: &mut HookContext) -> Result<(), HookError> {
        if let Some(list) = self.handlers.get(event) {
            for entry in list {
                if context.stop_propagation.get() {
                    break;
                }
                (entry.handler)(context).map_err(|e| {
                    HookError::HandlerFailed(format!("处理器 {} 执行失败: {}", entry.name, e))
                })?;
            }
        }
        Ok(())
    }

    /// 列出指定事件的所有处理器信息
    pub fn list_hooks(&self, event: &str) -> Vec<HookInfo> {
        self.handlers
            .get(event)
            .map(|list| {
                list.iter()
                    .map(|e| HookInfo {
                        id: e.id.clone(),
                        name: e.name.clone(),
                        priority: e.priority,
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    /// 检查事件是否有注册的处理器
    pub fn has_hooks(&self, event: &str) -> bool {
        self.handlers.get(event).map_or(false, |l| !l.is_empty())
    }

    /// 清除指定事件的所有处理器
    pub fn clear_event(&mut self, event: &str) {
        self.handlers.remove(event);
    }

    /// 清除所有处理器
    pub fn clear_all(&mut self) {
        self.handlers.clear();
    }
}

impl Default for HookSystem {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    #[test]
    fn test_hook_register_and_emit() {
        let mut hooks = HookSystem::new();
        let log = Arc::new(Mutex::new(Vec::new()));

        // 注册两个处理器，不同优先级
        let log1 = log.clone();
        hooks.register(
            "render_start",
            Box::new(move |ctx| {
                log1.lock().unwrap().push(format!("A:{}", ctx.event));
                Ok(())
            }),
            10,
        );

        let log2 = log.clone();
        hooks.register(
            "render_start",
            Box::new(move |ctx| {
                log2.lock().unwrap().push(format!("B:{}", ctx.event));
                Ok(())
            }),
            5, // 优先级更高，先执行
        );

        // 触发
        let mut ctx = HookContext::new("render_start");
        hooks.emit("render_start", &mut ctx).unwrap();

        let entries = log.lock().unwrap();
        assert_eq!(entries[0], "B:render_start"); // 优先级5先执行
        assert_eq!(entries[1], "A:render_start"); // 优先级10后执行
    }

    #[test]
    fn test_hook_stop_propagation() {
        let mut hooks = HookSystem::new();
        let log = Arc::new(Mutex::new(Vec::new()));

        let log1 = log.clone();
        hooks.register(
            "test",
            Box::new(move |ctx| {
                log1.lock().unwrap().push("first");
                ctx.stop_propagation();
                Ok(())
            }),
            1,
        );

        let log2 = log.clone();
        hooks.register(
            "test",
            Box::new(move |_ctx| {
                log2.lock().unwrap().push("second");
                Ok(())
            }),
            2,
        );

        let mut ctx = HookContext::new("test");
        hooks.emit("test", &mut ctx).unwrap();

        let entries = log.lock().unwrap();
        assert_eq!(*entries, vec!["first"]); // 第二个被阻止
    }

    #[test]
    fn test_hook_unregister() {
        let mut hooks = HookSystem::new();

        let id = hooks.register("test", Box::new(|_ctx| Ok(())), 1);

        assert_eq!(hooks.list_hooks("test").len(), 1);
        hooks.unregister(&id).unwrap();
        assert_eq!(hooks.list_hooks("test").len(), 0);
    }
}
