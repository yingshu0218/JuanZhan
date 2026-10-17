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
