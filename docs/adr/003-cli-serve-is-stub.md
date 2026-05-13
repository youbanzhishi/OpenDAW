# ADR-003: opendaw-cli的serve命令是占位代码

## 状态
已采纳

## 背景
opendaw-cli有serve子命令，但它只打印"starting"信息就退出，不启动任何HTTP服务。新团队成员和运维容易误以为CLI的serve能启动Web服务。

## 决策
真正的HTTP服务由opendaw-api binary提供。CLI的serve仅作占位，未来可能通过子进程启动API。

## 理由
- CLI和API是不同的二进制，职责分离
- CLI是无状态的命令行工具，API是长运行的服务
- 未来CLI可能通过子进程方式启动API（类似docker CLI → dockerd）

## 后果
- ⚠️ 部署时必须用opendaw-api而非opendaw-cli
- v1.0.1的Dockerfile错误地`cargo build -p opendaw-cli`导致部署失败
- v1.0.2修复为`cargo build -p opendaw-api`
- 建议未来CLI serve自动启动opendaw-api子进程
