# 档案库统一产品需求文档（PRD）V0.4

> 文档状态：开发基线草案，可据此进行 MVP 实施；依赖规格 `archive-schema-v0.4.sql`、`archive-openapi-v0.4.yaml`、`archive-roadmap-v0.4.md`。
> 2026-10-16 整合 V0.3 的《文件组织与操作体验设计规范》和《元数据与结构化内容设计规范》，保留原文于附录以便逐条追溯。**本篇“统一决议”优先于附录中早期建议和示意接口。**

## 1. 产品概述

- **目标**：构建参考 Paperless-ngx 的轻量化、可自部署档案系统。既能托管新上传文件，也能只读索引现有磁盘/NAS 文件，统一分类、检索、预览和提取结构化内容，向将来的数据分析或 AI 系统提供稳定 API。
- **首版用户**：单管理员、单实例；保留多 Space 结构但不承诺多账号/共享权限。
- **运行形态**：Docker Compose；档案应用、独立文档转换服务；SQLite + FTS5、本地托管卷、只读外部挂载；OCR 按需启用。后续按负载拆任务队列或升级数据库。
- **解析输入优先级**：PDF、DOCX、MD、HTML、TXT、EPUB；JPG/PNG/TIFF 与扫描 PDF 可选 OCR；不支持格式仍可以存档、手动分类、下载。
- **明确不做**：LLM、向量检索、自动 AI 分类、双向云盘同步、外部文件写回、细粒度企业权限和审批。

## 2. 不可变设计原则与统一决议

| 编号 | 必须遵守的决策 | 可直接验证的结果 |
|---|---|---|
| D01 | 一个 Document 是稳定的逻辑身份；每个 Document 一份主原件、可多次 Revision | 文件改名/重新解析不换 document_id |
| D02 | 托管和原地索引统一在 Document 下；物理来源是独立视图 | 调整 folder、title、tags 不修改磁盘文件 |
| D03 | 外部首次接入可按目录树建立逻辑文件夹，之后彻底解耦 | 后续新增文件默认 folder=null 且 needs_review（可设置固定目标）；旧逻辑位置不随磁盘移动 |
| D04 | Inbox 是 `triage_status=needs_review` 的虚拟集合，而非文件夹 | 有 folder 的档案仍能出现在收件箱 |
| D05 | 导入成功以原件安全登记为准，解析和索引均异步 | 处理失败时档案和原件仍能查看 |
| D06 | 业务文档类型（合同）与 MIME/扩展名（PDF）分离 | 同格式档案可以具有不同文档类型 |
| D07 | 人工字段权威；解析器只给候选值，不自动覆盖已确认值 | 重跑 OCR 不会改人工合同编号 |
| D08 | 同内容哈希不等于同一个 Document | 同 SHA-256 可存在多条业务档案记录 |
| D09 | 逻辑删除与外部取消索引不同；V1 绝不删除外部原件 | 用户删除索引后 Source 不会自动重导入 |
| D10 | 解析定位不可靠时用 unknown，不虚构页码或结构 | EPUB 返回 spine/章节定位而不是假页码 |
| D11 | 目录、标签、业务字段均限定在 Space 内，服务端强制拒绝跨 Space 关联 | API 返回 422/403，不污染数据 |
| D12 | 中文搜索需要受测试约束的分词与短词策略 | 两字中文词、数字/英文混排有可复现结果 |

## 3. 功能范围（MoSCoW）

**MVP 必须**：空间/逻辑目录/标签/文档类型；上传及本地托管；只读外部目录扫描及首次可选导入目录；收件箱；移动/多选/批量操作；详情页原件/正文/属性/历史；版本、解析任务、OCR 开关、错误重试；元数据基础七类型与候选值采纳；全文搜索与结构化过滤；回收站、索引排除；API、审计、备份与基本安全。

**可延后到 V1.1**：保存的搜索视图、跨文件夹高级撤销、用户视图偏好、复杂批量异步快照优化、预览定位高亮、复杂文档版面表格保真优化。

**不在首版**：多附件单档案、多用户权限矩阵、外部原件写入/删除、云盘 OAuth、在线 Office 编辑、自动业务规则、LLM/向量数据库。

## 4. 信息架构与关键页面

1. **总览**：档案总数、待整理、处理队列、来源健康、最近文件。
2. **档案管理**：空间选择 + 左侧逻辑目录/标签/虚拟集合 + 列表/网格 + 右侧详情；支持搜索筛选、批量和 OS 拖入上传。
3. **文件来源**：真实来源树、挂载健康、扫描预览/任务、忽略列表；绝不将磁盘绝对路径开放给普通浏览界面。
4. **处理任务**：等待/运行/完成/失败/取消，有限重试、失败详情、重新执行。
5. **设置**：Space、文档类型、字段定义、OCR、扫描间隔、备份和系统健康。

**详情 Tabs**：原件预览、提取正文、业务属性（含候选值）、历史/任务。展示两个互不替代的状态：原件可用性与解析状态。

## 5. 关键用户旅程与验收

### 5.1 上传并整理

1. 用户从文件系统拖入或选择文件；选择目标 Space/Folder；系统异步上传并持久化原件。
2. 检测到相同内容时默认返回 409 `DUPLICATE_DETECTED` 且不建立新档案，用户可选择保留独立档案后重传；原件登记后创建 Document、Revision；默认 `needs_review`；返回文档 ID 与处理任务 ID。
3. 转换器生成 ParseRun、TXT/MD/JSON 和块，成功后更新当前成功解析引用与搜索索引。
4. 用户设置 Folder、Tag、DocumentType、自定义字段并确认 `filed`；解析失败时仍可完成整理。

### 5.2 外部目录首次接入与后续增量

1. 仅管理员配置的挂载别名供选，服务端校验路径、只读性质、边界和文件读权限；预扫描显示预计数量与大小。
2. 初扫选 `tree`：复制原相对目录层次至目标逻辑文件夹；选 `flat`：归入单一指定文件夹；**不复制原件**。
3. 之后每次增量扫描：仅新增文件默认进入收件箱，且不继续镜像磁盘目录；可配置固定目标文件夹。
4. 源离线：不标记所有文件丢失；文件单独丢失时先 suspected_missing，后续在线复扫确认后才 missing；原件离线时已缓存正文可读取但必须注明旧快照。
5. 用户取消外部档案索引：记录排除规则，防止下一次重新导入；任何操作不删除 NAS 原件。

### 5.3 文件夹/标签/批量交互

- 单 Document 只有一个 Folder；标签可多对多；同一 Space 下规范化的标签名唯一，同级文件夹名唯一。
- 应用内部拖动档案到文件夹：只更新 `folder_id`；系统文件拖入应用：生成托管新档案。
- 批量标签使用 `add/remove`，不能隐式覆盖全部；操作按文档逐条报成功/跳过/失败。批量选择“当前页”和“当前结果集”必须显式区分。
- 用户改字段提交 `expected_document_version`，若版本冲突返回 409，不静默覆盖。

### 5.4 元数据与内容

