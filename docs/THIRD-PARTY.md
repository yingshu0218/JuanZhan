# 转换解析依赖与许可证

## 2026-10-21 旧Office/RTF补充

| 组件 | 锁定版本 | 许可/用途 |
|---|---|---|
| olefile | 0.47 | BSD类及包内PIL来源通知；CFB识别，完整许可证/历史说明按原相对路径保存在licenses/legacy/olefile |
| xlrd | 2.0.2 | 包内两份BSD类通知均保留；旧XLS存储值/日期读取，不计算公式 |
| striprtf | 0.0.33 | BSD-3-Clause；只读RTF提取，UTF-16代理对正确合并 |
| Debian catdoc | 1:0.95-6，Linux amd64 | GPL-2（非一概MIT）；字符表另有Unicode/Apple通知，完整copyright及GPL-2在licenses/legacy/catdoc；DOC通过独立CLI提取文本；PPT最终使用本库受限persist解析器，不调用包内catppt |

Python版本及wheel哈希锁定于uv.lock/requirements.lock；只新增上述三个纯Python包，其余既有依赖版本未升级。实际wheel下载合计219566字节。catdoc .deb为86248字节，哈希与签名APT元数据及Debian HTTPS下载页一致；native工具及三份对应源码文件逐个URL/大小/SHA256锁定于legacy-tools.lock.json。源码总187014字节，orig/debian源码哈希与.dsc的Checksums-Sha256匹配。镜像离线校验并dpkg安装，完整对应源码/.dsc/锁清单放在/usr/share/doc/catdoc/corresponding-source，Debian许可证/字符表通知和系统GPL-2文本保持，不修改工具源码。

准备命令`python scripts/setup_legacy_tools.py --download`（只下载/验证），构建内`--install`仅允许Linux x86_64。native-packages为可重建缓存，不提交二进制；公开发行镜像时须连同对应源码及许可入口提供，不可只分发闭包工具。无LibreOffice、Java、新模型或主机系统安装，新增工具只进入项目镜像；测试平台仍为devtest Linux amd64。

## 前端PDF阅读补充 · 2026-10-19

| 组件 | 锁定版本 | 许可记录 | 用途 |
|---|---|---|---|
| pdfjs-dist | 6.4.299 | Apache-2.0，全文licenses/pdfjs/LICENSE | 浏览器只读PDF解析、Canvas、文字层及同源worker |
| @napi-rs/canvas | 1.0.11（可选间接依赖） | npm包声明MIT，licenses/napi-canvas-LICENSE.txt | 开发Node环境可选依赖；浏览器与生产镜像不使用node_modules |
| PDF.js标准字体 | 随上述固定包 | standard_fonts/LICENSE_FOXIT与LICENSE_LIBERATION | 原样复制资源；Liberation随包文本为GPLv2及字体例外，不能笼统标为Apache |
| CMap/ICC/WASM及解码器 | 随上述固定包 | licenses/pdfjs/cmaps、iccs、wasm中的独立许可文本 | 版本化本地资源；保留Adobe、OpenJPEG、QCMS、JBIG2和PDF.js包装层各自许可 |

package-lock.json记录完整性，主包sha512与官方registry元数据核对一致；安装沿用已有npm镜像解析。构建只分发阅读器JS/worker、必要资源和完整许可，不复制开发node_modules或可选Node原生canvas。文本层CSS从该锁定包的上游CSS提取并保留Mozilla版权/Apache声明。实际安装包许可均已复制到licenses/pdfjs/，随资源构建再次保留；没有新增Python/OCR模型/系统服务。

