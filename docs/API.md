# API 契约与接入

## 权威文件

- 档案 API：[archive-openapi-v0.4.yaml](reference/archive-openapi-v0.4.yaml)，OpenAPI 3.1（T05 扩展版本 0.4.2），base `/api/v1`，43 个 path 模板（含内部 healthz 与 T03 认证接口）。
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