- 基础字段：title、description、document_date、folder、tag、triage_status、document_type。
- 自定义类型 V1：text、long_text、integer、decimal、date、boolean、single_select。
- Decimal 使用 **固定四位小数的缩放 INTEGER（×10,000）**，API 使用 decimal 字符串，范围查询使用整数索引；null 代表未设置，与 bool false 分离。
- 业务字段的解析候选保存在 `extracted_metadata`，仅显式采纳/人工修改才写入 `metadata_values`。
- ContentBlock：heading、paragraph、list_item、table、image、page_break、unknown；locator 可为 page/character/section/epub/unknown；不可靠就用 unknown。
- 某版本重新解析失败时，不清空前次成功的内容；返回 `content_revision_id` 与 `stale_for_current_revision` 提示。

## 6. 核心状态与异常边界

- `documents.triage_status`: `needs_review | filed`。
- `sources.status`: `ready | scanning | offline | error | disabled`；来源整体离线不能直接使所有 entries 变成 missing。
- `source_entries.status`: `available | suspected_missing | missing | needs_match`。
- `parse_runs.status`: `queued | running | completed | failed | unsupported`。
- `jobs.status`: `queued | running | completed | failed | cancelled`。
- `documents.deleted_at` 表示回收站；清空回收站是单独的二次确认异步操作；托管对象按引用计数/可达性回收，外部文件不删除。
- 外部历史文件二进制不保证可恢复：未托管历史快照时，仅可能保留元数据/曾经解析内容。

## 7. API、数据库与安全交付标准

- **数据库**：见 `archive-schema-v0.4.sql`。SQLite（FK ON、WAL）、同空间复合 FK、文件夹 root 唯一索引、必要应用层事务校验、版本乐观锁、审计事件。
- **API**：见 `archive-openapi-v0.4.yaml`。路径 `/api/v1`；REST + 异步任务；上传用 `POST /documents/upload`；高级搜索用 `POST /documents/search`；外部来源扫描 `POST /sources/{id}/preview-scan`、`POST /sources/{id}/scan`；分页统一 `page/page_size`。
- **认证**：首版管理员会话或 API Bearer Token，所有读取和写入均鉴权；浏览器会话写操作需 CSRF 防护；API Token 可用于自动化调用。
- **隔离**：外部 Source 只读 bind mount，根目录白名单及真实路径校验，拒绝符号链接逃逸/路径遍历；转换器限 CPU/内存/页数/时间/输入大小并隔离不可信格式，HTML 预览消毒或 sandbox。
- **一致性**：原件先安全落盘并校验，再提交档案记录；逻辑操作在事务内；异步工作任务幂等；数据库与原件/派生文件须进行一致性备份及恢复演练。
- **全文搜索**：应用预分词并建立 FTS5 单文档记录；tokenizer_version 可重建；中文 2 字词、混排、英文、数字、繁简体和日期/Decimal 过滤有自动测试。

## 8. DoD 总清单

- 继承下方 UX-01 至 UX-14 和 META-01 至 META-16 **全部 30 条原始验收用例**；每条映射到 Roadmap 测试任务。
- 所有数据库脚本可以在 SQLite 空库执行；外键与同空间约束有失败路径测试。
- OpenAPI 所有 `$ref` 可解析、HTTP 状态码和后端实现保持一致。
- 至少通过：文件重名/同哈希不同身份、外部离线、目录重命名、两字符中文搜索、带脚本 HTML、安全路径、断点任务重试、历史版本不可恢复提示、回收站误删防护。

## 9. 文件职责与冲突解决

- **本 PRD**：用户体验、业务规则、范围与 DoD 的权威来源。
- **SQL**：存储模式的权威来源；应用必须实现数据库不能表述的跨表类型/路径验证。
- **OpenAPI**：服务端 HTTP 参数及响应的权威来源；旧 V0.3 附录中的接口路径为设计示意，发生不同时以新 OpenAPI 为准。
- **Roadmap**：任务依赖、批次验收与测试追踪；如果功能降级，应同时更新 PRD、SQL、API 和测试，而不是单边更改。

---

# 附录 A · V0.3 文件组织与操作体验原始完整规范

> 以下保留源规范以保持验收可追溯。若与上文统一决议/新 OpenAPI 冲突，上文及对应规范文件优先。

# 档案库 V0.3 — 文件组织与操作体验设计规范

- 文档状态：产品设计定稿（用于第一版开发，细节允许实现时保持兼容地优化）
- 版本：0.3
- 设计依据：双模式（托管 + 原地索引），外部来源首次可导入目录结构，之后逻辑目录与物理目录解耦；转换器独立部署；暂不使用 LLM。
- 范围：信息架构、页面、收件箱、文件夹、上传与来源扫描、拖拽、批量管理、标签、搜索、回收站、异常反馈、验收标准。

## 1. 核心产品原则

1. **档案是逻辑对象**：`document_id` 稳定；一个档案记录属于一个 Space 和一个主逻辑 Folder（可为空），可有多个 Tag；来源和实际文件位置与逻辑分类分离。
2. **来源是物理视图**：Sources 显示真实目录树，只读展示，不直接操纵外部文件系统。逻辑目录中的重命名、移动、删除索引不影响外部原件。
3. **收件箱是状态**：`triage_status=needs_review|filed`；它不是物理文件夹，和 `folder_id` 独立。一份档案可位于任意逻辑文件夹且仍待整理。
4. **导入不被解析阻塞**：原件成功登记即可查到；转换、OCR、缩略图、索引异步运行。状态按原件可用性和处理状态两个维度显示。
5. **危险动作明确区分**：`移至回收站`（针对逻辑档案）与 `从来源取消索引`（外部）不等于删除磁盘文件。V1 不提供外部原件物理删除。
6. **先简单后强大**：V1 单管理员/单实例，数据模型为多空间预留；高级权限、协同审批、自动 AI 分类、云盘登录式同步暂不实现。

## 2. 导航与信息架构（IA）

### 2.1 全局导航

- 总览：档案总数、原件可用性、解析进度、待整理数量、最近导入、异常来源。
- 档案：空间切换器；全部档案；收件箱；最近访问；收藏；文件夹树；标签视图；回收站。
- 文件来源：托管来源（不暴露内部哈希路径）；外部挂载来源；来源树、连接状态、最近扫描、重新扫描、忽略规则。
- 处理任务：导入、扫描、转换、OCR、索引等任务的状态与操作。
- 设置：空间、标签、文档类型、自定义字段、检索配置、OCR、备份、导出、系统健康。

### 2.2 档案页面布局

桌面：左侧可折叠导航树（建议 240px）、中间列表/网格、自适应右侧详情预览（建议 320px）；顶部全局搜索、空间切换与新增按钮。

窄屏：单栏主列表；详情通过抽屉或新页面显示；批量动作固定底部；文件夹树由弹出导航承载。

文档列表列：名称/标题、文档类型、所属文件夹、标签、来源类型、文件格式/大小、创建或归档时间、解析/原件状态、最后修改。

视图：列表（默认）、网格（缩略图），排序默认 `imported_at DESC`；可切换名称、文档日期、大小、修改日期。排序有稳定的 `id` 次级排序，保证分页不跳行。

筛选状态可通过 URL 查询参数恢复/分享；用户偏好中的列显示、排序、视图可保存在本地配置或用户配置表。

## 3. 逻辑组织模型

### 3.1 Space（档案空间）

