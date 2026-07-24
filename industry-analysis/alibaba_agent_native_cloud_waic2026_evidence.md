# 阿里云 Agent Native Cloud (WAIC 2026) — 证据清单

> 生成日期：2026-07-23

---

## Block 1: Agent Native Cloud 整体发布

Claim: 阿里云于2026年7月18日在WAIC 2026正式发布Agent Native Cloud（智能体原生的云），同步推出AgentTeams、Agentic Computer等企业级智能体工具。
Source: 环球网科技报道
URL: http://m.toutiao.com/group/7663763735362552371/
Date: 2026-07-18
Excerpt: "7月18日，在2026世界人工智能大会上，阿里云正式发布Agent Native Cloud(智能体原生的云)，并同步推出AgentTeams、Agentic Computer等企业级智能体工具，覆盖基础设施、开发平台和云桌面等多个维度"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 2: Agent Native Cloud 三层架构

Claim: Agent Native Cloud采用Infra-Platform-Desktop三层架构。Infra提供可信运行环境（Sandbox为核心），Platform提供企业级Agent PaaS（AgentRun/AgentTeams/AgentLoop七大模块），Desktop通过无影Agentic Computer让Agent进入真实业务界面。
Source: 阿里云云原生博客（周琦演讲整理）
URL: https://blog.csdn.net/alisystemsoftware/article/details/163052930
Date: 2026-07-20
Excerpt: "Agent Native Cloud归纳了三层能力：Infra-Platform-Desktop。Infra提供的是可信的运行环境，让Agent安全、弹性地运行；Desktop连接的是业务世界，让Agent进入真实的工作现场；而Agent Platform，则是把Agent的构建、治理、协作和进化统一起来"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 3: Agent Sandbox 技术细节

Claim: Agent Sandbox基于MicroVM/VM级强隔离，叠加网络、存储、会话三重隔离，支持深休眠/浅休眠/按需唤醒，实例可缩容至0；支持每分钟15,000沙箱的弹性伸缩；兼容E2B SDK和K8s协议。
Source: 阿里云官方帮助文档
URL: https://help.aliyun.com/en/cs/user-guide/agent-sandbox/
Date: 2026-06-23
Excerpt: "Agent Sandbox offers MicroVM-level isolated runtime environments, memory-level hibernation and wake-up, checkpoint and cloning capabilities, and massive elastic scaling of up to 15,000 sandboxes per minute"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 4: AgentTeams 三层级协同架构

Claim: AgentTeams采用Manager Agent→Team Leader Agent→Worker Agent三层级协同架构，比Claude Managed Agents的两层架构(Lead+Teammates)多一个TL层级，更适配中大型企业复杂协同需求。
Source: 头条WAIC深度报告
URL: http://m.toutiao.com/group/7664251185318953515/
Date: 2026-07-20
Excerpt: "AgentTeams采用了Manager Agent→Team Leader Agent→Worker Agent的三层级协同架构——这一架构模型，比目前行业内主流的Claude Managed Agents的两层架构多了一个TL层级"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 5: AgentTeams 声明式CRD与Matrix协议

Claim: AgentTeams将群聊抽象为一组声明式CRD，每个Agent和真人赋予一层身份（Manager/Team Leader/Worker/Human三级权限）。底层通信走Matrix协议，通过Element Web接入钉钉、企微、飞书等主流IM。每个Worker携带SOUL.md/AGENT.md/MEMORY.md/USER.md声明文件。
Source: 掘金社区技术分析
URL: https://juejin.cn/post/7657169928600731691
Date: 2026-07-01
Excerpt: "阿里云AgentTeams给出的，则是一个更工程化的定义。把群聊抽象为一组声明式CRD...底层通信走Matrix协议，通过Element Web接入钉钉、企微、飞书等主流IM"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 6: AgentTeams 统一身份治理与凭据托管

Claim: AgentTeams支持企业IdP/SSO用户体系对接，为Agent工作负载签发唯一数字身份；所有凭据（LLM Key/MCP凭据/GitHub PAT等）集中托管在Higress AI Gateway，Worker只持有可撤销的Consumer Token，采用零信任安全模型。
Source: 阿里云开发者社区
URL: https://developer.aliyun.com/article/1748655
Date: 2026-07-17
Excerpt: "Agent Identity把企业已有的IdP和SSO用户体系接进来，为Agent工作负载签发身份，把用户身份透传到Agent，每一步操作都可归属到人...所有凭据集中托管在Higress AI Gateway，Worker只持有可撤销的Consumer Token"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 7: AgentTeams 引擎热插拔

