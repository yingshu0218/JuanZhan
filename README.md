# JuanZhan

轻量、可自部署的档案库：同时管理托管文件与只读外部目录，提取可检索的结构化内容和元数据，支持后续数据分析与 API 调用。首版不接入 LLM。

本仓库当前阶段是 **开发知识库 + 可运行参考原型 + T01～T10 与 T17 生产基础、真实上传、档案管理、批量操作与字段定义**，不是已完成的生产档案系统。中文正式名称尚未从可访问记录中核实，仓库名称为 JuanZhan。

- 开发助手先读：[AGENTS.md](AGENTS.md)
- 文档导航：[docs/README.md](docs/README.md)
- 开始开发：[Codex 交接](docs/CODEX-HANDOFF.md)
- 已实现与未实现：[状态](docs/STATUS.md)
- 产品需求：[PRD](docs/PRD.md)
- 最新交互：[UI/UX](docs/UI-UX.md)
- 既有规格：[原始 V0.4](docs/reference/)
- 原型源码：[参考原型](docs/prototype/README.md)

重要：最终交互方向是“默认阅读提取并结构化的数据，通过关联文件入口查看原件”。参考原型尚未实现这一变更。请勿因原型能运行而跳过后端、转换器和安全实现。

生产骨架开发与运行：[DEVELOPMENT](docs/DEVELOPMENT.md)。T01～T10 与 T17 已新增服务、认证、存储、分类、档案事务、任务worker、真实上传、档案管理、批量撤销与字段定义，尚非完整档案系统。
