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

## T19 当前实现 · 协议0.4.1

六路径HTTP协议已实现，schema_versions=[1.0]，supported_input_types仅[text/plain]；OCR/预览不可用。最小UTF-8 TXT支持BOM，按最多4096 Unicode码点切文本段，character范围为BOM移除后的[start,end)，保留换行；不声明语义段落识别或其他编码支持。空输入/非文本/其他格式unsupported；解码失败明确failed，不用替换字符冒充成功。声明为其他语义格式的文本不走TXT解析。
每次任务一个受限子进程，无自动重试，默认4MiB输入、16MiB输出、10000块、30秒墙钟、10秒CPU、256MiB RLIMIT_AS；接收60秒、同时接收1份、spool最多2个任务（含已完成待清理）。内存限制是子进程地址空间，不等于整容器RSS保证。JSON和资产均验证后发布，源数据不执行或获取远程内容。
受控产物是随机32位小写hex引用，经private DB映射到任务文件；下载attachment/nosniff/no-store。客户端下载先写私有暂存，核验长度及sha256后才返回文件流供后续持久化，不接URL/绝对路径。主动DELETE只允许终态，活动返回409；TTL默认自接收起3600秒，终态才清理，容量满429。
临时SQLite不是Archive业务数据库，也不承诺容器重建持久性。相同parse_run_id绑定输入sha256及全部选项，重复返回原job_id，冲突409；DELETE/TTL/重建tmpfs后映射不保留。同spool服务重启恢复queued，running标CONVERTER_RESTARTED；发布/存储异常恢复后，单runner将遗留running标CONVERTER_PUBLISH_FAILED，不无限阻塞队列。Archive必须保留原件并按有限预算重新协调，不能把临时Job当永久事实。
当前Archive仅有内部客户端，尚未把parse任务接入本服务或持久化ParseRun/块/资产；这些属于T22。六格式转换T20、OCR T21、内容/候选API T23及界面T29仍待开发。
