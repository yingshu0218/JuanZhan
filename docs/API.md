# API 契约与接入

## 权威文件

- 档案 API：[archive-openapi-v0.4.yaml](reference/archive-openapi-v0.4.yaml)，OpenAPI 3.1（T15 扩展版本 0.4.16），base `/api/v1`，48 个 path 模板（含内部 healthz 与 T03 认证接口）。
- 转换器：[converter-openapi-v0.4.yaml](reference/converter-openapi-v0.4.yaml)，OpenAPI 3.1（T19版本0.4.1），6 个 path 模板，独立服务根路径。

不要从旧附录或原型字符串反推 HTTP 接口；参数、响应和错误引用需按 YAML 实现。

| 接口簇 | 主要调用 |
|---|---|
| 组织 | /spaces、/folders、/tags |
| 类型与字段 | /document-types、/field-definitions |
| 档案 | /documents、/documents/upload、/documents/{id} |
| 元数据 | /documents/{id}/metadata、/metadata/adopt-candidate |
| 内容与版本 | /documents/{id}/content?format=blocks、/revisions、/parse-runs |
| 原件 | /documents/{id}/download（先核验当前字节/版本可用性） |
| 整理与删除 | /triage、/trash、/restore、/purge；不能删除外部原件 |
| 搜索 | GET /documents?q=…、POST /documents/search |
| 批量/来源/任务 | /documents/batch、/sources…、/jobs/{id}、/jobs/{id}/retry |
| Converter | /healthz、/v1/capabilities、/v1/jobs、任务状态/result、/v1/artifacts/{artifact_ref} |

表内以 / 开始的子路径在有上下文时为对应 document 路径下后缀；精确完整路径以 YAML 为准。

## 结构化优先的详情加载

选中 Document 后读取 document 详情、content blocks、metadata、parse-runs/revisions。分别显示原件状态、解析状态、业务确认状态。无内容不伪造“成功解析”；可显示排队、失败、unsupported 或旧成功快照。点击原件入口再调用受保护下载；浏览器 PDF 查看可以复用受保护内容通道，但若新增专门 preview/asset 路由，先补 API 契约，当前不能宣称已有预览路由。

## 写入和错误

Cookie 会话所有写请求带 X-CSRF-Token，Bearer API 无 CSRF。修改档案/字段带 expected_document_version，冲突 409；类型/跨空间非法输入按契约拒绝。上传默认 duplicate_policy=reject，检测重复返回 409 DUPLICATE_DETECTED；显式 keep_separate 后建独立 Document。

分页 page/page_size；稳定次级 ID 排序；批量对象采用选择快照，逐档案报告失败，不动态扩大目标。错误体使用 YAML Error，而非任意字符串。

## 必须补齐的接口设计缺口

T03 已补齐并实现 `/auth/session`、`/auth/login`、`/auth/logout`、`/auth/tokens`、`/auth/tokens/{id}`；行为与初始化流程见 DEVELOPMENT.md。结构化正文纠错/编辑与确认某标题为 Document.title 的精确映射尚未定义，不能把原型“确认候选”直接连到任意 PATCH。需要检查 adopt-candidate 与字段定义映射，并更新契约。以上为明确待实现工作，不虚构现成接口。

## 完整路径索引（自动从原始契约读取）


### archive-openapi-v0.4.yaml

| 路径 | 方法 |
|---|---|
| `/spaces` | GET, POST |
| `/folders` | GET, POST |
| `/folders/{id}` | PATCH |
| `/folders/{id}/delete` | POST |
| `/tags` | GET, POST |
| `/tags/{id}` | PATCH, DELETE |
| `/document-types` | GET, POST |
| `/document-types/{id}` | PATCH |
| `/field-definitions` | GET, POST |
| `/field-definitions/{id}` | PATCH |
| `/documents` | GET |
| `/documents/upload` | POST |
| `/documents/search` | POST |
| `/documents/{id}` | GET, PATCH |
| `/documents/{id}/metadata` | GET, PATCH |
| `/documents/{id}/metadata/adopt-candidate` | POST |
| `/documents/{id}/triage` | POST |
| `/documents/{id}/trash` | POST |
| `/documents/{id}/restore` | POST |
| `/documents/{id}/purge` | POST |
| `/documents/{id}/revisions` | GET |
| `/documents/{id}/parse-runs` | GET |
| `/documents/{id}/content` | GET |
| `/documents/{id}/download` | GET |
| `/documents/{id}/reprocess` | POST |
| `/documents/batch` | POST |
| `/sources` | GET, POST |
| `/sources/{id}` | GET |
| `/sources/{id}/entries` | GET |
| `/sources/{id}/preview-scan` | POST |
| `/sources/{id}/scan` | POST |
| `/sources/{id}/exclusions` | GET |
| `/sources/{id}/exclude-entry` | POST |
| `/sources/{id}/exclusions/{exclusion_id}` | DELETE |
| `/jobs/{id}` | GET |
| `/jobs/{id}/retry` | POST |
| `/system/summary` | GET |

