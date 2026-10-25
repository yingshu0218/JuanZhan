# 数据库设计

0017_agent_imports.sql新增显式导入授权标志、agent_imports及不可变agent_analyses，原件/分析版本绑定，幂等键和原件级联清理；共17迁移。分析随SQLite一致备份保存。

T53 新增 0016_revision_markdown.sql（共16迁移）：版本 Markdown 对象与持久待办、Revision/ParseRun 触发更新、统一 derived_object_references 引用保护；原15迁移不修改。

0015_reading_previews.sql（rc.15已部署）按Revision登记阅读PDF的storage_key/hash/size/renderer/创建时间；derived_object_references统一派生产物与阅读缓存引用，用于备份和GC。原14条迁移保持不变。业务实际13→15迁移通过，旧SQL校验不变。

rc.15已部署：0014_source_snapshots.sql增加external Revision到managed_object的已校验快照关联及统一original_object_references视图。原file_revisions的managed/external互斥结构保持；外部绑定保留，副本不另建Document。备份与GC必须使用统一引用视图，防止误删外部快照。触发器校验快照哈希/大小与登记版本一致。当前devtest业务为15迁移。

T41已部署：新增[0013_oauth.sql](../services/migrations/0013_oauth.sql)，授权族关联既有只读Agent凭据，新增客户端、会话请求、哈希授权码、刷新轮换重用记录及公共端点速率表。令牌与客户端删除级联撤销；不改档案、人工业务字段与解析结果。此前12条迁移不变，devtest实际12→13升级及新卷恢复已验证。

2026-10-21新增[0012_agent_access.sql](../services/migrations/0012_agent_access.sql)，共12条不可变迁移：agent_tokens保存随机凭据的SHA-256、名称、有效期及分钟请求计数；agent_token_spaces通过外键关联Token与授权空间，删除时级联清除授权。不存明文凭据，不改Document/Revision/ParseRun/人工字段。密码重置及备份恢复撤销全部Agent凭据。概要按需从已有成功正文生成，不新增概要副本表。原11条迁移不变。

2026-10-19：新增不可变迁移0009_source_schedules.sql，当前9条迁移。source_scan_schedules以source_id为外键主键，保存配置version、next_due_at Unix秒/null和last_job_id外键/null；到期索引支持有界调度。来源插入及间隔更新触发器维护期限/版本，旧正间隔保留并初始化；原有8条迁移未改。API暴露UTC时间，更新计划与调度均在SQLite事务中完成。详见ADR-052。

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

## T13 首扫原子登记

无新迁移。复用scan_runs(mode=initial)、jobs(kind=scan,target_type=source_initial,target_id=scan_runs.id)。完成事务同时写sources.initial_import_completed_at与last_successful_scan_at。
SourceEntry保存source/space/document、精确相对路径、size/mtime_ns/sha256/身份hint、available及last_seen_scan_id；Revision storage_kind=external、source_entry_id与相对source_path_at_capture，不关联managed_object。
先建Document再Entry/Revision并回填current_revision_id；version=1、初始triage来自Source，无自动按hash合并。document_created事件actor=source_scan，与parse幂等任务同事务。
临时initial_folder_map只在当前连接/事务存在，回滚/退出即消失；永久目录与首扫完成标记一同发布。无新迁移、不修改历史DDL，错误不留下部分目录/条目/档案/解析任务。

## T14 增量迁移0004

新增source_root_baselines(source_id PK/FK,root_digest长度64)与source_missing_observations(source_entry_id PK/FK,scan_run_id FK)，均级联清理引用，不存绝对路径；前三已应用迁移不改。
首扫原子保存私有根digest；增量根身份一致才允许更新，旧库必须可信锚点后建基线，缺失时不得直接将全部条目标missing。
增量在同一事务登记新Entry/Document/Revision、更新既有Entry与新增Revision、保留current_parse_run_id、写source_updated和解析Job，文档版本随系统事实变化递增。
缺失证据必须来自同来源、不同的completed incremental；失败清证据但不改Entry状态，返回文件清证据并available。成功增量只更新last_successful_scan_at。
歧义新Entry document_id可null（原DDL已允许），status=needs_match；既有Document不合并/删除。源路径变化不重写历史Revision的source_path_at_capture。

## T15 迁移0005

新增source_exclusion_versions(source_id,version)、source_exclusion_intents(job_id,source_entry_id唯一,source_id,path)、document_purge_receipts(document_id,document_version,job_id,created_at)、managed_gc_candidates(storage_key,eligible_after)。应用旧迁移checksum不变。
排除规则及屏障变化递增epoch，扫描围栏事务必须复核；终态失败释放intent，成功变为source_exclusions。原Entry可保留用于恢复，Purge时删除并留下规则。
永久清理先断开Document current指针，再删Revision/解析级联与Entry/Doc/搜索；取消活动文档任务，保留最小receipt，不保留原业务字段。外部字节不在数据库清理操作范围。
managed_objects不立即随Doc删除，GC必须核查所有file_revisions引用，候选从最后引用解除/首次发现计时至少24小时；物理失败可留无引用记录，重试清理不影响仍被引用的对象。

## T19 Converter临时数据库（不属于Archive迁移）

Converter在独立私有spool内维护tasks（临时ID/parse_run_id幂等指纹/状态/尝试/时间/安全错误/规范结果）与artifacts（随机ref→任务/sha256/大小/media_type）。SQLite FK/WAL及spool排他进程锁，只用于临时任务传输/TTL，不引用Archive表，不获得业务卷访问。Archive仍5个不可变迁移；ParseRun/DerivedAsset/ContentBlock的正式写入待T22，不因转换完成提前创建或切换current_parse_run_id。