- V1 默认一个空间；允许增加多个空间，不跨空间直接移动档案（V1 可用“复制记录至另一空间”作为未来能力，不在首版提供）。
- 文件夹、标签定义、文档类型和自定义字段默认在 Space 内生效（字段模板可预留系统级作用域）。
- 每个 Space 有独立收件箱、回收站、统计和来源归属。

### 3.2 Folder（逻辑文件夹）

- 任意层级，但 UI 为性能可设置推荐上限（例如 10 层，不强制截断已有结构）。
- 同父文件夹的名称不允许重复（在标准化比较规则下），不同父目录可以同名；一个文件夹不能移动进自身或子孙文件夹。
- 档案一次只隶属一个主文件夹；未归类档案 `folder_id=null`。
- 删除非空文件夹时给出三个明确选项：取消、把其中档案移动到父文件夹再删除、连同子树中的逻辑档案移至回收站（需二次确认）。默认安全选项是取消。
- 逻辑目录重命名、移动不改变托管文件的物理存储路径，也不改变外部文件的路径。
- 初次从外部导入目录树：复制相对路径层次到所选空间及目标文件夹；已有同名路径可复用对应逻辑目录。创建操作用事务保证树结构一致。
- 首次导入结束后目录无永久镜像关联。后续新文件默认标记待整理并保持 `folder_id=null`，管理员可为具体 Source 设置固定的“新文件目标文件夹”。

### 3.3 Tag（标签）

- 标签与逻辑文件夹正交，一个档案可有多个标签。标签字段：`id, space_id, name, color(optional), description(optional), created_at`。
- 同一空间标签名称（规范化后）唯一，不区分显示顺序的重复绑定。
- 支持列表批量添加/移除标签、详情页快捷创建标签、按标签组合过滤。
- 默认同组内 OR、不同筛选维度 AND；高级模式支持“同时包含全部选中标签”。
- 标签改名在所有引用处统一更新；删除标签仅解除关系，不删除档案。
- 不用标签模拟强约束的文件类型，类型使用单独 `document_type_id`。

### 3.4 收藏 / 最近 / 保存视图

- 收藏为 `is_favorite` 用户属性；最近根据访问事件计算（可限最近 N 条）；两者均为虚拟集合。
- V1 支持“保存筛选视图”可推迟至 V1.1，但 URL 中需要支持持久化筛选条件。

## 4. Inbox（收件箱）流程

### 4.1 触发规则

- 全局上传：默认 `triage_status=needs_review`，`folder_id=null`，除非明确在某逻辑文件夹上传且选择“直接归档”。
- 文件夹内上传：默认属于当前文件夹，`triage_status=needs_review`，保证仍可审核。
- 首次外部来源扫描且勾选“导入目录结构”：复制目录结构，导入的档案默认 `triage_status=filed`（可在向导中选“首次扫描也要审核”）。
- 后续外部新增文件：`triage_status=needs_review`；默认 `folder_id=null`，若 Source 设置了固定目标文件夹则写入该文件夹。
- 重新解析、仅修改标签、外部原件变更，不应悄悄把已归档文件重新标记为待整理；但可产生“内容变化待关注”的独立提示。

### 4.2 收件箱内可执行动作

- 选中文档 → 文件夹、文档类型、标签、日期、备注（部分可选）→ 点击“完成整理”。
- 标记“完成整理”只改变 `triage_status=filed`；即使没有逻辑文件夹也允许（系统给出未分类提示但不强制）。
- 支持“保持待整理”“标记已整理”批量操作；不因移动文件夹自动清空收件箱，避免意外遗漏审核。
- 对未解析文件仍可以人工分类；OCR 完成后更新正文，不覆盖人工填入的元数据。
- 出现重复文件提示时提供“保留为独立档案”“查看现有档案”“取消本次导入”，不自动合并记录。

## 5. 文件导入与外部来源

### 5.1 上传体验

- 提供“添加文件”按钮、文件列表空状态上传、文件夹/档案列表拖入上传；同时支持多文件。
- 从操作系统拖入视为**上传新档案**；档案库内部拖拽已有记录视为**逻辑移动**。两者通过拖拽来源明确区分，不能误触原件操作。
- 当前文件夹为默认目标；上传弹窗允许改空间/文件夹，选择“放入收件箱”与“导入后直接归档”。
- 上传队列逐文件显示：等待、上传中、已保存等待解析、处理完成、处理失败。原件保存成功应立即反馈。
- 支持逐文件失败重试、取消尚未完成的上传；服务端配置单文件大小限制和总请求限制。
- 不允许通过浏览器“输入服务器任意路径”读取宿主机文件；外部 Source 仅接受服务器管理员预挂载白名单路径。

### 5.2 Source 接入向导

1. 选择经过管理员配置的可访问目录，并检测只读挂载、根路径及访问权限。
2. 填写来源名称，选择所属 Space。
3. 配置首次导入：复制相对目录层级到目标逻辑文件夹 / 统一放入一个文件夹；首次文件是否标记待整理。
4. 配置后续：新文件默认进收件箱，或在收件箱状态下放到固定目标文件夹；扫描间隔，忽略文件名规则。
5. 执行扫描预览（只统计，不落库）：估算文件数量、大小、文件类型、忽略数量、同名文件夹冲突，确认后开始后台任务。
6. 导入完成展示新增/已存在/忽略/失败明细与源目录树。

### 5.3 扫描增量与失联处理

- 使用稳定的 `source_id + normalized_relative_path` 做来源记录定位；同时保存大小、mtime（精度）、可用时的 file id/inode 与 SHA-256。
- 文件大小和修改时间可作快速筛查；需要确证内容变化时使用哈希，不能仅靠 mtime 断定内容相同。
- 路径消失时优先扫描同来源的新位置，必要时通过哈希辅助重关联；多个同哈希候选时不做自动合并。
- 来源不可挂载/整体离线 → `source.status=offline`，不把该来源的全部文档批量置为已失联，更不能删除文档。
- 来源在线且连续扫描确认某个条目缺失 → 将文件原件状态从 `suspected_missing` 转为 `missing`，保留历史元数据与之前解析内容。
- 默认忽略符号链接以防越界/循环；对网络文件系统注意大小写语义、Unicode 规范化与路径分隔。
- 同一个物理根目录不得重复配置重叠来源，除非明确接受重复索引；V1 建议禁止嵌套来源。
- 从档案库“取消索引”外部文件时写入 `source_exclusions`（可恢复），防止下次扫描立即重新导入。

## 6. 拖拽及批量操作语义

| 来源 → 目标 | 操作结果 | 是否改变实际磁盘文件 | 回退方式 |
|---|---|---|---|
| 操作系统文件 → 文件列表 | 上传并创建新档案 | 托管保存新副本 | 在上传成功前可取消；成功后移动到回收站 |
| 档案列表 → 左侧逻辑文件夹 | 修改 `folder_id` | 否 | 撤销最近一次逻辑移动 |
| 档案列表 → 标签 | 批量添加该标签 | 否 | 撤销标签变更 |
| 逻辑文件夹 → 另一逻辑文件夹 | 移动逻辑子树 | 否 | 事件记录/撤销 |
| 外部来源树 → 逻辑文件夹 | 为选中索引档案分配逻辑文件夹 | 否 | 恢复旧的 `folder_id` |
| 逻辑档案 → 来源树 | V1 禁止此目标 | 不适用 | 给明确提示 |
| 档案 → 回收站 | 逻辑删除 | 外部文件不删除；托管原件按回收站策略保留 | 恢复档案 |

