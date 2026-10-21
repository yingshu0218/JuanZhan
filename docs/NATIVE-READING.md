# 源文件阅读与副本管理（开发中）

本批已部署devtest rc.15，Archive0.4.32/93路径、15迁移；0014服务器副本、0015阅读缓存已应用。执行范围与验收见[BATCH-SOURCE-FILES](BATCH-SOURCE-FILES.md)。压缩延期，原件完整保留。

## 用户流程

主视图只显示统一分点概览。右侧“查看源文件”打开源文件窗口，可按版本查看、下载。PDF由同源PDF.js按页读取；PNG/JPEG读取经像素限制的原件；文字类原文件按有界纯文本显示，不执行HTML；Office及TIFF按需生成独立阅读PDF。预览不改变原件、不重解析、不修改人工字段或文档版本，复杂排版/缺少字体可能导致阅读预览差异。

外部Revision保留source_entry关联和external类型。解析或显式副本任务把经过哈希/大小验证的原件保存到托管区，并登记revision_snapshots；原路径永不写入。来源失联后，已保存副本仍可下载。内容变化由扫描产生新Revision，旧版本副本保留；相同字节不会因扫描重复产生版本。显式来源迁移按页安排当前版本的独立子任务，游标推进、请求幂等，失败有限重试，在任务中心核对各文件结果。未保存且已经变化的旧外部字节不能凭新文件还原。

源文件窗口的版本列表分页；每个下载/预览请求固定revision_id并验证所属Document。历史版本清理需要选定版本、明确确认和乐观锁；当前版本、当前成功概要依赖的原件、已确认业务字段来源和活跃任务使用的版本均受保护。清理不删除外部文件。

## 独立渲染边界

私有服务契约：[office-preview-openapi.yaml](reference/office-preview-openapi.yaml)。业务接口：[source-files-openapi.json](reference/source-files-openapi.json)。私有服务只接鉴权原件字节和白名单MIME，不接文件路径/URL，不挂载业务卷，不发布宿主端口。11类输入为DOCX/XLSX/PPTX/ODT/ODS/ODP/DOC/XLS/PPT/RTF/TIFF；原件本身的PDF/PNG/JPEG不经过Office转换。

容器只读根目录、用户10001、无capabilities、NoNewPrivileges；768MiB内存、1CPU、128进程、192MiB临时区。单请求含响应发送占用一个名额；输入32MiB、输出64MiB、90秒墙钟/60秒CPU，超出或繁忙返回有界错误。TIFF额外最多100帧、单帧1200万像素和总2400万像素。每次使用独立临时目录及LibreOffice profile，退出杀死并回收整个进程组。

原生子进程清除服务凭据，seccomp禁止IPv4/IPv6/packet/vsock套接字，保留所需Unix通信。父进程设为不可dump，阻止同用户子进程读取父环境。profile禁用宏与活动OLE/DDE，阻止不可信来源链接，配置语义来自固定[LibreOffice25.2.3.2官方Common.xcs](https://raw.githubusercontent.com/LibreOffice/core/libreoffice-25.2.3.2/officecfg/registry/schema/org/openoffice/Office/Common.xcs)。这些限制不表示任意畸形文件都可成功阅读；失败不会损坏原件或最近成功概要。

## 持久化与清理

reading_previews按Revision登记不可变派生对象；任务有lease栅栏、有限重试与幂等。成功才发布缓存引用。备份、恢复及GC使用统一原件/派生引用视图，包含外部副本和阅读PDF，未引用对象先隔离至少24小时才回收。

存储页显示已登记对象占用，不冒充操作系统实际磁盘用量。物理总量按对象去重；当前/历史/外部副本为交叉分类，不可求和。清理阅读缓存仅移除可重建缓存登记，原件不变；清理闲置对象仍须通过引用和保留期检查。大原件鉴权下载使用数据卷中的私有匿名临时文件，避免1GiB文件耗尽/tmp内存盘；并发两路时需为原件准备预留最多约2GiB临时磁盘空间。

## 重建与验证

依赖记录：[LOCAL-DEVELOPMENT](LOCAL-DEVELOPMENT.md)。187个Debian包精确大小/SHA256见office-preview-tools.lock.json；脚本验证后离线构建deploy/OfficePreview.Dockerfile。镜像保留Debian包版权文件和系统包清单，不在宿主安装办公软件。源文件、锁文件和备份不属于可随意删除的开发缓存。

实物矩阵由scripts/verify_native_reading.py运行，所有凭据从环境读取。当前9类真实Office/ODF/RTF样本经私有HTTP成功；DOCX和两页TIFF经真实SQLite/文件/HTTP任务测试通过。桌面1440和手机390打开XLSX并清理缓存的浏览器测试已通过。来源实物增量/失联双版本、契约、完整615项后端、最终成品升级恢复及公网实际Word阅读已通过，逐项证据见批次最终记录。