接口与渲染依据[Mozilla示例](https://mozilla.github.io/pdf.js/examples/)及[官方API](https://mozilla.github.io/pdf.js/api/draft/module-pdfjsLib.html)，具体方法同时核对已安装6.4.299源码，避免旧版销毁API混用。

T20新增的解析依赖均为纯Python，不引入浏览器、LibreOffice、Java或系统PDF命令作为运行依赖。版本与分发哈希分别锁在uv.lock和requirements.lock；容器从wheelhouse离线安装并验证哈希。构建架构仍需匹配Python3.12和目标平台；未声称本轮已在Apple Silicon实测。

| 包 | 锁定版本 | 随包许可证 | 用途 |
|---|---|---|---|
| pypdf | 6.21.1 | BSD-3-Clause | PDF文本层、页数和文档属性 |
| markdown-it-py | 4.2.0 | MIT（包含markdown-it原始许可） | CommonMark及表格token解析 |
| mdurl | 0.1.2 | MIT | markdown-it-py间接依赖；不联网获取链接 |
| defusedxml | 0.7.1 | Python Software Foundation License v2 | DOCX/EPUB/XML实体与DTD防护 |

本轮检查了实际安装包的dist-info许可证全文入口和版权头；pip安装保留这些许可证文件。新增依赖没有额外模型、外部可执行程序或系统服务。XML不加载外部实体，HTML通过标准库HTMLParser提取纯文本，ZIP通过标准库在内存中按预算读取成员，不解压到服务器目录。

这些许可证允许再分发，但发布镜像仍应保留原版权和许可证文件；完整发布清单由T34接续，不把此表当作所有既有依赖的完整许可证审计。依赖升级需重新锁定、核对许可及真实格式/恶意输入回归。

## T21 原生OCR/渲染与模型

| 包/数据 | 固定版本 | 许可与分发说明 | 用途 |
|---|---|---|---|
| tesserocr | 2.11.0 | MIT；Linux wheel内含Tesseract 5.5.1/Leptonica 1.85.0及图像库 | 子进程调用真实OCR，无需系统CLI |
| cysignals | 1.12.6 | LGPL-3.0；独立可替换Python扩展，保留许可证及对应GPL文本 | tesserocr间接依赖 |
| pypdfium2 | 5.14.0 | BSD-3-Clause/Apache-2.0，及wheel自带PDFium/第三方BUILD_LICENSES；文档另含CC-BY-4.0 | PDF栅格化 |
| Pillow | 13.0.0 | MIT-CMU及图像库许可，保留wheel内LICENSE | 图像解码、清除元数据并重编码PNG |
| tessdata_fast eng/chi_sim | 87416418657359cb625c412a48b6e1d6d41c29bd | Apache-2.0，仓库licenses/tessdata_fast/LICENSE | 两种LSTM识别模型 |

不是“全部纯Python/全部MIT”：T21新增原生wheel以及LGPL-3.0间接依赖。已读取实际wheel的dist-info许可证及PDFium BUILD_LICENSES，镜像pip安装保留原包许可，同时COPY仓库licenses。cysignals原版源码入口为https://pypi.org/project/cysignals/1.12.6/#files 与https://github.com/sagemath/cysignals；未修改/静态链接进应用。公开发布镜像前，T34须完成包括该库对应源码与可替换机制、Tesseract/Leptonica及其捆绑图像库通知在内的完整发布清单；本地开发镜像不是正式发行验收。

模型固定源URL、完整提交、大小和SHA256见ocr-models.lock.json；setup_ocr_models.py只从该清单下载并校验，不跟随可变HEAD，也不使用用户密钥。模型约6.3MiB，Git忽略，构建前下载、构建内再次离线验证。生产不读取系统字体、不下载任何远程文档资源；Noto CJK仅为开发真实扫描样本绘制使用。Linux x86_64容器实际加载并OCR通过，其他架构尚未实测。


## T24 · OpenCC归一字典

[opencc-python-reimplemented](https://github.com/yichen0831/opencc-python) 0.1.7：Apache-2.0，以实际wheel内LICENSE.txt为准，完整副本保存在licenses/opencc/LICENSE.txt，镜像保留dist-info许可。其词典只用于繁简转换；中文检索使用本仓库Han单/双字算法，不依赖语义分词词库。wheel SHA-256锁定于uv.lock/requirements.lock，25份.txt/.json字典/配置按相对路径排序、路径+NUL+字节+NUL计算SHA-256：4ffd2aa3019bda697f811e0d7e27604e30c9f30b31204af1b89622f7cd818179，运行首次使用验证。regex沿用既有锁定依赖；无外部下载服务。

## 独立原生阅读镜像（rc.15候选）

本批新增Office原生阅读依赖只进入独立juanzhan-office镜像，不安装本机/服务器系统，不替换Archive/Converter解析器。Debian trixie及security来源187包、207581860字节下载，精确文件名/上游URL/大小/SHA256见office-preview-tools.lock.json；LibreOffice固定25.2.3-2+deb13u8，包含Writer/Calc/Impress及字体，不含Java。版本与来源按锁校验，构建network=none；镜像保留完整dpkg清单/app/office-system-packages.tsv和Debian /usr/share/doc各包copyright。对成品rc.15实测187个新增包的copyright全部存在。

这些依赖包括LibreOffice及其原生库、字体等，各自许可证以固定Debian包的copyright为准，不能统一宣称为项目许可证。当前镜像仅在授权devtest自建运行，未向外发布；若将镜像再分发，必须连同对应版本的许可证和适用的对应源码义务检查发行内容，不能只提供本项目源码替代第三方源码。本项目Python/前端包仍按既有锁和许可记录，不新增模型、向量库或外部文件上传服务。构建缓存与卸载边界见LOCAL-DEVELOPMENT。