### 6.1 批量操作栏

- 全选当前页/当前筛选结果需区分，默认仅选当前页。
- 操作包括：移动逻辑文件夹、添加标签、移除标签、设置文档类型、标记已整理/待整理、收藏、加入回收站、重新解析、导出列表（可在后续实现）。
- 高风险操作（删除、覆盖字段）须确认数量及范围；不提供一键物理删除外部文件。
- 批量修改需记录 `batch_job_id`、每条结果和失败原因；小批量同步更新，大批量异步任务处理。
- 对“筛选结果全部选择”先将档案 ID 集合快照化，防止边执行边更改筛选结果；返回成功/跳过/失败数量。
- 用户编辑字段时使用 `document_version`（元数据乐观锁），避免并发覆盖；批量冲突仅失败相应单项，不应影响已成功记录。
- Undo 至少支持本次会话最近一次逻辑移动、标签增删、批量标记状态；复杂历史回滚不进入 V1。

## 7. 删除、回收站与安全

- 档案放入回收站：保留数据记录、原件、解析产物，默认不显示在常规视图与搜索。
- 恢复：返回原空间及原文件夹（文件夹不在时恢复到未分类），并恢复整理状态。
- 托管档案清空回收站：需要二次确认；二进制对象仅在无其他引用且超出保留策略时由清理任务删除。
- 外部索引档案清空回收站：永久移除系统元数据/解析产物（按保留政策），**永不删除外部原件**；写入排除规则，避免扫描重现。
- 来源离线不构成“可删除”证据；按 Source 显示健康状态。
- 转换/预览 HTML 必须消毒且沙箱隔离；下载与预览必须鉴权；路径只允许白名单映射、规范化及校验，杜绝 `../` 遍历。

## 8. 检索体验

### 8.1 全局搜索（V1）

- 默认跨当前空间搜索标题、原始文件名、可解析正文、标签名称与经授权可搜索的元数据；同时显示匹配来源（标题/正文/标签/字段）。
- 支持过滤：逻辑文件夹（仅当前/含子树）、来源、存储模式、文件类型（MIME/扩展名）、文档类型、标签、整理状态、处理状态、原件状态、时间范围（导入时间/文档日期）、大小范围。
- 标签过滤默认“任一匹配”，可切换“全部匹配”；不同过滤维度 AND。
- 搜索结果先展示相关性，提供时间/名称排序；列表中高亮命中片段但必须 HTML escape，不能渲染文件中携带的 HTML。
- 查询语法首版优先 UI 过滤器与普通文本，不要求实现复杂 DSL；保留结构化 API 查询对象作为将来高级查询基础。
- 对未完成 OCR 的文件显示“正文尚未可检索”，不误导用户它肯定不包含关键词。

### 8.2 中文检索

- SQLite FTS5 建立 `document_search` 索引，但不要直接假设 `unicode61` 能满足中文分词。
- V1 建议预处理中文词项（例如分词结果 + 原文辅助字段），配合 FTS5；同时测试混合中英、编号、短词、标点、繁简体。
- 文本索引由正文版本与展示元数据增量更新；所有解析任务可重建索引；结构化字段的日期/金额/数字范围筛选必须走类型化 SQL 索引而非全文 FTS。

### 8.3 搜索空状态

- 区分“没有文档”“当前条件无结果”“处理任务未完成”“某来源离线，结果可能不完整”。
- 提供清除筛选、查看收件箱、查看任务等明确下一步操作。

## 9. 详情界面

- 顶部：可编辑标题、来源状态、存储模式、收藏、下载原件、更多操作。
- Tabs：原件预览 / 提取正文 / 属性元数据 / 历史与任务。
- 原件预览：PDF、图片、浏览器可安全显示的文本；其他格式使用生成的预览（并标明来源）；不能预览时允许下载原件。
- 正文：按章节/页、段落/表格展示；提供复制、搜正文、跳转到对应原件页或位置（只有位置数据可靠时才展示跳转）。
- 属性：逻辑文件夹、标签、文档类型、日期、备注、自定义字段及字段来源标识；不直接暴露外部完整绝对路径给非管理员。
- 历史：原件版本、解析运行、元数据修改、扫描记录、错误与重新解析入口。

## 10. 关键操作流程

### 操作 A：归档收件箱里的文件
1. 进入当前 Space 收件箱；按新文件优先排序。
2. 选中一条或多条；按需设置文件夹、标签、类型、日期。
3. 点击“完成整理”；记录修改事件并离开收件箱。
4. 如果解析正在进行，依然允许整理；完成后可打开解析正文核查。

### 操作 B：外部文件夹首次接入
1. 选择预挂载只读目录并检测权限。
2. 预扫描；选择“复制相对目录树”，目标如“公司资料/历史资料”。
3. 后台创建逻辑目录、档案记录与来源映射；不复制原件。
4. 扫描完成后，新增文件按用户后续策略进入收件箱，不追随物理目录位置变动而修改逻辑分类。

### 操作 C：NAS 文件改名或离线
1. 扫描发现旧路径消失，若 NAS 整体离线，仅标记来源离线。
2. 在线时尝试匹配新路径；匹配唯一且可信，更新 `source_entry` 路径，不改变 `document_id/folder_id/tags`。
3. 无法确定时显示“需确认”，保留上次内容，不自动新增或合并错误档案。

## 11. API 对界面的最低要求

- `GET /api/v1/spaces`, `GET/POST/PATCH /api/v1/folders`
- `GET /api/v1/documents`（分页、结构化筛选、排序）
- `POST /api/v1/documents/upload`（上传，返回 document_id + job_id）
- `GET/PATCH /api/v1/documents/{id}`（含元数据乐观锁版本）
- `POST /api/v1/documents/batch`（批量补充/删除标签、改文件夹等，返回批次 ID）
- `POST /api/v1/documents/{id}/triage`（标记待整理或完成）
- `POST /api/v1/documents/{id}/trash`, `POST /api/v1/documents/{id}/restore`
- `GET/POST /api/v1/sources`, `POST /api/v1/sources/{id}/preview-scan`, `POST /api/v1/sources/{id}/scan`
- `GET /api/v1/jobs/{id}`, `GET /api/v1/search`（简单文本 + 过滤器）

API 应有分页、错误码、服务端验证与审计记录。外部来源的创建/编辑只允许访问管理员配置的挂载根目录。

## 12. 验收用例（开发 DoD）

