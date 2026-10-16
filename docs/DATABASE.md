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
