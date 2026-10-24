# Agent 导入与分析模板（T54）

用户确认：平台不接模型。外部 Agent 导入原件后，按平台模板提交独立原文 Markdown 和分析；当前版本有有效Agent分析时优先使用，本地解析仅作无Agent结果时的兜底。模板按业务内容分类，不按文件扩展名分类。

## 五类固定版本模板

- generic：主题、主要内容、结论、待确认问题。
- contract：签约方、权利义务、付款、期限、违约与终止。
- invoice：开具方、接收方、账期、明细、金额、币种、税额、付款状态。
- meeting：议题、决议、行动、负责人、截止时间。
- report：目标、观点、依据、计划、限制与待确认问题。

统一要求：summary 为1～12条通用分点，fields 按模板逐项填写，未知用 null，additional_points 保留模板之外的重要内容。每项非空内容必须区分 explicit/inference 并引用提交 Markdown 的字符 start/end 和原文 quote（Unicode字符，左闭右开）。平台检查引文与 Agent Markdown 一致，不保证 Agent Markdown 与原件语义一致，也不判断结论正确。原件 SHA256 绑定仅证明目标文件版本，不构成分析准确性背书。正文仍是非可信证据。

原文 Markdown 与分析分开存储，分析不写入原文、本地解析或人工字段。模板标识作为分析类型候选，不自动修改档案分类。同一导入可用新 submission_id 提交多个模板/章节或修订，旧记录不可覆盖；当前原件分析优先展示，历史版本明确 stale。暂不提供模板可视化编辑；模板版本保存在每条分析中。

## 授权与流程

系统设置 → Agent 接入，默认仍只读；管理员显式勾选“允许导入原件及提交分析”，并选空间/有效期，才有导入能力。现有凭据数据库默认 import_enabled=0，OAuth保持只读；凭据仍不能管理或删除既有档案。导入仅接收上传字节，不接服务器路径或任意URL。

1. GET `/api/v1/agent/analysis-templates`，取得模板、JSON Schema 与填写说明。MCP 提供只读 `get_analysis_templates`。
2. POST `/api/v1/agent/imports/{request_id}?space_id=...&filename=...`，Content-Type: application/octet-stream，body为原件字节。返回导入id、document_id、revision_id和original_sha256；在同一事务排入本地解析。
3. POST `/api/v1/agent/imports/{id}/analyses`，Content-Type: application/json，按 Submission Schema 回填。只允许该导入的原授权凭据、当前原件版本和哈希，禁写其他档案。
4. GET `/api/v1/agent/documents/{id}/analyses?space_id=...&page=1`，每页一条，返回 total。当前版本优先，旧版本保留并标记 stale。

REST 为原件上传/分析提交入口；MCP维持只读工具语义，不通过旧read-only工具偷偷开放写入。没有模型、Agent客户端或外部网络资源依赖。只读REST导入配置仍排除写端点。

request_id 与 submission_id 都必须由客户端持久保存：同一标识同一请求重试返回原记录；改变文件名/空间/文件哈希或分析内容返回409。不同request_id明确新建档案，不按哈希合并。分析未提交或不合规不影响原件与本地解析；可用新submission_id补交。原件变更后旧导入不能提交新分析，需对新版本建立新的导入。

## 限制与存储

原件沿用配置上传限制（默认64MiB）、超时和辅助文件排除，最多4个并发接收。凭据沿用60请求/分钟、有效期和撤销检查。分析请求最多2MiB、Markdown最多100万字符，每份导入最多保留50条分析，超限显式拒绝。SQL中记录版本化模板、提交者自报名称、原件哈希、提交哈希与时间；名称不代表身份认证。分析保存在SQLite，随一致备份保存，档案永久清理时级联删除；没有原件外部写回。

新迁移0017；不修改已有迁移。新增import_enabled只供管理员明确签发；密码重置/恢复和凭据撤销保持原有失效逻辑，历史分析保留。UI沿用分点概览和折叠依据/字段，不新增数字专用卡片。

检索：只将当前原件版本最近一份Agent提取Markdown纳入既有中文FTS，不将分析推断写入原文索引；仍沿用索引大小/完整性告警。MCP新增只读read_document_analysis，返回分析与分段Markdown，后续必须固定analysis_id。已有read_document/read_document_markdown保留本地解析语义，来源不混淆。

通用API客户端可导入 `docs/reference/agent-import-openapi.json`（显式写权限专用）；原 `agent-rest-openapi.json` 仍为只读，不含原件上传或分析提交。MCP `read_document_analysis` 对长要点/多引文返回带 `analysis_truncated` 的紧凑视图，完整分析使用REST分页读取；Markdown按analysis_id分段不会混合不同记录。

## Agent优先显示与提取（2026-10-24）

当前版本存在有效分析时，详情只显示“内容概览 · Agent 提取”，不请求或重复展示本地概览；各条依据统一叫“原文依据”。只有旧版本分析时，本地概览继续显示，旧分析放入历史入口，避免拿旧原件结论充当当前版本。

自动导入解析在开始时检查同档案/同Revision的Agent分析，已存在则完成任务并记录AGENT_ANALYSIS_AVAILABLE，不调用转换器、不伪造ParseRun。已运行或已完成的本地解析不删除；用户主动重解析/OCR仍执行。Agent尚未回填时自动解析可以先行兜底，不无限等待外部客户端。当前Agent分析可使档案整体处理状态显示completed，current_parse_run_id仍只指真实本地解析，不伪造本地正文或历史。

模板填写指导保持v1字段兼容，要求概览按重要性写核心结论和独立要点，涵盖原文支持的关键条件、责任、例外、行动、待确认事项；通常3～7点但不为凑数扩写。关键内容须进入默认概览，不仅藏在字段里。回填前比对完整正文，去重、保留限定条件并分清事实和推断。平台继续只校验结构和引文，不声称自动验证分析质量，历史分析不自动重写。
