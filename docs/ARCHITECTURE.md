# 技术架构

## 既有 V0.4 基线

- Archive 应用：Python HTTP API（FastAPI 为既有推荐，尚未有生产实现）、SQLite + FTS5、本地文件卷、SQLite 持久 Job/worker、Web 前端。
- Converter：独立 Python HTTP 服务，受服务 Token 保护，读取任务输入，产出结构化结果和临时资产，不直接访问 Archive 业务库。
- 两个主服务通过 Docker Compose 部署；MVP 不需要先引入 Redis、消息中间件、向量库或独立搜索集群。
- 原型采用 React 19 + Vite 6 + Phosphor Icons；这是可运行的视觉成果，不等于生产前端选型已被用户最终锁定。

## 数据流

1. Web/API 上传 → Archive 鉴权/校验/MIME 嗅探 → 临时写、校验、原子落盘 → Document + Revision 事务登记。
2. 或只读 Source 扫描 → SourceEntry → 外部 Revision。首次目录映射仅初始化逻辑分类。
3. Archive Job 创建 ParseRun → 二进制 multipart 发送给 Converter → 轮询任务 → 验证 ParseResult → 拉取受控 artifacts。
4. Archive 保存派生文件、块、候选元数据 → 事务切换当前成功解析 → 增量重建单文档 FTS。
5. UI 默认请求 blocks/metadata → 结构化阅读；点击关联原件时鉴权并校验 Revision 可用性后预览/下载。

## 存储边界

| 存储区域 | 所有者 | 约束 |
|---|---|---|
| database | Archive | SQLite、短事务、每连接 FK ON/WAL，备份一致性 |
| managed | Archive | 原件不可就地覆盖；新字节建新 Revision |
| derived | Archive | 按 ParseRun 隔离，成功切换引用，历史保留 |
| temporary | Converter | 任务隔离、资源限制、TTL 与主动清理 |
| external | 宿主机只读挂载 | 配置别名白名单、真实路径检查、无写回/物理删除 |

Converter 无需直接挂载 Archive 数据库或 managed 写权限；文件经受信 HTTP 边界传递。未来内部集成可以复用纯解析模块，不能让解析库接管业务元数据写入。

## 一致性/异常

上传落盘与数据库并非分布式原子事务，需设计孤儿清理/失败恢复，禁止数据库引用未完成文件。任务 claim/租约/进程数需要 T07 定义；SQLite 多 worker 写竞争以实际测试控制。新解析失败保持旧 current_parse_run_id，UI 由 content_revision_id/stale_for_current_revision 判断展示含义。

## 选型状态（不能误当最终决定）

建议沿用 React 来复用原型；建议 FastAPI 作为 API。ORM/迁移框架、解析依赖、OCR 引擎、中文分词器、文档大小/页数/时间上限、保留配额需在相应任务中选择并记录 ADR。先验证依赖重量、许可证、Apple Silicon 与目标服务器容器兼容性，再定版本；不在无实测时承诺 10 万档案吞吐量。

部署必须区分 UI 会话和服务 Token；Converter 默认仅内网，healthz 仅容器检查。生产运行配置与凭证由部署环境提供，不提交仓库。
