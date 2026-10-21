# 项目开发知识库

2026-10-21当前交付：T37～T42完成，devtest rc.14、20种输入MIME、REST/OpenAPI/MCP/stdio及OAuth、IP HTTPS已验证。入口与数据保护见DEVTEST，逐项验收见BATCH-2026-10-21，外部模型联调见AGENT-INTEROP，授权见OAUTH，IP证书续期/停用见IP-TEST，依赖与清理见LOCAL-DEVELOPMENT。正式域名和正式上线按用户决定延期。

当前开发摘要更新于2026-10-20；最初整理日期2026-10-16（Asia/Shanghai）。用于把当前可访问 Chat/Work 决策、原始设计文件和已有原型交给 Codex；不是所有历史聊天全文的导出。

| 文档 | 用途 |
|---|---|
| [PRD](PRD.md) | 当前产品范围与验收规则 |
| [技术架构](ARCHITECTURE.md) | 服务边界、数据流、部署与待选项 |
| [数据库](DATABASE.md) | 实体关系与迁移约束 |
| [Agent接入](AGENT-API.md) | MCP/REST只读凭据、协议、客户端和分析证据 |
| [文件类型验证](FORMATS-VERIFIED.md) | 当前全部输入MIME、OCR及不支持边界 |
| [当前后续批次](BATCH-2026-10-21.md) | 旧Office/RTF、通用Agent/API/OAuth及IP端口测试的完整执行范围 |
| [API](API.md) | 两套 HTTP 契约、调用顺序与缺口 |
| [转换器](CONVERTER.md) | 六格式、OCR 与标准输出 |
| [解析依赖许可](THIRD-PARTY.md) | T20版本、许可及再分发入口 |
| [UI/UX](UI-UX.md) | 结构化内容优先交互与原型差距 |
| [决策记录](DECISIONS.md) | 已确认、基线、建议和待定分开 |
| [开发任务](TASKS.md) | 按依赖实施，逐项验收 |
| [本机依赖与清理](LOCAL-DEVELOPMENT.md) | 本机安装、缓存、测试夹具与安全清理边界 |
| [验证](TESTING.md) | 本次规格检查及生产测试要求 |
| [功能交付核对](FEATURE-BACKLOG.md) | 本阶段补充功能与最终验收门槛 |
| [项目状态](STATUS.md) | 已有成果与未实现能力 |
| [Codex 交接](CODEX-HANDOFF.md) | 可直接执行的首轮工作指令 |
| [上下文缺口](CONTEXT-GAPS.md) | 无法核实的信息和冲突处理 |
| [来源清单](SOURCES.md) | 原始文件版本、摘要范围与出处 |
| [历史 V0.4](reference/) | 原始 PRD、SQL、API、路线图，完整保留 |
| [参考原型](prototype/) | React/Vite 示例源码和缩略图；不是生产实现 |

## 权威顺序

最新明确用户决定 → 对应现行领域规格 → V0.4 PRD 统一决议 → V0.3 附录 → 原型示意。API/SQL 与新需求冲突必须先更新契约与迁移设计。结构化内容优先是明确的后续 UI 决定，并不改变一档案一个主 Folder 的数据规则。

本知识库不引入其他无关业务、账号或个人资料。用户要求直接交付 GitHub，不制作新的 ZIP。

当前后端已交付至T25：正文/历史/候选API、版本化中文FTS及简单/高级检索已接真实持久数据；T29结构化正文/候选及历史阅读已交付，T30生产搜索/组合过滤/URL恢复已交付，T31任务中心与单档案重解析/OCR已交付，T32安全原件下载/PNG预览及管理员备份恢复已交付，T33整体验收与故障注入已交付，T34本地候选/性能基线/发布Compose与升级恢复手册已交付（尚未对外发布）。模型安装与许可见[开发环境](DEVELOPMENT.md)及[第三方依赖](THIRD-PARTY.md)。

30项验收映射与执行入口见[整体验收](ACCEPTANCE.md)，本次实际验证证据见[测试](TESTING.md)。

本地候选与部署/回退见[发布手册](RELEASE.md)，真实测量与限制见[性能基线](PERFORMANCE.md)。

当前阶段（2026-10-20）：T01～T34及FEATURE-BACKLOG全部功能已交付；481项后端、七组浏览器39项及30项映射通过，rc.2升级/恢复与生产依赖实物验证通过。当前Archive0.4.28/63路径、Converter0.4.3/6路径、10迁移。最新完整证据和首轮问题修正见TESTING；未对外发布或替换业务实例。

2026-10-20试用迭代：任务中心增强文件名及真实分步进度，0011迁移、Archive0.4.29/63路径、11迁移，候选rc.4；测试/部署状态以TESTING/DEVTEST最新记录为准。
