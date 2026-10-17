# 数据库设计

权威 DDL：[archive-schema-v0.4.sql](reference/archive-schema-v0.4.sql)。本文件只解释模型，不另写一份有差异的迁移。

## 实体边界

| 实体 | 关系/职责 |
|---|---|
| spaces / folders / tags | Space 内隔离；一个主 Folder、多标签；Folder 树防环/同级规范名称唯一 |
| documents | 稳定逻辑身份、triage_status、版本乐观锁、软删除、当前 Revision/成功 ParseRun 引用 |
| managed_objects | 不可变托管字节；hash + size 去重存储，不等同合并业务档案 |
| sources / source_entries / scan_runs | 来源、真实相对路径条目、扫描状态；与逻辑分类独立 |
| file_revisions | 每档案版本号；managed/external 互斥引用；原始文件名/MIME/hash |
| document_types / field_definitions / document_type_fields | 业务类型、字段定义与归档必填模板；MIME 与业务类型正交 |
| metadata_values | 已采用业务字段，类型值互斥、来源/确认状态、乐观锁由应用事务保证 |
| parse_runs / content_blocks / derived_assets | 解析版本、可定位结构块与派生文件 |
| extracted_metadata | 原始候选值、provenance、置信度；不直接覆盖正式字段 |
| jobs / document_events / source_exclusions | 持久任务、审计、外部排除重导规则 |
| document_search / document_search_state | 单档案 FTS 投影和 tokenizer_version，非事实主表 |

## 不可误读

- 一个 Document 只有一个主 Folder。原型 PDF 中“一个文件可在多个文件夹”是示意图错误，不可按图建多对多文件夹模型。
- metadata_values 的 decimal 是 ×10,000 INTEGER；API 使用字符串，支持四位小数并验证范围，不能浮点/字典序比较。
- bool false 与未设置 null 分开；字段 key/type 改动必须迁移；换业务类型不清除旧字段。
- 外部历史 Revision 只记录当时事实，不保证当时字节可恢复；source_path_at_capture 不是恢复证据。
- current_parse_run_id 可能对应旧 Revision，因此需要 stale 显式提示。
- SQL 的元数据候选 provenance_json、块 locator_json 需应用做结构验证；不能只校验 JSON 语法。

## 迁移/事务准入

SQLite >=3.38，启用 JSON/FTS5。每个连接配置 foreign_keys=ON、busy_timeout，WAL 由初始化管理。V0.4 SQL 为设计基线，T02 接入迁移执行器；在未发布生产迁移前也必须用测试明确版本管理，不直接把 IF NOT EXISTS 当升级策略。

验证复合 FK、同文档引用、root folder 唯一、防环、各字段类型和托管对象 hash/size；审查 UPDATE 路径及跨表约束，SQL 未覆盖的由应用事务补齐。FTS 删除旧投影再插入一次并更新 state，保证单文档当前记录，无重复。

本次仅执行空库 SQL、重复执行与 integrity_check；不是对全部业务并发与异常规则的完整证明。完整测试见 TESTING。

## T03 增量认证表

`services/migrations/0002_auth.sql` 新增 auth_admin、auth_sessions、auth_api_tokens、
auth_login_throttle，schema_migrations 记录 0.4.1。0001 与 V0.4 参考 DDL 保持不变。
认证摘要、期限和限流计数持久化于 Archive SQLite；Converter 不访问这些表。
密码重置事务内撤销会话和 Token；Cookie 凭据管理写入在事务锁内再次验证会话及 CSRF。

## T06 事务接入

DocumentService 直接复用既有 documents/file_revisions/managed_objects/document_events 表，
未修改已应用迁移。当前 Revision 与创建/追加事件在一个事务提交；递增编号和乐观版本检查由写锁串行化。
人工字段与旧 ParseRun 不被追加原件覆盖；软删除/恢复保留文件引用。审计写入失败触发整笔回滚。
T05 标签删除已复用共享审计插入，仍递增受影响 Document 版本。孤儿对象 GC 与扫描登记尚未实现。