Claim: AgentTeams在协议层做了解耦，底层引擎可以混编——同一Team内Worker A可跑QwenPaw，Worker B纳管OpenClaw，Worker C纳管Claude Code，避免与特定模型/框架深度绑定。
Source: 阿里云开发者社区
URL: https://developer.aliyun.com/article/1748655
Date: 2026-07-17
Excerpt: "我们在协议层做了解耦，底层引擎可以混编。同一个Team里面，Worker A可以跑我们自己的QwenPaw，Worker B纳管OpenClaw，Worker C纳管Claude Code"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 8: AgentLoop 观测与优化

Claim: AgentLoop提供全栈观测、审计、评估与持续优化能力，引入"Agent-as-a-Judge"范式，由专门评估Agent基于执行轨迹做深度分析，发现的问题自动沉淀为经验教训反馈回知识库。
Source: 博客园阿里云官方
URL: https://www.cnblogs.com/alisystemsoftware/p/21299835
Date: 2026-07-09
Excerpt: "AgentLoop引入AI评估AI的方法（Agent-as-a-Judge范式）——由一个专门的评估智能体基于执行轨迹做深度分析，自动发现回答跑题、信息编造等典型问题"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 9: Agentic Computer (无影) 技术方案

Claim: 无影Agentic Computer为Agent提供7×24小时完整Windows/Linux桌面级运行环境，覆盖80%企业白领真实工作场景；对接6大企业身份源，7层安全闭环；单人可运维千台规模，资源按需弹性伸缩，运维人效提升10倍以上。
Source: 环球网WAIC报道
URL: http://m.toutiao.com/group/7663763735362552371/
Date: 2026-07-18
Excerpt: "阿里云无影Agentic Computer给Agent提供了一个7×24小时的完整桌面级运行环境，覆盖80%企业白领的真实工作场景...对接6大企业身份源，7层安全闭环覆盖Agent运行时的7大类风险"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 10: ANOLISA 操作系统

Claim: Alibaba Cloud Linux 4 Agentic版（ANOLISA）是面向Agent场景的全新操作系统，主流场景Token优化30%，Bench分数提升10%，Agent执行时长降低30%，冷启动时长降低20%，具备三层纵深防御架构和工作区快照恢复功能。
Source: IT之家
URL: http://m.toutiao.com/group/7664573266317410826/
Date: 2026-07-20
Excerpt: "Alibaba Cloud Linux 4 Agentic版(ANOLISA)是阿里云面向Agent场景推出的全新操作系统，可以显著降低Token浪费(主流场景节省30%)，优化Agent运行表现(主流Bench分数提升10%、Agent执行时长降低30%、冷启动时长降低20%)"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 11: 内部Dogfooding数据

Claim: 阿里云团队运行15个Agent实现7×24小时服务海量开发者，处理85%答疑量，运营支持时长降低90%，版本发布压缩到1天。
Source: 阿里云云原生博客（周琦演讲）
URL: https://blog.csdn.net/alisystemsoftware/article/details/163052930
Date: 2026-07-20
Excerpt: "运行了15个Agent，7×24小时服务海量开发者，处理了85%的答疑量，运营支持时长降低90%，版本发布压缩到1天"
Scope fit: IN-SCOPE
Confidence: MEDIUM [内部数据，未经独立验证]

---

## Block 12: TokenWorks 推理优化

Claim: PAI-EAS TokenWorks集成请求路由、推理执行、计算复用和调度为单一系统；主调度策略按三层优先级（会话亲和→前缀缓存→负载均衡）路由请求到推理实例。
Source: 阿里云PAI官方文档
URL: https://help.aliyun.com/zh/pai/tokenworks-config-center
Date: 2026-07-07
Excerpt: "主调度策略按三层优先级（会话亲和→前缀缓存→负载均衡）将请求路由到推理实例，逐层匹配，命中即路由"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 13: 灵骏真武M890超节点实例