- UX-01：两个同名但不同目录的文件能分别创建档案，不错误合并。
- UX-02：外部首次复制目录树后，用户移动逻辑文件夹，NAS 路径不变。
- UX-03：外部后续新增文件进入收件箱，且目录不被重新镜像。
- UX-04：已在逻辑目录内的文件仍能处于“待整理”；整理后不必移动位置。
- UX-05：从 OS 拖入创建托管文件，从档案列表拖入文件夹只做逻辑移动。
- UX-06：批量设置标签为“添加/移除”而非默认覆盖；失败项有独立错误。
- UX-07：外部文件移出旧位置，能可信重关联则保持同一 document_id；歧义时请求确认。
- UX-08：NAS 整体离线不删除索引，也不把全部原件标成永久丢失。
- UX-09：外部记录取消索引后，下次扫描不会再次自动导入。
- UX-10：放入回收站再恢复，逻辑文件夹、标签、文档类型和元数据仍在。
- UX-11：搜索标题、中文正文、标签、自定义字段与日期范围可组合过滤。
- UX-12：OCR 尚未完成时，搜索 UI 显示内容尚不完整。
- UX-13：同一条档案的并发编辑发生冲突时，不静默覆盖。
- UX-14：任何 UI 操作都不能物理删除外部只读源文件。

## 13. 不在 V1 范围

- 云盘 OAuth 双向同步，权限细分/共享审批，LLM 分类与语义检索，复杂全文 DSL，自动规则引擎，高级回滚，协作评论，外部文件编辑或写回，跨空间复制/同步，WOPI 在线 Office 编辑。

## 14. 参考（设计参考而非代码依赖）

- Paperless-ngx 使用与检索：https://docs.paperless-ngx.com/usage/
- Paperless-ngx API：https://docs.paperless-ngx.com/api/
- Docspell 元数据与工作流概念：https://docspell.org/docs/webapp/metadata/



---

# 附录 B · V0.3 元数据与结构化内容原始完整规范

> 与附录 A 同级，旧版本中的表结构与 API 路径是设计草案；具体 SQL/HTTP 协议以 V0.4 独立文件为准。

# 档案库 V0.3 — 元数据与结构化内容设计规范

- 状态：产品设计定稿（第一版开发输入）
- 版本：0.3
- 适用：双模式存储的档案库；外部文件原地索引；文档转换器为独立服务；无 LLM。
- 目标：实现稳定的档案身份、可配置的文档类型/自定义字段、可复用的解析产物、类型正确的搜索与过滤。

## 1. 核心术语与边界

| 术语 | 含义 | 示例 |
|---|---|---|
| Document（档案） | 用户管理的一条逻辑记录，稳定 ID | doc_1024 |
| Source（来源） | 托管文件池或外部挂载根目录 | nas_work |
| SourceEntry（来源条目） | 某来源下找到的具体物理文件与路径 | contracts/2026/a.pdf |
| FileRevision（文件版本） | 某次原件内容状态、指纹及位置引用 | revision 2 / SHA-256 |
| DocumentType（文档类型） | 业务分类，独立于 MIME | 合同、发票、会议纪要 |
| FieldDefinition（字段定义） | 字段键、数据类型、作用域、约束、UI 描述 | contract_no:string |
| MetadataValue（字段值） | 档案级的业务属性 | contract_no=HT-2026-001 |
| ParseRun（解析运行） | 对特定文件版本执行的一次解析行为 | parser v1.3 + OCR zh/en |
| DerivedAsset（派生文件） | 解析输出：Markdown、JSON、TXT、预览 PDF 等 | parse-98.md |
| ContentBlock（内容块） | 标题、段落、表格等独立内容单元 | 页 2 的表格 |

**V1 建议每个 Document 只含一份主原件（可有多个历史 Revision）。** 多附件组成一份档案、合并 PDF 等复杂语义作为后续功能，避免本期对搜索和版本模型造成过大复杂度。

档案的逻辑文件夹、标签、文档类型和人工字段都属于 Document 级，不随原件更新而清零；正文和原件技术属性属于 FileRevision / ParseRun 级。

## 2. 元数据分为四层

### 2.1 系统基础属性（系统维护）

`document_id`, `space_id`, `folder_id`, `title`, `triage_status`, `document_type_id`, `created_at`, `imported_at`, `updated_at`, `document_version`, `deleted_at`, `is_favorite`。

- `title` 是档案库展示标题，可人工改名；不直接重命名外部磁盘文件。
- `original_filename` 是原文件名，存于 FileRevision，不因标题修改而更改。
- `document_date` 可作为 Document 上的内置业务日期，允许用户修订，和导入时间/mtime 区分。
- `source_id / source_entry_id` 只能间接引用当前原件；不得把绝对路径当作 Document 主键。

### 2.2 文件技术属性（从原件自动得到）

`sha256`, `size_bytes`, `mime_type`, `extension`, `original_filename`, `file_modified_at`, `page_count(optional)`, `encoding(optional)`, `language(optional)`。

- 技术属性与具体 FileRevision 绑定，不允许直接覆盖历史版本。
- `mime_type` 由文件嗅探与扩展名联合确定；不完全信任扩展名。
- 页数仅在可靠解析后填入；未知用 NULL，不以 0 代替。

### 2.3 业务元数据（用户编辑，按类型扩展）

内置通用字段：`document_date`, `description`, `document_type_id`, `tags`, `folder_id`, `triage_status`。

自定义字段示例：合同编号、甲方、乙方、金额、币种、合同生效日期、到期日期、关联项目、发票号码、是否已付款。

### 2.4 解析结果与候选元数据（程序自动生成）

由转换器抽取：标题候选、文档内日期、作者、语言、PDF 属性、HTML 元标签、EPUB 书名和作者、文本段落及页码/定位符。

这些结果保存在 `extracted_metadata` 或对应 `parse_run` 结果中，**默认不会直接覆盖用户已经确认的业务字段**。

## 3. 字段来源、优先级和确认机制

每个可被自动填充的业务字段至少记录：

- `value`：实际展示值；
- `value_origin`：`manual | imported | rule | extracted`；
- `is_confirmed`：是否被人工确认；
- `source_parse_run_id`：来自哪次解析（自动来源可有值）；
- `updated_at`, `updated_by`（单用户 V1 可填系统管理员）。

建议的写入优先级（从高到低）：

1. **已确认的人工值**（最高，不得被解析任务覆盖）；
2. 未确认的人工/明确导入值；
3. 用户配置的确定性规则（以后增加）；
4. 解析器候选结果（最低）。

V1 最安全的执行策略：解析器**只产出候选值**。若业务字段为空，可以显示“建议填入”让用户一键采纳；仅对少数可靠文件技术属性自动写入（例如 MIME 和字节大小）。

重新解析：生成新的 ParseRun 和候选数据；保留全部人工字段；可标记旧候选过期，不清空历史操作记录。

## 4. 文档类型 DocumentType 与字段模板

DocumentType 是**业务分类**，与实际文件格式完全不同。一份 PDF 可以是合同、发票或教材；一份合同可以是 PDF、DOCX 或扫描图片。

### 4.1 V1 内置文档类型（建议，可由用户编辑/新增）

| 类型 | 建议字段 | 说明 |
|---|---|---|
| 通用文档 | 文档日期、备注 | 默认类型，不强制字段 |
| 合同 | 合同编号、甲方、乙方、生效日、到期日、金额、币种 | 不开启强制自动提取 |
| 发票/票据 | 票据号、开票日、主体、金额、币种、付款状态 | 金额与币种分别存储 |
| 会议纪要 | 会议日期、会议主题、关联项目、参与人（文本） | 不与作者混淆 |
| 项目资料 | 项目名称、资料版本、负责人（文本） | 适用于方案/报告 |
| 图书/电子书 | 书名、作者、出版日期、ISBN、语言 | 与 EPUB 内置元信息映射为候选 |
| 其他 | 自定义字段 | 无须预置字段 |

