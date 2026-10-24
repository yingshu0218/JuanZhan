# 项目开发知识库

2026-10-24 T56已部署devtest rc.24（源码8eb76b3）：文档多选标签、标签筛选/跨浏览器快捷组合及平台/Agent入库标签优先级。203项组合回归、5项标签/备份专项、6项浏览器及公网实测通过；原13档案/69文件保留，新增可删除示例后14档案/71文件。见IMPORT-TAGS、TESTING和DEVTEST。新增0018（18迁移）、契约0.4.37/99路径，无新依赖。

2026-10-24 T55已部署devtest rc.23（源码323ed2e）：当前版本Agent概览优先且不重复显示本地兜底，标题统一注明来源；已存在分析时自动解析跳过提取，保留主动重解析/版本回退；模板强化核心结论、关键条件及行动。52项组合后端、最终源码15项Agent集成、1项浏览器及公网五模板桌面/手机复验通过。13档案/69文件及业务表不变，17迁移，无新增依赖；入口仍为https://8.153.19.221:9443/。历史分析内容不自动重写。

T54 deployed to devtest rc.22 (2026-10-24), source 3a36641, image sha256:b9a97b2f2702a0644d159e431807e34104ffcbf76bd35ee048959426f5c5f360. Five business templates, explicit scoped import grants, immutable version/hash-bound external analyses, local parser fallback, Markdown search, and read-only MCP template/analysis tools are available at https://8.153.19.221:9443/ . Migration 0017 applied (17 total), contract 0.4.36/98 paths. Existing 8 documents and 45 files preserved; five synthetic sample documents added to the removable Agent template acceptance space (13 documents/69 files total). All five originals and independently parsed quotes verified, public desktop/mobile UI checked; readonly import denied and temporary test credentials revoked. No internal model or new dependencies. See AGENT-IMPORT and TESTING.

T53 deployed to devtest rc.21, source 7bde918, image sha256:efe0e89339c663eab0ccde0465cb84bc38dda4a2efa3de38d7731729622acb22. Entry: https://8.153.19.221:9443/ . Migration 0016 applied (16 total); contract 0.4.35/94 paths. All 8 revisions have persistent Markdown copies (28505 bytes): 7 content, 1 metadata-only unavailable. REST and MCP each verified all 8 copies and hashes. Existing business tables and 37 files unchanged; 8 new copies, 45 file hashes unchanged after QA. Final focused tests: 60 passed. See MARKDOWN-COPIES, TESTING and DEVTEST.

2026-10-22 T52已部署rc.20：上传跳过Git/SVN/Hg/Bazaar元数据目录及Git配置/指针文件，保留README/源码，不解释上传项目.gitignore内容。53后端/契约及6目录/枚举检查通过，公网跳过/拒绝和数据保护通过；8档案/37文件不变，无新依赖/迁移。更广依赖/缓存/构建目录范围待用户选择，完整规则见UPLOAD-EXCLUSIONS。下文为历史交付。

2026-10-22最新T51已部署rc.19：上传排除已知系统元数据/缩略图缓存/锁文件和系统辅助目录，Web/API共享规则，界面可查看跳过记录；普通隐藏文档与备份保留。完整清单见UPLOAD-EXCLUSIONS，契约0.4.33/93路径，无新增依赖/迁移。43后端/契约及9上传/界面检查通过，公网拒绝/跳过与数据保护通过，部署前8档案/37文件不变。下文为历史交付。

2026-10-22最新：T50文件夹选择及文件/文件夹混合拖放已部署devtest rc.18，保留逻辑目录层级，真实22文件目录选择、原生CDP混合拖放/空目录/重复及重试检查通过。无新增依赖/迁移/API变化，原4档案/业务表/20文件不变；范围及入口见STATUS、TESTING、DEVTEST。下文为历史交付。

最新交付：T48紧凑资料列表、T49系统概览与自适应列表已部署devtest rc.17。根入口显示全空间真实统计/近期档案/任务入口，未选文件列表全宽、选中才展开详情，保留显式URL/筛选/批量/拖放。15项浏览器流程及公网1440/390复验通过，原4档案/业务表/20文件不变，无新增依赖/迁移。精确证据见STATUS、TESTING、DEVTEST。下文为历史交付记录。

当前交付：BATCH-SOURCE-FILES的T43～T47已完成并部署devtest rc.15（15迁移、Archive0.4.32/93路径），包括概览专用详情、平台源文件/历史版本阅读、外部服务器副本与存储管理。完整测试/最终升级恢复/公网Word及Agent验证见BATCH-SOURCE-FILES、DEVTEST、TESTING；依赖与清理见LOCAL-DEVELOPMENT。原4档案及业务表不变、旧19文件完整保留，新增1份可重建阅读PDF。压缩和正式域名/发布按用户决定延期。下文rc.14/T37～T42为历史交付。

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
| [源文件批次](BATCH-SOURCE-FILES.md) | T43～T47交付范围及逐项验证 |
| [源文件阅读](NATIVE-READING.md) | 服务器副本、版本、隔离预览与清理规则 |
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