### converter-openapi-v0.4.yaml

| 路径 | 方法 |
|---|---|
| `/healthz` | GET |
| `/v1/capabilities` | GET |
| `/v1/jobs` | POST |
| `/v1/jobs/{job_id}` | GET, DELETE |
| `/v1/jobs/{job_id}/result` | GET |
| `/v1/artifacts/{artifact_ref}` | GET |

T01 新增根路径 `/healthz`（path-level server `/`），仅内部就绪检查，不属于 `/api/v1`。Converter 骨架的任务提交明确返回 501，能力为空。业务 API 尚未实现。

## T05 分类接口已实现范围

Space、Folder、Tag、DocumentType 路径已接入服务，行为与错误码见 DEVELOPMENT.md。
Space 仅 GET/POST；类型用 PATCH is_active 停用。folders GET 为扁平树；所有列表稳定排序，
可选 space_id 省略时跨空间列出（单管理员），父目录过滤只读直属子项。
目录删除仅 only_if_empty 实现；另外两种删除策略在契约中明确501，待 T09 接入。
接口更新未添加表，现有跨空间/防环/唯一 SQL 约束复用，严格输入校验与事务错误使用统一 Error。

## T06 服务与公开路由边界

内部 DocumentService 已实现托管登记/追加版本/软删除恢复，不新增公开 Document 路由。
restore 契约现要求 JSON expected_document_version，防止恢复绕过并发校验，公开实现留T09。
统一 Error 响应保留受控 details/current_document_version。上传 DUPLICATE_DETECTED 的
 details.duplicates 采用同空间 Document ID 数组，含历史版本和回收站命中；keep_separate 不合并业务档案。
原件替换的公开操作路径仍需接入前补契约，不能从内部方法推断现成 POST /revisions。

## T07 任务接口已实现

GET /jobs/{id} 返回安全公开状态；POST /jobs/{id}/retry 不重置尝试预算，允许未耗尽预算的
可重试失败任务排队或提前唤醒退避任务，其他状态409。Cookie写操作要求CSRF。
任务payload/幂等键/worker/租约令牌均不公开。详细有限重试与handler范围见 DEVELOPMENT。

## T08 上传接口已实现

POST /documents/upload接受单文件multipart，受鉴权/CSRF保护，201只表示saved。
默认重复409给出details.duplicates，keep_separate保留独立Document；parse任务同事务登记但当前handler如实失败。
文件/表单/时间/并发限制、保守MIME及400/408/413/429/503语义见DEVELOPMENT。

## T09 档案管理已实现（覆盖前文历史待实现项）

GET documents及/{id}、PATCH /{id}、POST /{id}/triage、trash、restore与GET /{id}/revisions已实现。
列表默认排除回收站，trash=only/include可调整；支持空间/目录/类型/整理/收藏/来源过滤和稳定分页排序。
非空q返回501，不能把普通列表当成搜索结果。编辑、整理、回收恢复要求expected_document_version，冲突409附当前版本。
类型必填值缺失422，自定义归档约束尚不支持时501；完整类型验证留T18。
目录非空删除支持move_contents_to_parent/trash_contents，必须confirm_folder_id等于路径ID；Source引用阻止删除409。
可用性新增unknown，外部未验证挂载不宣称available。详情与版本列表不泄露内部路径。

## T10 批量与撤销已实现

POST /documents/batch 返回202 job_id；必须传space_id、1～100个唯一document_ids、selection_mode、
完整expected_versions、operation、payload。explicit与snapshot都持久化提交的固定集合；snapshot不接受动态筛选。
任务JSON最大64KiB。GET /jobs/{id}.result是BatchResult：succeeded/skipped/failed计数与逐项document_id/status，
成功/跳过有document_version，失败有error_code；任务completed表示逐项处理完成，可能含失败项。