第一版字段模板仅决定：该类型的详情页展示哪些字段、排列顺序、是否建议填写；**不应在未完成整理时阻止上传**。若字段设置为必填，只在用户点击“完成整理/确认归档”时验证，可配管理员豁免开关。

### 4.2 字段定义 FieldDefinition

建议字段结构：

```json
{
  "key": "contract_amount",
  "label": "合同金额",
  "type": "decimal",
  "scope": "space",
  "required_for_types": ["contract"],
  "searchable": true,
  "filterable": true,
  "default": null,
  "help_text": "不包含币种，币种另设 currency 字段",
  "active": true
}
```

字段 `key` 采用小写英文蛇形命名，创建后不可改动；展示名称 `label` 可以变更。字段被引用后不能硬删除，只能停用。字段类型发生变化必须先执行迁移验证，不允许原地强制转换造成数据丢失。

### 4.3 V1 支持的字段类型

| 类型 | API / 存储 | 校验与检索 | 控件 |
|---|---|---|---|
| `text` | string | 长度限制、完全匹配/包含 | 单行 |
| `long_text` | string | 最大长度、全文检索可选 | 多行 |
| `integer` | integer | 最大/最小、范围 | 数字框 |
| `decimal` | decimal 字符串，如 `"1234.50"` | Decimal 精确比较，范围 | 数字框 |
| `date` | ISO 日期 `YYYY-MM-DD` | 范围、精确值 | 日期选择器 |
| `boolean` | true/false/null | 三态筛选 | 开关/未设置 |
| `single_select` | 稳定 option ID | in/equals | 下拉 |
| `multi_select` | option ID 数组（可后续阶段） | any/all | 多选 |
| `url` | string（可后续阶段） | URL 结构检查 | 单行链接 |

**首版最低实现**：text、long_text、integer、decimal、date、boolean、single_select；multi_select、url 在模型中预留。货币不要直接使用二进制浮点；用 Decimal 字符串 + 业务币种字段（例如 ISO 4217）。

字段定义可配：`min/max/regex/max_length/options/required/searchable/filterable/display_order`，服务端验证为权威来源。自定义字段总量、每个文档字段数应有合理限制，避免 EAV 过量拖慢查询。

## 5. SQLite 关系数据模型（逻辑版）

此表结构表达外键和主键边界；最终迁移文件须单独设计。建议所有 ID 为 UUID/ULID 字符串或稳定整型，API 不依赖自增顺序。

| 表 | 关键列与约束 |
|---|---|
| `spaces` | id PK, name, created_at |
| `folders` | id PK, space_id FK, parent_id FK nullable, name, normalized_name；UNIQUE(space_id,parent_id,normalized_name) 实际需 NULL 特别处理 |
| `tags` | id PK, space_id FK, name, normalized_name, color；UNIQUE(space_id,normalized_name) |
| `document_types` | id PK, space_id FK, key, label, active；UNIQUE(space_id,key) |
| `documents` | id PK, space_id FK, folder_id nullable FK, document_type_id nullable FK, title, description, document_date, triage_status, is_favorite, current_revision_id, document_version, imported_at, created_at, updated_at, deleted_at |
| `document_tags` | (document_id,tag_id) 复合 PK；服务端确保同 Space |
| `sources` | id PK, space_id FK, kind(managed/external), root_ref, status, scan_policy, import_policy |
| `source_entries` | id PK, source_id FK, normalized_relative_path, identity_hint, size_bytes, mtime, sha256 nullable, status, last_seen_scan_id；UNIQUE(source_id,normalized_relative_path)（考虑大小写策略） |
| `file_revisions` | id PK, document_id FK, revision_no, storage_kind, source_entry_id nullable FK, managed_object_id nullable, sha256, size_bytes, original_filename, mime_type, created_at；UNIQUE(document_id,revision_no) |
| `managed_objects` | id PK, sha256, storage_key, size_bytes, ref_count（或实时查询引用）；注意垃圾回收事务一致性 |
| `field_definitions` | id PK, space_id FK, key, label, type, constraints_json, active, indexed；UNIQUE(space_id,key) |
| `document_type_fields` | document_type_id FK, field_definition_id FK, required, display_order；复合 PK |
| `metadata_values` | id PK, document_id FK, field_definition_id FK, value_text/value_integer/value_decimal/value_date/value_bool/value_json（按类型仅一个值），origin, is_confirmed, source_parse_run_id nullable；UNIQUE(document_id,field_definition_id) |
| `parse_runs` | id PK, revision_id FK, parser_name, parser_version, output_schema_version, status, started_at, completed_at, error_json |
| `derived_assets` | id PK, parse_run_id FK, type(text/markdown/json/preview/thumbnail), storage_key, checksum, size_bytes |
| `content_blocks` | id PK, parse_run_id FK, block_index, type, text, structural_json, locator_json；UNIQUE(parse_run_id,block_index) |
| `extracted_metadata` | id PK, parse_run_id FK, key, value_json, provenance_json, confidence nullable |
| `jobs` | id PK, kind, target_id, status, attempts, max_attempts, payload_json, error_json, created_at, updated_at |
| `document_events` | id PK, document_id FK, event_type, before_json, after_json, actor, created_at |
| `source_exclusions` | id PK, source_id FK, relative_path_norm, hash_fingerprint nullable, reason, created_at |

### 5.1 数据约束细节

- `folders` 的 ROOT 同名唯一约束：SQLite 的 `NULL` 在 UNIQUE 中不视为相同值；应使用表达式索引 `COALESCE(parent_id,'ROOT')` 或独立根标识，不能仅依赖普通复合 UNIQUE。
- `documents.space_id` 必须与引用的 `folder.space_id`, `document_type.space_id`, `tags.space_id` 一致；外键本身无法跨表表达所有约束，需要服务端事务验证或复合外键设计。
- `current_revision_id` 必须属于本 Document；通过写入事务验证，避免跨文档引用。
- 表示删除采用 `deleted_at` 软删除；回收站状态不改变已保存的文件版本。
- `metadata_values` decimal 可以用字符串存储并通过辅助排序列/应用层查询保证数值比较正确；**不能对十进制字符串直接做字典序范围比较**。实际实现可以采用缩放整数（限定精度）或可索引的 Decimal 编码，选择一种并加测试。
- `content_blocks` 无需第一版对每个块建立独立 FTS；先将段落聚合到文档级索引，并利用块映射进行命中定位。

## 6. 统一解析结果协议（Converter → Archive）

### 6.1 原则

- 转换器独立运行，通过 REST 接口或受信任务工作队列接收临时输入，返回任务状态与结构化结果。
- 转换器**不写档案库业务元数据表、不改逻辑文件夹/标签**；只产出 ParseRun 数据与可供用户确认的候选字段。
- 档案库保存原件、派生文件、解析文本和索引；解析结果要绑定明确的 `file_revision_id` 和 `parse_run_id`。
- 统一 JSON schema 采用版本号 `schema_version`；升级解析器时产生新 ParseRun，不覆盖历史产物。
- 对无法可靠提取版面结构的文件，允许返回纯文本段落并声明低保真，不伪造页码、表格或坐标。

