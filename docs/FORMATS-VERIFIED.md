# 文件类型验证范围 · 2026-10-21

覆盖Converter当前声明的全部9种输入MIME，而不是宣称能解析任意文件。全部样本经真实HTTP上传、独立转换进程、SQLite/文件存储和共享概要API；不支持或失败也核验原件下载字节SHA-256不变。

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
| CSV | 以纯文本回退读取，不声称结构化电子表格解析 |
| DOC、XLS、XLSX、PPT、PPTX | 用真实Apache POI文件测试：原件保存/下载正常，解析明确unsupported，未实现对应适配器 |
| ODT、ODS、ODP | ODF ZIP容器测试明确unsupported，不把文件名或容器内容伪称成功正文 |
| RTF、GIF、BMP、WebP、ZIP、未知二进制 | 当前不支持提取，原件保留；RTF不再把控制字串当作纯文本概要 |
| 密码保护PDF、损坏PDF/DOCX、非法BOM文本 | 明确失败/错误状态，无伪造概要，原件字节保留 |
| 空文件 | 原件保留，未生成假正文 |

真实旧Office/OOXML样本来源固定到Apache POI提交d91a76448f0963a93b6cd95fb97fbe1d8bad82c6；URL/大小/SHA-256记录于[样本来源](reference/format-fixture-sources.json)。测试校验OLE签名或OOXML主文档成员及SHA-256；文件仅保留私有开发目录，不打包进镜像或提交仓库。来源项目许可/文件声明以上游为准。

新增测试为tests/test_format_acceptance.py；图片OCR复核/置信度、模型缺失和资源上限同时由既有test_conversion_ocr.py覆盖。未支持格式在将来增加解析器前，不能因“测试通过”而改称可解析。最终执行数和耗时见TESTING。