payload严格匹配操作：move_folder={folder_id}、add_tags/remove_tags={tag_ids}、set_type={document_type_id}、
set_triage={triage_status}、set_favorite={is_favorite}、trash={}。空目录/类型用null；收藏只接受布尔。
reprocess/set_metadata返回501。每项版本过期、跨空间、引用缺失或归档失败不影响其他成功项，无事实变化标skipped。

POST /jobs/{id}/undo无请求体，202返回幂等撤销job；只处理原成功变更，不支持再次撤销撤销任务。
执行时必须仍为原操作后的版本，且恢复引用/归档规则有效；冲突逐项失败并保留新编辑。Cookie写入须CSRF。

## T17 字段定义与模板维护已实现

GET /field-definitions（可按space_id过滤，包含停用）与POST /field-definitions、PATCH /field-definitions/{id}已实现。
创建必填space_id/key/label/type，默认constraints={}、searchable=false、filterable=false、is_active=true。
key为小写英文字母起始的[a-z0-9_]，最长255且同空间唯一；label去首尾空白/NFC、非空/无控制字符、最长255。
PATCH仅接受label/constraints/searchable/filterable/is_active，至少一个字段，不接受null或额外属性，布尔不做字符串/数字转换。
key/type/space不可修改，无硬删除。每空间最多1000个定义（含停用）；约束配置紧凑JSON16KiB、最大8层、禁止NaN/Infinity。
constraints整体替换，{}清空；规则词汇/选项形状和字段值验证留T18。searchable/filterable只保存配置。

模板fields同空间/去重，禁止新增停用字段绑定；已有绑定可保留/调整required_for_filing/display_order或移除。
停用和模板变更不删除历史metadata_values、不自动切档案整理状态或修改document_version；后续归档仍按现行模板验证。
未新增元数据值读写/候选采纳API；归档遇未实现复杂约束仍501。Cookie写入须CSRF，Bearer无需CSRF。

## T18 元数据与候选采纳已实现（覆盖前文待实现约束说明）

GET/PATCH /documents/{id}/metadata与POST /documents/{id}/metadata/adopt-candidate已实现。
PATCH需expected_document_version、values（字段key到值）、严格布尔confirm；局部更新，null删除，false为布尔值。
返回完整已存字段列表含来源/确认/source_parse_run_id，Decimal固定四位字符串；不新增/返回虚构未设置行。
每次1～1000键、值JSON256KiB、单文本65536字符；unknown/cross-space key和停用字段写入/删除拒绝，回收档案先恢复。
版本冲突409，类型/约束422，历史未知规则501；整次回滚，无事实变化不增版本，人工origin=manual。

规则词汇：text/long_text支持min_length/max_length（0～65536）与regex（512字符、完整匹配、20ms超时、量词数值上限65536）；
integer/decimal/date支持min/max，边界类型同值且min≤max；boolean仅{}；single_select的options是唯一稳定{id,label}数组，值用ID。
integer为有符号64位；date为有效YYYY-MM-DD；Decimal只接普通十进制字符串最多4位小数，范围±9000000000000.0000，禁止浮点/指数/非有限值。
新定义/约束更新拒绝未知词汇，历史未知配置需显式修复；不自动重写旧值。归档验证现模板全部必填及可选已存值。

候选采纳必须指向同档案当前成功内容/当前Revision，旧候选409、跨档案422、null候选不允许删除。
显式版本化采纳可替换人工值，记录origin=extracted/is_confirmed=true/source_parse_run_id和事件候选ID，原值留审计，原候选保留。
真实解析候选生成仍待后续；批量set_metadata/reprocess尚未开放。

## T26 Web承载边界

Archive根路径`/`及`/favicon.svg`、`/assets/{asset_path}`提供公开GET/HEAD编译静态资源，path-level server为根路径，不在/api/v1下。
只包含Web外壳和代码，不包含档案/凭证；根HTML no-store及同源CSP，assets拒绝目录穿越。不开放POST或数据卷路径。
所有业务API仍按既有鉴权/CSRF执行；生产UI完全使用已实现接口，未新增假上传/正文/预览/搜索API。
未构建web/dist时根路径明确503 WEB_NOT_BUILT，不影响健康和API测试。OpenAPI0.4.11，47个路径模板。

## T27 批量恢复

BatchRequest.operation新增restore，payload={}，沿用固定document_ids/expected_versions、异步逐项事务及审计，无新路径。
活动档案恢复为skipped；回收档案清除deleted_at，保留同空间现存folder，否则置空。实际变化递增版本；过期版本失败且不修改档案。
恢复不重新上传/复制/转换原件；一次撤销仍仅作用原成功项，并按当前版本保护后续编辑。

