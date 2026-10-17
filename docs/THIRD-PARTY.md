# 转换解析依赖与许可证

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
