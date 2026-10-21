# 文件类型验证范围 · 2026-10-21

rc.13已部署，共20种输入MIME：六种原有文档＋XLSX/PPTX/ODT/ODS/ODP/CSV/TSV/DOC/XLS/PPT/RTF＋PNG/JPEG/TIFF。实际证据见TESTING/DEVTEST。不宣称能解析任意文件或所有历史版本。全部样本经真实HTTP上传、独立转换进程、SQLite/文件存储和共享概要API；失败/未支持仍核验原件下载字节SHA-256不变。

PPT/PPTX备注已进入正文并区分来源；旧PPT仅读取当前persist引用，不以主题或废弃编辑冒充正文。真实DOC含中文与补充平面字符；旧Office加密样本明确失败，宏和嵌入物不执行。当前legacy适配以CFB Word97+/Excel BIFF/PPT97+为范围，不承诺任意早期非CFB格式。

| 文件类型 | 当前结果 |
|---|---|
| PDF文本层 | 可提取正文并生成分点概要；多页和中文另有既有真实样本回归 |
| DOCX | 可提取标题/段落/列表/表格并生成概要 |
| Markdown：md、markdown | 可提取结构化文本、列表、表格 |
| HTML：html、htm | 可提取可读内容，脚本/外部资源不进入活动视图 |
| TXT：UTF-8、带BOM UTF-8/UTF-16/UTF-32 | 可真实上传识别并解析，原始编码字节保留 |
| EPUB | 可提取章节与阅读顺序，不伪造物理页码 |
| PNG、JPEG（jpg/jpeg）、TIFF（tif/tiff） | 默认OCR关闭，无文本时如实为空；显式开启eng OCR后提取真实文本/概要，保留复核提示 |
| 扫描PDF | 同上，显式OCR后可生成概要；中英和混合PDF见完整回归 |
| CSV、TSV | 新增结构化记录读取，保留引号换行、文本小数/长整数；公式为字面文本，不执行 |
| XLSX、PPTX | 新增SafeZip/XML解析，固定版本真实Apache POI样本已读出正文；公式仅已有缓存值，工作表实际行号/幻灯片顺序定位，布局/图表等明确降级 |
| ODT、ODS、ODP | 新增ODF正文/表格/幻灯片解析，合成ZIP/XML与3份固定blob真实LibreOffice1.3样本通过；重复行列有界展开，缺失正文包失败，不制造概要 |
| DOC、XLS、PPT | T38新增，真实固定版本样本含宏/国际字符与加密拒绝；DOC仅文本，XLS源数值精度/缓存警告，PPT含当前形状及备注，布局/图表/嵌入物有界降级 |
| RTF | T38新增正文读取，中文、emoji和Gothic字符通过，孤立代理字符/不平衡组失败；不执行域指令/对象/链接 |
| GIF、BMP、WebP、ZIP、未知二进制 | 当前不支持提取，原件保留 |
| 密码保护PDF、损坏PDF/DOCX、非法BOM文本 | 明确失败/错误状态，无伪造概要，原件字节保留 |
| 空文件 | 原件保留，未生成假正文 |

真实旧Office/OOXML样本来源固定到Apache POI提交d91a76448f0963a93b6cd95fb97fbe1d8bad82c6；URL/大小/SHA-256记录于[样本来源](reference/format-fixture-sources.json)。测试校验OLE签名或OOXML主文档成员及SHA-256；文件仅保留私有开发目录，不打包进镜像或提交仓库。来源项目许可/文件声明以上游为准。

新增测试为tests/test_format_acceptance.py；图片OCR复核/置信度、模型缺失和资源上限同时由既有test_conversion_ocr.py覆盖。未支持格式在将来增加解析器前，不能因“测试通过”而改称可解析。最终执行数和耗时见TESTING。