## T11 挂载别名发现

GET /source-mounts需要已有认证，Cache-Control:no-store；返回{items:[{alias,status,error_code}]}，默认items=[]。
status为ready/offline/unavailable；错误码为null、SOURCE_OFFLINE、SOURCE_NOT_READ_ONLY、SOURCE_UNREADABLE、SOURCE_UNSAFE_OR_UNAVAILABLE。
无服务器绝对路径，不接受客户端根路径，不创建来源或扫描。ready仅代表即时根探测，子路径/后续读取仍需验证。
本轮契约版本0.4.12、48路径；/sources及其扫描/条目接口仍待T12～T15，本轮不宣称已实现。

## T12 来源与预扫描已实现

GET/POST /sources、GET /sources/{id}、GET /sources/{id}/entries、POST /sources/{id}/preview-scan已实现；路径模板数仍48，契约0.4.13。
创建仅external和管理员root_alias，名称规范化/255字符，初始tree/flat、filed/needs_review及同空间目标目录；scan_interval_minutes可null或0～525600，只存配置，调度尚未实现。
全局禁止重复别名、相同inode及重叠配置/物理根，409 SOURCE_OVERLAP；现有根不可探测时409 SOURCE_OVERLAP_UNVERIFIED。Linux身份信息只在内部使用。
Source增加initial_target_folder_id/initial_triage_status与health{mount_status,error_code}；即时挂载offline独立于扫描错误和条目状态，查询不写入条目。
条目仅读数据库；relative_prefix按完整路径/目录段匹配，%/_为普通字符，不接受绝对/遍历/尾斜杠。page1～1000000、page_size1～100，默认1/30，排序relative_path_norm,id。
预扫描不接收根路径或导入参数；活动任务合并，返回202{job_id,status}；结果见既有Job.result。统计pdf/docx/md/markdown/html/htm/txt/epub候选扩展名，不证明真实格式/转换能力。
结果含source_id/estimated_files/estimated_bytes/ignored_files/by_extension/warnings；METADATA_ESTIMATE_NOT_SNAPSHOT表示动态元数据估算，IGNORED_UNSUPPORTED_UNSAFE_OR_INVALID_ENTRIES表示跳过项（符号链接目录按一个项计）。
默认访问项100000、目录深度64、执行120秒、最多3次尝试，超限SOURCE_PREVIEW_LIMIT失败；不可读/嵌套可写不返回截断成功。scan_runs与Job状态/结果同事务保存，preview不设置成功扫描/导入时间。
/source…/scan、排除规则/取消索引及来源UI仍待T13～T15/T28，自动扫描调度、忽略规则及同名逻辑目录冲突预检不在本轮实现。

## T13 首次导入契约

POST /sources/{id}/scan需要{mode:"initial"}，拒绝未知字段；incremental仍501 INCREMENTAL_SCAN_NOT_IMPLEMENTED。OpenAPI0.4.14、48路径。
活动initial复用原Job；与活动preview互斥409 SOURCE_SCAN_BUSY。成功完成后再次initial返回原Job/status=completed，不创建新扫描或改写档案；遗留成功标记无对应Job时409 SOURCE_INITIAL_ALREADY_COMPLETED。
按配置tree/flat和初始triage登记，初始目标目录同空间；tree创建相对目录含空目录，flat忽略物理目录。规范名碰撞（含磁盘大小写/Unicode碰撞）或目标已有同名子目录使任务SOURCE_FOLDER_CONFLICT，修复逻辑目录后可新建首扫。
Job.result为SourceInitialResult：source_id/mode=initial/imported_files/imported_bytes/created_folders/ignored_files。相同hash不同路径独立建档，不合并业务记录；未支持扩展名/非法路径/链接/特殊项计入忽略。
读取/分块hash/sniff在写锁外；变化SOURCE_CHANGED可有限重试。匿名元数据清单64MiB，超限SOURCE_MANIFEST_LIMIT；访问100000项/64层沿用SOURCE_PREVIEW_LIMIT；initial超时300秒、最多3次尝试。超限或冲突均整体失败，无截断成功。
发布事务同时写目录、条目、外部Revision、档案/事件/parse Job及扫描结果/两个来源完成时间；异常或过期租约回滚全部。已有遗留条目且无完成标记SOURCE_INITIAL_STATE_CONFLICT，不覆盖。
导入不复制/移动外部原件，哈希仅记录观察时事实，不构成历史字节快照。原件当前可用性仍unknown；parse排队不表示已转换。增量、排除与来源UI后续交付。

