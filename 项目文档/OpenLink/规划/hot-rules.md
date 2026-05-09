# OpenLink 热规则

> ⚠️ 此文件内容必须在每次派发任务时注入任务描述
> 主对话负责维护，其他session只读

## 🔴 铁律（违反=任务失败）

1. **核心层零业务逻辑**：路由引擎不知道"短链"是什么，新功能=注册扩展，核心代码不改
2. **Rust版本**：必须用 `~/.cargo/bin/cargo`（1.95.0），不要用系统 `/usr/bin/cargo`（1.75.0会编译失败）
3. **编译输出目录**：`CARGO_TARGET_DIR=/tmp/openlink-target`，默认target/在hpvs_fs上极慢
4. **编译并发**：`CARGO_BUILD_JOBS=2`，超过2会OOM（1.8G内存）
5. **文件安全铁律**：覆盖=犯罪，先读后动，删除→回收站

## 🟡 警告（容易犯错）

1. **condition vs conditions**：Phase1用`condition`单数字段，Phase2加了`conditions`数组+`condition_logic`，评估时用`all_conditions()`方法统一获取，不要只读一个
2. **ActionResult枚举**：新增了`WebhookTriggered`等变体，匹配时要用`_`通配符兜底，不要穷举
3. **Action枚举**：Phase2新增了`Webhook`变体，不要只处理`Redirect`和`JsonData`
4. **Hook三阶段**：BeforeRoute→路由→AfterRoute，还有OnError，不要忘记OnError
5. **visibility字段**：links表有visibility(public/private)，Hook只对public生效，安全过滤只对public生效

## 🟢 提醒（容易忘）

1. **新增扩展要注册**：写完扩展crate后，在workspace Cargo.toml加members，在bin/main.rs调register()
2. **测试要跑全量**：`cargo test --workspace`，不要只跑单个crate
3. **推送到GitHub用SSH**：`GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519_openlink" git push`

## 🔵 Phase 3 踩坑记录

### agent.rs 编译错误修复
1. **模块路径错误**：`crate::error::ApiError` 不存在，改用 `(StatusCode, String)` 元组作为错误类型（与 link.rs 一致）
2. **Store 方法名错误**：
   - `find_link_by_code` → `get_link_by_code`
   - `get_route` → `get_route_by_link_id`
3. **list_links 签名**：`list_links(offset, limit)` 只接受 2 个 i64 参数，不是 3 个
4. **AppConfig 无 base_url 字段**：需用 `server.host` + `server.port` 构建 URL
5. **缺少 rand 依赖**：需在 Cargo.toml 添加 `rand = "0.8"`

### middleware 修复
- `middleware/auth.rs` 和 `middleware/logging.rs` 中移除未使用的 `body::Body` 导入
- `middleware/auth.rs` 需要导入 `IntoResponse` trait

### unused variables 警告处理
- 对于未使用的函数参数，使用 `_` 前缀（如 `_state`, `_headers`）
- 不要简单地删除参数，否则会导致调用处编译错误

## 🔵 Phase 4 踩坑记录

### 编译环境问题
1. **内存限制**：3.8G内存，`CARGO_BUILD_JOBS=1` 逐个crate编译，避免OOM
2. **清理进程**：编译前执行 `pkill -f cargo; pkill -f rustc; sleep 2`
3. **清理缓存**：`sync; echo 3 > /proc/sys/vm/drop_caches`
4. **Cargo镜像**：使用 ustc 镜像加速 `https://mirrors.ustc.edu.cn/crates.io-index/`

### 依赖问题
1. **crate名称错误**：`dns_sd` → `dns-sd`（crates.io上是dns-sd带连字符）
2. **缺失依赖**：
   - ext-direct-transfer: 需要 `rand`, `hex`
   - ext-daw-distribute: 需要 `uuid`, `thiserror`, `urlencoding`
   - openlink-node: 需要 `reqwest`, `thiserror`, `tracing-subscriber`
3. **dns-sd系统库依赖**：需要 `avahi-compat-libdns_sd`，如无则去掉依赖

### warp 回复问题
1. **Bytes 不实现 Reply**：使用 `warp::http::Response::builder().body(warp::hyper::Body::from(vec))`
2. **with_header 用法**：`warp::reply::with_header(body, header, value)` 第一个参数需实现 Reply trait
3. **tracing初始化**：`use tracing_subscriber::prelude::*;` 导入 SubscriberExt trait

### 测试修复
1. **TXT记录解析测试**：`\x08` 表示长度8字节，但 `node_id=abc` 是11字节，测试数据长度值要正确
