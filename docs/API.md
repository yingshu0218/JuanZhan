# API 契约与接入

## 权威文件

- 档案 API：[archive-openapi-v0.4.yaml](reference/archive-openapi-v0.4.yaml)，OpenAPI 3.1（T17 扩展版本 0.4.8），base `/api/v1`，44 个 path 模板（含内部 healthz 与 T03 认证接口）。
- 转换器：[converter-openapi-v0.4.yaml](reference/converter-openapi-v0.4.yaml)，OpenAPI 3.1，6 个 path 模板，独立服务根路径。

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