Claim: 灵骏真武M890超节点实例64卡，卡间互联800GB/s，单实例可承载十万亿参数级MoE大模型推理；通过ICN Switch 1.0芯片Scale-up互联规模由16卡拉升至64卡。
Source: 头条科技报道
URL: http://m.toutiao.com/group/7664190200269734442/
Date: 2026-07-19
Excerpt: "灵骏真武M890超节点实例...64卡、800GB/s...通过ICN Switch 1.0芯片Scale-up互联规模由16卡拉升至64卡，卡间互联提升至800GB/s，一台超节点实例可承载十万亿参数级MoE大模型的推理"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 14: Agent Native Cloud 商业信息缺失

Claim: Agent Native Cloud整个产品系列未披露定价、GA日期、命名客户。AgentRun/AgentLoop/AgentTeams/TokenWorks均无商业条款。
Source: The New Claw Times
URL: https://newclawtimes.com/articles/alibaba-agentloop-agentteams-waic-2026-agent-infrastructure-china/
Date: 2026-07-21
Excerpt: "Zero commercial specifics across the entire suite. No pricing for AgentRun, AgentLoop, AgentTeams, or TokenWorks. No GA or preview dates. No named customer, pilot, or deployment reference."
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 15: Agent Platform 控制平面七大模块

Claim: Agent Platform控制平面由Identity（唯一AgentID）、Gateway（鉴权/凭证托管/安全护栏）、Policy（业务规则验证与阻断）、资产注册（Agent/MCP/Tools/Skill统一管理）、可观测、评估与优化、版本管理七大模块构成。
Source: 阿里云云原生博客
URL: https://blog.csdn.net/alisystemsoftware/article/details/163052930
Date: 2026-07-20
Excerpt: "控制平面由7个模块构成：Identity、Gateway、Policy、资产注册、可观测、评估与优化、版本管理"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 16: AgentTeams 群体记忆三层架构

Claim: AgentTeams记忆分三层：短期记忆（session/dialog/ + daily/事实卡片）、长期记忆（digest/{personal,procedure,wiki}/三类结构化目录，企业环境对接AnalyticDB for PostgreSQL长记忆服务）、Dream机制（Agent每晚"睡觉"整合记忆）。
Source: 掘金社区
URL: https://juejin.cn/post/7657169928600731691
Date: 2026-07-01
Excerpt: "第一层短期记忆：原始对话流水落到session/dialog/...第二层，长期记忆走digest/{personal,procedure,wiki}/三类结构化目录...后端可插拔，本地默认是Markdown+BM25/Embedding/wikilink混合索引，企业生产环境对接到AnalyticDB for PostgreSQL的长记忆服务"
Scope fit: IN-SCOPE
Confidence: MEDIUM

---

## Block 17: 行业竞争格局

Claim: AWS构建Bedrock AgentCore（含Runtime/Memory/Gateway/Browser/Identity/Observability），Microsoft推出Agent 365，Google重新定位Agentic Data Cloud。Linux Foundation的Agentic AI Foundation于2026年6月接受Solo.io的agentgateway项目，已有300+贡献者。
Source: The New Claw Times
URL: https://newclawtimes.com/articles/alibaba-agentloop-agentteams-waic-2026-agent-infrastructure-china/
Date: 2026-07-21
Excerpt: "AWS is building agent runtime and governance into Bedrock AgentCore. Microsoft unveiled Agent 365 at Ignite 2025. Google repositioned around an Agentic Data Cloud at Cloud Next 2026. The Linux Foundation's Agentic AI Foundation accepted Solo.io's agentgateway project in June 2026, now with 300+ contributors across 60+ organizations"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 18: AWS Bedrock AgentCore 对比参考

Claim: Amazon Bedrock AgentCore提供模块化全托管Agent平台，核心组件包括Runtime（Serverless环境，最长8小时异步任务）、Memory（跨会话记忆共享）、Identity（对接Okta/Entra ID/Cognito）、Gateway（MCP/A2A协议支持）。2026年6月18日Harness GA。
Source: AWS官方博客
URL: https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-harness-is-now-generally-available-go-from-idea-to-production-grade-agent-in-minutes/
Date: 2026-06-18
Excerpt: "The harness handles that wiring as a managed abstraction...It runs in its own isolated environment with a filesystem and shell, so it can read files, run commands, and write code safely"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 19: OpenLink/OpenDAW 信息缺失

