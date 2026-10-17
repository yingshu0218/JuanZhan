# 技术架构

## 既有 V0.4 基线

- Archive 应用：Python HTTP API（已采用 FastAPI，当前实现范围见 STATUS）、SQLite + FTS5、本地文件卷、SQLite 持久 Job/worker、Web 前端。
- Converter：独立 Python HTTP 服务，受服务 Token 保护，读取任务输入，产出结构化结果和临时资产，不直接访问 Archive 业务库。
- 两个主服务通过 Docker Compose 部署；MVP 不需要先引入 Redis、消息中间件、向量库或独立搜索集群。
- 生产与原型均采用 React 19 + Vite 6 + Phosphor Icons（ADR-026 实施选择）；原型仍是独立的示例视觉成果。

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

T01/T02 已固化选择见 ADR-015，运行步骤见 DEVELOPMENT.md；其余依赖仍按对应任务实测决策。

T03 已提供管理员 Cookie 会话与 API Token 边界；认证表属于 Archive，CLI 密码重置会撤销全部凭据，详见 ADR-016。

T04 已实现本地 managed 对象存储，发布与恢复协议见 ADR-017/DEVELOPMENT。
文件持久化先于数据库引用；崩溃后可以遗留完整孤儿对象，T15 再实现数据库感知清理。
现有存储层不能替代 T06 文档事务或 T08 HTTP 上传，也不接入 external。

T05 分类定义服务位于 catalog.py，复用 SQLite 跨空间约束与 T03 鉴权；写锁内复核凭据，读请求使用一致性事务。非空目录删除依赖文档生命周期，当前明确501，详见 ADR-018。

T06 已实现 DocumentService 内部事务，管理托管文件登记、Revision追加和软删除/恢复；事件统一由 document_events.py 写入，公开接口及状态投影仍待后续，见ADR-019。

T07 Compose增加Archive worker执行容器（非新业务服务），与API共用持久SQLite和托管卷；
Converter仍不访问Archive数据库。worker子进程执行限时，队列恢复与围栏规则见ADR-020。

T08 上传服务位于uploads.py：受限接收、保守MIME与原子落盘后，档案/版本/事件/parse任务同事务登记；解析handler仍未实现，201只代表原件安全归档。详见ADR-021。

## T09 公开管理投影

Document API复用DocumentService写事务与共享快照/版本检查；Folder删除以同连接完成子树档案和审计更新。
读API返回字段白名单，独立投影原件可用性、当前版本处理状态及旧内容stale；不输出托管键或来源文件路径。

## T10 批量处理

Batch API把已枚举选择ID与精确版本映射持久化到JobQueue；worker子进程在租约围栏事务中执行结果回调。
有界批量的业务失败用逐项savepoint隔离，档案/事件/最终结果与任务完成原子提交。Undo复用原事件快照和版本校验。
重新解析/元数据批改不接占位成功handler，暂返回501，等待对应业务服务。

## T17 字段定义边界

Field API共享catalog空间检查、写锁内认证和唯一性冲突处理；存储字段定义与模板配置，保留已有文档值。
资源界限在Pydantic输入和写锁内总量检查实施；不启动索引/解析，不将开放约束JSON当成已执行规则。T18负责实际值类型与归档校验。

## T18 统一字段值校验

类型/约束与filing检查集中metadata_values.py，HTTP、整理、批量类型/状态与撤销均复用；metadata.py提供版本化人工值与显式采纳。
规则配置更新也验证已知词汇，旧未知配置保留但使用时拒绝；regex匹配具独立超时。候选生成/索引仍与人工事实写入隔离。

## T26 Web运行边界

web/生产React组件分为会话入口、工作区导航、列表、详情、上传队列、API/通用UI；数据请求并发获取并在切换/卸载时取消。
Vite开发时/api代理到Archive；生产由Archive公开编译静态资源同源承载，Cookie/CSRF只在内存与HttpOnly Cookie中流转。
HTML提供CSP/no-store/nosniff，静态路径不能访问业务卷；API鉴权在middleware保留，仅GET/HEAD的根HTML/favicon/assets豁免。
Docker不运行Node前端进程，构建在宿主按锁生成dist；生产仍为两个业务服务和独立worker进程。无数据库迁移。
