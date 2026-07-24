# 阿里云 Agent Native Cloud (WAIC 2026) 深度调研报告

> **完成日期**：2026-07-23  
> **发布事件**：2026年7月18日，WAIC 2026（世界人工智能大会），上海  
> **信息截止**：2026-07-23

---

## 核心发现

**阿里云在WAIC 2026发布了Agent Native Cloud——一套从自研芯片到多Agent编排的垂直集成架构，核心主张是"智能体正在取代人类工程师成为云计算的第一用户"。** 这不是单一产品发布，而是对整个云平台的产品逻辑重构：Infra层以MicroVM级Agent Sandbox为核心提供安全弹性运行环境，Platform层通过AgentRun/AgentTeams/AgentLoop三大件构成企业级Agent PaaS控制平面，Desktop层以无影Agentic Computer和ANOLISA操作系统让Agent直接进入生产工作界面。

**AgentTeams的多Agent编排设计是本次发布最具工程深度的组件。** 它采用Manager→Team Leader→Worker三层级协同架构（比Claude Managed Agents多一个管理层级），将企业组织建模为一组声明式CRD，底层通信走Matrix协议接入主流IM。在安全层面，所有凭据集中托管于Higress AI Gateway，Worker仅持有可撤销的Consumer Token，实现了零信任安全模型。更关键的设计决策是引擎热插拔——同一Team内不同Worker可运行不同Agent引擎（QwenPaw/OpenClaw/Claude Code），通过协议层解耦避免了与特定模型的锁定。

**最值得注意的信号是：Agent Native Cloud是WAIC 2026所有发布中唯一尝试覆盖"芯片→推理→运行时→观测→编排"全栈的声明。** 但整个产品系列未披露任何商业信息——无定价、无GA日期、无命名客户。这既说明架构设计的前瞻性，也意味着短期内无法进行独立验证。

---

## 1. Agent Native Cloud 整体架构与设计理念

### 1.1 核心主张：从AI-Native到Agent-Native

