# 概览与源文件管理执行批次

用户目标：把最新规划全部完成。压缩明确延期，当前完整保留原件。此目标覆盖下列五项，完成某一项不等于整批完成。

| 任务 | 状态 | 验收 |
|---|---|---|
| T43 概览专用详情页 | 初版专项通过，未部署 | 桌面/390手机真实上传解析1项浏览器通过；不显示格式选择/候选/解析历史且不请求其API。尚需按新交互更新旧阅读验收与完整回归 |
| T44 平台内源文件阅读 | 待实施 | 右侧查看源文件；PDF/图片与Word/Excel/PPT实际文件预览，按需生成且不上传第三方，权限与版本校验 |
| T45 外部文件服务器快照 | 实施中，未部署 | 0014外部Revision快照映射、解析前保存、下载优先快照、备份/GC引用保护初版；真实只读sysfs/SQLite/HTTP两项通过。仍需显式迁移任务/状态接口与增量整体验证 |
| T46 来源版本更新 | 待实施 | 内容相同不新增，变化产生新Revision/快照/解析；旧成功概要/人工字段保护；历史版本可读与迁移入口 |
| T47 存储管理 | 待实施 | 原件/历史版本/预览缓存占用可见；明确清理入口，有引用保护，外部文件不删除 |

实施约定：历史原件初期保留，清理须明确选择和确认；压缩不在本批。依赖/许可/资源与可清理产物持续记入LOCAL-DEVELOPMENT；新字段用迁移，HTTP变化同步OpenAPI；全部构建/依赖/真实样本与浏览器验证在devtest执行。最终提交、推送、devtest升级与数据不变验证属于交付范围。

2026-10-21继续实施（未部署）：隔离Office阅读服务在devtest启动，首轮三类真实样本因强制gen图形后端尝试连接X11而失败；改用svp无界面后端后，XLSX/PPTX/DOC分别通过私有HTTP返回PDF（20577/22926/21153字节，1.59/1.78/1.38秒）。这仅证明三类样本的原生转换链路，不代表完整格式、安全、业务API或浏览器验收完成。容器只读根目录、非特权、768MiB/1CPU/128进程、192MiB临时区，不挂载业务卷。源文件窗口改为复用任务轮询，失败任务保持可见；补充阅读与存储管理布局，尚待浏览器测试。

继续验证：来源页增加显式服务器副本迁移入口，request_id在网络失败时保留；后台按页安排独立子任务，保留来源关联。新增真实SQLite/文件/HTTP的两页迁移与重放、最近成功概要及活跃任务版本清理保护、原生DOCX→持久PDF→鉴权读取与原件不变回归。`.local/source-files-protection-tests.log`共7项通过/12.16秒，前端构建成功。副本与阅读任务增加validate/copy或render/publish有序进度，同步主OpenAPI步骤枚举。仍缺完整浏览器回归、全部预览格式/安全验收、迁移恢复演练与最终部署，不能标记本批完成。

浏览器专项：`.local/source-files-browser.log`两项/24.0秒通过，桌面1440与手机390实际打开XLSX原生PDF、版本固定、显式清理缓存、下载原件字节/版本不变；截图native-source与storage-mobile已人工查看。清理后统计更新的更强UI断言已补充，待重跑。渲染容器实测seccomp拒绝IPv4/IPv6、允许Unix IPC，子进程无法读取父进程环境。旧reading/overview-formats/legacy阅读用例已按概览专用交互改写；候选/历史仍由后台/API回归覆盖，页面不再提供旧阅读格式。首轮reading四项3通过，返回列表断言在桌面隐藏按钮上超时，改为手机返回场景；扩大阅读组首轮6通过、2项因未传已有CJK字体环境而未执行，已按实际字体路径重跑。未宣称完整回归通过。

扩大阅读回归已终态通过：`.local/source-reading-all-font.log`8项/1.5分钟，覆盖Agent设置、旧Office/RTF、七类新Office/分隔文件、六格式十份实际文件、概览样式、重解析历史保护、恶意文本与过期会话。仍不代替原生预览全部类型、来源增量、完整后端与升级恢复验收。完整后端在专用容器`juanzhan-source-backend-tests`运行，日志`.local/source-full-backend.log`；初次挂载父目录因生产app用户无法遍历宿主私有目录而无法加载Python，重跑仅测试容器改为root，不改宿主权限/生产运行用户。

补齐多页TIFF源文件阅读：在同一受限子进程内由Pillow将原始图像帧生成派生PDF，不执行OCR或替换原件；32MiB输入/100帧/单帧1200万及总2400万像素/64MiB输出限制。真实两页TIFF经上传、任务、PDF读取及原件字节校验，与原生DOCX共2项通过（`.local/source-native-tiff.log`，7.73秒）。首轮测试误用了未安装的pymupdf，改用已有pypdf计页，无新增依赖。私有renderer安全profile增加DisableActiveContent与BlockUntrustedRefererLinks，取自固定LibreOffice25.2.3.2官方Common.xcs，不据此单独声称恶意文档整体验收完成。

部署Compose新增独立office-preview服务（无宿主端口/业务卷，768MiB/1CPU/128进程/192MiB临时区）及worker私有连接；新镜像候选rc.15仍待最终构建验证与部署。原生预览/缓存清理更强浏览器断言重跑2项/28秒通过（source-files-browser-final.log），统计确实更新为0份、原件字节保持。完整后端首个失败是旧离线下载预期与新服务器副本行为冲突，测试已本地修正为副本可读/来源关联保留，尚待专项重验；完整回归仍运行。

第一轮完整后端已终态：588通过、6失败、20可选实物样本未设环境而跳过（source-full-backend.log，473.86秒）。离线副本旧预期专项已修正并通过（source-offline-acceptance.log）。另5项失败均定位为人工来源匹配对“尚无Revision ID的新发现条目”调用original时误走快照逻辑；source_matching显式allow_snapshot=False以核验当前外部字节，不让缓存掩盖来源变化。专项source-match-regression正在运行。不能将本轮报告当作全通过；下一轮完整回归需携带真实样本环境，消除可选实物跳过。原生9类实物矩阵source-native-matrix.json已全部HTTP200（约1.2～1.7秒/份）；DOCX/TIFF另有持久API验证。

人工匹配修复后专项9项/7.12秒通过（source-match-regression.log），覆盖重新关联、相同哈希不合并、源字节变化、审计回滚和lease失效。已启动携带两套锁定真实样本环境的完整回归（source-full-backend-final.log；专用容器juanzhan-source-backend-tests），等待结果后再判定完整后端验收。

完整后端复验已终态全部通过：source-full-backend-final.log为615项/463.36秒，无跳过（含两套固定实物样本、源匹配修复与原生预览）。后加契约2项/1.16秒通过，阅读PDF备份恢复2项/8.13秒通过。真实独立只读bind/HTTP/worker/Converter演练source-snapshot-real-drill.log确认同大小同mtime变化新版本、未变不增版、原路径删除后两版本仍可读、人工说明保留；临时容器/卷/网络均按确切随机名称退出清理。候选版本设为rc.15，构建脚本将输出业务和独立renderer两个镜像的源码/dirty/ID，仍未构建或部署本候选。