### 6.2 示例 JSON（结构规范，非完整 JSON Schema）

```json
{
  "schema_version": "1.0",
  "file_revision_id": "rev_002",
  "parse_run_id": "parse_984",
  "source_mime": "application/pdf",
  "parser": {"name": "pdf-extractor", "version": "1.0.0"},
  "status": "completed",
  "language": "zh-CN",
  "page_count": 2,
  "extraction": {"text_available": true, "ocr_used": true, "ocr_languages": ["chi_sim", "eng"]},
  "blocks": [
    {
      "id": "b1",
      "index": 0,
      "type": "heading",
      "level": 1,
      "text": "设备采购合同",
      "locator": {"kind": "page", "page": 1},
      "confidence": 0.95
    },
    {
      "id": "b2",
      "index": 1,
      "type": "paragraph",
      "text": "双方就设备采购达成如下约定。",
      "locator": {"kind": "page", "page": 1},
      "confidence": 0.92
    },
    {
      "id": "b3",
      "index": 2,
      "type": "table",
      "text": "设备 数量 | 打印机 2",
      "table": {
        "headers": ["设备", "数量"],
        "rows": [["打印机", "2"]]
      },
      "locator": {"kind": "page", "page": 2},
      "confidence": null
    }
  ],
  "metadata_candidates": [
    {
      "key": "document_title",
      "value": "设备采购合同",
      "source": "parsed_content",
      "confidence": 0.95
    }
  ],
  "artifacts": [
    {"kind": "plain_text", "media_type": "text/plain", "artifact_ref": "artifact_text_01"},
    {"kind": "markdown", "media_type": "text/markdown", "artifact_ref": "artifact_md_01"}
  ],
  "warnings": []
}
```

**安全要求**：`artifact_ref` 是由系统协定的受控对象引用，而不是客户端可提交的任意本地绝对路径。文档 HTML 作为不可信输入，不得将 script 或远程资源直接渲染进管理端。

### 6.3 ContentBlock 类型（V1）

- `heading`: `level(1..6)`, `text`。
- `paragraph`: `text`。
- `list_item`: `text`, `list_kind(optional)`, `depth(optional)`。
- `table`: `table.headers`, `table.rows` 和供搜索用的 `text`；对合并单元格等无法可靠恢复的情况标记 `warnings`，不虚构单元格。
- `image`: 可以只包含 `artifact_ref`, `alt_text`（有则用）；无 OCR 时不生成猜测内容。
- `page_break`（可选）：用于 PDF 等有物理页码的格式。
- `unknown`: 其他未支持块，保留原始文本和警告信息。

索引和顺序：`index` 以整个解析结果为单位从 0 递增；`id` 在同一 ParseRun 内唯一。解析器升级后块 ID 可以变化，不作为用户长期引用的唯一身份；引用使用 `parse_run_id + block_id`。

### 6.4 位置定位 Locator

- PDF/扫描件：`{"kind":"page","page":1}`；明确约定页码为**1-based**。可选 `bbox`，坐标单位与页尺寸必须显式记录。
- DOCX/Markdown/HTML/TXT：`{"kind":"section","heading_path":["..."],"char_start":120}` 或 `{"kind":"character","start":120,"end":180}`，字符偏移必须相对于明确的规范化文本。
- EPUB：`{"kind":"epub","spine_index":3,"href":"chap3.xhtml","fragment":"p5"}`；EPUB 没有固定的物理页码，不伪造页码。
- 无可靠定位：`{"kind":"unknown"}`；UI 不提供原件跳转。

### 6.5 不同文件格式的最低处理要求

| 输入 | 基础文字提取 | 结构保真目标 | 定位 | 注意 |
|---|---|---|---|---|
| DOCX | 段落、表格、列表 | 中高（依文档复杂度） | 段落/章节 | 图片、文本框、浮动布局可能降级；原件保留 |
| 可复制文本的 PDF | 文本层、页码 | 中（阅读顺序可能错） | 页面 | 表格和多栏需质量标识 |
| 扫描 PDF | 按页 OCR | 低至中 | 页面 | OCR 可选，必须输出置信度/警告（若引擎提供） |
| MD | 标题、段落、列表、代码块、表格 | 高（语义结构） | 字符/标题 | 图片链接为外部资源时不自动下载 |
| HTML | 清洗后的正文与标题 | 中高 | 元素/字符 | 去脚本、样式、跟踪内容；保留原件 |
| TXT | 原始正文，按换行推断段落 | 中低 | 字符 | 编码识别/错误报告 |
| EPUB | 章节、书目元信息、正文 | 高（语义章节），中（复杂排版） | Spine/章节 | 不制造固定页码 |
| JPG/PNG/TIFF | 无文本或 OCR 结果 | 低至中 | 图像/区域 | OCR 关闭时仍可存档、缩略图预览 |
| 不支持格式 | 不解析 | 无 | 无 | 可存储原件、搜索文件名、标签、人工元数据 |

第一版格式范围以 DOCX/PDF/MD/HTML/TXT/EPUB 为优先，图片与扫描件 OCR 可以按需启用；XLSX、PPTX 不因为示例文件名而暗示已支持结构化解析，可作为下一阶段。

## 7. 派生资产及存储

- 托管原件采用内容寻址或独立的存储键，原件不可就地覆盖；新内容产生新 Revision。
- 派生资产按 `parse_run_id` 隔离：`.txt`, `.md`, `.json`, 预览 PDF/缩略图；不能把解析后的 Markdown 误当原件。
- 外部索引文件即使源盘离线，只要派生内容已缓存，仍可以打开历史正文；UI 显示“原件离线，显示上次解析快照”。
- 新解析成功后在事务中切换 `documents.current_parse_run_id`（或当前 revision 的选定解析运行），旧解析记录按保留策略清理。
- 解析失败保留旧成功内容并显示“当前原件版本尚未解析/索引可能过期”，避免误认为最新文件内容。
- 内容缓存大小配额、保留周期、清理策略是系统设置而非从磁盘路径判断。

## 8. 检索架构与属性查询

### 8.1 索引内容

建议为每份档案当前展示版本建立统一搜索索引（可使用 SQLite FTS5）：

`title + original_filename + tags + document_type_label + searchable_business_metadata + parsed_plain_text`。

- 文档类型、Tag/Folder/Source 的 ID 用关系表联查；不要依靠全文索引来表达精确匹配。
- 数字、日期、布尔、枚举的过滤走类型化字段索引。
- 全文搜索应返回片段和命中字段；结果仅针对当前版本。OCR 未完成时显示搜索内容不完整提示。
- OCR/解析、元数据编辑、标签变更、逻辑标题修改都会触发增量重建索引。
- 对中文采用可测试的预分词方案，验证短词、连写数字、繁简体、中文/英文混排；不依赖 FTS5 默认 tokenization 自动得到高质量中文词语检索。

### 8.2 筛选 API 查询示例

```json
{
  "space_id": "space_1",
  "text": "设备采购",
  "folder": {"id":"folder_contracts","include_descendants":true},
  "document_type_ids": ["contract"],
  "tags": {"ids": ["important", "purchase"], "match": "all"},
  "metadata": [
    {"key":"contract_amount","operator":"gte","value":"10000.00"},
    {"key":"effective_date","operator":"between","value":["2026-01-01","2026-12-31"]}
  ],
  "source_kind": "external",
  "triage_status": "filed",
  "sort": [{"field":"imported_at","order":"desc"}]
}
```