阿里云云原生应用平台负责人周琦在WAIC现场明确提出："下一轮竞争，比的不是谁拥有更多Agent，而是谁能把Agents变成可控、可复用、可协作、会进化的组织资产" [(阿里云云原生博客)](https://blog.csdn.net/alisystemsoftware/article/details/163052930)。这一表态标志着阿里云将产品逻辑从"为AI提供算力"转向"为Agent提供生产关系"——Agent不再是云上运行的一个负载类型，而是成为定义整个平台设计的基础原语。

这一转向的深层逻辑是：过去一年，Demo级Agent产品大量涌现，但从原型到生产的鸿沟依然显著。企业面临的真正问题不是"能否构建一个Agent"，而是"如何让数百个Agent安全、可控、可审计地协同运行"。Agent Native Cloud正是对这一 operational gap 的系统性回应。

阿里云进一步定义了"Agent Native"需在五个维度同时成立：**业务原生**（Agent进入关键生产流程）、**组织原生**（人机协作机制明确）、**工程原生**（Agent的构建/发布/复用全生命周期管理）、**运营原生**（观测/评测/持续优化）、**基础设施原生**（运行/数据/身份/可靠性保障） [(阿里云云原生博客)](https://blog.csdn.net/alisystemsoftware/article/details/163052930)。

### 1.2 三层架构：Infra → Platform → Desktop

Agent Native Cloud的整体架构分为三层，每层解决Agent落地链路中的一个核心问题：

**Infra层**解决"Agent在哪里安全运行"——以Agent Sandbox为核心，提供MicroVM级隔离、弹性伸缩和长会话低成本能力；叠加Database、Filesystem和Network组件，构成Agent运行的基础底座。

**Platform层**解决"Agent如何被组织化治理"——这是一个统一的控制平面，由AgentRun（全生命周期管理）、AgentTeams（多Agent协作治理）和AgentLoop（观测评估优化）三大核心产品，加上Identity、Gateway、Policy、资产注册、可观测、评估与优化、版本管理共七个模块组成。其核心价值是"复利"：一个团队沉淀的Skill和策略可被下一场景复用，一次风险发现可变成全局规则。

**Desktop层**解决"Agent如何进入真实工作现场"——无影Agentic Computer提供7×24桌面级运行环境，ANOLISA操作系统为Agent提供内核级优化，轻量应用服务器智能体专用型实例将算力与Token一体化打包。

![Agent Native Cloud 三层架构图](https://www.coze.cn/s/y9vVUz1wz7s/)

---

## 2. AgentTeams：多智能体编排协作机制

### 2.1 三层级协同架构

AgentTeams是本次发布中工程复杂度最高的组件，其设计核心是将人类企业的组织管理架构映射到多Agent协同逻辑中。它采用了**Manager Agent → Team Leader Agent → Worker Agent**的三层级协同架构 [(头条WAIC深度报告)](http://m.toutiao.com/group/7664251185318953515)：

- **Manager Agent（全局监管层）**：不直接执行业务任务，负责全局并发调度、跨团队协作编排、资源监控和模糊目标拆解。具备全局业务视角，可跨团队感知所有Agent工作状态。

- **Team Leader Agent（团队调度层）**：作为职能团队的负责人，接收Manager下发的子任务，进一步拆解为技术执行步骤，根据Worker的实时负载动态分配任务，并全程监控执行进度、处理容错。

- **Worker Agent（任务执行层）**：专注执行具体业务任务，每个Worker最多被授权使用两到三类工具，遵循高内聚、低耦合原则。

这一设计相比Claude Managed Agents（CMA）的两层架构（Lead + Teammates），多出的TL层级解决的是管理幅度问题——当Agent规模达到成百上千时，单层调度必然失效。阿里云开发者社区的技术文章明确指出："CMA解决的是'一次任务怎么并行'，我们解决的是'一个组织怎么长期运转'" [(阿里云开发者社区)](https://developer.aliyun.com/article/1748655)。

### 2.2 声明式CRD与Matrix协议

AgentTeams最独特的设计决策是将群聊抽象为一组**声明式CRD（Custom Resource Definitions）**，这一做法直接借用了Kubernetes的资源模型思想 [(掘金)](https://juejin.cn/post/7657169928600731691)。每个成员（无论Agent还是人类）都被赋予明确的身份类型：

| 成员 | 身份 |
|------|------|
| Manager | 人类成员，平台级管理员 |
| Team Leader | Agent，N个Workers的管理者 |
| Worker | Agent，最小执行单元 |
| Human | 人类成员，三级权限（L1 Admin / L2 Team Leader / L3 Worker） |

每个Worker携带四份声明文件：**SOUL.md**（身份定义）、**AGENT.md**（能力边界）、**MEMORY.md**（记忆配置）、**USER.md**（用户偏好）。底层通信采用**Matrix协议**，通过Element Web接入钉钉、企微、飞书等主流IM [(掘金)](https://juejin.cn/post/7657169928600731691)。

Team CRD中"1个Team Leader + N个Workers"的结构本身就是**并发的声明式表达**，每个Worker是独立的容器实例，由hiclaw-controller reconcile，类比Pod在K8s控制平面下的弹性调度。

### 2.3 零信任安全与凭据托管

在安全设计层面，AgentTeams实现了三层凭据管控：

1. **集中托管**：所有凭据（LLM Key、MCP凭据、GitHub PAT、内部API Key）集中托管在Higress AI Gateway，Worker只持有可撤销的Consumer Token，每次出向调用由网关代换为真实凭据。这相当于将K8s的ServiceAccount + RBAC模型平移到Agent的出向流量层。

2. **主Key二次签发**：一个Team持有一把主API Key，平台基于此派生N把派生凭证分发给每个Worker，天然带租户/Team/Worker三级标签。单个Worker被攻破的影响范围被严格约束在它自己的派生凭证内。

3. **MCP凭据按需下发、用完即焚**：Worker调用MCP Server时，凭据按任务粒度下发、执行完即销毁、不可转发、不可持久化 [(掘金)](https://juejin.cn/post/7657169928600731691)。

同时，AgentTeams支持企业现有IdP/SSO用户体系（钉钉/飞书/企微/RAM）的无缝对接，Agent操作的审计日志可直接追溯到对应企业用户身份。

### 2.4 引擎热插拔

AgentTeams在协议层做了关键解耦——底层Agent引擎可以混编。同一个Team内，Worker A可运行QwenPaw，Worker B纳管OpenClaw，Worker C纳管Claude Code [(阿里云开发者社区)](https://developer.aliyun.com/article/1748655)。这一设计避免了与特定模型或框架的锁定，回应了"Agent引擎在可预见的未来一定会快速迭代和分化"的行业判断。

### 2.5 群体记忆机制

AgentTeams的群体记忆分三层运作：

- **短期记忆**：原始对话流水写入session/dialog/，每次回复后由auto_memory钩子将事实卡片和摘要写入daily/目录。
- **长期记忆**：走digest/{personal, procedure, wiki}/三类结构化目录，分别对应个人事实/操作经验/知识节点。后端可插拔，本地默认Markdown + BM25/Embedding/wikilink混合索引，企业生产环境对接AnalyticDB for PostgreSQL长记忆服务。
- **Dream机制**：Agent定期"休眠"进行记忆整合（类似人类睡眠期的记忆巩固过程） [(掘金)](https://juejin.cn/post/7657169928600731691)。

---

## 3. Agentic Computer：Agent运行环境技术方案

### 3.1 无影 Agentic Computer — 桌面级运行环境

无影Agentic Computer为Agent提供完整的Windows/Linux桌面级运行环境，核心设计假设是：**Agent需要像人一样使用企业现有软件，而非通过API适配**。关键参数：覆盖80%企业白领真实办公场景，对接6大企业身份源，7层安全闭环（系统快照→安全网关→行为审计），单人可运维千台规模，运维人效提升10倍以上 [(环球网)](http://m.toutiao.com/group/7663763735362552371)。

企业可通过钉钉等办公IM直接@Agent下发指令，Agent在云端环境中代为执行。数据中心级SLA保证7×24不间断运行，不会因笔记本合盖休眠或断网中断任务。

### 3.2 Agent Sandbox — MicroVM级隔离运行时

Agent Sandbox是Infra层的核心组件，提供MicroVM级隔离运行时环境。技术规格：

- **安全隔离**：每个沙箱运行在独立MicroVM中，叠加网络、存储、会话三重隔离
- **弹性能力**：每分钟可创建最多15,000个沙箱，支持镜像缓存加速（拉取时间降低90%+）
- **状态持久化**：支持内存级休眠/唤醒（1-10秒恢复）、检查点与克隆
- **生态兼容**：兼容E2B SDK、K8s协议，覆盖函数计算FC和容器计算ACS场景
- **定价**：中国大陆vCPU CNY 0.078/小时，内存CNY 0.039/GiB/小时，休眠状态不收vCPU/内存费用 [(阿里云官方文档)](https://help.aliyun.com/en/cs/user-guide/agent-sandbox/)

### 3.3 ANOLISA — Agent专属操作系统

Alibaba Cloud Linux 4 Agentic版（ANOLISA）是面向Agent场景重新设计的操作系统，核心优化指标：

- Token浪费降低：主流场景节省**30%**
- 主流Bench分数提升：**10%**
- Agent执行时长降低：**30%**
- 冷启动时长降低：**20%**
- 安全能力：三层纵深防御架构 + 工作区快照恢复 [(IT之家)](http://m.toutiao.com/group/7664573266317410826/)

### 3.4 轻量应用服务器智能体专用型实例

阿里云将vCPU、内存、云盘、200Mbps峰值带宽（免流量费）与大模型Tokens打包为预付费套餐，提供从2核0.5G+1亿Tokens到16核64G+32亿Tokens共9款规格。入门版（2核2G+2亿Token/月）活动价262.5元/月，已在北京、上海、广州等12个地域上线 [(阿里云开发者社区)](https://developer.aliyun.com/article/1749820/)。

### 3.5 TokenWorks — 推理调度优化

PAI-EAS TokenWorks集成请求路由、推理执行、计算复用和调度为单一系统。主调度策略按三层优先级执行：**会话亲和**（同会话路由到同一实例避免上下文丢失）→ **前缀缓存**（优先选择已缓存相同前缀的实例减少重复计算）→ **负载均衡**（least-token/least-request/round-robin算法） [(阿里云PAI文档)](https://help.aliyun.com/zh/pai/tokenworks-config-center)。

---

## 4. 垂直集成栈与竞争格局

### 4.1 从芯片到编排的全栈声明

Agent Native Cloud最核心的战略信号是其垂直集成深度：

| 栈层 | 组件 | 关键指标 |
|------|------|----------|
| 芯片层 | 平头哥真武Zhenwu | 累计出货56万片（截至2026.04），覆盖400+客户/20+行业 |
| 芯片软件 | T-Head SAIL（已开源） | 兼容主流AI生态，跨OS/SDK/接口多层 |
| 超节点算力 | 灵骏真武M890 | 64卡/800GB/s卡间互联/单实例十万亿参数MoE推理 |
| 推理服务 | TokenWorks (PAI-EAS) | 三层调度（会话亲和→前缀缓存→负载均衡） |
| Agent运行时 | AgentRun + Agent Sandbox | MicroVM隔离/15,000沙箱/分钟 |
| 观测评估 | AgentLoop | Agent-as-a-Judge范式 |
| 多Agent治理 | AgentTeams | 三层级架构/声明式CRD/Matrix协议 |

正如The New Claw Times的分析："没有其他WAIC发布尝试过如此完整的栈声明" [(The New Claw Times)](https://newclawtimes.com/articles/alibaba-agentloop-agentteams-waic-2026-agent-infrastructure-china/)。

### 4.2 与AWS Bedrock AgentCore的对比

AWS Bedrock AgentCore是阿里云在Agent基础设施领域最直接的竞争对手。两者在产品形态上高度趋同，但路径选择存在差异：

| 对比维度 | 阿里云 Agent Native Cloud | AWS Bedrock AgentCore |
|----------|---------------------------|----------------------|
| 架构层级 | Infra-Platform-Desktop三层 | 模块化组件按需组合 |
| 沙箱隔离 | MicroVM（自研，兼容E2B） | MicroVM（Lambda底层） |
| 多Agent编排 | AgentTeams（三层级Leader-Worker + Matrix协议） | 无原生多Agent编排，依赖CrewAI/LangGraph等第三方框架 |
| 身份治理 | 企业IdP/SSO对接 + Higress Gateway凭据托管 + 零信任 | IAM + Okta/Entra ID/Cognito + Token Vault |
| 推理优化 | TokenWorks（三层调度策略） | 无独立推理调度服务 |
| 桌面环境 | 无影Agentic Computer（Win/Linux桌面） | 无对应产品 |
| Agent OS | ANOLISA（面向Agent的全新操作系统） | 无对应产品 |
| 自研芯片 | 真武Zhenwu（垂直集成） | 无（依赖NVIDIA等） |
| 框架绑定 | 引擎热插拔（QwenPaw/OpenClaw/Claude Code可混编） | 声明不绑定框架（CrewAI/LangGraph/LlamaIndex均支持） |
| 商业状态 | 公测中，无定价/GA日期 | Harness已GA（2026.06.18），有定价 |
| 命名客户 | 无 | Twilio/TUI/VTEX/FUJISOFT等 |

核心差异在于：阿里云选择了更重的垂直集成路线（从芯片到桌面环境），而AWS选择了更轻的模块化组合路线。阿里云的优势在于对Agent运行环境的全栈控制（特别是ANOLISA操作系统和无影桌面），劣势在于更强的平台锁定和更晚的商业化节奏。

### 4.3 行业趋同信号

四家Hyperscaler在约一年时间内独立收敛到相同的产品形态——Agent运行时、可观测、多Agent编排、身份治理——这验证了"Agent Operations"正在成为企业技术栈中一个独立层 [(The New Claw Times)](https://newclawtimes.com/articles/alibaba-agentloop-agentteams-waic-2026-agent-infrastructure-china/)。Linux Foundation于2026年6月接受Solo.io的agentgateway项目（300+贡献者/60+组织），进一步佐证了这一趋势。

但Gartner预测超过40%的Agentic AI项目将在2027年前被取消，这意味着当前阶段的竞争更多是"卡位"而非"收割"。

---

## 5. 与OpenLink/OpenDAW的关联分析

> **重要说明**：通过多轮公开搜索（中/英文），未能找到名为"OpenLink"的Agent协作网络产品或"OpenDAW"的AI Agent友好基础设施产品的具体技术文档或公开信息。以下分析基于Agent Native Cloud已披露的技术设计，对这两个方向的参考价值进行推演。标注为 [INFO_GAP]。

### 5.1 对Agent协作网络方向（OpenLink关联）的参考

AgentTeams在多Agent编排协作方面的设计，对Agent协作网络类项目具有以下参考价值：

**编排思路**：AgentTeams的三层级Manager→TL→Worker架构提供了一种"组织建模"范式——不是简单的任务编排（DAG/Pipeline），而是将Agent视为组织中有角色、有权限、有边界的"成员"。这种设计比Anthropic的CMA（两层Lead+Teammates）多了一个管理层级，更适合大规模Agent集群的治理场景。

**协议设计**：AgentTeams选择Matrix协议作为底层通信协议（通过Element Web桥接主流IM），并将组织关系声明为K8s风格的CRD，这是一个值得关注的工程选择。Matrix协议的联邦特性天然适合跨组织Agent协作场景，CRD的声明式管理则与现有云原生工具链无缝集成。

**凭据安全模型**：集中托管+可撤销Consumer Token+MCP凭据用完即焚的三层设计，为Agent协作网络中的信任问题提供了工程级解法——Agent之间协作时不需要直接交换真实凭据，所有出向调用由网关代理。

**引擎热插拔**：协议层解耦使得不同Agent引擎可以在同一Team内混编，这对Agent协作网络的互操作性设计有直接参考意义。

### 5.2 对"AI Agent友好"基础设施方向（OpenDAW关联）的参考

Agentic Computer和ANOLISA操作系统对"AI Agent友好的基础设施"设计提供了以下信号：

**桌面级而非API级**：Agent Native Cloud的核心假设是Agent需要像人一样使用软件（通过GUI操作），而非仅通过API调用。无影Agentic Computer提供完整Windows/Linux桌面，企业现有软件无需改造即可运行。这对"AI Agent友好"基础设施的定义提供了一个激进但务实的视角：**真正Agent友好的环境不是暴露更多API，而是提供Agent可以直接操作的完整计算环境**。

**OS级优化**：ANOLISA操作系统在内核层面为Agent做了专项优化（Token浪费降低30%、执行时长降低30%、冷启动降低20%），这表明"Agent友好"不是应用层的特性，而需要下沉到操作系统层。

**算力+Token一体化**：轻量应用服务器智能体专用型实例将计算资源与模型Tokens打包定价，消除了Agent运行中"算力"和"智力"分别采购的割裂。这指向一个趋势：未来的Agent基础设施将同时提供计算和推理能力，而非让用户自行拼凑。

### 5.3 阿里云作为基础设施供应商的战略信号

阿里云明确释放了"云的用户正在从人类工程师变成智能体"的信号 [(新浪财经)](https://cj.sina.cn/articles/view/7879996043/1d5af328b06802fpgo)，并据此重构整个技术体系。这意味着：

- 后续ECS等核心计算产品可能出现Agent专用实例类型
- 计费模式可能从"按资源付费"向"按结果付费"演化
- 竞争核心从"GPU数量"转向"系统工程能力"（计算+存储+网络+模型服务+Agent编排的整合）

---

## 6. 关键不确定性

1. **商业化节奏**：AgentTeams/AgentLoop均处于公测阶段，无GA日期和定价。整个Agent Native Cloud产品系列未披露任何命名客户。短期内无法评估市场接受度。

2. **内部数据验证**：15个Agent处理85%答疑量等数据来自阿里云内部Dogfooding，尚未经过独立第三方验证。这一数据描述的是特定工作负载（内部开发者支持），外推性存疑。

3. **Agent Sandbox的竞争位置**：E2B、Daytona、Modal等独立Agent Sandbox厂商在冷启动延迟（Daytona <90ms vs Agent Sandbox数百毫秒）和开源生态方面可能有优势。阿里云Sandbox的差异化更多在于与全栈的深度集成。

4. **Matrix协议的选择**：Matrix协议在主流IM桥接方面有优势，但在Agent专用通信场景中是否是最优选择（vs A2A/gRPC/WebSocket）需要进一步验证。

---

## 7. 结论

Agent Native Cloud是阿里云对"Agent正在成为云计算第一用户"这一判断的系统性工程回应。其核心价值不在于某个单一组件的技术突破，而在于**将Agent治理（身份/权限/审计）下沉到基础设施层**的设计哲学——这解决了当前Agent项目从原型到生产的最大瓶颈。

对Agent协作网络类项目的直接参考是：**组织建模（而非任务编排）是多Agent协作的正确抽象层级**；**声明式CRD + Matrix协议**是一种值得借鉴的工程实现路径。

对"AI Agent友好基础设施"类项目的直接参考是：**Agent友好的定义应该从API层下沉到OS层**（ANOLISA的思路），以及**桌面级运行环境（而非API调用）可能是Agent执行复杂任务的更自然载体**。

最关键的判断是：Agent基础设施的竞争已经不再是"要不要做"的问题——四大Hyperscaler的独立收敛验证了这一点。真正的差异化将来自**身份/隔离/可观测的集成深度**，以及**谁先拿到规模化生产的独立验证数据**。阿里云在架构完整性上暂时领先，但在商业化节奏和客户验证上落后于AWS。