## T07 任务迁移

0003_jobs.sql 对既有 jobs 增量添加幂等键/请求摘要、可认领时间、租约所有者/令牌/期限、
执行限时与重试控制，补 worker_heartbeats。迁移不重建 jobs、不丢弃已有记录；原0001/0002不变。
任务完成与业务 effect 必须共享同一SQLite事务，过期租约提交失败则整笔回滚；不得在effect中另开写事务。

## T09 事务接入

未新增或改写迁移。公开档案编辑/整理与目录子树删除复用document_version和document_events；
子树操作在BEGIN IMMEDIATE中验证Source引用、更新档案并审计，再按深度删除目录。失败整体回滚。
软删除/恢复、目录删除不删除Revision或managed_objects，也不触碰外部原件。

## T10 批量审计与撤销

无新迁移；复用jobs(kind=batch)固定payload、result_json和document_events.batch_job_id。
每项SAVEPOINT内写逻辑字段、版本与前后审计，业务失败回滚该项；最终结果与整个任务完成在同一围栏事务提交。
撤销查询原成功事件，用after.document_version比较当前版本，恢复引用重新验证；新审计关联撤销任务。
原件与Revision无副作用，失败/崩溃不留下部分任务提交；错误只含稳定代码，不持久化原始异常路径。

## T17 字段维护

复用原field_definitions和document_type_fields，无新迁移。API将key/type/space固定，停用不会删除模板/metadata_values。
新增模板绑定要求启用/同空间，已有停用绑定可保留/调整/移除；所有模板替换在同一写事务验证并提交。
约束配置保留JSON，七类型值落盘及规则求值留T18；目录、原件、Revision和现存文档版本不因定义更新而改变。

## T18 元数据值与来源

无新迁移；复用metadata_values现有互斥类型列、Decimal±90000000000000000缩放整数及SQLite类型触发器。
API null删除行；boolean false存0，未设置无行。Decimal API固定四位字符串，不用浮点或文本做数值比较。
元数据变化/版本递增/含前后metadata的document_events同事务；采纳事件附extracted_metadata_id，行关联source_parse_run_id。
候选行不删除、旧人工值保留审计；失败回滚、no-op不改updated_at或版本。历史值读取不自动迁移/强制转型。

## T26 浏览器边界

无新迁移。浏览器不含演示业务数据库，不写localStorage中的档案/认证凭证；空间/目录/上传由既有API事务落SQLite。
E2E临时SQLite与随机管理员跟随一次性测试服务清理，不使用或重置正常Compose卷。

## T27 数据变更边界

无新增迁移。批量restore复用既有deleted_at、document_version、jobs与document_events；逐项事务清除回收标记并校验目录，递增版本且记录审计。
无变化项不增版本；冲突不修改。恢复/撤销均保留托管字节及元数据，不恢复不可用目录引用。

## T11 无数据表变更

本轮仅配置挂载白名单与安全访问，无迁移，GET /source-mounts不创建sources/source_entries/documents或扫描记录。
Source/SourceEntry访问及扫描预览留T12，复用已存在的DDL，不把挂载ready误写为last_successful_scan_at。

## T12 复用来源与扫描表

无新迁移。创建来源写sources（root_ref只保存管理员别名）；preview事务写scan_runs(mode=preview,status=queued)及jobs(kind=scan_preview,target_type=source_preview,target_id=scan_runs.id)。
队列事务同时更新scan_runs的status/started_at/finished_at/result_json/error_json及sources状态；重试清除结束标记/旧结果，保留首次started_at，最终完成与Job结果原子落库。
preview不写source_entries/documents/file_revisions/folders，不更新initial_import_completed_at或last_successful_scan_at；离线仅读取库存，不改条目状态。
条目查询按source_id及完整路径段筛选，relative_path_norm,id稳定排序，Unicode精确保留。