对结构化复杂筛选推荐 `POST /api/v1/documents/search`，简易搜索仍可保留 `GET /api/v1/documents?q=...`。

## 9. API 契约（建议）

| 方法与路径 | 作用 |
|---|---|
| `GET/POST /api/v1/document-types` | 列出/创建文档类型 |
| `PATCH /api/v1/document-types/{id}` | 更新名称/字段模板（不改已有业务值） |
| `GET/POST /api/v1/field-definitions` | 列出/创建自定义字段 |
| `PATCH /api/v1/field-definitions/{id}` | 更新展示、验证约束；字段类型修改需单独迁移 |
| `GET/PATCH /api/v1/documents/{id}/metadata` | 查看/更新档案级业务字段（含版本冲突检查） |
| `GET /api/v1/documents/{id}/revisions` | 原件版本列表及可恢复能力说明 |
| `GET /api/v1/documents/{id}/content?format=blocks|text|markdown` | 获取当前成功解析数据；标明所属 revision/parse_run |
| `GET /api/v1/documents/{id}/parse-runs` | 历史解析记录和候选值 |
| `POST /api/v1/documents/{id}/reprocess` | 提交重新解析任务 |
| `POST /api/v1/documents/search` | 全文检索+类型化字段过滤 |
| `GET /api/v1/jobs/{id}` | 转换/解析/索引异步任务状态 |

### 9.1 更新字段示例

```json
{
  "expected_document_version": 8,
  "document_type_id": "contract",
  "values": {
    "contract_no": "HT-2026-001",
    "contract_amount": "12500.00",
    "currency": "CNY",
    "effective_date": "2026-10-15"
  },
  "confirm": true
}
```

- 乐观锁版本不一致返回 HTTP 409 与当前版本信息，前端提供合并或刷新。
- 类型错误/必填不满足返回 HTTP 422 并附具体字段错误；服务端不接受未定义字段或越权跨空间写入。
- 批量编辑明确表达 `set / clear / add_to_set / remove_from_set`，不要默认为“整批覆盖”。
- API 输出对每个字段有 `value, origin, is_confirmed`，供前端显示来源与待确认标记。
- 解析器返回任务结果的 `schema_version` 与 `parser_version`，便于升级时重建。

## 10. 自定义字段操作界面

### 10.1 设置 > 字段管理

字段列表：显示名称、稳定 key、类型、所属空间、使用文档类型、可搜索/可筛选、是否启用、引用文档数。创建字段向导：命名 → 选类型 → 约束 → 文档类型关联 → 预览。

### 10.2 设置 > 文档类型管理

每个类型配置图标/名称、关联字段、展示顺序、是否归档时必填。管理员可以复制“合同”模板创建自定义文档类型。

### 10.3 文档详情 > 属性

分组为：**基础属性**（标题、日期、类型、文件夹、标签）；**业务字段**（随文档类型变化）；**文件信息**（只读技术属性）；**内容提取候选**（建议值与来源）。

字段旁允许显示：已手动确认 / 程序建议 / 来源文件属性。用户采纳建议值时才写入业务字段，记录 provenance 与版本事件。

### 10.4 批量编辑

- 批量设置文档类型不默认删除旧字段值；不适用于新类型的值仍保存在档案上，界面折叠进“其他属性”，可人工清理。
- 批量设置同一个字段前检查每份文档是否允许该字段；不适用的文档标记跳过并输出原因。
- 清空字段与赋值为空字符串区分；布尔 false 与 null 区分。

## 11. 示例工作流

### 11.1 扫描 PDF 合同

1. 外部来源扫描新增 PDF → 创建 Document 与 Revision，进入收件箱。
2. 处理器检测文件无文本层 → 根据 OCR 开关运行 OCR。
3. 产生 ParseRun、文本、块、预览及“标题/日期”等候选值。
4. 用户查看原件 + OCR 正文，选择类型“合同”，采纳或输入合同编号/金额。
5. 点击“完成整理” → 提交字段、逻辑文件夹、标签、整理状态；索引增量更新。
6. 后续源文件变更 → 新 Revision，新 ParseRun；人工合同编号和标签保持不变。

### 11.2 EPUB 电子书

1. 原件 EPUB 导入，提取 manifest/spine/章节及元信息候选。
2. `document_type=book`，书名、作者候选可采纳；保留 EPUB 章节定位。
3. 用户搜索书内片段 → 命中文本块，详情展示原文上下文；无固定页码时按章节跳转。

### 11.3 文件类型暂不支持

1. 文件被安全保存并登记文件名、大小、MIME、来源。
2. 处理状态 `unsupported`，仍可进行标签、类型、字段、目录和按文件名搜索。
3. 将来新增解析器后，可为既有档案批量重新解析，不重建档案身份。

## 12. 验收测试（开发 DoD）

- META-01：同一 PDF 文件可按业务分别分类为“合同”和“发票”，原始 MIME 不变。
- META-02：手动修改的合同编号不会被再次 OCR 覆盖。
- META-03：重新解析产生新 ParseRun；旧业务字段、标签、逻辑文件夹不消失。
- META-04：日期支持 ISO 规范化与范围筛选；非法日期 422。
- META-05：金额 `2.00` 与 `10.00` 范围比较按数值而非字符串字典序。
- META-06：布尔 false、null、true 三态查询正确。
- META-07：字段 key 不可在被引用后改名；字段类型变更必须经过显式迁移。
- META-08：DOCX/PDF/MD/HTML/TXT/EPUB 解析结果均符合统一 schema；不支持的定位使用 unknown，不编造页码。
- META-09：外部源离线后已缓存正文仍可查看，明确标注源离线/内容快照。
- META-10：解析失败时不会抹掉最近一次成功解析内容，且能识别“旧版本正文”。
- META-11：来源正文中含恶意 HTML/script 时不会在管理端执行。
- META-12：并发修改同一档案字段触发 HTTP 409，而不是静默覆盖。
- META-13：跨空间绑定字段/标签/文档类型被拒绝。
- META-14：同一文档多次重新解析不会造成重复的当前搜索记录。
- META-15：中文、英文、混排、编号及两字符查询有明确、可复现的命中策略。
- META-16：文档类型转换后不适用字段的历史值不会默默丢失。

## 13. 技术边界与实施顺序

### 首版必须

- 稳定 Document/Revision/ParseRun 身份，基础字段和自定义字段（最低 7 种类型），文档类型模板，人工确认优先，TXT/MD/JSON 派生，中文可测全文检索，文件格式回退策略，API/校验/审计。

### 随后增强

- 自动规则分类、候选字段映射配置、高级多选字段、解析块原文精准高亮、专用表格结构化提取、保存的复杂搜索、邮件和云盘来源、LLM/向量数据库。

## 14. 参考资料

- Paperless-ngx Custom Fields/搜索/API：https://docs.paperless-ngx.com/usage/ ; https://docs.paperless-ngx.com/api/
- Docspell 的标签、文档属性与检索方案：https://docspell.org/docs/webapp/metadata/ ; https://docspell.org/docs/query/