## T14 增量扫描契约

POST /sources/{id}/scan支持{mode:"incremental"}，首扫未完成409 SOURCE_INITIAL_REQUIRED。与preview/initial互斥409 SOURCE_SCAN_BUSY；同模式活动请求合并，完成后再次POST为独立增量。OpenAPI0.4.15/48路径。
新文件needs_review+new_file_target_folder_id，绝不创建物理镜像目录；旧路径每次hash，内容变化追加Revision和parse任务，保留人工字段/分类/旧成功解析。大小/mtime相同不等于字节未变。
hash+size在旧库存/当前观测中各唯一才重关联，保留稳定Document/Entry及历史路径；多个同hash或inode复用风险均needs_match。新歧义路径以document_id=null条目记录，显式人工匹配接口尚未交付。
SourceIncrementalResult含scanned_files/scanned_bytes/ignored_files/imported_files/updated_files/reassociated_files/recovered_files/unchanged_files及三个当前状态总数needs_match/suspected_missing/missing。更新与恢复计数可能重叠，不能相加冒充文件总数。
完整在线扫描的两个独立completed增量才确认missing；失败/离线/超限不推进缺失且清除未完成凭据，已有Entry状态不变；重现恢复available。preview不推进确认。last_successful_scan_at随成功增量更新，首次完成时间不改。
私有根身份不匹配SOURCE_ROOT_CHANGED失败，不扫描错误只读空根；旧库基线缺失且无可信锚点SOURCE_ROOT_UNVERIFIED，不能静默接受整库失联。该摘要不出现在HTTP响应。
状态/路径/Revision系统变化也递增document_version，过期编辑/撤销仍应刷新重选；人工字段不被扫描覆盖。当前无字节读取保证，外部原件availability保守unknown；离线投影可为source_offline而库存保留。

## T15 排除与清理接口

GET /sources/{id}/exclusions、POST /sources/{id}/exclude-entry、DELETE /sources/{id}/exclusions/{exclusion_id}、POST /documents/{id}/purge已实现，契约0.4.16/48路径，写请求仍鉴权/CSRF。
取消索引body为source_entry_id、reason（最多1000字符）、expected_document_version（有关联Doc时必填）。返回202 Job；活动请求复用首个快照，非即时修改新请求内容。成功原子写精确文件路径排除规则并逻辑回收Doc；不删Entry/原文件。
待处理屏障立即阻止扫描该文件；失败终态释放，有限重试期间保留。排除epoch改变时扫描提交SOURCE_CHANGED重试。规则仅精确路径，不glob、不按hash屏蔽其他副本；移除不自动恢复回收站，但允许重新观察/清理后重新建档。
永久清理body必须confirm_document_id和expected_document_version，ID不一致422，非Trash/旧版本409；执行时再校验，恢复后的旧任务不能删除新状态。完成清系统记录，外部路径留排除规则；最小receipt支持同ID/版本返回原completed Job，外部字节永不删除。
托管文件不随purge立即物理删；Job.result含gc_job_id，GC延迟至少24小时且核查全部历史/回收引用。GC只由内部持久任务/本地管理员CLI触发，无客户端路径或缩短保留期选项。派生物理文件GC尚未开放。

## T28 Web接入（契约不变）

来源界面使用source-mounts、sources、entries(relative_prefix/page/page_size)、preview-scan、scan(initial/incremental)、exclusions、exclude-entry及jobs读取/条件重试。目录导航仅从已登记文件路径生成，不承诺目录枚举或空目录接口。取消索引先GET document取得document_version，确认后写expected_document_version；版本冲突不自动重提。
任务回执和统计按真实result展示；预扫描不是导入/解析，离线不是单项missing。无新HTTP结构，Archive OpenAPI仍为0.4.16、48路径。

## T19 Converter协议接通

Converter OpenAPI0.4.1六路径已实现，任务提交202；身份只接受Archive生成的安全ID和multipart二进制，额外字段/重复字段拒绝。parse_run_id在本spool有效期内按输入hash+选项幂等，冲突409；容量429/超大小413/接收超时408/OCR不可用422。协议完成不等于支持格式：规范ParseResult.status可能unsupported。
状态/result/asset均鉴权，结果未完成409，不存在/过期404。终态DELETE清理，活动409。artifacts强制随机ref、sha256和size_bytes；客户端还校验schema/Revision/ParseRun身份及下载字节，不跟随重定向。详见CONVERTER与ADR-034。Archive业务HTTP契约和迁移不变，parse handler接入留T22。