## T21 更新 · 2026-10-17

T21无数据库迁移，仍为5条不可变迁移。OCR块/置信度、源页/帧定位和缩略图目前仅在Converter私有spool；ParseRun/ContentBlock/DerivedAsset/候选及当前成功指针的持久化、事务围栏由T22实现。不得直接把Converter SQLite当业务库。


## T22 迁移0006/0007

parse_requests(sequence INTEGER PRIMARY KEY AUTOINCREMENT,job_id唯一,document_id,revision_id)以入队事务确立请求顺序，复合FK约束档案与Revision；升级按原created_at/id回填可关联的parse/ocr任务，不改状态或重放旧失败。parse_attempts(parse_run_id主键,request_sequence,attempt,remote_job_id)的请求+attempt唯一，每次重试留下独立历史；失败钩子只关闭当前尝试。

parse_asset_order(parse_run_id,asset_index,derived_asset_id,source_artifact_ref)保留原产物顺序和同字节多帧关系；derived_assets已有唯一约束保持不动，多个逻辑帧可关联同一资产。derived_gc_candidates(storage_key,eligible_after)仅是无引用候选，GC每次复查所有derived_assets引用，至少发现后24小时宽限；purge级联删除引用并排延迟GC，不物理删除NAS。

完成事务同时写parse_runs、content_blocks（结构/真实locator/置信度）、extracted_metadata（值/来源/locator）、derived_assets/顺序及成功指针，Job也同时completed；跨表失败全部回滚。规范完整JSON作为派生产物保存，包含OCR语言与所有降级警告。失败或unsupported不插成功正文/不切指针，旧成功全部历史保留。没有新增FTS写入，搜索仍T24。旧5条迁移不改。

0007对parse_attempts与parse_asset_order增加INSERT/UPDATE作用域约束，拒绝跨Document/Revision关联尝试或跨ParseRun关联资产；已应用0006保持不变。当前共7条迁移，升级与新装执行同一序列。


## T23 无新增迁移

继续使用7条不可变迁移。正文/候选/历史读取既有ContentBlock、extracted_metadata、ParseRun及派生资产；无临时SQLite替代业务真相。reprocess请求通过既有jobs.idempotency_key/request_hash、parse_requests/attempt记录，同一写事务排队并捕获当前Revision；不新增动态路径、外部写回或业务字段自动覆盖。完整分页页字节预算在SQLite内计算后读取，业务版本只在人工操作/显式采纳变化时递增。


## T24 迁移0008

当前共8条迁移，既有7条校验和不变。search_dirty(document_id主键及级联FK,generation,scheduled_generation,last_error)为持久脏队列；document_search_state增加generation。升级只标记已有档案待索引，不重放旧解析失败。documents的业务版本/正文指针/回收状态、标签关联/名称、类型名称、可搜索字段值与字段启停触发代次变化；永久清理删除FTS行，级联触发器先检查档案存在。

复用既有document_search FTS5及document_search_state。正文取current_parse_run_id最近成功缓存，字段仅active且searchable；索引包括标题/描述/日期/标签/类型/当前原始文件名。发布同时更新hash、tokenizer_version、ParseRun及代次；hash相同仍推进代次。脏队列不是公共检索结果，T25需空间/回收过滤及新鲜度投影。


## T25 无新增迁移

继续8条不可变迁移；SELECT真实FTS与业务表，不引入搜索缓存库或新增来源写入。integer/decimal/date/boolean/text比较使用既有ix_metadata_* typed列索引；Decimal固定4位缩放、日期ISO，is_null为没有metadata_values行。当前业务条件/计数/分页同一SQLite读快照，索引状态比较search_dirty.generation与document_search_state.generation/tokenizer_version，不以Job completed冒充新鲜。FTS正文可能来自旧Revision，结果保持content_stale及原件可用性独立。


## T32 更新 · 2026-10-18

T32无新迁移。备份通过SQLite Backup API包含WAL已提交事实，冻结期间复制Revision/ParseRun引用对象；恢复校验完整性/外键/引用及精确migration_checksums，撤销旧会话/API token/心跳，running Job沿原预算处理，不修改原库。只读外部字节不在包内。

## 0010备份管理迁移 · 2026-10-20

开发版本新增backup_records、recovery_records和backup_schedule，当前10条迁移。记录关联持久job，内部source/artifact令牌不暴露API；备份完成字段成组非空，删除保留墓碑。计划保存version、分钟间隔、数量/天数保留、next_due_at及last_job_id，默认关闭。原0001～0009未改；旧9迁移备份须先使用对应旧代码恢复，再正常升级，不跳过精确迁移检查。

## 0011：任务步骤进度

jobs新增steps_json（JSON数组，旧记录默认[]），保存当前尝试的有序步骤code/status/done/total。只持有效租约的worker可推进；领取新尝试清空上轮步骤，失败/租约过期保留失败步骤，完成步骤状态与任务结果同事务提交。无原件/业务字段变化，原0010及之前迁移保持不变。


2026-10-24 0018新增document_tag_policy（文档/当前处理Revision/自动来源/人工锁）、automatic_document_tags（自动拥有的标签）和saved_filters（空间、规范化名称、惰性条件JSON，同名唯一）。自动标签仍落document_tags；人工变更锁定自动更新，外键级联清理，策略Revision删除置NULL以保留人工锁。组合随备份保留。见IMPORT-TAGS及原始0018 SQL。

2026-10-25 0019新增单行upload_policy(version,config_json)，19迁移；策略随备份恢复，固定系统辅助清单与可配置格式清单分离。
