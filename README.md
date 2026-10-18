# JuanZhan

轻量、可自部署的档案库：同时管理托管文件与只读外部目录，提取可检索的结构化内容和元数据，支持后续数据分析与 API 调用。首版不接入 LLM。

本仓库当前为 **第一版MVP候选实现**：已覆盖T01～T15、T17～T34主线，并在用户授权Linux测试服务器完成418项后端、21项浏览器及30项验收映射，生产镜像解析/OCR与备份恢复演练通过。尚未正式对外发布或切换真实业务实例；T16等延后能力见状态文档。中文正式名称尚未从可访问记录中核实，仓库名称为 JuanZhan。

- 开发助手先读：[AGENTS.md](AGENTS.md)
- 文档导航：[docs/README.md](docs/README.md)
- 开始开发：[Codex 交接](docs/CODEX-HANDOFF.md)
- 本机/服务器依赖与清理：[开发记录](docs/LOCAL-DEVELOPMENT.md)
- 已实现与未实现：[状态](docs/STATUS.md)
- 30项验收映射与命令：[整体验收](docs/ACCEPTANCE.md)
- 本地候选/部署/升级恢复：[发布手册](docs/RELEASE.md)
- 1万/10万档案查询观测：[性能基线](docs/PERFORMANCE.md)
- 产品需求：[PRD](docs/PRD.md)
- 最新交互：[UI/UX](docs/UI-UX.md)
- 既有规格：[原始 V0.4](docs/reference/)
- 原型源码：[参考原型](docs/prototype/README.md)

重要：最终交互方向是“默认阅读提取并结构化的数据，通过关联文件入口查看原件”。参考原型尚未实现这一变更。请勿因原型能运行而跳过后端、转换器和安全实现。

生产骨架开发与运行：[DEVELOPMENT](docs/DEVELOPMENT.md)。T01～T15、T17～T25 与 T26～T30 已新增服务、认证、存储、分类、档案事务、任务worker、真实上传、档案管理、批量撤销、字段定义和值/候选维护及生产Web整理界面，尚非完整档案系统。

生产前端位于 `web/`，独立于参考原型。先 `npm ci --prefix web`、`npm run build --prefix web` 再构建 Compose；Archive 根路径提供登录页。
真实管理员初始化与HTTPS/本地开发说明见 [DEVELOPMENT](docs/DEVELOPMENT.md)，不含默认密码；浏览器验收见 [TESTING](docs/TESTING.md)。

T11～T15 已提供只读来源、扫描、排除/取消索引及永久清理接口；托管GC检查全部引用并保留至少24小时宽限。默认不接入外部目录，配置见 [DEVELOPMENT](docs/DEVELOPMENT.md)。T28已接来源配置、扫描预览/首扫/增量、库存/离线/失联与排除界面；T19～T23已交付六格式基础解析、按需OCR/受限缩略图、正文持久化及内容API；T24已接版本化中文FTS增量索引。T25公开简单/高级检索、T29结构化阅读、T30搜索与URL恢复、T31任务/重解析、T32安全原件访问/备份恢复均已实现。2026-10-19新增批量重解析界面与子任务追踪，并在用户授权Linux服务器完成当前版本完整验收，尚未对外发布。
