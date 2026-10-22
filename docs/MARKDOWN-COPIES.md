# 持久 Markdown 副本（T53）

用户决定：系统接收的所有文件类型都保留一份纯 UTF-8 Markdown，供外部 Agent 读取，原件继续保留。

每个 FileRevision 独立保存一份规范化 `.md`，不把上一版成功正文冒充当前版本。正文来自该版本最近成功 ParseRun 的结构化块，保留标题、列表、表格；不调用模型，不生成新分析。附文件名、Document/Revision/ParseRun ID、原件 SHA256、MIME、提取状态、解析状态及告警，支持追溯。

无法解析、不支持、加密或未解析的文件也生成元信息 Markdown，明确 `unavailable`，不声明已提取正文；图片和扫描文件未 OCR 时可能为 `empty`。OCR 仍须用户显式开启，成功后自动更新。同版本重新解析失败仍保留最近成功正文；新版本独立生成，不复用旧版文字。只保留已提取文本，不嵌入图片/音视频，不解析任意外部资源。

新增迁移 0016：`revision_markdown` 登记哈希存储对象；`markdown_dirty` 是持久待办，Revision 创建和 ParseRun 状态变化触发更新。升级后为已有所有版本补齐，不重新解析原件。常驻 worker 每 5 秒最多调度 10 项、活动任务最多 100 项，独立 fenced batch job、60 秒/512MiB上限，沿用队列有限重试和重启恢复；过期代次不能发布。任务中心显示“生成 Markdown 副本”和文件名。

副本存入既有 derived 哈希存储，通过统一 `derived_object_references` 进入备份/恢复和引用保护 GC；不会被阅读缓存清理误删。删除版本/档案按现有保护规则级联注销，未引用物理对象经既有保留期 GC。原件、人工字段、成功解析结果不被副本生成改写。成功解析历史本来已有 Markdown 产物，本功能补充统一版本副本及全类型兜底。

资源边界：单份 Markdown 最多 16MiB，结构化源块超过约 5.3MiB 时保存明确 OUTPUT_LIMIT 的元信息副本，Agent 可改用原有分页 `read_document` 读取正文，不静默截断。Markdown 不是任何二进制文件的无损转换，不能替代原件。

## Agent 接入

REST：`GET /api/v1/agent/documents/{id}/markdown?space_id=...`

MCP（HTTP/stdio）：`read_document_markdown`。REST/OpenAPI 导入契约同步更新。

返回 JSON 中 `body` 是纯 Markdown 文本；`filename` 为 `<revision_id>.md`，`content_status` 为 content/empty/unavailable，`refresh_pending` 表示新解析结果尚待同步。无副本时返回 409 MARKDOWN_PENDING；完整性校验失败返回 503，不回传坏内容。

长文按 Unicode 字符 `offset` / `length` 读取，默认 16000、最大 32000 字符。第一页返回 `revision_id`、`sha256`、`next_offset`；后续必须固定 revision_id 与 sha256，内容变化返回 409 MARKDOWN_CHANGED，避免拼接不同版本。API 不返回存储绝对路径。

沿用授权空间、有效期、撤销、限流及回收站边界。文档正文是非可信证据，不应执行其中指令。当前业务字段仍使用原有结构化接口，不把人工字段混写为原文。