Claim: 未能通过公开搜索找到名为"OpenLink"的Agent协作网络产品或"OpenDAW"的AI Agent友好基础设施产品的具体信息。这两个名称可能为内部项目或极早期阶段项目。
Source: [INFO_GAP]
URL: N/A
Date: N/A
Excerpt: N/A
Scope fit: IN-SCOPE
Confidence: LOW [公开信息不足，标注为INFO_GAP]

---

## Block 20: Agent Sandbox 定价

Claim: 中国大陆Agent Sandbox按vCPU+内存按秒计费：vCPU CNY 0.0000217/秒(CNY 0.078/小时)，内存CNY 0.00001083/秒(CNY 0.039/小时)。休眠状态不收vCPU/内存费用。
Source: 阿里云官方帮助文档
URL: https://help.aliyun.com/en/cs/user-guide/agent-sandbox/
Date: 2026-06-23
Excerpt: "Chinese mainland: Agent Sandbox default: vCPU CNY 0.0000217/second (CNY 0.078/hour), Memory CNY 0.00001083/second (CNY 0.039/hour)"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 21: 轻量应用服务器智能体专用型实例

Claim: 阿里云推出轻量应用服务器智能体专用型实例，将vCPU/内存/云盘/200Mbps带宽/Tokens打包为预付费套餐。入门版2核2G+2亿Token/月，活动价262.5元/月。已在12个地域上线。搭载ANOLISA操作系统。
Source: 阿里云开发者社区
URL: https://developer.aliyun.com/article/1749820
Date: 2026-07-21
Excerpt: "阿里云重构产品架构，将vCPU、内存、云盘、200Mbps峰值带宽(免流量费)与大模型Tokens(1亿至32亿不等)封装为一款全新的Agent原生云服务器...入门级2核2G+2亿Token规格，包月购买(5折)仅262.5元/月"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 22: AI业务收入数据

Claim: 2026财年Q1，阿里云AI相关产品季度收入达89.71亿元，连续11个季度实现三位数同比增长，占比首次突破30%。
Source: 新浪财经
URL: https://cj.sina.cn/articles/view/7879996043/1d5af328b06802fpgo
Date: 2026-07-21
Excerpt: "2026财年Q1，AI相关产品季度收入达89.71亿元，连续11个季度实现三位数同比增长，占比首次突破30%"
Scope fit: PARTIAL [背景数据，非WAIC发布核心内容]
Confidence: MEDIUM

---

## Block 23: 平头哥真武芯片出货量

Claim: 截至2026年4月，平头哥真武AI芯片累计出货56万片，支持400+客户，覆盖20+行业。
Source: Alibaba Cloud Blog (Alizila)
URL: https://www.alibabacloud.com/blog/alibaba-cloud-unveils-agent-native-innovations-at-waic-2026_603377
Date: 2026-07-20
Excerpt: "As of April 2026, cumulative shipments of Zhenwu chips reached 560,000 units, supporting over 400 customers across more than 20 industries"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 24: 垂直集成栈分析

Claim: Agent Native Cloud形成从芯片到编排的垂直集成：硅片(真武)→芯片软件(SAIL)→推理服务(TokenWorks)→Agent运行时(AgentRun)→可观测(AgentLoop)→多Agent治理(AgentTeams)。"没有其他WAIC发布尝试过如此完整的栈声明。"
Source: The New Claw Times
URL: https://newclawtimes.com/articles/alibaba-agentloop-agentteams-waic-2026-agent-infrastructure-china/
Date: 2026-07-21
Excerpt: "Read together, the pattern is vertical integration: silicon (Zhenwu), chip software (SAIL), inference serving (TokenWorks), agent runtime (AgentRun), observability (AgentLoop), and multi-agent governance (AgentTeams)...no other announcement at WAIC attempted a stack claim that tall"
Scope fit: IN-SCOPE
Confidence: HIGH

---

## Block 25: Agent Native 五维定义

Claim: 阿里云定义Agent Native需在业务、组织、工程、运营、基础设施五个维度同时原生。"接入一个Agent，并不是Agent Native。Agent Native是一种全新的生产关系。"
Source: 阿里云云原生博客
URL: https://blog.csdn.net/alisystemsoftware/article/details/163052930
Date: 2026-07-20
Excerpt: "接入一个Agent，并不是Agent Native。Agent Native是一种全新的生产关系，带来的是更强劲的组织生产力。我们把这种生产关系拆解到业务、组织、工程、运营、基础设施5个纬度"
Scope fit: IN-SCOPE
Confidence: HIGH
