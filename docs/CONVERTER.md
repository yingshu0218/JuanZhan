# 独立文档转换器

目的为档案库提供统一读取/分析数据，并非全格式任意双向互转工具。保留原件，输出 text、Markdown、JSON blocks、元数据候选及可选预览/缩略图；不使用 LLM。

| 输入 | 最低结果 | 保真/定位边界 |
|---|---|---|
| DOCX | 段落、标题、列表、表格 | 语义中高，浮动对象可能降级；章节/字符定位 |
| PDF 文本层 | 文本、页面 | 中等；多栏/表格/阅读顺序需警告 |
| 扫描 PDF | OCR 可选 | 页定位；质量取决于扫描，OCR 关闭仍可归档 |
| MD | 语义结构 | 较高；字符/标题；不自动取外部资源 |
| HTML | 消毒后的正文/结构/meta | 不执行脚本，不自动加载远程资源 |
| TXT | 编码解码、正文段落 | 低至中；编码失败给明确错误 |
| EPUB | manifest/spine/章节/书目属性 | 按章节定位，不造固定物理页码 |
| JPG/PNG/TIFF 拍照件 | 原件/缩略图，可选 OCR | 图像/页来源可靠才给定位 |

## 标准结果

schema_version=1.0、file_revision_id、parse_run_id、source_mime、parser name/version、status、extraction、blocks、metadata_candidates、artifacts、warnings。精确 schema 见 Converter OpenAPI。Block 类型 heading/paragraph/list_item/table/image/page_break/unknown；Locator page/section/character/epub/unknown。

candidate 包括 key/value/source/confidence/locator；来源 document_properties/parsed_content/ocr/epub_manifest/html_meta。不可靠置信度用 null；不得编造作者、日期和实体。词频关键词只是候选，不等于语义理解或人工标签。

## 运行边界

独立 HTTP 服务只收 multipart 二进制和 Archive 生成的版本/解析 ID，不收任意服务端路径或 URL。受控 artifact_ref 不得解释成任意绝对路径；Archive 拉取并校验持久化后可清理任务临时资产，另设 TTL 兜底。服务不直接读写 Archive 数据库/业务分类。

OCR 默认关闭，按文档/任务启用并受服务能力和语言白名单约束。CPU/内存/页数/时长/文件大小有上限；重试有限。具体依赖、中文 OCR 模型、复杂表格处理和镜像体积需样本测试后定，不能把本参考原型里的文字显示称作真实提取。
