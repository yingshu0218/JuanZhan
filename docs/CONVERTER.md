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
当前Archive仅有内部客户端，尚未把parse任务接入本服务或持久化ParseRun/块/资产；这些属于T22。六格式T20及按需OCR/缩略图T21已交付；业务管线T22、内容/候选API T23及界面T29仍待开发。

## T20 当前实现 · 协议0.4.2

能力包括六种输入MIME。UTF-8文本可通过declared_mime指定Markdown/HTML子类型（仅字节看不出可靠语义）；二进制签名优先。TXT除UTF-8/BOM外支持带BOM UTF-16/32，不盲猜GBK/单字节编码；字符定位是解码且移除BOM后的Unicode码点范围。Markdown为CommonMark+表格，源码定位取实际行范围对应的字符跨度；长的规范化片段无法准确映射时unknown。
DOCX读取word/document.xml及styles/core属性，在有界ZIP内复制实际标题/段落/样式继承列表/表格；不解压目录、不执行宏/字段或跟随关系外链。真实标题路径可用则section，否则unknown；不推测页数。浮动图像不提取，合并/嵌套表格可平铺；脚注/页眉页脚/修订与未知正文元素等按代码能力警告，不承诺排版保真。
HTML用HTMLParser提取文本、标题、列表、简单表格和真实meta属性；丢弃script/style/iframe/object/svg/math/template等活动区域及显式hidden/aria-hidden/内联隐藏节点，不加载CSS/图片/链接。没有浏览器布局或外部CSS计算，因此只保证文本提取，不承诺完整视觉可见性。原始HTML不作为产物返回。Markdown内原始活动HTML同样不输出，可识别链接只保留文本标签，不生成源资源链接；普通URL字面值仍可作为纯文本保存。
EPUB验证mimetype/container/OPF，按spine而非ZIP/manifest顺序读取XHTML/HTML，解析真实书目候选；章节locator保留spine_index/href及真实标题路径，page_count永远null。XHTML前缀命名空间被安全规范化供文本解析；严格拒绝DTD/实体及用于读取的外部/越界章节引用，其他资源不加载；不保证兼容依赖DTD实体的旧EPUB/复杂脚本书籍。非HTML spine项略过并警告。
PDF通过pypdf提取文本层、页码和实际Title/Author；不调用JavaScript、OCR或外部资源。所有页受200页默认上限，解码内容流8MiB上限，CPU/地址空间/墙钟兜底；多栏和表格阅读顺序明确未验证。无文本层可completed但text_available=false，有NO_TEXT_LAYER_OCR_REQUIRED；加密/密码文件明确失败，不伪造已识别文字。
六格式均输出plain_text和由块重新生成的Markdown，完整表格结构以JSON为准，Markdown布局可能降级；Markdown中的HTML/特殊语法转义，不保留源文件主动资源。元数据仅来自实际属性/meta/manifest，均候选/confidence=null，不写人工业务值，不猜正文作者/日期/语言。
默认ZIP成员1024、膨胀总量及累计读取16MiB、单成员8MiB、压缩比200，拒绝重复/加密/符号链接/非规范路径或非stored/deflate成员；保留4MiB输入、16MiB产物总量/JSON、10000块及T19子进程限制。PDF解码可能先触发子进程内存/时限保护，不能承诺任意复杂4MiB文件都可转换。
OCR、原件预览及业务正文入库未实现，仍按T21/T22接续。结果completed只表明当前基础转换完成，不等于Archive已切换成功正文。


## T21 当前实现 · 协议0.4.3

在六格式基础上增加image/png、image/jpeg、image/tiff。ocr_enabled默认false；开启时不传语言默认eng，允许显式eng/chi_sim或逗号组合，禁止重复/任意模型路径。capabilities仅声明完整性校验通过的模型；服务CONVERTER_ENABLE_OCR=false或缺失模型时不声明OCR，提交开启请求明确422，不静默假装识别。关闭OCR仍可完成图片归档后的独立转换：text_available=false、IMAGE_OCR_DISABLED，按选项生成缩略图。

扫描PDF仅对extract_text为空的真实页运行OCR，混合PDF保留文本层，读取顺序/表格仍未保证。OCR块定位page为源PDF页或图片实际帧（非伪造物理分页）；置信度是Tesseract MeanTextConf/100，并非校准概率，原文本层保持null。ocr_used仅在实际运行时true；空识别有OCR_NO_TEXT_DETECTED，所有OCR结果有OCR_TEXT_REQUIRES_REVIEW，均值低于0.7有OCR_LOW_CONFIDENCE；不会据识别文本自动确认标题/作者/日期等业务字段。

generate_preview=true仅对PDF/上述图片生成重新编码PNG thumbnail产物（非preview_pdf），按源页/帧顺序，单张最大边1024，不带原EXIF或活动PDF内容。默认前5页，更多页有PREVIEW_TRUNCATED；PREVIEW_THUMBNAILS_IN_SOURCE_ORDER说明产物与源顺序对应。关闭预览不生成图像产物。DOCX/EPUB/HTML等仍PREVIEW_NOT_AVAILABLE，不提供排版保真承诺。

OCR默认最多10实际识别页，超出OCR_PAGE_LIMIT；输入/渲染单页超过1200万像素报IMAGE_PIXEL_LIMIT；PDF栅格120DPI；输出累计仍16MiB，JSON/文件/页数/CPU/墙钟限制与进程组终止、TTL、资产校验协议保持。原生库地址空间预算512MiB，OMP单线程；资源失败不抹除Archive原件。模型固定提交、校验与原生依赖许可见THIRD-PARTY/DEVELOPMENT。

本轮只交付Converter和内部客户端真实验收，Archive解析handler/ParseRun/派生资产入库及内容API待T22/T23；Web和用户原件预览待T29/T32。


## T22 更新 · 2026-10-17

T22已将Archive parse/ocr handler接入真实HTTP转换器：原件校验、独立尝试、规范结果与派生资产校验、短事务围栏发布及历史保护。规范完整JSON/文本/Markdown/缩略图持久在Archive data/derived，转换器只保留临时副本，始终没有业务库/来源卷权限。远端清理异常由墙钟+TTL兜底。公开读取与界面仍待T23/T29。
