# 测试与交付验收

2026-10-22 T52：上传HTTP47项通过（Cookie/Bearer拒绝.git、gitignore/gitattributes/gitmodules/gitkeep/git-credentials/hgignore/bzrignore，不新增原件/档案/任务；README/package.json/main.py保留）；源/Agent契约6项通过。folder-upload＋upload-exclusions 6项通过，真实原生目录选择及CDP拖放均跳过4种VCS目录及配置，仅保存正常文档，逻辑目录不包含.git等；枚举专项确认被排除VCS目录不调用createReader。Vite构建通过；Docker构建SSH通道在导出阶段断流且挂起，服务器无构建进程后核对镜像标签source-dirty=false、revision=e31060e9f60463cddc963a2fc4d665ba5ed9257c和运行镜像/健康/源码对应，清理本机悬挂SSH通道；未重建已验证产物或改动业务卷。公网1440/390零控制台错误，前端跳过gitignore/gitattributes且无上传HTTP，直接API上传gitignore返回422 UPLOAD_EXCLUDED；部署与QA前后全部业务表和37文件哈希不变。无新依赖，Browser插件未列出，沿用devtest Playwright。未重跑全后端/转换矩阵。

2026-10-22 T51：tests/test_uploads.py 37项通过，覆盖Cookie与Bearer辅助文件422拒绝、不新增Document/Revision/managed_objects/Job和原件目录文件树不变，以及8种普通隐藏/备份/相似文件名可保存；source/agent契约合并共43通过。首轮新增测试误将存储初始化.store.lock视作上传残留，改为严格比较调用前后的文件树/字节后通过，未删锁或放宽存储保护。Playwright archive＋folder-upload＋upload-exclusions共9通过；规则大小写匹配与枚举预算调整后folder/exclusions 6项再通过。真实原生目录选择和CDP目录拖放均仅上传5份保留文档、跳过7辅助项目，无__MACOSX目录入库；直接选择.DS_Store增加跳过数但无上传HTTP。枚举专项确认被排除目录不会调用createReader。保留原22文件层级/重复/重试/分页/取消流程，1440/390无溢出。生产构建通过，沿用既有PDF chunk提示；契约测试有既有HEAD operationId警告。公网rc.19跳过DS_Store/Thumbs.db不发送上传HTTP，直接Cookie上传DS_Store返回422 UPLOAD_EXCLUDED，零控制台错误；部署/QA后业务表及37文件哈希不变。Browser插件未列出，使用devtest已有Playwright/Chromium，无本机依赖安装。本轮未重跑全后端或转换矩阵，未修改转换器/数据库/外部扫描。

2026-10-22 T50：Playwright使用真实SQLite/文件存储/HTTP验证原生文件夹选择（22个文件，超过旧20上限；嵌套/已有目录复用/重复文件显式另存/下载字节不变）；CDP Input.dispatchDragEvent传入真实服务器临时目录和文件，验证混合拖入、空目录、子目录及503后重试，390无溢出。枚举专项验证121文件跨100/21/空批次读取、1000项限额、路径穿越拒绝、取消和权限失败。archive/organize/overview-home/folder-upload共14项最终通过：首轮发现文件输入标签子串冲突、目录选择器默认multipart filename携带relativePath被后端拒绝，分别改为独立标签与显式file.name；再验13通过1取消等待提示失败，恢复等待/活动取消的真实区别后archive＋folder-upload 6项复验全通过。原件路径校验未放宽。构建通过，保留既有PDF chunk提示。Browser插件未列出，沿用devtest Playwright/Chromium，无本机包安装。公网rc.18只读验证1440/390入口、原生multiple目录选择、零控制台错误，不向业务实例导入样本；部署前后及QA后原4档案/业务表/20文件哈希一致。后端未修改，本轮未重跑全后端套件；实际转换不属于本轮新增验收，保存成功不冒充解析成功。

2026-10-21 T49：devtest生产构建通过（沿用既有PDF chunk提示），archive＋organize＋overview-home共11通过；首页验证覆盖全局计数与真实SQLite/文件上传、跨空间近期入口、关闭详情后的全宽列表、URL刷新/前进后退及390布局。新增稳定等待统计后手机截图和任务中心入口后home单项再通过。真实Converter search 4项最终通过：首轮3通过，OCR样本因漏传JUANZHAN_TEST_CJK_FONT失败；补齐既有字体路径后该项通过。公网rc.17只读验证首页真实4文档/计数、列表宽度>1100（1440视口）、Word概览打开及返回收起、任务入口、390无横向溢出和控制台零错误；部署前、部署后、QA后业务表和20文件哈希一致。Browser插件未列出，使用devtest已有Playwright/Chromium，未安装本机依赖；本轮未重跑全后端测试，后端无代码/契约/迁移变更。

2026-10-21 T48：document_api＋overviews 18通过；search＋files 54通过（使用既有rc.15容器、只读sysfs和CJK字体路径）。首轮宿主机检查51通过3失败，原因为漏传CJK字体及宿主sysfs可写，按既有容器环境重跑全部54通过。Vite生产构建通过，保留既有PDF chunk体积提示。archive＋organize首轮9通过1失败；新增偏好检查刷新页面导致上传队列清空，修正测试顺序后该项独立复验通过。覆盖默认列表、网格切换、批量、拖放、分页、空间隔离、上传及390响应布局。公网只读复验真实4份文档、一行摘录、默认列表、网格/列表重开偏好、零逐行overview请求及零控制台错误，1440/390截图已检查。Browser插件不可用，使用devtest既有Playwright，无本机依赖安装。未承诺没有现成PNG的Office自动生成首页缩略图；浏览列表不触发转换。

当前T43～T47已在devtest rc.15交付。完整615项后端、额外契约/读取缓存恢复/确认来源专项、阅读8项/PDF9项/概览清理2项/PNG-JPEG1项/主界面12+1复验，以及最终成品49.09秒升级恢复、公网Word与Agent9项均通过。原4档案、业务表和19文件完整保留，仅按需新增1份阅读缓存。逐项证据和失败修复过程见BATCH-SOURCE-FILES及本文末尾；早期记录不能覆盖当前交付。

## 2026-10-21 六格式、十份文档的概要引擎实测

用户目标是常见格式解析和概要提取。本轮使用完全合成的真实二进制/文本文件，运行隔离Archive + TCP Converter + worker，实际SQLite、文件存储、HTTP上传与Playwright；未导入或修改用户文档。Browser plugin not available，使用既有Playwright，无新依赖。

| 样本 | 格式 | 最终结果 |
|---|---|---|
| 摄影课程说明 | DOCX | 课程要点/安排保留，数字普通文本，无专用卡片 |
| 服务合同 | DOCX | 服务范围、付款验收和延期说明均保留 |
| 会议纪要 | TXT | 决议、负责人、截止时间及注意事项保留 |
| 项目计划 | Markdown | 进展、下一步列表、风险保留 |
| 设备清单 | HTML | 表格中主机/路由器及验收状态保留 |
| 操作手册 | EPUB | 首章/次章名称及正文保留，不伪造页码 |
| 季度报告 | PDF | 三页报告的进展、风险及后续动作可读 |
| 120段笔记 | TXT | 有界8点，并提供部分范围提示，不宣称全文概括 |
| 扫描报告 | PDF | 默认不启用OCR，正确显示暂无可提炼文本，本轮未测试OCR提取 |
| 含脚本和外链图像的网页 | HTML | 可读内容保留，概要无活动元素，脚本未执行 |

每份检查默认概览、无领域卡片、正文来源跳转（扫描空文本除外）、1440×1000/390×844截图、无横向溢出，以及只读查看不改Document版本/Revision/ParseRun。十份样本场景28.1秒；另4项完整阅读回归均通过，整组5项49.1秒。8项纯规则回归通过（含新增不一致章节层级首章保留）。控制台/截图与测试初始页面身份通过现有测试断言和人工截图复核。未重跑完整后端或全部其他浏览器组。

实测发现并修复：首个唯一一级标题被一律视为总标题，EPUB下一章使用二级标题时首章名称被省略；现在保留父标题及原文来源，再展示子章节。初次仅前5份通过即在EPUB断言失败，日志保留overview-types-before-fix.log；没有放宽章节期望。另有初始浏览器Compositor因/tmp共享内存写权限崩溃，使用私有TMPDIR解决，未改系统目录权限；中断的环境诊断不计通过。

证据：.local/overview-types.log；.local/types-browser-tmp/juanzhan-overview-types-results.json（十份passed）、juanzhan-types-*-desktop/mobile.png；本机/tmp/juanzhan-types-contract.png、juanzhan-types-epub-mobile.png及结果JSON。可重跑命令：TMPDIR=/opt/juanzhan-dev/.local/types-browser-tmp LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PLAYWRIGHT_BROWSERS_PATH=/opt/juanzhan-dev/.local/playwright JUANZHAN_TEST_CJK_FONT=/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Medium.otf npm run test:e2e:reading（在web目录）。隔离数据库/存储/样本退出自动删除，截图/日志按LOCAL-DEVELOPMENT清理。

rc.10镜像sha256:8fc85cbf73f4ddc356c15d9fccbfabe297a6fe72002fe6a284bcb5e6654705a7，干净源码281b929；manifest /tmp/juanzhan-release-njyhi7e4/manifest.json，副本私有rc10-manifest.json。仅概要规则/测试变化，无接口或迁移；这不代表已提供后端概要API，也不证明任意复杂文档或长文都能生成语义摘要。

## 2026-10-20 通用分点内容概览（rc.9）

最终镜像sha256:83776d5283eead7eabca8da5d147664137209092aa5abe4027647fee42b27349，干净源码7168700；构建manifest为/tmp/juanzhan-release-1hgyu80e/manifest.json并复制私有rc9-manifest.json。表格摘录补充后7项规则再次通过，部署后的真实Word只读核对在此最终镜像执行。此前5168ff6构建为中间产物，不作为最终运行镜像。

按最新用户决定移除课程/价格/时长/受众等专用事实卡片与领域判断。概览按实际章节、子标题、代表句或纯文本顺序组成通用要点；数字保留在原句，标题/短标签/明确粗体做安全React强调，不渲染活动HTML。表格摘录包含列名及实际数据，避免只摘表头。100块/4000字符读取预算、8点上限、原文依据和章节/全文入口保留；范围/方法仍通过信息图标展示。无依赖/API/迁移/业务字段变更。

验证：7项规则覆盖课程与通用报告/会议、纯文本、表格、边界/空内容/XSS字符串与输入不变。阅读浏览器4项覆盖真实HTML概览、单列要点、标签加粗、无专用卡片、提示/触屏与原文导航、真实DOCX候选/并发/历史、安全文本和失败/会话；首次3通过1因旧.document-abstract选择器失败，改为新要点选择器后单项5.9秒通过。基础浏览器首轮12通过1跨页选择收件箱计数暂为0而非1，未改业务逻辑，单独重跑该项18.5秒通过；保留两次日志，不将其归因本轮摘要代码。累计17项浏览器通过；未重跑后台484项或其他浏览器组。

Browser plugin not available，沿用devtest已有Playwright缓存。生产构建通过（既有PDF大分包提示保留）。真实用户Word在1440/390只读核对：默认通用要点、数字无卡片、标题强调、原文跳转、无控制台错误/框架错误层/横向溢出；Document版本、Revision和ParseRun不变，未重解析。私有证据为test-instance/generic-overview-browser.mjs、generic-overview-smoke.json及同前缀PNG；日志.local/generic-reading.log、generic-library.log、generic-library-retry.log与generic-rc9-build.log。

## 2026-10-20 概览优先与全站信息提示（rc.8）

目标流程：点击资料 → 主阅读区默认摘要/关键信息 → 信息图标悬浮/键盘聚焦显示说明 → Escape关闭；手机点击与视口边界核对。Browser plugin not available，沿用devtest已有Playwright，无新增依赖。

已验证：7项摘要规则；4项阅读浏览器（21.9秒，含提示隐藏/悬浮/聚焦/Escape/触屏与390像素边界）；4项任务浏览器（28.4秒）。基础13项中12项直接通过，首条旧“正文内容”断言更新为默认摘要后单独通过（6.0秒），未修改产品来适配旧测试。初次浏览器启动错误来自误设/usr/bin/chromium，已使用既有PLAYWRIGHT_BROWSERS_PATH缓存重跑。来源初次使用默认旧foundation镜像，结果不计本轮验收，须用JUANZHAN_E2E_IMAGE=juanzhan:0.1.0-rc.8。

生产构建通过，既有PDF分包大小提示仍存在。实际devtest Word只读1440/390验证通过，摘要/价格/时长/课次/未说明受众、原文入口、悬浮提示、无控制台错误与溢出；document_version、Revision、ParseRun不变，未重解析。私有证据为test-instance/info-overview-browser.mjs、info-overview-browser-smoke.json及同前缀PNG。

rc.8镜像sha256:8956c1a0aaa6dbbe0fc0cc0297310b8e5142fd5e9ca43b8d57a2116addfcdd2b；干净源码b0e903c，manifest为/tmp/juanzhan-release-6h1k_xr9/manifest.json。仅前端交互，无API/迁移/后端变化，本轮不重跑完整后端484项；全站补充浏览器结果在下方追加。

最终补充：来源4项（rc.8镜像，1.5分钟）、搜索4项（首轮3项通过，缺字体的扫描PDF夹具按已有CJK字体补环境后单项8.3秒通过）、原件/PDF9项（37.5秒）、备份3项（15.4秒）通过。累计七组41项浏览器及7项规则通过，按失败原因只重跑相应用例，未反复重跑已通过组。复用JUANZHAN_TEST_CJK_FONT=/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Medium.otf，LANG/LC_ALL=en_US.UTF-8，无字体安装或断言放宽。原有Starlette弃用提示属于测试库提示，无浏览器应用异常。

界面核对：页面身份/非空/无框架错误层、控制台、桌面1440与手机390截图及交互全部通过。最新真实Word核对在最终rc.8镜像完成；临时隔离来源容器/卷正常清理，线上三服务及原两个无关服务保留。证据日志为info-reading.log/info-jobs.log及本机/tmp/juanzhan-info-broad.log、info-broad-verified.log、info-extra-verified.log、info-final-verified.log；后两份分别含来源/搜索与字体修正后的搜索/文件/备份结果。

## 2026-10-20 摘要与关键信息卡片

用户明确选摘要/卡片优先，原章节摘录保留为次级模式。本轮仅前端，未改HTTP契约/11迁移/后台/依赖；未重新执行无变化的484项后端。Node原生规则测试7项全部通过（120ms），日志.local/summary-cards-unit-verified.log：原文标价与报价/收益例子隔离、四位小数/早鸟条件/价格区间/单位原文保留、适合人群明示/未知、课程标题后的时长与镜头时长区分、部分读取边界、章节内容与出处。

最终阅读浏览器4 passed（19.8s），任务4 passed（27.5s），.local/summary-cards-reading-verified.log及summary-cards-jobs-verified.log。真实SQLite/文件存储/HTTP/Converter/worker验证课程HTML样本、默认摘要/卡片、缺失受众、报价不进入学费、出处到正文、章节摘录/全文/分页/安全源文本/候选/历史/失败/次级重解析与手机布局。Browser插件未提供，复用现有Playwright，无新依赖。

rc.7干净e04653c构建并部署：manifest /tmp/juanzhan-release-8x8je1ok/manifest.json，镜像sha256:f23eb175eb8f9badb0f6f3d77b00856a3fc56afa6513e825dfb255928e3af9b2。实际用户Word1440/390只读验证摘要优先、1980元/12小时/6节直播课、适合人群未说明、五类课程内容、原文依据到完整正文、无溢出/控制台错误；document_version/current_revision_id/current_parse_run_id前后相同，未重解析。三个服务健康，原有服务保留。私有实例summary-cards-browser-smoke.json/png记录，实际文档截图本机/tmp/juanzhan-word-summary-cards-*.png，不提交Git。当前提炼为可追溯规则摘要，未接LLM，未推断未知值或写入业务字段。

## 2026-10-20 内容概览优先与阅读降噪

无后台/API/迁移/依赖变化。真实阅读浏览器3项通过（17.0s），.local/content-overview-reading-final-verified.log；任务4项通过（29.2s），.local/content-overview-jobs.log。覆盖默认原文章节摘录、语义表格、进入完整正文、逐段定位显式开关、分页/源文本安全、候选冲突/采纳、历史/失败/过期会话、次级重解析及手机布局。Browser插件未提供，复用现有Playwright。首轮旧正文标题断言及列头AX角色断言不适用于新默认视图/单列表格，分别改为验证新概览标题及真实thead/th值；原失败日志content-overview-reading.log、content-overview-reading-final.log保留。

rc.6干净e9484b8构建并部署，manifest /tmp/juanzhan-release-mgnd6hov/manifest.json，镜像sha256:e53f7680c63a70ea039b791cf14ef94c80a4f77abeab675378eb629e5c44a36d。实际用户Word已有75块（20标题、26段落、26列表项、3表格），只读验证默认呈现开篇信息/4个主章节、完整正文入口、定位按需开启、说明默认折叠；1440/390无溢出或控制台错误，三个服务健康。未重解析、改写原件/正文/业务字段，未生成语义摘要或推测信息。报告私有实例content-overview-browser-smoke.json，实际文档截图content-overview-desktop/mobile.png；本机/tmp/juanzhan-word-overview-*.png。未重跑无变更的后端484项。

## 2026-10-20 任务中心单列竖向调整

仅UI布局调整，后台/63路径契约/11迁移/依赖不变。devtest构建及任务浏览器4项全部通过（30.8s），真实DOCX/失败任务/刷新持久性/原位详情/1440与390视口，日志.local/task-column-build.log、task-column-browser.log，截图本机/tmp/juanzhan-task-column-{desktop,mobile}.png。Browser插件未提供，复用已有Playwright；未重复运行无改动的484项后端。

rc.5已从干净3f81626构建并更新juanzhan-test，镜像sha256:ccb4ae85cc237372697d9806ef3f94f43c87fe2560600422e7de2d5d152b31e6，manifest /tmp/juanzhan-release-8nsk0677/manifest.json。部署后三个服务健康；实际1440/390浏览器验证卡片横坐标/宽度相同且纵向不重叠、详情在原任务内、六条真实进度、无溢出/控制台错误、test登录及原4份档案保留。私有实例目录task-column-browser-smoke.json及task-column-*.png保存结果。

## PDF全页阅读专项 · 2026-10-19

服务器实际构建产物/HTTP/浏览器：原件组9 passed（最终代码34.5秒），日志`/opt/juanzhan-dev/.local/pdf-reader-browser-final-code.log`。覆盖原有下载/被动预览/HTML隔离/历史下载，新增真实8页PDF（超出缩略图范围）、跳页/旋转/缩放、高DPR画布像素预算、文字选择和跨页查找、PDF脚本/URI不执行、中文本地CMap、真实扫描页非白像素、加密文件错误密码后纠正、版本冲突/损坏、快速关闭重开后worker数为0、真实10001页拒绝。最后加载失败/超限后worker释放断言专项2 passed（9.6秒），日志`.local/pdf-reader-failure-cleanup.log`；正常方向/宽度适配截图流程1 passed（8.5秒），日志`.local/pdf-reader-browser-final-visual.log`。

服务器只读sysfs隔离容器tests/test_web.py + tests/test_files.py：8 passed，7.59秒，1条既有客户端弃用提示，证据`.local/pdf-web.log/xml`。验证新worker CSP仅同源、禁止JS eval、nosniff，既有鉴权/当前与历史原件/损坏/外部边界/被动预览不变。HTTP契约0.4.27/56路径、9条迁移未变；前端构建通过，PDF模块548KiB左右按需加载，构建器保留大分块提示，不掩盖警告。

桌面1440×1000和手机390×844截图`/tmp/juanzhan-full-pdf-{desktop,mobile}.png`已目视检查，完整控件和真实文字可见，无页面横向溢出；高倍缩放在PDF面板内部滚动。本机副本`/tmp/juanzhan-remote-qa/`。初次辅助浏览器测试重复登录已登录会话导致超时，修正夹具后通过；10001页预算测试发现PDF.js6缺少PDFDocumentProxy.destroy，改为loadingTask.destroy后验证明确超限和释放。初步/预算/布局日志保留`.local/pdf-reader-browser-*`。测试源生成器有pypdf add_js弃用提示，非产品失败。未重新宣称本阶段完整后端/所有浏览器/发行镜像恢复验收通过。

## 歧义文件人工处理专项 · 2026-10-19

服务器标准只读sysfs容器执行test_source_matching、test_source_incremental、test_maintenance、test_adoptions、test_source_scheduler：38 passed，26.68秒，1条既有客户端弃用提示。证据`/opt/juanzhan-dev/.local/source-matching-final.log/xml`。最后补充前后相对路径审计及匿名请求拒绝后，匹配专项8 passed（8.89秒），证据`.local/source-matching-audit.log/xml`。覆盖真实只读字节、保留档案/Revision/人工字段、独立登记不合并、幂等/CSRF/鉴权、分页/严格类型、并发版本/条目观察冲突、旧路径存在、哈希不符、审计回滚、失效租约、Purge取消与屏障释放。sysfs由元数据观察夹具登记，未声称无扩展名文件由实际扫描发现。

真实只读bind来源通过正常首次扫描、实际两文件重命名及增量歧义检测，再由Web选择旧档案关联、将另一份登记为独立档案：完整来源浏览器组4 passed（1.4分钟），日志`.local/source-match-browser-full.log`。最后优化手机单选/确认布局后，专项1 passed（17.1秒），日志`.local/source-match-browser-visual.log`，原件/人工字段/Revision不变和独立档案数均核对；手机截图`/tmp/juanzhan-source-match-mobile.png`已目视检查，无横向溢出，本机副本`/tmp/juanzhan-remote-qa/`。首次新增浏览器测试getByLabel精确名称因包含select子文本超时，改用combobox角色/名称后通过，初始日志保留`.local/source-match-browser-initial.log`；首次后端夹具误读公开Entry的space_id已修正，不属于业务失败。

前端构建和OpenAPI YAML解析通过，Archive0.4.27/56路径、9迁移不变。最终专项开发镜像juanzhan:source-matching-dev（dirty）ID为sha256:a5ca0c3fb88251522e0771b34647838ed14a0accf7dafa0f5be08d8786483a10。未替换既有候选或业务服务，尚未执行本阶段最终全仓库/所有浏览器/发行恢复验收。

## 来源定时扫描专项 · 2026-10-19

服务器标准只读sysfs容器运行test_source_scheduler、test_sources、test_foundation、test_backup、test_source_initial、test_source_incremental、test_adoptions：55 passed，30.51秒，1条既有客户端弃用提示。证据`/opt/juanzhan-dev/.local/source-schedule-final.log/xml`。6项新增计划测试验证CSRF/类型/版本冲突/关闭、初次导入门槛、多worker并发只排一次、持久期限、活动扫描/禁用、排队失败事务回滚、真实只读worker、备份恢复及8→9迁移保留配置/旧校验值。额外历史parse_requests升级测试1 passed，0.45秒，日志`.local/source-schedule-upgrade.log`。

真实daemon浏览器专项1 passed（9.7秒）：在Web开启1分钟计划，仅回拨一次性测试库期限，由正常worker自动发现真实新增文件，关闭后重载保留。完整来源浏览器组3 passed（1.1分钟），覆盖原导入/失联/排除、托管接管与定时扫描，日志`.local/source-schedule-browser-full.log`。测试只通过私有fixture的.container-name定位随机容器，不增加生产测试API或改变实际worker调度代码。新手机截图`/tmp/juanzhan-source-schedule-mobile.png`已目视检查，可读且无横向溢出；本机副本在`/tmp/juanzhan-remote-qa/`。

前端构建通过，OpenAPI YAML解析确认0.4.26/54路径。独立dirty开发镜像juanzhan:source-schedule-dev用于本组，既有RC标签未改。当前9迁移，release_drill迁移数量断言同步源码迁移集合，但本轮尚未重跑完整发布演练；完整后端/全部浏览器/新正式候选验收仍需最后执行。

最后核对将下次计划显示为本地日期和具体时分秒，并保留time datetime UTC值；相应真实daemon浏览器流程补充1 passed（10.1秒），日志`.local/source-schedule-time-browser.log`。此显示修正后的开发镜像ID为sha256:7b2af5d345b228fdc93b9ff47c18a249cf0adb08d7e47068abb3bb4f2b3bade1。

## 本次知识库检查

- 五个原始规格从当前可读取的文件完整读取，文件大小与来源元数据一致。
- 两份 OpenAPI 3.1 YAML 可解析；全部本地 $ref 可定位（检查脚本由本次整理执行，不等于完整 OpenAPI 语义验证）。
- V0.4 SQL 在内存 SQLite 空库执行、重复执行、integrity_check 通过；这只验证 DDL 基线，不等于 T02 已实现。
- Markdown 相对链接与原型引用资源检查；原型沿用既有成果，本次不修改 UI。
- 原型此前 Work 浏览器验证过主界面、视图切换、搜索、文本切换、标签与导入演示；不是生产端到端验证，移动端未验收。

## 实施必须测试

沿用 reference/archive-roadmap-v0.4.md 中 UX-01～14、META-01～16；新增 UX-15～18 见 PRD。

重点：同 hash 不误合并、收件箱与 Folder 正交、首扫目录解耦、来源整体离线不误判 missing、取消索引不重导、外部零写入、并发 409、Decimal 数值/日期/布尔三态、人工值不被重解析覆盖、旧成功内容不丢、中文两字/混排检索、HTML 与路径安全、任务有限重试/幂等、恢复演练。

真实 SQLite + 文件存储 + HTTP 集成是门槛；转换器至少每格式真实样本、扫描与图片 OCR 开/关、坏文件、超限和超时样本。默认详情必须展示结构化块/真实异常状态，原件仅通过关联入口打开，返回保持位置。

每次记录实际命令与结果；未执行项明确未验证。不把 YAML 能解析当成所有请求响应已正确，不把构建成功当成浏览器验证。

## T01/T02 本轮实测 · 2026-10-16

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：7 项通过。
  覆盖真实磁盘 SQLite、逐连接 FK/WAL、目录循环/根重名/跨空间拒绝、
  Document/Revision/托管文件持久化、并发迁移、失败回滚、校验和篡改拒绝、
  Archive HTTP readiness、Converter 鉴权/空能力/501 和缺令牌启动拒绝。
- Docker 镜像离线哈希校验安装成功；Compose 两服务健康检查通过。
- `python scripts/smoke.py`：真实运行容器 HTTP 请求通过。
- 容器重启/重建后，测试 Space 与 managed 文件均保留，integrity_check=ok；探针数据已清理。
- 两份 OpenAPI YAML 解析通过，不代表业务接口已实现。
- 存在 Starlette TestClient 对 httpx 的弃用警告，不影响本轮结果；后续维护需关注适配。
- 本轮未验证业务认证、上传崩溃恢复、转换/OCR、外部只读来源或生产浏览器端到端行为。
- 构建环境初始 DNS 不可用，改为宿主下载 wheelhouse、镜像离线复核哈希；
  非 root 容器读取源码的权限问题已通过 COPY 显式权限修复。

## T03 本轮实测 · 2026-10-16

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：19 项全部通过（含 T01/T02）。
  新增真实 SQLite 认证测试覆盖会话轮换与 Cookie 标志、未授权读写拒绝、登录/退出/Token 管理 CSRF、
  跨站写拒绝、Bearer 免 CSRF、无效 Bearer 不回退 Cookie、令牌撤销/过期、密码重置撤销全部凭据、
  持久限流、匿名会话容量与过期清理、输入错误不回显秘密、重启会话保留、增量迁移保留旧数据。
- `DOCKER_CONFIG="$PWD/.local/docker" docker compose build archive`：镜像构建通过。
- `python scripts/smoke_auth.py`：隔离容器 + 独立真实数据卷 + 管理员 CLI + 实际 HTTP 全链路通过；
  Secure Cookie 属性已检查，内部 HTTP hop 手动传 Cookie 模拟 TLS 终止后的请求，未声称完成浏览器 HTTPS 验收。
  容器重启后会话和 API Token 有效，撤销及退出后立即拒绝；测试容器/卷已清理。
- `docker compose up -d --wait --no-build` 与 `python scripts/smoke.py`：当前两服务升级与健康检查通过。
- 两份 YAML 可解析，全部本地 $ref 可定位；认证契约扩展为 Archive API 0.4.1。
- 仍有既有 Starlette/httpx TestClient 弃用警告。尚未实现生产登录 UI、部署 HTTPS 代理、
  多用户/角色、密码邮件找回及档案 CRUD；未将这些能力计为已验证。

## T04 本轮实测 · 2026-10-16

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：41 项全部通过（含此前 19 项）。
  新增测试覆盖有界读取、空文件、大小/哈希校验、读取中断、磁盘 fsync/发布故障、8 路并发复用、
  不同内容保留原件、损坏对象拒绝覆盖、路径与符号链接拒绝、活跃写入时恢复互斥、
  过期临时文件清理及新文件/未知文件/符号链接保留。
- 子进程真实 `os._exit` 分别中断流写和原子发布后流程：临时文件可恢复，
  未完成对象不发布；完整已发布对象在清理 staging 后仍可校验读取。
- 私有 HTTP 测试适配器 + 真实 SQLite + 真实文件存储验证：写入失败无数据库引用，
  后续 SQL 失败不删除共享对象，完整孤儿对象保留。测试适配器不属于生产 API，T08 尚未实现。
- 64 MiB 生成流单次实验：Python tracemalloc 分配峰值约 134 KiB，耗时约 0.062 秒。
  这是当前本地文件系统样本，不是进程 RSS、正式基准或产品容量/SLA 承诺。
- 镜像构建、正常 Compose 两服务升级与健康检查、`python scripts/smoke.py` 均通过。
- `python scripts/smoke_auth.py`：隔离容器中真实 HTTP 认证仍通过；SQLite 引用的托管对象
  重启后可验证读取，启动恢复删除预置的过期 .part；测试容器与数据卷已删除。
- 仍有既有 TestClient 弃用警告；未验证断电/硬件损坏恢复、网络文件系统或生产上传/下载接口。

## T05 本轮实测 · 2026-10-16

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：49 项全部通过（新增8项分类集成测试）。
  覆盖 Cookie/Bearer、CSRF、重启持久化、规范化重名、目录自身/后代循环、跨空间创建/移动与模板引用、
  子目录/回收站档案/来源引用阻止空目录删除、未实现策略501、类型停用及模板替换保留历史值、
  未知资源404与严格输入422、失败后原目录/类型事务回滚。
- 两路并发重复标签请求分别201/409；相互移动目录请求分别200/409，未形成循环，FK检查通过。
- 真实 SQLite + 托管文件 + HTTP 标签删除测试：关联解除，Document version递增，审计事件生成，
  Document/Revision/原件内容保留，未造成物理删除。
- 两份 OpenAPI YAML 检查通过：拒绝重复键、全部本地 $ref 可定位。Archive契约扩展为0.4.2。
- 镜像构建、`python scripts/smoke_auth.py` 隔离容器实际HTTP分类创建/冲突/更新/删除/重启保留通过；
  认证与存储恢复验证仍通过，测试容器/卷自动清理。
- 正常 Compose 两服务升级及 `python scripts/smoke.py` 通过。仍有既有TestClient弃用警告。
- 未实现生产分类UI、自定义字段定义CRUD/归档必填验证，以及目录非空迁移/回收两策略。
  最后两策略明确501，不作为成功删除计入测试。

## T06 本轮实测 · 2026-10-16

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：68项全部通过（新增19项）。
  覆盖 Document/Revision/对象/事件同事务登记、同空间重复提示/显式独立档案、跨空间物理复用、
  新版本保留原 ID/人工字段/标签/旧 ParseRun、版本与编号跨重启连续、并发追加/重复登记互斥。
- 真实 SQLite 触发器故障注入：创建或追加时审计写入失败，所有相关数据库变更回滚，
  原档案不变，已发布完整字节仍保留。缺失或伪造文件描述符不产生引用。
- 软删除/恢复版本递增、匹配版本重复目标状态无新增事件、过期版本409、目录链接移除后恢复到未分类。
  外部只读样本文件软删除/恢复后字节、inode、mtime均不变；外部纳入托管明确501。
- 私有HTTP适配器验证CSRF及版本冲突错误携带 current_document_version；
  这不是公开 Document 路由，未把T08/T09标为完成。
- 镜像构建、`python scripts/smoke_auth.py` 独立容器生命周期实测通过：
  登记→追加Revision→软删除→容器重启→恢复，原件可读、Revision连续、四条审计事件与FK检查一致。
  既有真实HTTP认证/分类/存储恢复均通过，测试容器与数据卷自动清理。
- 正常Compose升级健康，`python scripts/smoke.py`通过。既有TestClient弃用警告仍在。
- 未验证生产上传/下载、MIME嗅探、公开状态投影、外部扫描或后台任务幂等；这些能力尚未实现。

## T07 本轮实测 · 2026-10-16

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：83项全部通过（新增15项任务测试）。
  覆盖幂等键同请求复用/异请求409、入队与业务事务回滚、8路并发入队与唯一认领、
  过期租约恢复与旧令牌拒绝、累计尝试上限、退避/手动提前重试、永久错误拒绝重试、进度与心跳。
- effect和完成标记同事务测试：重复完成只执行一次业务SQL；effect抛错或提交时租约过期，业务写入回滚。
  使用真实Document、原件与审计表验证文档版本/事件仅变化一次，原件保留。
- 子进程限时测试确实终止长运行handler，handler直接退出被分类为WORKER_CHILD_EXITED；
  实际独立进程在认领后os._exit，重启队列在租约过期后恢复同一任务，累计attempts继续而非归零。
- 真实维护handler清理旧staging文件；未实现parse明确HANDLER_NOT_AVAILABLE，非法payload不回显私有值。
- 迁移测试验证原任务与空间数据保留。既有认证迁移测试纳入新0003迁移版本。
- 镜像构建及隔离容器验收通过：排队任务跨容器重启保留，真实 `worker --once` 执行清理，
  HTTP查询/CSRF拒绝/手动重试/已完成拒绝重试及attempts累计均通过；测试容器/卷已清理。
- 正常Compose的Archive API、Archive worker、Converter三个容器均healthy，
  `python scripts/smoke.py` 验证API/Converter及worker心跳通过；已有生命周期/分类/认证验收仍通过。
- 本轮未验证远程转换幂等、真实扫描/解析/上传handler、任务中心UI或多机队列；不得将其视为已实现。
  整体为至少执行一次，不承诺文件/网络exactly-once；仍有既有TestClient弃用警告。

## T08 本轮实测 · 2026-10-16

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：102项全部通过（新增19项上传测试）。
  真实HTTP适配器/SQLite/文件存储验证单文件multipart归档、MIME不信任客户端声明、
  同事务档案/Revision/对象/审计/Job登记、默认重复409与显式独立档案复用物理对象。
- 验证Cookie/Bearer/CSRF，未知或跨空间引用拒绝、非法/重复字段、路径式文件名、多文件、
  恰好文件上限成功、超限413、无Content-Length的分块总请求上限413、截断/主动断流400、接收超时408。
- 两个挂起上传占满槽位时第三个立即429，结束后无数据库引用；中文文件名及约254KiB中文文件
  走spool落盘后内容/MIME/大小一致；新建parse任务未实现时明确失败，原件仍保留。
- ZIP/DOCX/EPUB元信息嗅探不解包路径条目；文本/HTML/Markdown/PDF/图片/未知二进制样本验证通过。
  这是类型嗅探，不代表已完成真实转换、安全扫描或HTML消毒。
- SQLite触发器注入入队失败：档案/Revision/对象记录/事件/任务全部回滚，完整孤儿字节保留。
- 镜像通过锁定哈希安装新增python-multipart；隔离容器真实网络上传约273KiB原件、重复拒绝、
  keep_separate、parse明确失败、容器重启后两个档案共享对象及字节校验均通过。
  容器脚本的嵌套字符串转义问题已修正并重跑；测试容器/卷已清理。
- 正常Compose API/worker/Converter全部healthy，`scripts/smoke.py`通过。
  两份契约无重复键、全部本地$ref可定位。既有TestClient弃用警告仍在。
- 未验证完整HTTP的64MiB/1GiB容量或吞吐量、生产上传UI、公开档案详情/下载、真实解析/OCR。
  T04的64MiB存储实验不能替代完整HTTP容量测试。

## T09 验证 · 2026-10-16

`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：112通过，保留一项Starlette/httpx既有弃用警告。
新增真实SQLite/文件测试覆盖列表排序/筛选/分页、编辑/标签/日期/跨空间拒绝、并发版本冲突、必填与false值、
旧解析与新任务状态、外部未验证/离线、文件缺失、目录两种子树策略、Source引用阻止及注入审计失败回滚。
OpenAPI 0.4.6的YAML重复键和全部本地引用验证通过，43个path模板。

重建镜像后运行`python scripts/smoke_auth.py`：隔离容器真实HTTP上传后编辑/冲突/整理/回收恢复、
子树回收/恢复、原件及数据库重启持久化通过。随后Compose升级与`python scripts/smoke.py`通过，API/worker/Converter健康。
尚无生产界面验证；未声明转换、OCR、下载、全文检索或完整类型约束已完成。

## T10 验证 · 2026-10-17

`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：126通过，保留一项Starlette/httpx既有弃用警告。
14项新增用例覆盖固定集合不扩张、严格payload/完整版本映射/限额/CSRF、跨空间与引用、类型/整理、标签增删/no-op，
逐项冲突和注入审计失败回滚、真实spawn worker、重复完成幂等、租约前后失效整次回滚、撤销引用缺失与后续编辑保护。
OpenAPI0.4.7：44路径，重复键与全部本地引用验证通过。

重建镜像后`python scripts/smoke_auth.py`通过：真实HTTP提交选择快照，容器重启后worker执行，成功与冲突逐项结果正确，
重复撤销请求复用任务，撤销恢复收藏且不覆盖另一档案并发标题编辑；既有上传/目录/存储/鉴权检查继续通过。
Compose升级及`python scripts/smoke.py`通过，API/worker/Converter健康。未验证大规模批量吞吐或生产UI。

## T17 验证 · 2026-10-17

`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：144通过，保留一项Starlette/httpx既有弃用警告。
新增18项用例覆盖七类型/默认值/排序/空间过滤、重启持久化、严格输入与CSRF、不可改key/type/space、停用不释放key，
真实并发重名/总量竞争、约束深度/大小/非有限值拒绝、现存停用模板保留与新增绑定拒绝、移除模板/切类型保留历史值及FK。
OpenAPI0.4.8：44路径，重复键与全部本地引用验证通过。

重建镜像后`python scripts/smoke_auth.py`通过：隔离容器真实HTTP创建/重复/更新/停用字段与模板必填绑定，
跨容器重启保留配置/停用状态/模板，既有上传/批量/撤销/存储/认证验证继续通过。
Compose升级与`python scripts/smoke.py`通过，API/worker/Converter健康。未宣称字段值/规则求值、全文索引或生产UI已完成。

## T18 验证 · 2026-10-17

`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：169通过，保留一项Starlette/httpx既有弃用警告。
新增25项用例验证七类型真实存储/读取、Decimal±边界/四位/范围、日期、false/null、稳定选项、规则格式与regex超时，
metadata多键/归档失败及注入审计失败全部回滚、no-op、并发版本冲突、停用/空间/CSRF/回收保护、人工/候选来源和旧候选拒绝。
既有字段/批量/档案测试继续通过；T17开放规则测试改为已知options，新配置未知规则拒绝，历史未知规则501仍有测试。
OpenAPI0.4.9：44路径，重复键与本地引用通过。

生产依赖锁定regex并更新离线wheel/hash锁，镜像离线构建通过。隔离容器`python scripts/smoke_auth.py`验证真实HTTP
保存Decimal→filed类型→必填删除/越界回滚→显式候选采纳→再次重启来源/版本持久化，既有链路继续通过。
候选由真实SQLite夹具登记，不是解析器产物；未宣称真实解析/OCR/检索已实现。
Compose升级和`python scripts/smoke.py`通过，API/worker/Converter健康。

## T26 验证 · 2026-10-17

Python：171项通过（既有169加2项静态承载边界），保留一项Starlette/httpx既有弃用警告。
`npm ci --prefix web --cache /workspace/.npm`及`npm run build --prefix web`通过，初始JS gzip约82KiB；Vite HTML/入口/样式/API代理HTTP200。
`JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e --prefix web`：3条真实HTTP/SQLite流程通过，不使用假业务响应：
登录→首空间/目录→上传→结构化详情/真实Decimal字段→关联原件信息/ESC→列表网格→重复显式另存→移动返回→退出；
31份真实上传的分页/排序/空间切换与失效会话；断网失败与空结果区分、真实413、等待项取消及进行中取消的不确定保存提示。
取消测试只延迟网络传输，不伪造成功响应。测试服务一次性目录/随机管理员，测试上传限制32KiB用于验证413，不改正常实例。

| 浏览器检查 | 结果与证据 |
|---|---|
| 页面身份/非空 | 根路径、JuanZhan标题及真实登录/列表/详情DOM |
| 框架覆盖层/控制台 | 编译应用无覆盖层；成功链路无相关console/pageerror，重复409和异常测试的网络错误为预期 |
| 交互 | 3条端到端流程与171项Python检查通过 |
| 响应式 | 1440×1000、1024×768、390×844；后两者断言无横向溢出 |
| 安全边界 | 公开HTML/JS/CSS，API匿名拒绝；静态POST/目录穿越拒绝，缺构建503 |
| 构建/容器 | 离线镜像、隔离smoke_auth、Compose升级和smoke通过，三容器healthy |

Browser插件/skill未提供（Browser plugin not available），改用Playwright与已安装/usr/bin/chromium；未安装或禁用额外浏览器校验。
原型由独立Vite5175渲染，生产由一次性Archive8767渲染；设计基线为已接受docs/prototype，而非新生成设计。
同一QA轮用view_image检视/tmp/juanzhan-reference.png、最新/tmp/juanzhan-desktop.png、/tmp/juanzhan-mobile.png；截图不提交。

| 对照项 | 原型证据与本轮落实/有意差异 |
|---|---|
| 栏位/容器 | 64px顶栏、194px目录、355px文件区、297px属性；保留开放多栏与中央纸面 |
| 色彩 | #fdfdfb顶栏、#fbfcf9侧栏、#f4f5f2阅读底、#164634主操作；说明文字略加深提升可读性 |
| 字型/图标 | 无衬线控件、衬线标题，Phosphor书本/文件/上传/网格/列表同一图标体系 |
| 间距/选中态 | 纸面20px外距、细分割线、墨绿浅底选中和单一导入主动作，收敛控件字号和间距 |
| 首屏文案差异 | 保留档案库/收件箱/导入文件等；移除未实现搜索/设置空动作、假数据和页码，改真实空间/类型过滤与业务字段 |
| 原件/媒体 | 没有真实派生产物，不复制示例缩略图；统一文件图标，关联原件只展示真实信息，不伪造下载 |
| 响应式 | 原型窄屏未验收，本轮明确单栏列表→全屏详情→返回，属性下移、无横向挤压 |

已修正字段断言的DOM范围、列表/返回按钮的选择器歧义、创建空间测试等待选中名称的竞态、目录树前序排列、窄屏错误返回、说明对比度与失败/空状态混淆。
首屏文案对照的差异均由最新结构化优先要求或尚未实现能力解释；视觉语言和最新交互已对照验收，无遗留已知遮挡/横向溢出。
只验证Chromium及上述视口；未验证Safari/Firefox、真实解析/预览/下载、T27拖拽/批量/恢复UI或正式生产发布。
环境配置install_script/start_skill草稿已保存补入生产前端构建/启动步骤，未发布新快照；未修改网络规则、凭证或正常管理员。

## T27 验收 · 2026-10-17

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：174 passed；保留既有Starlette/httpx弃用提示。
- `npm run build --prefix web`：通过，生产静态资源构建完成。
- `JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium npm_config_cache=/workspace/.npm npm run test:e2e --prefix web`：8 passed，52.9s。Browser插件不可用，使用Playwright与系统Chromium。
- 新增5条真实浏览器流程：并发版本冲突与撤销保护；目录/标签/收藏/回收/恢复及移动端整理；真实内部拖放与OS文件上传/伪令牌拒绝；31份跨页固定快照且后续上传不混入；101份超限明确拒绝。使用临时SQLite、真实文件/HTTP/worker，未mock业务响应。
- 新增Python覆盖批量恢复/撤销/陈旧版本、已活动项跳过，以及父管道关闭的worker确认发送。无新迁移。
- 测试发现并修复窄屏样式误隐藏整理按钮、移动后详情消失留空状态、worker关闭时BrokenPipe；真实31项任务积压的浏览器等待设为30秒，不缩减业务流程。

视觉复核已对照`/tmp/juanzhan-reference.png`与最新`/tmp/juanzhan-t27-desktop.png`、`/tmp/juanzhan-t27-results.png`、`/tmp/juanzhan-t27-mobile.png`：暖白/墨绿配色、多栏比例、标题/图标/留白沿用；新增选择栏/标签/结果弹窗为真实功能所需，原型假正文不保留。1440/1024/390视口由套件覆盖，390px操作弹窗无水平溢出；主流程无应用pageerror。未验证Safari/Firefox。
尚未验收真实转换/OCR/检索/下载/原件预览、字段编辑UI与任务结果刷新恢复，不将当前通过视为完整产品验收。

T27容器验收：`DOCKER_CONFIG=/workspace/JuanZhan/.local/docker docker compose build archive`及`docker compose up -d --wait --no-build`通过，Archive/worker/Converter三容器健康。`python scripts/smoke_auth.py`通过隔离容器真实HTTP、批量回收/恢复及重启持久化；`python scripts/smoke.py`通过Web/CSP/静态资源、API就绪、Converter鉴权/空能力/501和worker心跳。

## T11 验收 · 2026-10-17

`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：202 passed（新增28项），仅既有Starlette/httpx弃用提示。
新增覆盖路径遍历/绝对路径/盘符/反斜杠/控制字符/空段/Unicode代理项、重复别名/坏配置、Unicode精确保留、真实sysfs只读与chmod目录拒绝、根/叶符号链接拒绝、离线与缺文件区分、鉴权HTTP及不泄露路径。
`DOCKER_CONFIG=/workspace/JuanZhan/.local/docker docker compose build archive`及`docker compose up -d --wait --no-build`通过，三容器健康；`python scripts/smoke.py`通过Web/CSP/API/Converter能力边界与worker心跳。
本轮未改前端，未重复浏览器套件；上一切片8项浏览器验收保留，不将其记为本轮新运行。

`python scripts/smoke_sources.py`通过：一次性容器中的真实只读/可写/嵌套可写bind，鉴权别名HTTP与SQLite；Unicode读取、根内/越界符号链接、路径遍历、FIFO/目录拒绝，内核写入返回EROFS。100轮失败探测无描述符泄漏；宿主替换已打开路径为越界符号链接后，读取仍绑定原inode。原件hash不变、无来源/条目/档案记录产生，测试容器和临时目录已清理。初次测试发现测试目录继承宿主umask导致容器无读取权，及写权限先于挂载只读检查；夹具显式设置读取/遍历与文件写权限后验证EROFS，未放宽应用检查。

## T12 验收 · 2026-10-17

`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：209 passed（新增7项），仅既有Starlette/httpx弃用提示。
新增真实SQLite/HTTP/worker覆盖：来源CSRF/别名/跨空间目标/重叠拒绝，列表详情；持久预扫描与活动请求合并、重启后读取；前缀%/_字面与目录段/分页；离线库存保留；离线有限重试恢复；过期租约围栏与幂等完成；终态失败与disabled来源拒绝。预扫描无档案/条目/Revision及成功导入标记。
Archive镜像构建及正常Compose升级通过，三个容器健康；`python scripts/smoke.py`通过Web/CSP/API/Converter边界及worker心跳。
本轮前端未改，未重复浏览器验收；原有8项浏览器结果仍属T27。首扫/增量/真实格式转换、忽略规则与来源UI未验收，不视为完整外部来源交付。

`python scripts/smoke_sources.py`已通过真实只读bind/SQLite/HTTP/worker：保存来源、CSRF、跨bind别名同根与父子根拒绝、预扫描活动合并、2份文件24字节/2项忽略的精确统计、嵌套可写挂载终态失败、Job与scan_runs结果一致、容器重启后会话/来源/结果保留。无档案/条目/Revision产生、原件hash不变、fixture卷和容器清理。
1,000份真实文件的元数据预扫描基线为0.032秒、进程峰值RSS 21,368 KiB（本开发机Linux容器；非大规模性能承诺），逐项数/深度的低限实验均以SOURCE_PREVIEW_LIMIT失败，未静默截断。默认上限100,000项/64层为可调整保护值，未声称验证10万文件吞吐。重启验收发现Docker临时端口可能变化，脚本已重新查询映射后检查就绪。
补充移除/遗留预扫描目标的队列验证：不存在scan_runs时handler明确INVALID_SOURCE_PREVIEW失败，不在claim阶段回滚造成队首阻塞。

## T13 验收 · 2026-10-17

新增7项Python验证首扫CSRF/模式边界、预扫描互斥/活动请求合并、真实worker空来源完成/重启重放、tree/flat同哈希独立登记与初始triage、目录/规范名冲突的整体回滚与修复重试、发布中租约过期连同parse Job回滚、匿名元数据上限失败与临时文件清理。SQL发布测试使用可信清单夹具；真实文件读取/hash/全链路由容器验收覆盖，未把清单夹具冒充真实NAS导入。
`python scripts/smoke_initial.py`初次通过真实只读bind/HTTP/SQLite/worker：tree的3份文件（含空文件）与2层目录（含空目录）、flat的2份文件、同hash不同路径各自建档；规范名冲突无部分记录，修复后成功；人工改名/移动与后续新文件不会被initial重放覆盖/导入。
额外1,000份真实文件的首扫/队列执行最终基线2.924秒（并行回归首次3.545秒；本开发机测量，不是大规模性能承诺）；共1007个Document/Entry/外部Revision、1007个审计/parse任务，托管对象/原件副本为零，FK检查通过，匿名清单退出无残留。容器重启后结果/会话/人工改名保留，原件hash保持不变。
共享遍历器改造后`python scripts/smoke_sources.py`回归通过，预扫描仍只统计，嵌套可写/链接拒绝、资源上限、重启和原件完整性验证保留；本轮1,000文件预扫描0.064秒、峰值RSS21608 KiB（当前开发机）。前端未改，未重复浏览器验收。

T13最终`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：216 passed，40.84秒，仅既有弃用提示。最终smoke_initial还验证宿主在文件被安全遍历器打开时改变字节，迭代继续前明确SOURCE_CHANGED，未接受过期观察；随后还原测试原件并确认hash。
`DOCKER_CONFIG=/workspace/JuanZhan/.local/docker docker compose build archive`与`docker compose up -d --wait --no-build`通过，三容器健康；`python scripts/smoke.py`验证Web/CSP/资源、API/Converter边界与worker心跳。OpenAPI0.4.14/48路径唯一键与本地引用检查通过。

## T14 验收 · 2026-10-17

`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：228 passed，46.45秒，仅既有Starlette/httpx弃用提示。新增11条增量用例及1条旧库升级用例；迁移数量断言同步为4，前三checksum与旧来源配置/完成时间保留，重复迁移及FK检查通过。
增量用例覆盖相同size/mtime但hash变化、人工值与旧解析保留、新文件needs_review/目标且无新目录、同inode/不同inode唯一hash重关联、重复hash即使inode相同也不匹配、两次缺失/恢复、失败清证据、根变化/无锚点拒绝、旧库可信锚点升级、过期租约整体回滚、真实挂载离线的Document投影与库存独立。
`python scripts/smoke_incremental.py`通过真实只读bind/HTTP/worker/SQLite：同大小/mtime内容更新，保留人工标题/目录/标签/收藏/已确认字段及旧ParseRun；唯一rename保ID，重复hash待匹配且不建重复Document；两次失联、恢复、不可挂载worker根失败后重新确认，以及另一只读空根SOURCE_ROOT_CHANGED不改库存。无外部写回或managed原件副本，重启结果保留。
`python scripts/smoke_initial.py`回归通过首扫tree/flat/冲突/重放/1000文件原子发布，新增根摘要未破坏首扫，当前资源基线3.504秒（本开发机并发验证，非性能承诺）。新迁移正常Compose升级三容器健康。
前端未改，未重复浏览器套件；自动调度、人工匹配写接口、排除规则/取消索引、来源UI、真实转换/检索/预览仍未验收。

T14最终镜像回归：`python scripts/smoke_incremental.py`再次通过，容器重启后执行新的增量仍接受原根基线，保持待匹配/已确认missing与人工版本；最后补充同来源缺失凭据校验后，11条增量针对性测试再次通过。`docker compose build archive`及`up -d --wait --no-build`通过，`python scripts/smoke.py`通过Web/CSP/资源、API/Converter能力边界和worker心跳。OpenAPI0.4.15/48路径唯一键与引用校验通过，无新依赖或云启动步骤。

## T15 验收 · 2026-10-17

新增取消索引/规则移除/扫描屏障与epoch过期、失败屏障释放、外部purge留规则与移除后重发现；新增purge确认/CSRF/版本/receipt、排队后恢复拒绝、共享与历史/回收引用保护、至少24小时宽限、孤儿两轮GC、登记共享锁阻止GC与合法键符号链接拒绝。
`python scripts/smoke_maintenance.py`真实只读bind/HTTP/worker/SQLite通过：取消索引后preview=0/ignored=1、增量不重导；外部purge仅删系统记录，源hash/字节保留；移除规则后新建不同Document。托管共享对象仍有引用不删，最后引用清除后宽限内保留，只快进一次性fixture候选时间后实际unlink；恢复先于排队purge时VERSION_CONFLICT，链接不跟随；重启后最小清理回执与恢复状态保留，FK检查通过。
未在正常数据卷执行purge/GC时间快进，未改正常管理员。派生物理GC/生产来源UI尚未验收，前端未改，不重复浏览器套件。

最终`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：238 passed，52.07秒（新增10项），仅既有弃用提示。过期异常GC候选不再阻断新孤儿后续任务，有针对性回归。最终镜像重新运行smoke_maintenance通过；Compose三容器升级健康，smoke.py通过Web/CSP/静态资源、API/Converter边界与worker心跳。OpenAPI0.4.16/48路径唯一键/本地引用校验通过。

## T28 验收 · 2026-10-17

环境：Linux云工作区、实际SQLite/文件/HTTP/独立worker，Chromium通过Playwright运行。Browser插件未提供（工具发现为空），采用仓库现有Playwright；无业务响应Mock。保留既有暖白/深绿参考，检查实际截图而非仅断言DOM。
目标流程：配置只读来源 → 预扫描 → tree/flat首次导入 → 分页/目录下钻与结构化详情返回 → 离线/失联/恢复 → 排除/移除规则。

| 检查 | 结果 |
|---|---|
| `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q` | 238 passed，58.89秒；仅既有Starlette/httpx弃用提示 |
| `npm run build --prefix web` | 通过；无新应用依赖 |
| `JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e --prefix web` | 原有8项通过，最终1.3分钟 |
| `JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium DOCKER_CONFIG=$PWD/.local/docker npm run test:e2e:sources --prefix web` | 新增1条完整来源场景通过，最终44.5秒 |
| Compose构建/升级与`python scripts/smoke.py` | 三容器健康；Web/CSP/资源、鉴权/Converter未实现边界及worker心跳通过 |
| 浏览器入口/显示/控制台 | URL/标题/真实内容正确，无Vite错误覆盖层/未捕获异常；唯一预期409为主动制造的档案版本冲突 |
| 响应式截图 | 1440×1000桌面、1024×768平板、390×844手机；平板/手机无页面横向溢出，实际截图已查看 |

来源场景用独立Docker只读bind和数据卷：33份可读文件/1份忽略文件，预扫描后Document仍为0；首扫33份真实登记，30项分页可访问后页中文相对目录，打开结构化档案后返回保持前缀。第二独立来源flat导入亦成功。离线通过移动测试目录模拟，库存保留、扫描按钮禁用，恢复同inode目录后继续；一次完整增量suspected_missing，下一次独立成功扫描missing，原件重现恢复available。
取消索引弹窗捕获版本后通过真实HTTP并发修改档案，确认返回VERSION_CONFLICT且未回收；重新读取确认后真实worker成功，字节读取前后相同。移除排除规则后回收档案仍在Trash，未伪恢复；重复hash新路径明确needs_match，没有假匹配入口。OS文件drop到来源明确拒绝且不上传，初始预扫描仍无Document。实际任务排在首扫产生的parse失败任务之后，验收等待真实队列完成（最多60秒），不跳过后台任务。最后补充真实GET延迟（放行原请求，不伪造响应）后切换导航，验证取消索引读取被中止、返回来源不弹出过期确认；关联详情同时复用工作区整理刷新信号。

夹具首次运行揭示云环境umask 077导致非特权容器不可读，已对仅测试目录/文件显式设置755/644，内核只读仍保留；浏览器option禁用断言改为直接验证disabled属性。两处均在修复后重跑通过。fixture容器/卷/目录在退出后清理，正常数据卷/管理员未修改。Python后端/迁移/OpenAPI未改，本轮没有重复T11～T15全部专项容器脚本，保留其阶段证据。

截图证据（本机/tmp，不入Git）：`/tmp/juanzhan-t28-sources.png`桌面库存，`/tmp/juanzhan-t28-wizard.png`配置确认，`/tmp/juanzhan-t28-offline.png`离线历史库存，`/tmp/juanzhan-t28-mobile.png`手机歧义状态。当前工作区无Browser插件，后续若安装可优先使用；此次真实浏览器证据已完成。
边界：只展示已登记文件及其路径层次，不宣称完整物理目录枚举；没有自动扫描、人工匹配写入口、来源配置编辑、任务列表/刷新恢复、正文/原件预览或真实转换能力。来源回执仅当前空间页面保留。下一阶段T19，不是最终产品验收。

## T19 验收 · 2026-10-17

`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：253 passed，51.35秒（比T28新增15项），仅既有Starlette/httpx弃用提示。Converter专项+foundation为23项通过；基础旧501/空能力断言已改为真实TXT能力及非法multipart拒绝，未删除验收要求。
专项覆盖真实受限子进程/SQLite/磁盘/HTTP：UTF-8 BOM/中文/emoji/换行与精确码点定位，规范结果与null置信度，产物大小/hash/下载头及DELETE后404；PDF/HTML/二进制unsupported；全路径Token、未知/重复字段、路径/ID/布尔/OCR语言拒绝、大小与不完整multipart；相同parse_run_id同字节复用、冲突409、容量429与TTL回收；墙钟终止、块/输出额度失败、UTF-8后半段非法编码失败；同spool排他锁、queued重启恢复与running安全失败；注入发布/存储中断后，单runner把遗留running置failed并完成后续真实任务，尝试数仍1，不永久占据队首。内核RLIMIT保留，输出额度在写入前主动拒绝。
客户端通过真实uvicorn/TCP验证chunked multipart、规范结果/Revision/ParseRun身份、下载hash校验和清理；错误hash不暴露暂存流。另有明确标注的fake contract peer只验证恶意JSON重复键/NaN/嵌套/超大返回、非法任务ID/资产引用与重定向拒绝，不把fake结果用于转换成功验收。
首次检查暴露两处实现问题并已修复后重跑：子进程依赖调用者PYTHONPATH导致普通pytest找不到包，改为服务文件确定的包路径且不继承敏感环境；输出超限曾落为通用子进程失败，改为写前明确RESULT_LIMIT。没有放宽资源保护或禁用断言。

`DOCKER_CONFIG=$PWD/.local/docker python scripts/smoke_converter.py`通过：独立网络/Archive与Converter容器/临时数据卷，真实HTTP管理员/空间/原件上传及SQLite登记；从Archive容器使用实际ManagedStore原件和内部客户端，跨HTTP提交Job/轮询/取规范JSON/核验产物/主动清理及404，PDF明确unsupported。Converter只有128MiB tmpfs，没有Archive卷；原件hash、标题和current_parse_run_id不变，parse_runs仍0/FK正常。随机测试凭证仅进程环境/安全stdin传递，不输出或保存，夹具容器/卷/网络已清理。
`DOCKER_CONFIG=$PWD/.local/docker docker compose build archive`及`docker compose up -d --wait --no-build`通过，最终三个容器healthy；新`smoke.py`通过Web/CSP/资源、鉴权、真实TXT能力/非法multipart边界及worker心跳。额外一次性容器以默认128MiB tmpfs/256MiB子进程地址空间，处理恰好4MiB含emoji的真实UTF-8文件，完成规范结果/产物hash验证及清理；不承诺大规模性能。无新依赖、业务迁移、前端改动；本轮未重复浏览器套件，9项浏览器结果仍属T28。Converter OpenAPI0.4.1/6路径及Archive0.4.16/48路径唯一键/本地引用检查通过，已应用5次迁移未变。

边界：只证明最小UTF-8 TXT及独立传输协议，不是六格式/OCR/预览或产品正文交付。单进程同spool重启已验证；Docker tmpfs重建丢失任务是允许边界，本轮未执行该故障场景，不能宣称远端ID跨容器重启持久。Archive parse handler、ParseRun/DerivedAsset/ContentBlock事务入库与历史正文保留仍在T22；上传解析任务仍明确未实现，不因Converter可用伪报业务成功。下个任务T20。

## T20 验收 · 2026-10-17

最终`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：279 passed，81.02秒，仅既有Starlette/httpx弃用提示。新增28项六格式测试，T19中PDF/HTML的旧unsupported断言被真实格式成功/失败用例替代（净增26项）；未把测试改成伪解析JSON或关闭资源保护。
真实二进制文件通过受限子进程、私有SQLite、鉴权HTTP和规范模型验证：DOCX标题/样式列表/显式表头/表格/实际属性，MD CommonMark和表格，HTML隐藏/活动区域过滤与实际meta，TXT UTF-8/BOM UTF-16/32及精确字符范围，EPUB按spine顺序/前缀XHTML/书目属性且无伪页数，PDF真实页码、属性、空文本OCR提示和密码失败。每种格式核验plain_text与Markdown资产大小/hash及清理，置信度null。DOCX false表头和numId=0不伪造表头/列表。
安全覆盖具有实际DOCX包身份的越界/反斜线路径、ZIP膨胀/压缩比/成员额度、符号链接/重复成员、XML实体/DTD；EPUB章节远程/越界引用拒绝，HTML本地HTTP资源探针收到0请求；PDF页数和Flate解码内容流额度生效，活动Markdown不输出原HTML/脚本且生成语法被转义。真实中文PDF的Unicode映射由pypdf及本机独立`pdftotext /tmp/juanzhan-t20-cjk.pdf -`均读出“中文资料”；pdftotext不是生产依赖。
初始回归发现TXT段落正则的$在末尾换行前匹配导致定位拆段，改用严格EOF；Markdown里不被识别为链接的URL属于普通文本，验收改为检查生成Markdown不形成活动链接，不无故删除原文字面值。代码检查发现pypdf ContentStream可为空字典但仍含解码数据，改为is not None并加入真实Flate流额度回归。上述修正及DOCX布尔语义均经最终全量验证。

`DOCKER_CONFIG=$PWD/.local/docker UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen python scripts/smoke_formats.py`通过：独立Archive/Converter容器、网络/数据卷，六种实物文件真实上传并在Archive登记；Archive内部客户端跨HTTP提交/轮询/取规范blocks与定位/候选、下载两种产物核验并DELETE，6份原件hash/标题/current_parse_run_id不变，parse_runs仍0且FK正常。样本生成器只生成文件格式本身，不生成解析输出；SQLite/文件/HTTP链路均为实际实现。夹具退出后清理，不触碰正常数据卷/管理员。
原`scripts/smoke_converter.py`回归通过，能力更新为六格式，unsupported改用真正未知二进制；未继续把已支持PDF/HTML当unsupported。`uv add`锁定新依赖，随后哈希校验wheelhouse下载、Docker离线安装/构建成功，正常Compose三个容器升级healthy；`smoke.py`通过Web/CSP/资源、鉴权、六格式能力/非法multipart及worker心跳。依赖与许可见THIRD-PARTY，无系统工具/模型新依赖。
Converter OpenAPI0.4.2/6路径、Archive0.4.16/48路径唯一键/本地引用检查通过，5个已应用SQL迁移未改。前端未变，本轮不重复9项T28浏览器验收；安装/启动仍使用原冻结依赖+wheelhouse+Compose通用步骤，无新凭证需求。

边界：基础文本/语义结构已验收，不承诺DOCX复杂布局/浮动图像/页眉页脚/脚注、PDF多栏/表格顺序、HTML外部CSS可见性或所有旧EPUB兼容；降级警告及严格编码/XML范围见CONVERTER。扫描PDF无文本不等于OCR完成，OCR/受限原件预览仍T21；业务ParseRun/派生物持久化和旧成功正文仍T22。没有测试或宣称10万文件/大文档性能、跨平台发布或最终产品完成。


## T21 验收 · 2026-10-17

最终`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：297 passed，81.56秒，比T20新增18项；无跳过/禁用，只有既有Starlette/httpx弃用提示。新增验收使用Pillow+实际Noto CJK字体绘制中英文光栅，PDF为嵌入扫描图片且pypdf确认没有隐藏文本层，未伪造OCR输出。

真实子进程/文件/私有SQLite/鉴权HTTP覆盖PNG/JPEG/TIFF/扫描PDF识别与PNG缩略图，中文“真实中文档案/测试识别”、英文实际文字、真实页/帧定位及引擎均值置信度；混合PDF原文本层保留且只有缺文本第二页OCR。关闭OCR/关闭预览、不需OCR的文本层、空白识别提示、多帧TIFF缩略图截断，像素/OCR页数额度失败，OCR请求墙钟终止和清理、破损图片失败、密码PDF在预览开启时仍有准确错误。服务OCR关闭、缺失/损坏模型、仅eng模型能力、未安装语言拒绝、重复/未知语言及管理布尔配置均有回归。缩略图PNG格式、最大边1024、去EXIF与实际下载SHA256核对，输入hash保持。

最终镜像内真实网络链路`uv run --frozen python scripts/smoke_formats.py --ocr`通过4种扫描实物（中文PNG、英文JPEG/TIFF/PDF）：独立Archive/Converter/网络/随机管理员/数据卷，真实上传归档并从Archive内部客户端提交OCR、取规范结果/缩略图、下载hash校验/清理。每份原件、标题和current_parse_run_id不变，parse_runs仍0且FK正常。无业务正文持久化的事实也被断言，不能据OCR成功声称T22已交付。原六格式smoke_formats.py及协议smoke_converter.py同样通过，退出清理仅本次夹具。

完整安装步骤`.local/cloud-install.sh`已实际执行成功：冻结uv、模型校验、哈希wheelhouse、npm ci/build、离线Docker构建；全新临时目录额外运行模型下载脚本再重复运行，TLS/固定大小/SHA256和复用通过。首次容器测试发现umask077导致模型清单/模型不可由非root读取，已改Docker COPY权限并重建重测。PDFium页/bitmap不支持上下文协议的问题已改为ExitStack显式close并通过回归。正常Compose重建后3服务healthy，smoke.py验证Web/CSP/已编译资源、鉴权、能力和worker心跳。正常.env/管理员/数据卷及5条不可变迁移保留。

Converter OpenAPI0.4.3/6路径、Archive0.4.16/48路径成功解析并通过既有规格校验。真实中文扫描PDF缩略图`/tmp/juanzhan-t21-preview.png`已目视检查，证据在本机不入Git。前端源代码未变，本轮不重复浏览器套件；只验证构建和正常Web冒烟。保存可复用环境install_script/start_skill草稿，含模型准备/校验、冻结安装与重启健康检查；草稿保存不等于发布或新任务恢复验证。

边界：仅Linux x86_64容器实测，不承诺所有扫描质量、倾斜手写、复杂布局/大文件性能/其他平台。OCR置信度为引擎均值而非校准概率，必须人工复核。预览仅前若干页PNG缩略图，不是完整PDF/Office排版或用户预览API；T22/T23/T29/T32及T34发行许可清单待后续完成。


## T22 验收 · 2026-10-17

最终全量`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：317 passed，126.27秒（较T21新增20项），无跳过/禁用；只有既有Starlette/httpx弃用提示。覆盖每次attempt独立排延迟GC，以及数据库拒绝跨档案/跨解析关联。没有仅靠Mock宣称转换成功。

新增真实Archive HTTP上传→持久Jobs/worker子进程→uvicorn TCP Converter→规范结果/原件和产物校验→SQLite正文/候选/资产/成功指针，六种实物文件均通过。规范完整JSON、文本、Markdown和缩略图通过安全store实际读取/hash核验，业务标题/标签/整理状态/document_version不因解析改变。实际OCR多帧TIFF保留真实1/2帧定位，两帧相同PNG共享字节但资产顺序仍完整。

失败/不支持保留旧成功正文，跨Revision与同Revision最近失败均显示stale；未知类型归档不丢原件，unsupported不晋升。租约过期关闭旧尝试、有限重试新建独立run；旧token不能提交。新请求/新Revision/回收三个围栏均用真实转换结果验证；额外验证旧请求较晚开始/返回也不覆盖新成功的状态投影。故障注入在真实发布事务写完后、提交前抛出IO错误，块/候选/资产/指针全部回滚，已落文件作为孤儿保留；重试真实转换可复用字节并成功。损坏托管原件明确ORIGINAL_INTEGRITY且无部分正文。派生GC先发现候选，宽限24h后删真正孤儿，同时所有历史成功资产仍可实际打开。升级从旧5迁移回填请求映射，queued/failed原状态不变、无擅自ParseRun/重放，旧checksum保留且重复迁移成功。

容器`scripts/smoke_formats.py --persist`（需uv run --frozen python）通过6格式自动入库；`--persist --ocr`通过真实中英文PNG/JPEG/TIFF/扫描PDF入库；`--persist --external`通过真实来源HTTP配置/首扫→内核只读bind→worker解析入库。外部源同大小字节被宿主夹具故意改变后，SOURCE_REVISION_CHANGED明确拒绝，旧成功指针和缓存保留且stale=true，夹具恢复原字节后hash一致；Archive未写外部源。Converter从未获得来源/业务卷。每组独立容器/网络/卷/随机管理员，退出清理仅本次夹具。

独立Archive `smoke_auth.py`真实认证/CSRF/token/重启/上传/文件管理/批量/七类型字段/采纳回归通过；该夹具故意无Converter配置，断言由旧HANDLER_NOT_AVAILABLE更新为真实CONVERTER_NOT_CONFIGURED。正常Compose重建后自动执行第6/7迁移，3服务healthy，`smoke.py`验证Web/CSP/已编译资产、鉴权、转换能力和worker心跳。前5迁移、正常.env/管理员/数据卷保留。前端源码未改，不重复浏览器交互套件。

Archive OpenAPI0.4.17/48路径，Converter0.4.3/6路径；现有规格解析/引用与迁移检查通过。可复用环境只更新start_skill草稿，加入自动持久化与上述验收，install_script沿用；保存草稿不等于发布或新任务恢复验证。没有测试/声称跨平台、10万文件性能、生产发布或备份恢复完成。

边界：正文/历史/候选公开GET、重解析入口仍T23，中文FTS和搜索T24/T25，结构化阅读T29、用户原件下载/预览及备份T32仍未完成。远端主动DELETE尽力执行，崩溃/请求仍活动时靠Converter执行期限+TTL兜底；历史失败不会因升级自动重排。

补充数据库硬约束验收：不同档案的ParseRun/attempt或资产顺序关联在INSERT/UPDATE时被SQLite拒绝，不只依赖调用方判断；0007为独立增量迁移，0006应用后未改checksum。


## T23 验收 · 2026-10-18

全量`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`：330 passed，145.25秒（比T22新增13项），无跳过/禁用，仅既有Starlette/httpx弃用提示。补齐parse_run_id空值/最大长度查询约束后，受影响content专项13项再次全部通过（25.66秒）。无依赖、迁移或前端源码变更。

专项使用真实上传/文件/Archive SQLite/worker子进程/真实uvicorn TCP Converter/派生store：六格式三种正文GET、默认blocks及单项分页、历史顺序/当前标记、candidate_count与无远端任务引用；真实DOCX候选值/来源读取、人工确认字段在解析前后保留、显式采纳写来源、重解析保留字段、历史候选不能冒充当前候选。跨档案Run查询404，失败新Revision仍返回旧正文并stale；无成功缓存404、未完成Run409。派生文件实际篡改/删除时text503且不泄露路径，DB中的blocks仍可读取，不用重新解析原件掩盖损坏。

全部新GET/POST未认证401，Cookie写操作缺CSRF403、Bearer可写，业务版本/Revision冲突409，未知字段/严格布尔/重复语言/语言与OCR开关冲突422；已有成功未force拒绝，其他活动任务拒绝，同request_id同选项复用、不同选项409，完成后重发也不创建额外Run。不同请求并发仅一项受理，另一项409。分页/格式/RunID边界拒绝，降低实际响应预算的故障测试验证SQLite先验页面预算及413，不静默截断。

Docker实际构建与三组跨容器链路通过：smoke_formats.py --persist（六格式）、--persist --ocr（真实中英文PNG/JPEG/TIFF/扫描PDF）、--persist --external（真实内核只读来源HTTP配置/首扫）。脚本现在从客户端经正式HTTP读取三格式正文/历史/候选，再POST版本/request_id保护的重解析并重发同请求，真实worker完成后历史增加且旧Run保留。外部同大小字节变化拒绝，旧缓存仍可经公开content读取。附加第二Archive实例共享仅业务卷、源别名指向实际不存在目录，来源确实不可访问而非Mock离线标志；同一认证会话仍读到相同已保存正文，availability=source_offline、stale=true且无后端绝对路径。

所有容器夹具独立随机管理员/数据卷/网络，退出只清理本次资源；正常.env/管理员/数据卷保留。正常Compose重建并通过smoke.py的Web/CSP/已编译资源、鉴权、能力及worker心跳。7条迁移保持，无新增安装步骤/凭证/环境配置变更；不重复前端浏览器套件。Archive OpenAPI0.4.18/49路径、Converter0.4.3/6路径的唯一键/引用与既有契约测试通过；YAML只重写相关路径和schema，原未修改定义语义保留。

边界：本轮JSON API不直接渲染HTML、提供二进制下载或读取外部原件；源可用性unknown独立表达，不能当原件已验证。公开查询不是阅读UI，T29待接；中文FTS/搜索T24/T25、批量reprocess/set_metadata、原件下载/预览/备份T32和正式发布仍未交付。请求202只代表受理，模型/转换能力最终由后台检查；失败仍保留旧成功正文。


## T24 验证 · 2026-10-18

全量UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q：344 passed，177.17秒，无跳过/禁用；仅既有Starlette/httpx弃用警告。新增test_indexing.py 14项，专项与Job合计30 passed（31.52秒），foundation 8 passed。使用真实SQLite/文件/HTTP Converter/worker子进程，覆盖中文双字/繁简/全半角/英文数字、字段边界、title/标签/可搜索字段变更、回收恢复/永久删除、幂等重建修复重复行、并发调度、旧词元版本恢复、Job租约丢失和较新编辑围栏、真实发布后故障回滚、资源限制与显式恢复。失败新Revision保持旧成功正文及索引；公开q仍501有断言。

实际Docker哈希离线wheel构建通过。两组隔离容器验收均通过：

```sh
uv run --frozen python scripts/smoke_formats.py --persist --index --daemon --external
uv run --frozen python scripts/smoke_formats.py --persist --index --ocr
```

六格式及真实OCR经上传/只读来源→Converter→缓存入库→FTS；逐档案校验唯一FTS行、状态版本/代次/ParseRun，实际MATCH查询繁简中文双字和英文数字。全量显式重建无重复，HTTP修改标题仅一档案增量。持续worker实际发现另一HTTP编辑并自动发布FTS。真实只读来源变字节拒绝且旧缓存保留；第二Archive无可用来源挂载，仍能读鉴权缓存正文与持久FTS行。不是公开搜索API验收。

所有夹具使用独立网络/卷/随机凭证且已清理；不接触正常管理员/数据。未改前端，未重复浏览器套件；没有大语料性能或最终产品完成承诺。OpenAPI保持Archive0.4.18/49路径、Converter0.4.3/6路径。

正常Compose保留.env/管理员/数据卷，以新镜像up --wait --no-build成功；smoke.py验证Web/CSP/编译资源、Archive就绪、Converter鉴权/六格式能力和worker心跳，三个容器healthy。实际数据库8条迁移、foreign_key_check为0；正常库当前0档案，索引内容证明来自上述隔离实物夹具。可复用start_skill已更新为不硬编码迁移数量并加入FTS验收/维护流程，安装脚本和网络/凭证保持；草稿保存不等于发布或新任务恢复已验证。

## T25 验证 · 2026-10-18

全量uv run --frozen pytest -q：389 passed，198.97秒，无跳过/禁用，仅既有Starlette/httpx弃用警告。其后补齐旧正文失败/相关性排序及扫描PDF未请求OCR三个边界，最终test_search.py专项48 passed（26.22秒），含最后的limited_content/逐项content_incomplete字段和实时状态观察一致性改动；不把新增专项重复计为全量已跑392项。

专项经真实鉴权HTTP/SQLite/托管字节/Converter TCP与worker子进程：繁简中文/英文数字正文检索，GET/POST一致、字面FTS运算符不执行；联合元数据、目录后代、类型范围、标签any/all、固定快照稳定分页、relevance双向及默认排序。七类型eq/in、精确Decimal闭区间/整数最大值/有效日期、false与缺值区别、contains的%_字面匹配；浮点Decimal/精度溢出/布尔混类型/无效日期/倒置区间/不支持运算符422。实际EXPLAIN QUERY PLAN确认decimal/integer/date使用既有类型索引。

新编辑未索引时旧命中标pending；终止索引失败旧命中标failed；零命中仍有范围missing/processing/incomplete。新Revision真实解析失败保留旧正文可搜且content_stale、stale_content和failed_processing为真；真实扫描PDF未请求OCR时虽completed/current仍limited_content/content_incomplete。当前空间、回收默认排除/显式only、非filterable/停用/未知字段与跨空间引用拒绝。鉴权401、Cookie缺CSRF403、Bearer查询通过；首页summary真实聚合/空间/回收计数与no-store验证。

实际降低请求/响应预算返回413，真实SQL进度预算超限503，降低实时状态观察上限返回SEARCH_STATUS_LIMIT，不静默返回部分结果。输入长度、操作数列表、排序白名单/重复排序、严格布尔与分页、未知键均拒绝；SQLite/路径/输入值不泄露。请求流1MiB、响应16MiB及先验页面字节预算，查询3秒SQLite进度预算；状态观察最多5000档案，需要先收窄筛选。没有大库性能承诺或外部文件系统原子快照保证。

OpenAPI0.4.19/49路径及Converter0.4.3/6路径通过唯一YAML键和全部本地引用验证；原有未涉及schema/path语义比较保持，field-definitions仅说明searchable/filterable生效。8条迁移不改，无新应用依赖/模型/凭证/环境变量。生产Web未改，未重复浏览器套件；下一T29阅读与T30搜索界面，不能据API测试声称完整产品完成。

最终镜像真实Docker构建及两组容器验收退出0：smoke_formats.py --persist --index --daemon --external与--persist --index --ocr。均经公开鉴权GET/POST查中文正文/相关性、范围索引完整性和真实summary；HTTP标题编辑后的搜索结果正确。六格式只读来源首扫、自动解析、持续worker脏队列及重建无重复保留，外部同大小变字节拒绝后仍可读旧缓存。第二Archive完全无来源挂载，经正式POST FTS+availability_status=source_offline仍搜到旧正文，未用Mock离线标志。

正常Compose保留.env/管理员/卷，以新镜像up --wait --no-build成功；smoke.py验证Web/CSP/编译资源、Archive就绪、Converter鉴权/六格式能力及worker心跳，三个容器healthy。实际正常库8迁移、foreign_key_check=0、0档案；正文检索证据来自隔离实物夹具，夹具均已清理。安装/启动流程未改变，无需更新已有环境草稿，也未声称发布或新任务恢复完成。

## T29 生产正文阅读验证 · 2026-10-18

Browser plugin not available，使用仓库Playwright及现有/usr/bin/chromium，无新增浏览器依赖。目标路径：真实登录/上传→详情正文与表格→候选显式选字段确认→历史切换→手机返回原列表。npm run build --prefix web通过；本轮未运行搜索专项或全量Python，正文与Web后端相关测试15 passed（31.32秒），仅既有Starlette/httpx弃用警告，无跳过/禁用。

独立reading-server.py使用临时业务SQLite/managed/derived及真实TCP Converter/worker，随机服务Token/独立管理员、不接正常数据卷；reading专项最终3 passed（17.1秒）。真实DOCX属性产生候选，先人工并发修改触发409、证明未写业务字段，再刷新后显式采纳，确认人工字段origin/值更新且档案标题未改变；历史旧Run不能采纳，返回当前结果恢复。实际DOCX标题/列表/表格单元格可读，Markdown只作为源文本；45段真实TXT分页20/20/5，切纯文本后回结构块重置第一页，img/script/iframe/a元素不产生。损坏PDF真实解析failed，不虚造正文，业务字段仍显示；失效会话刷新回登录。

Chromium 1440×1000与390×844：页面身份/非空/无框架overlay、页面异常与控制台检查通过（预期409版本冲突单独核对），DOM和截图证明桌面/手机正文可读且无横向溢出，返回列表保持父级位置。截图在/tmp/juanzhan-t29-desktop.png及/tmp/juanzhan-t29-mobile.png；截图人工核对了标题、正文/表格、来源折叠信息、刷新入口和手机工具栏。报告/截图/日志均不入库。

验证中修复两处读取边界：按完整路径隔离usePage结果，格式切换首帧不把旧块数组作为字符串渲染；没有成功ParseRun时不请求必然404的正文，避免重复控制台错误，保留真实失败/未处理提示。既有过期会话测试允许后台详情读已提前收到401返回登录，仍断言实际登录页和会话过期提示，不忽略鉴权失败。

无后端/迁移/依赖或HTTP规范变更（Archive0.4.19/49路径、Converter0.4.3/6路径、8迁移）。未演练超大正文/十页历史/OCR浏览器视觉；底层内容/转换器边界沿用既有后端测试，不将本轮浏览器测试当全格式/完整产品验收。原件预览下载T32、任务/重解析UI T31及生产搜索UI T30仍待开发。


既有库/整理浏览器回归最终8 passed（1.1分钟），真实只读来源向导/首扫/tree-flat/分页/失联/排除回归1 passed（1.1分钟）；没有修改这些功能的业务断言来掩盖失败。最初无正文读取产生404已通过产品代码修复；登出测试先后收到401的竞态仅调整等待方式，最终仍验证真实过期提示和拒绝访问。

最终Docker构建、正常Compose up --wait --no-build及smoke.py通过（Web/CSP/新编译资源、Archive/Converter鉴权/能力、worker心跳）；三个服务healthy，实际8迁移及foreign_key_check=0，保留.env/管理员/正常数据卷。来源夹具退出后自动清理自身容器/卷/目录。无安装或服务启动步骤变化，未另改环境草稿，未声称发布/新任务恢复验证。

最终阅读复验不再过滤404控制台错误，只单独识别并发版本冲突测试预期的409；3项全部通过，无其他页面异常/控制台错误。新增12项浏览器验证计数为阅读3+既有库/整理8+来源1，未将其与15项后端测试混作同一套全量运行。

## T30 生产搜索验证 · 2026-10-18

Browser plugin not available，使用现有Playwright/Chromium，不增加依赖。目标流程：真实上传/解析/FTS→提交关键词与组合过滤→重载/后退恢复→固定批量范围→手机详情返回。npm run build --prefix web及Docker构建通过，无HTTP/迁移/锁文件变化；Archive0.4.19/49路径、Converter0.4.3/6路径及8迁移保持。

搜索专项首轮最终4 passed（30.1秒）：独立临时Archive/SQLite/managed/derived、真实TCP Converter、真实worker和T24索引调度。覆盖繁简中文/英文数字、草稿不自动查询、相关性、标签any/all、多类型OR、Decimal闭区间/boolean false/业务日期联合过滤、URL重载/浏览器后退及精确批量快照。其余integer/date/text/long_text/single_select控制通过真实业务字段写入/HTTP结果核对；单选标签传稳定ID，超安全整数明确拒绝且URL不变。真实无OCR扫描PDF使零命中显示“暂未找到匹配档案”，纯文本完整范围则“没有匹配的档案”；真实断网显示独立读取错误，恢复后可重试。非法URL明确提示后回默认范围，无框架覆盖层或页面异常。

稳定网络环境复验：既有库/整理8 passed（1.1分钟）、阅读3 passed（14.0秒）；本轮来源专项1 passed（1.3分钟）。搜索/Web后端相关50 passed（29.64秒），无跳过/禁用，仅既有Starlette/httpx弃用警告。未重复392项全量Python，浏览器与后端计数分别记录。

复验发现并修复：同空间重复选择不再清空已加载结果，首个查询等待空间验证；页面过期自动修正用replace避免后退循环。新增搜索标签与操作弹窗标签同名，既有整理测试改为定位实际“档案操作”对话框，业务断言保持。一次并行来源Docker网络创建导致Chromium ERR_NETWORK_CHANGED；未过滤网络错误或关闭断言，来源结束后顺序运行的库/阅读套件全部通过。共享8767的套件必须顺序，来源虽用8768，其Docker网络变化也不应与浏览器控制台健康验证并行。

桌面1440×1000、手机390×844截图与DOM验证结果数量/查询输入/不全提示和返回列表，无横向溢出；页面身份/非空/框架覆盖层/控制台/交互均核对。截图在/tmp/juanzhan-t30-desktop.png、/tmp/juanzhan-t30-mobile.png，不入库。UI最多8字段、整数只安全范围；未验超大语料性能、非Chromium浏览器及全部组合排列，不把索引完成视为OCR/原件内容语义完全正确。

正常Compose三服务healthy、smoke.py验证Web/CSP/编译资源、Archive、Converter鉴权/能力和worker心跳。容器与工作区前端JS/CSS的SHA-256逐项相同；不重复构建相同产物。正常.env/管理员/卷保留，实际8迁移且foreign_key_check=0。临时夹具只清理自身资源；安装/启动步骤无变化，不另改环境草稿、不声称已发布。

稳定网络环境最终再验搜索4 passed（25.3秒），重新生成并人工核对桌面/手机截图；无额外控制台或页面错误。浏览器用例分别为搜索4+库/整理8+阅读3+来源1，共16项；与50项后端相关测试分开计数。临时目录清理后重新验证了smoke.py、8迁移/零外键错误及容器/工作区前端资产SHA-256一致。

## T31 · 2026-10-18

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest tests/test_jobs.py tests/test_content.py tests/test_web.py -q`：32 passed；列表摘要优化后再跑test_jobs为17 passed（不是新增17项）。覆盖真实SQLite/HTTP、认证、分页边界/状态过滤、结果/私密字段不泄露、重试预算与资格及既有正文保护。
- `npm run build --prefix web`：最终构建通过；OpenAPI解析/旧49路径语义一致及除Job外旧schema一致、50路径/0.4.20校验通过；git diff --check通过。
- Browser plugin not available；使用现有Playwright及`JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium`，未安装浏览器依赖。`npm run test:e2e`：8 passed；`npm run test:e2e:jobs`：最终2 passed。真实临时Archive/SQLite/文件/TCP Converter/worker，DOCX上传及显式重解析成功、勾选确认/OCR默认关与语言选择、任务编号重载找回、状态筛选与无任务、损坏PDF实际解析失败/无终态重试、原件Revision保留。最初固定任务总数断言不符合真实GC附带任务，改用真实受理ID查询后通过，未伪造业务成功。
- 1440×1000及390×844截图实看；页面标题/URL、非空、无Vite覆盖层、无页面/控制台错误、手机无横向溢出均通过。任务自动跟踪最多两分钟；手机选中详情置于列表前。截图`/tmp/juanzhan-t31-desktop.png`、`/tmp/juanzhan-t31-mobile.png`。
- 最终镜像构建、保留卷的Compose up --wait --no-build及scripts/smoke.py通过：Web/CSP/真实静态资源、Archive健康、Converter鉴权/六格式/OCR能力和multipart边界、worker心跳。未改.env/管理员/既有迁移，无需新云配置。
- 本轮未重跑来源/搜索/阅读专用浏览器套件或新增OCR识别质量验收；可重试写入与预算由既有真实后端HTTP测试验证，浏览器验证终态不可重试。来源扫描/批量任务深层逐项结果沿用既有后端，不宣称本轮全部格式/来源已重验。可选安装Browser插件便于后续诊断，不影响本轮完成。

## T32 · 2026-10-18

- `UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest tests/test_backup.py tests/test_files.py tests/test_content.py tests/test_web.py -q`：28 passed；最终备份清单/中断标记与启动守护调整后再跑backup/files为13 passed（同一批子集，不另加测试数）。真实SQLite/文件/TCP Converter/HTTP：下载附件与字节匹配、未授权/错Revision/坏字节拒绝、当前PNG与跨档案/过期/损坏隔离；实际只读sysfs字节通过共享登记服务接入，下载核验、来源离线/可写挂载/路径越界/哈希变化均拒绝，不宣称sysfs无扩展名被扫描导入成功。
- 真实备份恢复演练：已提交WAL数据库、托管原件/派生资产、正文及中文FTS在独立新目录恢复后可用；所有已完成记录不重跑，已claim任务旧租约失效且累计次数保持，原库租约仍running未被改写。验证已有目标拒绝、锁忙/缺原件失败、不完整/损坏/软链/遍历包拒绝与失败新目录清理；真实CLI子进程create/restore及重放拒绝通过，根700/DB600。RESTORE_IN_PROGRESS阻止Archive启动，worker/管理员初始化同用Settings.prepare_archive保护。
- Browser plugin not available；使用已有Playwright及`JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium`，未新增依赖。默认套件首轮7 passed/1 failed（旧“尚未开放”占位断言），按真实新空预览行为更新且保留MIME信息后原失败用例单独重跑1 passed，合计默认8项通过；新增`npm run test:e2e:files`最终2 passed。真实PDF预览自然尺寸、下载事件/中文文件名及下载字节与原上传完全一致、关闭回结构化详情、手机无横向溢出；HTML恶意script/远端img仅可下载，弹窗无iframe/object/embed/script，不执行脚本且没有远端请求。
- 1440×1000 / 390×844最终截图实看：`/tmp/juanzhan-t32-desktop.png`、`/tmp/juanzhan-t32-mobile.png`。标题/精确本地URL、非空、无框架覆盖层、页面与控制台无相关错误、真实交互均通过。
- 最终Vite生产构建通过；Archive OpenAPI0.4.21/52路径可解析，既有download之外所有旧路径与所有components语义保持；git diff --check通过。Compose离线wheelhouse镜像重建、保留原卷up --wait --no-build、scripts/smoke.py通过（Web/CSP/静态资源、Archive健康、Converter鉴权/格式/OCR能力/multipart边界、worker心跳）。原.env/管理员/数据卷/8条迁移未改变，未恢复覆盖现有实例。
- 本轮未重跑专用来源/阅读/搜索/任务浏览器套件、完整格式/OCR质量及并发大文件/断电测试；下一T33做整体验收与故障注入。预览是有限PNG缩略图，非完整原生PDF阅读器。浏览器下载64MiB/HTTP1GiB，不提供Range/历史原件。管理员备份不含外部原件/.env/模型/镜像，未实现Web恢复、加密签名、远端调度或真实业务数据卷切换。可以安装Browser插件改善后续交互诊断，不是本次依赖。

## T33 · 2026-10-18

本次验收证据以[ACCEPTANCE](ACCEPTANCE.md)及`scripts/acceptance-cases.json`的UX-01～14/META-01～16共30条映射为准；复用实际业务测试，不为凑数量复制30份镜像测试。

- 首轮未新增用例的全量`uv run --frozen pytest -q --junitxml=/tmp/juanzhan-t33-python.xml`：406 passed、0 failed/skip，201.64s。新增两条跨功能后通过真实入口`scripts/acceptance.py --phase backend --output /tmp/juanzhan-t33-backend`再次全量：408 passed、0 failed/skip，240.86s；随后补充真实OCR排队/人工合同编号保护用例单独运行1 passed到`/tmp/juanzhan-t33-ocr/backend.xml`。当前409个参数化后端测试全部有本次通过证据（408全量+1补验，不把重复回归相加或虚称409项同一次全量）。只有既有Starlette/httpx弃用警告，未修改锁定依赖绕过。
- 新`tests/test_acceptance.py`实际连接到TCP Converter、真实SQLite与存储：先形成成功正文，再对新Revision制造真实端口连接拒绝，确认同Job尝试1/3且可重试、人工字段/标签/旧正文保留、当前原件仍可下载；恢复真实Converter并显式唤醒，尝试2成功、历史正文仍可读、重复索引仅一行。只读来源实际sysfs字节通过共享登记/真实转换后，换成真实不存在挂载配置；缓存可读并标stale/离线、下载409。明确不把无支持扩展名的sysfs登记当真实扫描验收。真实扫描PDF先不启用OCR形成无文字结果，再排队OCR：queued时不称text_available，实际识别后才发布英文正文，人工合同编号保持。
- 新测试初稿的FTS表名和离线缓存stale预期与现行契约不符，核对SQL/投影后修正并通过；不把测试断言修正描述为修复生产故障。故障注入不伪造成功业务响应。既有全套覆盖实际worker退出/超时、租约过期、磁盘写入失败、事务回滚/晚到结果、索引代次、损坏备份与新目录恢复。
- `scripts/acceptance.py --phase browser --output /tmp/juanzhan-t33-browser`：Vite构建通过，sources1 + library8 + reading3 + search4 + jobs2 + files2 = **20 passed，0 failed/skip**。sources只用自身随机Docker容器/卷，完成清理后再串行跑其他浏览器；正常Compose数据卷/管理员/.env未改。实际源扫描/增量/缺失及歧义/排除、拖放/逐项失败/撤销、正文/候选/历史、中文/类型过滤/URL恢复、真实任务/重解析、附件下载及恶意HTML隔离全部执行。
- Browser plugin not available；使用已有Playwright/`/usr/bin/chromium`，未安装新浏览器依赖。页面标题/精确测试URL、非空、无框架覆盖层、相关控制台/页面错误、真实交互检查通过；1440×1000与390×844截图实看。测试入口为本地8767，来源8768；截图沿用套件路径，例如`/tmp/juanzhan-t30-desktop.png`、`/tmp/juanzhan-t30-mobile.png`（均为本次重跑生成）。
- 最终只读汇总：`scripts/acceptance.py --phase assess --reports /tmp/juanzhan-t33-backend /tmp/juanzhan-t33-ocr /tmp/juanzhan-t33-browser --output /tmp/juanzhan-t33-final`，实际JUnit判定 **30/30 passed**，报告`/tmp/juanzhan-t33-final/summary.json`。另外以不存在报告目录验证assess：0/30通过、30 not_run、退出1，不把缺证据判通过。所有ID/真实函数引用校验、py_compile与git diff --check通过；生成报告不进仓库。
- 现有镜像`scripts/smoke.py`通过（Web/CSP/资源、Archive健康、Converter鉴权/六格式/OCR能力/multipart边界、worker心跳）；正常库8条迁移、0档案、0外键违规保持。无应用/接口/迁移/依赖变更，未因测试重建或发布镜像，Archive0.4.21/52路径和Converter0.4.3/6路径保持；无新增云配置需求。

T33不替代T34性能基线/版本化镜像与升级恢复运维手册；测试时长不当作性能承诺。未覆盖真实手机/Firefox/WebKit、硬件断电、网络文件系统、大规模压力及真实业务数据卷切换。只读外部字节仍需独立备份，T16托管接管与批量reprocess/set_metadata等明确未实现。可选安装Browser插件改善后续页面导航、截图与诊断，不是当前验收前置依赖。

## T34 本地发行候选 · 2026-10-18

- build_release.py首次工作区构建如实记录dirty=true；实现提交cf6a8f7后重新构建，最终manifest在/tmp/juanzhan-release-o5gxvq5r/manifest.json，明确source_dirty=false、source_revision=cf6a8f7a2f9e8bd609b56e059e4c0a122402698f、Linux/amd64。OCI标签实际核验0.1.0-rc.1；最终本地image ID为sha256:48841d0012f536a14005ff59d458c87aeca60776c15b5b1ce8dbc81b95411996。基础FROM固定已验证digest，pip哈希离线安装、eng/chi_sim模型校验及生产Web构建通过。未推镜像/Git标签/GitHub Release，不把本地ID称registry digest。
- release_drill.py对最终干净候选完整实跑，报告/tmp/juanzhan-release-drill-7ku467tz/result.json：初装旧dev镜像（8迁移）→随机管理员→真实TXT上传/Converter解析/worker索引与中文HTTP检索→换candidate，身份/数据保留→暂停worker→持久卷备份→恢复新目录→独立项目挂恢复卷→拒绝旧会话/原密码重新登录→下载字节、正文与中文搜索/SQLite完整性通过。8迁移、integrity=ok、FK0；UID10001、readonly_root=true、cap_drop_all=true及真实Web shell/编译资源/CSP通过。67.13s只是一轮功能演练时长，不是吞吐基线。预演58.24s同样通过，但不把未提交镜像当最终候选证据。
- 发布Compose初稿tmpfs flow-list逗号未加引号，Docker拒绝非法挂载；修正后完整演练通过，没有放宽只读/权限规则。fixture随机项目/卷/凭证与正常Compose隔离；清理仅本次project label卷，无down -v。正常开发实例未替换，原.env/管理员/8迁移/数据卷保留。
- benchmark.py实测1万/10万合成档案、真实词元/SQLite/鉴权TCP HTTP，4种查询各20计时+预热、命中总数验证及integrity/FK通过；开发报告/tmp/juanzhan-performance-s0lv0m1s/baseline.json。最终候选容器以只读根和512MiB测试tmpfs同样执行，JSON在宿主私有/tmp/juanzhan-t34-container-baseline/baseline.json，160计时请求全部通过。开发Python3.12.14/SQLite3.53.1与容器Python3.12.15/SQLite3.46.1分别记录；最终容器10万条中文常见词p50/p95=616.42/659.86ms，列表47.01/54.36ms。完整表及范围见PERFORMANCE；不是十万份原件导入/解析、并发或OCR吞吐。
- 容器基线首次只输出tmpfs报告路径，退出后无法复制，未把丢失的报告当交付证据；增加--stdout后对最终镜像重测，在宿主成功保存/解析JSON。绑定脚本曾因云umask077导致UID10001不可读，调整公开测试源码为644，不改变私有数据/凭证权限。播种初稿spaces列数经SQL核对修正，完整命中断言未放宽。
- pytest tests/test_foundation.py tests/test_backup.py：17 passed（1条既有Starlette/httpx弃用警告）；脚本py_compile与git diff --check通过。无应用HTTP/数据库/依赖变化，未重复T33全量409/浏览器20验收。正常Compose smoke.py通过（Web/CSP/资源、Archive、Converter鉴权/能力、worker心跳），三服务健康；正常库8迁移/0档案/0外键违规保持。
- 构建、首装、私有env/HTTPS、只读来源override、持久备份导出、新卷恢复、同schema升级及匹配旧备份回退见RELEASE。当前只实测Linux/amd64与8→8迁移镜像替换；未发布registry/稳定版、未切真实业务卷，未承诺arm64/多用户/冷缓存/大规模OCR/任意跨版本升级。RC精确追溯cf6a8f7；后续提交只补运维记录和外部benchmark输出工具，不改变已测镜像应用源码。既有云开发安装/启动路径不变，无需新setup草稿。

## 本机P1批量重新解析 · 2026-10-19

macOS Apple M5 arm64 / CPython3.12.11，既有uv.lock冻结安装34包，无依赖变更。

- `pytest -q tests/test_batches.py tests/test_auth.py tests/test_jobs.py --basetemp=.local/pytest-core-final`：53 passed，6.96秒。真实SQLite/托管文件/HTTP及worker，覆盖严格选项、OCR子任务参数、跨空间/回收/并发版本、活动解析拒绝、父任务租约失效对子任务与parse_requests的原子回滚、不可撤销。
- 首次批量/正文组合执行：24 passed、13 failed；12项原有正文用例与新增真实Converter批量用例均未得到成功解析。日志`.local/targeted-tests.log`。之后新增的OCR参数测试另在上述53项内通过。
- 从HEAD导出原始services/tests/docs到`.local/baseline`，单跑原始`test_public_three_content_formats_and_bounded_history[txt]`同样失败；日志`.local/baseline-tests.log`，证明该转换故障在变更前存在。
- 本机最小`resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))`抛`ValueError: current limit exceeds maximum limit`，现有conversion_child在转换前使用该设置；任务报CONVERSION_FAILED。未放松生产资源边界。

新增真实Converter测试保留，须在支持的Linux环境执行通过后才能标记批量重解析完整验收。未运行完整全仓库/浏览器/容器/OCR验收；本轮不宣称这些通过。依赖与测试夹具清理见LOCAL-DEVELOPMENT。

补充基础测试`tests/test_foundation.py`：7 passed、1 failed；失败项test_converter_boundary固定要求ocr_available=true，而本轮未安装OCR模型，服务如实报告false。日志`.local/foundation-tests.log`。不计入上述53项成功结果。

## 用户授权Linux服务器复验 · 2026-10-19

devtest / Alibaba Cloud Linux4 x86_64 / CPython3.12.13；沿用原锁文件，通过阿里云PyPI镜像与require-hashes安装；官方固定中英文OCR模型再次验证。专用源码目录`/opt/juanzhan-dev/app`，报告及缓存位于其同级`.local/`，未改变服务器既有服务。

- 批量及正文：`pytest -q tests/test_batches.py tests/test_content.py --basetemp=/opt/juanzhan-dev/.local/pytest-batch --junitxml=/opt/juanzhan-dev/.local/batch-content.xml`：38 passed，42.87秒。真实TCP Converter、SQLite、文件存储、worker及六格式正文均通过，新增批量重解析force保护/实际生成第二条成功历史通过。
- 服务器`npm run build --prefix web`通过；`PLAYWRIGHT_BROWSERS_PATH=/opt/juanzhan-dev/.local/playwright npm run test:e2e:jobs --prefix web`：3 passed，19.9秒。新增批量流程验证固定选择、OCR默认关闭/语言选择、确认前禁用提交、父批次排队提示、无撤销按钮、子任务成功及两份档案各两条真实解析历史。
- 1440×1000及390×844截图已目视检查，弹窗可滚动且无横向溢出；页面标题/URL由login helper检查，无框架错误覆盖层；新增流程无pageerror，既有任务流程额外检查console error。截图服务器`/tmp/juanzhan-batch-reprocess-{desktop,mobile}.png`，本机副本`/tmp/juanzhan-remote-qa/`。
- 本机原8项library/整理浏览器流程通过，日志`.local/browser-library.log`。

Browser插件缺席，沿用仓库Playwright；服务器平台采用其Ubuntu回退浏览器，以上实际流程已通过。新增测试字体环境变量JUANZHAN_TEST_CJK_FONT，复用服务器已有Noto简中字体验证，不安装新系统字体。完整后端与全部浏览器/容器验收另记录，不以专项结果宣称全部通过。

## 第一版当前范围完整Linux验收 · 2026-10-19

运行时代码提交`838fa0796be4aef5ace51f8ca97c66eab7aa4890`。本轮实际结果：

| 验证 | 结果 | 服务器证据 |
|---|---|---|
| 完整后端，默认只读sysfs的隔离容器 | 418 passed，212.67秒；1条测试客户端弃用提示 | `.local/backend-container.log`、`.local/reports/838fa07/backend.xml` |
| 六组真实浏览器 | sources 1、library 8、reading 3、search 4、jobs 3、files 2，共21 passed，无跳过 | `.local/reports/838fa07/browser/`中的6份JUnit及summary.json |
| 30项原验收机器汇总 | 30/30 passed | `.local/reports/838fa07/assessment/summary.json` |
| 最新UX-15～18 | 对应完整后端及reading/files真实交互通过；结构化阅读、搜索桌面与原件手机截图已目视检查 | 对应JUnit及`/tmp/juanzhan-t29-*`、`juanzhan-t30-*`、`juanzhan-t32-*` |
| 候选镜像构建 | linux/amd64；source_dirty=false；模型/许可证/离线哈希依赖检查通过 | `.local/reports/838fa07/release-manifest.json` |
| 生产镜像六格式/只读来源/自动增量索引/离线缓存 | `smoke_formats.py --persist --index --daemon --external`退出0 | `.local/production-external-smoke.log` |
| 生产镜像真实OCR/正文/历史/候选/中文检索 | `smoke_formats.py --persist --index --ocr`退出0 | `.local/production-ocr-smoke.log` |
| 实际Compose初装→镜像替换→一致备份→新卷恢复 | passed，42.26秒；重新登录/下载/正文/搜索通过；8迁移、integrity=ok、外键错误0 | `.local/reports/838fa07/release-drill.json` |
| 当前候选1万/10万合成库HTTP基线 | 160次计时请求及预热核验通过 | `.local/reports/838fa07/benchmark.json`，见PERFORMANCE |

所有证据路径以`/opt/juanzhan-dev/`为根。完整后端在宿主直接运行先得到386 passed/32 failed：失败均涉及宿主可写sysfs与只读夹具前提；未关闭只读保护，改在标准容器中全部通过。首次把external与OCR两套不兼容样本参数合并造成smoke脚本失败，已按上述文档命令分别通过；脚本现提前拒绝该组合，错误信息与非零退出已验证，不把它记录为业务解析失败。

候选镜像ID`sha256:fbceee03458f533592860783f86c3363a74dece2557184b92e740248f9d26bc7`；该构建仅在测试服务器存在，无Git标签、GitHub Release、镜像仓库推送或正常实例切换。最后核对仅服务器原有nginx-proxy/simple-shell运行，无本轮遗留测试容器或具名卷。开发依赖、报告、测试夹具、镜像与清理边界见LOCAL-DEVELOPMENT。

## 批量业务字段专项 · 2026-10-19

服务器当前工作副本：tests/test_batches.py、tests/test_metadata.py、tests/test_content.py合计73 passed（46.59秒，1条测试客户端弃用提示），日志/报告为`/opt/juanzhan-dev/.local/batch-fields-final.log`及batch-fields-final.xml。覆盖七类型、64位整数、Decimal、false、清空必填保护、逐项版本冲突、撤销来源保真/规则变化、审计与租约回滚、快照大小限制，以及既有真实Converter正文回归。

新增两个library浏览器流程2 passed（18.1秒），日志`.local/batch-fields-browser-focused.log`；验证七类型批量设置、保留其他字段、清空/撤销、并发修改及浏览器不安全整数阻止提交。首次library运行原有8项通过、新增2项因getByLabel选择器超时失败，修正为有明确角色/名称的combobox定位后上述2项通过；初始日志保留于`.local/batch-fields-browser.log`。本轮未宣称全部浏览器/完整后端重新通过。

桌面1440×1000和手机390×844截图`/tmp/juanzhan-batch-fields-{desktop,mobile}.png`已目视检查，内容完整、表单可读，手机无横向溢出；本机副本`/tmp/juanzhan-remote-qa/`。无Browser插件，继续使用仓库Playwright。

## 历史原件下载专项 · 2026-10-19

### 后续T16托管接管验证

服务器默认只读sysfs容器执行test_adoptions、test_maintenance、test_sources、test_source_initial、test_source_incremental、test_documents：最终57 passed，39.87秒，1条既有客户端弃用提示。证据`/opt/juanzhan-dev/.local/adoption-final.log/xml`。7项新接管测试覆盖真实只读字节、幂等/CSRF、版本冲突、审计回滚、失效租约、哈希不匹配、旧扫描epoch失效、有限离线重试/终态释放屏障、托管绑定防重导及真实Converter重新解析/人工字段/旧成功正文保护。sysfs文件通过共享注册服务登记，明确不将无扩展名sysfs文件声称为实际扫描导入。

真实扫描与Web通过独立`juanzhan:adoption-dev`开发镜像和只读bind fixture验证。来源浏览器组2 passed（1.2分钟），日志`.local/adoption-sources-browser-final.log`；追加实际增量扫描/文件暂时隐藏后focused流程1 passed（10.3秒），日志`.local/adoption-browser-enhanced.log`。验证确认前禁用、任务完成、新managed版本、原件字节不变、受保护排除、增量扫描不切回external、来源不可用时managed下载正常而历史external返回409、刷新后接管入口消失、手机无横向溢出。手机截图`/tmp/juanzhan-adoption-mobile.png`已目视检查；本机副本在`/tmp/juanzhan-remote-qa/`。

浏览器进程继续使用已有UTF-8 locale及Playwright。初次将新接管测试放在全局空库断言之前导致原有测试失败；保持原有流程先执行后两个测试均通过，未放宽业务断言。前端构建通过，YAML解析确认Archive0.4.25/53路径及新adopt契约。非完整全仓库/所有浏览器/正式RC验收，开发镜像dirty，不替换既有候选镜像。

服务器标准只读sysfs容器执行tests/test_files.py：6 passed，7.05秒，1条既有客户端弃用提示。证据为`/opt/juanzhan-dev/.local/history-files-container.log`及history-files-container.xml。真实SQLite、文件和HTTP覆盖：旧版字节、鉴权、跨档案404、参数互斥、损坏拒绝、下载中新增Revision、当前原件版本保护，以及只读外部来源离线/可写/路径越界/哈希变化和PDF预览。

服务器前端构建通过；原件浏览器组3 passed，13.0秒，日志`.local/history-files-browser.log`。新增真实Revision服务追加后从Web版本列表下载旧字节，并核对当前字节、中文文件名和手机无溢出；原有PDF预览/返回和恶意HTML隔离也通过。手机截图`/tmp/juanzhan-history-original-mobile.png`已目视检查，本机副本在`/tmp/juanzhan-remote-qa/`。未执行本次代码的完整全量回归或镜像重建。

最终浏览器命令在进程环境指定`LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8`，并沿用已有JUANZHAN_TEST_CJK_FONT和PLAYWRIGHT_BROWSERS_PATH。SSH默认POSIX字符集使初次Chromium中文下载名退化为download；已有UTF-8 locale下全部通过，未放宽断言或改变产品Blob策略。首次宿主pytest未指定字体导致PDF夹具失败，补充已有字体环境变量后通过，最终容器6项全过。初步/调试日志保留于`.local/history-*`。浏览器测试私有pointer文件只用于一次性测试卷的真实Revision夹具，退出清理，不提供生产测试API。

## 字段/类型/模板管理专项 · 2026-10-19

在授权Linux开发服务器复用现有Node/Python/Playwright；Browser plugin not available，使用仓库Playwright。真实HTTP+SQLite+文件存储验证字段七类型、Decimal精度、模板排序和必填拒绝/通过、真实上传/归档、启停保留已有值、空间隔离和错误提示；int64原始JSON验证名称修改不舍入约束，详情明确精度提示且API原值保留。

- 后端test_fields.py/test_metadata.py/test_batches.py：77 passed（33.22s），服务器.local/catalog-manager.log/xml。
- 主界面全组13 passed（1.3m），.local/catalog-library-final.log；阅读3 passed（13.0s），.local/catalog-reading-final.log。
- 最后精度补丁重新构建后管理浏览器3 passed（12.5s），.local/catalog-precision-final.log；构建.local/catalog-build-final.log通过。
- 桌面1440×1000及手机390×844截图：/tmp/juanzhan-catalog-template-{desktop,mobile}.png、/tmp/juanzhan-catalog-manager-mobile.png，本机副本/tmp/juanzhan-remote-qa/。已检查可读性、控件布局及无水平溢出；测试收集控制台错误。

没有重建生产候选或对外部署；本专项不代替剩余功能完成后的全量验收。

## Web备份传输基础专项 · 2026-10-19

backup_archive模块与既有backup回归27 passed（8.89s），服务器.local/backup-transport-final.log/xml。真实SQLite+托管原件目录包导出ZIP、导入新目录、restore完整校验、HTTP重新登录和原件字节一致；当前实例保持可下载。拒绝穿越/绝对路径、符号链接、重复/额外成员、校验损坏/CRC错误、缺失标记、数量/容量超限、伪造中央目录数量/大小、NUL及尾随数据，失败不保留本次暂存目录；ZIP64有效样本通过，已有目录/归档拒绝覆盖。

初次组合测试25 passed/1 failed源于未指定服务器CJK字体（PIL不能打开样本字体），补充已有JUANZHAN_TEST_CJK_FONT后26项通过；增加CRC并修正额外对象/链接样本后最终27项通过。未安装新字体或依赖。这是传输基础证据，不证明Web接口、自动备份或全阶段验收完成。

## Web备份恢复与自动备份专项 · 2026-10-20

授权Linux服务器复用既有依赖，Browser plugin not available，采用仓库Playwright。真实SQLite/文件/HTTP、实际Converter回归和独立生产依赖镜像分别验证，未替换现有实例。

- 后端backup_management/backup_archive/backup/jobs/foundation最终64 passed（35.19s），服务器.local/backup-release-ready.log/xml。覆盖创建/下载/上传/新目录恢复、登录及原件字节、计划关闭和旧凭据失效、9→10迁移保留旧行/校验、持久计划/配置冲突/不补积压/数量保留、真实daemon到期执行及重启、损坏包/哈希、鉴权/CSRF/路径输入、忙锁有限重试、旧租约不发布、中断work清理、失败不删除最近成功备份、活动恢复阻止删除、操作员新目录暂存和明确清理。
- Web构建.local/backup-release-web-build.log通过；最终备份浏览器3 passed（15.2s），.local/backup-plan-reload-browser.log。真实下载ZIP→上传验证→恢复→计划保存/重载/关闭→删除；空空间入口、损坏包不可恢复、并发计划拒绝覆盖及重新读取服务器版本均通过。另有主界面13 passed（1.3m），.local/backup-final-library.log；任务3 passed（18.6s），.local/backup-final-jobs.log；管理界面入口3项复验通过。
- 桌面1440×1000及手机390×844截图/tmp/juanzhan-backup-{desktop,mobile}.png，本机/tmp/juanzhan-remote-qa/同名副本已人工查看。暖白/墨绿样式、长编号/哈希换行、纵向滚动、手机无水平溢出；测试含CSS实际加载断言及页面/相关控制台错误收集。
- juanzhan:backup-dev独立dirty开发镜像构建成功，.local/backup-image-build.log。scripts/backup_runtime_drill.py在随机具名容器/三卷、UID10001、read-only root、cap_drop ALL/no-new-privileges、1536MiB/2CPU上通过，.local/backup-runtime-drill.log。实际loopback HTTP和worker执行手动/自动备份、上传验证、恢复、数量保留，CLI再次校验并暂存到新卷，启动恢复实例重新登录/下载/计划关闭/integrity/FK/迁移集合/CSS均通过；未触碰外部来源。随机容器与测试卷自动清理。

首轮32项在传输基础上通过；后续并发/围栏/运维/迁移证据扩展至64项。调试中发现并修复本轮脚本误写styles.css：恢复已提交样式后重建、重跑并检查真实截图，早期无样式截图不作为验收证据。首轮浏览器失败与新计划冲突用例失败均因定位器匹配其他记录，已限定相应行/错误并最终通过。第一次tar含macOS AppleDouble迁移旁文件造成启动错误，已仅删除本轮tar清单中的._文件，后续COPYFILE_DISABLE=1；并未修改迁移运行器来跳过未知内容。

这是功能专项证据。本阶段所有功能交付后的全后端、七组浏览器、最新候选构建/升级恢复及文档依赖审计仍须完成；不能把历史418项或旧RC验收替代当前代码全量验证。

## 本阶段最终验收：后端与候选镜像 · 2026-10-20

当前全后端在受限Linux容器（1536MiB/2CPU、只读sysfs、真实CJK样本）481 passed（308.69s），无跳过/失败；证据/opt/juanzhan-dev/.local/final-features-verified-backend.log/xml。初次480 passed/1 failed是旧来源升级测试写死9迁移，改为核对当前迁移文件名集合并保留全部旧校验值断言后完整重跑通过；没有跳过或削弱只读检查，未修改旧迁移。

源码候选0.1.0-rc.2从干净16381a9d96f8180aca07fb6e5cff97bfb12ab001构建，镜像sha256:9b4b6025a19a5fac45c6390f5f95e130cbaed261fcd6247f3bd76d7f0e33237d，linux/amd64、source_dirty=false、published=false。构建日志.local/final-features-build.log，原manifest/tmp/juanzhan-release-mprm8mo9/manifest.json。后续仅验证脚本/测试与文档修正，不改该镜像的产品源码追溯；旧rc.1/foundation镜像保留。

- 当前候选六格式/真实OCR/公开正文与历史/候选、中文/繁简FTS、增量编辑与重建：final-features-formats-ocr.log通过。
- 当前候选真实只读来源/持久daemon/文件变化拒绝/源真实离线缓存及公开检索：final-features-formats-external.log通过；Archive、Converter、offline实例均显式使用rc.2，不把旧foundation标签当当前候选。
- 实际Compose从旧foundation的8迁移升级到候选10迁移，保留登录/原件/正文/检索；按文档由卷所有者收紧旧备份卷权限，再验证新备份接口和计划；一致备份→全新恢复卷→重新登录/下载/正文/检索、计划关闭与integrity/FK通过。证据final-features-schema-release-drill.log和/tmp/juanzhan-release-drill-jnyh188e/result.json，54.46s，明确previous_database_migrations=8/current=10、UID10001/read-only root/cap_drop ALL。旧same_schema报告不代替这份升级证据。
- 当前rc.2的独立backup_runtime_drill通过：final-features-rc2-backup-runtime.log；真实HTTP创建/ZIP下载上传/新目录恢复、实际daemon自动计划/保留、CLI再次校验到新卷、启动恢复实例并重新登录/下载/计划关闭/integrity/FK/迁移/CSS通过。随机容器和三卷自动清理。

全阶段七组浏览器与30项映射尚在汇总，最终结论以其实际终态为准。

## 本阶段最终完整结论 · 2026-10-20

全部本阶段功能已按FEATURE-BACKLOG和ACCEPTANCE补充索引核对完成。当前完整后端481 passed；七组浏览器共39 passed，无失败或跳过；原30项机器映射30/30 passed。原UX-15～18由完整reading/files、内容/候选/离线/OCR测试及实际截图共同验证，不只根据30项清单存在判断。

| 浏览器套件 | 通过项数 | 当前证据来源 |
|---|---:|---|
| sources | 4 | 首轮86.84s，当前rc.2镜像和真实内核只读挂载 |
| library | 13 | 首轮80.86s，包含管理界面与批量字段 |
| reading | 3 | 首轮14.58s，真实结构化/历史/候选 |
| search | 4 | 补齐已有CJK字体环境后22.7s |
| jobs | 3 | 17.5s，真实重解析子任务/失败与有限重试 |
| files | 9 | 33.7s，历史下载/完整PDF/密码/中文/资源释放 |
| backups | 3 | 15.1s，真实ZIP/新目录/计划/冲突/删除 |

首轮浏览器驱动在search样本生成时因缺JUANZHAN_TEST_CJK_FONT失败，保留原.local/reports/final-features-browser-16381a9/summary.json及日志。无需安装字体；加上服务器已有字体路径后只续跑search/jobs/files/backups，输出到.local/reports/final-features-browser-completion。未重跑已通过的前三组，也未把第一次failed摘要改成passed。

最终选用的481项后端与七个完整套件JUnit逐项检查无error/failure/skipped，按原字节汇集到.local/reports/final-features-accepted；provenance.json逐份记录来源/用例数/SHA-256和续跑原因。汇总脚本只接受明确的本次报告，校验481/39总数；acceptance.py --phase assess针对该目录得到30/30，证据.local/reports/final-features-assess/summary.json。没有混入旧MVP结果。

最终契约检查：Archive0.4.28/63路径、备份10个HTTP操作与运行应用生成的路由定义一致，错误体明确Error并补全404等状态，10条迁移；.local/final-features-contract.log。自动生成内部GET/HEAD operationId提示不构成公开契约，公开以仓库手写OpenAPI为准。

候选一致性：当前rc.2与工作区打包内容逐文件SHA-256比较，services 63文件、web/dist 208文件、licenses 17文件全部一致，.local/final-features-candidate-match.log。当前产品源码、配置和前端相对镜像构建提交16381a9无差异；后续仅文档/验证脚本和测试适配变动，不篡改候选源码追溯。实际升级/恢复、六格式/OCR、只读离线、自动备份/恢复验证见前一节。

结束检查：仅原有nginx-proxy、simple-shell-terminal-1服务运行；本轮临时后端/来源/镜像演练容器及其随机卷/网络已退出清理。未推送Git标签、Release、镜像仓库，未替换用户业务实例。本轮范围是既定单管理员Linux产品与明确补充功能，不包含PRD明确排除的LLM/向量/多用户/在线Office或未确认扩展。浏览器范围为既有Linux Chromium桌面/窄屏，具体资源和复杂格式边界仍按DEVELOPMENT/PERFORMANCE，不声称真实手机/所有浏览器/硬件断电或无限容量均已实测。

## 2026-10-20 后台任务进度可见性专项

Browser plugin not available，本次使用已有Playwright，无新依赖。devtest执行npm run build及npm run test:e2e:jobs：4项通过（32.0秒），真实SQLite/文件存储/HTTP/Converter/worker，新增DOCX上传→查看解析进度→对应任务完成→新增任务自动出现→刷新保留；其余覆盖批量解析、显式重解析及损坏原件失败。检查1440×1000与390×844截图、无页面错误、无水平溢出。日志在服务器.local/progress-build.log与.local/progress-jobs.log，截图在/tmp/juanzhan-progress-center-{desktop,mobile}.png。此专项不替代此前全量验收，不声称重新运行481项后端。

后续主界面回归npm run test:e2e：13项全部通过（1.6分钟），服务器.local/progress-library.log。干净提交c1f0a02构建rc.3并部署到原juanzhan-test项目/持久卷，三个服务健康。部署后用test账号对18080实际浏览器验证常驻数量、任务列表、1440/390布局与无控制台错误；原空间4份档案保留（含用户追加资料），不读取或重导用户原件。部署报告在私有实例目录progress-deployment-smoke.json。

## 2026-10-20 文件名与分步进度验证

最终验收：f951bff干净源码完整后端484 passed（310.68s），无失败/跳过；最终专项40 passed（29.22s），最终任务浏览器4 passed（38.0s），主界面13 passed（1.9m）。对应服务器.local/step-progress-full-verified.log/xml、step-progress-final-targeted.log、step-progress-browser-final.log、step-progress-library.log。未声称七组浏览器全部重跑，下文首轮失败报告保留。

rc.4干净构建：manifest /tmp/juanzhan-release-se57y0ix/manifest.json，源码f951bff/source_dirty=false，镜像sha256:cbd33b3d2f91d5f380b1fd3144ef22d6d1ce2a2116879fd97b574530f78d937e。真实8→11迁移升级、一致备份、新卷恢复、登录/下载/正文/中文检索及integrity/FK演练通过（62.13s），报告/tmp/juanzhan-release-drill-ka7sgrhr/result.json，日志.local/step-progress-release-drill.log；随机演练容器/卷已清理。

devtest原juanzhan-test实际10→11迁移完成，全部10个旧迁移SHA及原4档案的ID/原件Revision/正文引用/版本值保持，integrity=ok、FK=0，三个服务健康。只对最初虚构welcome.txt显式重解析，真实HTTP观察pending→validate→submit→extract→全步骤完成，文件名与列表/详情一致；未重跑用户Word。实际部署1440/390浏览器验证文件名、六条进度（总体+五步骤）、无溢出/控制台错误及test登录通过。私有实例目录保留before/after-rc4-schema.json、step-progress-deployment.json及step-progress-browser-smoke.json。

新增0011及Archive0.4.29。浏览器任务4项通过（28.3s），主界面13项通过（1.9m），真实DOCX/SQLite/文件存储/HTTP/Converter/worker，验证捕获文件名、五步独立条/总体完成步骤数、真实成功与损坏PDF失败所在步骤，1440×1000/390×844无水平溢出与控制台错误。截图本机/tmp/juanzhan-step-progress-{desktop,mobile}.png，服务器原图/tmp/juanzhan-progress-center-{desktop,mobile}.png，日志.local/step-progress-browser.log、step-progress-library.log。Browser插件未提供，复用现有Playwright，无新增依赖。

首次两组后端36通过/3失败：新增测试观察列表不能跨worker子进程回传、测试重试未等持久退避，以及未指定现有CJK字体。分别改为同进程实际execute+HTTP转换观察、按持久时钟推进退避、复用现有字体，随后39项通过（32.38s）。初次完整后端482通过/1失败（320.52s），原租约测试在10ms预算内未完成begin即失效；改为先以正常租约begin，再将真实SQLite租约时间设为过去，继续验证失效围栏/重试新ParseRun与GC不丢失，未放松生产租约逻辑。原始日志保留.local/step-progress-backend.log、step-progress-backend-verified.log、step-progress-full.log/xml；当前新增顺序/回退/丢弃发布断言与最终完整复验另记录。
# 2026-10-21 外部 Agent 与格式验收

最终完整后端回归：544 passed（355.80s），真实 SQLite、文件存储与 HTTP；报告在 devtest `.local/agent-final-full.log`、`.local/agent-full-reports/final.xml`。包含真实 TCP REST/MCP、stdio 子进程、空间越权/撤销/到期/限流、备份恢复清除授权、精确数字及概要来源验证。3 个既有框架警告（弃用/自动 OpenAPI favicon operation ID），无跳过。

真实格式矩阵见 FORMATS-VERIFIED.md：38项格式用例，包括全部声明格式、别名、BOM 编码、图像/扫描 PDF 实际 OCR、损坏与未支持格式；5份固定版本真实 Office 样本通过哈希验证后参与验收，不把 unsupported 算解析成功。概要规则8项；其余包含现有业务回归。

阅读浏览器6项已通过（52.7s），覆盖十份六格式真实文档和 Agent 设置/一次性密钥/撤销。Browser plugin 不可用，复用现有 Playwright。Chromium 使用专用 TMPDIR，未改变系统 /tmp 权限；桌面1440与手机390截图已核对，密钥隐藏后截图。

浏览器回归首轮基础13项通过；来源组首轮3过1失败，唯一失败为部署 Compose 切换期间 Chromium 报两次 ERR_NETWORK_CHANGED（所有业务断言已完成，最后控制台检查失败）。部署稳定后不修改测试/代码重跑，来源4项全过（1.5m），搜索4项全过（27.0s）。保留 `.local/agent-browser-sources-first.log`，最终各组报告为 `.local/agent-browser-{base,sources,search,jobs,files,backups}.log`；非忽略控制台错误或放宽断言。

最终浏览器7组43项全部通过：基础13、来源4、搜索4、任务4（29.4s）、文件9（38.8s）、备份3（15.5s）、阅读/Agent6。来源重跑后未再出现网络错误，测试断言未放宽。来源转换容器显式指定 rc.11，复用私有 Playwright 缓存/专用 TMPDIR；原业务实例保持健康，测试服务按各组退出清理。

## 2026-10-21 后续批次：原生Office/CSV适配

首轮新增五类Office及既有格式：40过/9失败（64.86s），9项均因容器未挂测试字体而在样本生成前报cannot open resource，未掩盖错误；日志`.local/office-first-tests.log`。补挂现有Noto字体后，格式/转换/上传专项99项通过（106.87s），无跳过，日志`.local/office-verified-tests.log`。之后补充公式空缓存/重复行边界，当前完整回归另行执行并以最终报告为准。

浏览器首轮6项通过/1项失败，失败为新增样本生成子进程缺少services模块搜索路径；修正测试脚本后只重跑该新增用例通过（28.7s），实际七份XLSX/PPTX/ODT/ODS/ODP/CSV/TSV逐一真实上传/转换/持久正文与概要/来源跳转、桌面1440和手机390验证。既有六格式十份样本与其他阅读用例均在首轮通过（共6项）。无放宽断言。Browser plugin不可用，沿用Playwright；未修改系统/tmp或安装浏览器。日志`.local/office-browser-reading-first.log`和`.local/office-browser-new-formats.log`；截图位于私有TMPDIR下juanzhan-office-*.png，已实际查看XLSX桌面与PPTX手机截图，通用分点/内联数字/布局正常。

T37最终完整后端：561 passed、3框架警告、无跳过（452.15s），日志`.local/office-full-tests.log`、JUnit `.local/agent-full-reports/office-full.xml`。随后仅增加测试数据与用例，运行3份固定blob真实LibreOffice ODT/ODS/ODP补充用例全部通过（5.58s），源码/运行依赖不变；日志`.local/office-real-odf.log`。新样本来源/大小/SHA-256/git blob见reference/extra-format-fixture-sources.json，4份共45940字节（其中RTF留给后续适配，未宣称已支持）。

构建镜像rc.12后执行`JUANZHAN_SMOKE_IMAGE=juanzhan:0.1.0-rc.12 .venv/bin/python scripts/smoke_formats.py --persist --external --office`通过。原六格式＋新七格式共13类：内核只读挂载真实来源导入，解析/块/候选/派生文件/哈希/当前指针入库，鉴权HTTP读取、显式重解析幂等，来源字节变化拒绝且旧正文保留；第二实例无来源挂载仍可读陈旧缓存。随机容器/卷/网络退出清理，未挂业务卷。日志`.local/office-image-smoke.log`。

## 2026-10-21 T38旧Office/RTF迭代

Python层首轮RTF/CFB/CSV及真实RTF9项通过；固定真实XLS/XLSX2项通过。加入实际catdoc工具镜像后，格式矩阵/Office/RTF68项通过（107.62s），包括真实DOC/XLS/PPT与当前全部20种输入MIME、OCR开关及未支持/损坏边界，测试原件下载哈希不变。

另增加固定blob的加密DOC/XLS/PPT、带宏DOC/XLS/PPT、国际字符DOC/PPT及Gothic RTF：首轮19过/1失败（28.67s），catdoc输出合法UTF-16代理对的CESU式字节被严格UTF-8拒绝；修正为仅合并合法代理对后20项通过（28.83s），无替换原始字符或放宽断言。实际DOC正文包含中文和补充平面字符；三种加密样本均失败且原件保留，宏只读正文。日志legacy-extra-first-failed.log与legacy-extra-verified.log保留。

阅读浏览器新增旧Office/RTF用例后8项全过（1.7m，无跳过）。通过JUANZHAN_E2E_CONVERTER_IMAGE=juanzhan:legacy-dev运行真实隔离Converter镜像，主机不安装catdoc；原六格式十样本、新七格式和旧四格式均真实上传/队列/持久化/默认概览/来源跳转/1440与390布局验证。随机Converter容器退出清理。完整回归尚以最终legacy-full报告为准，临时legacy-dev不是发布镜像。
T38语义复核：首轮完整583项虽通过，截图与上游样本预期比对发现catppt仅提取主题、漏备注，原先“非空即通过”的PPT断言不足，未以此作为最终发布验收。改为本库有界当前persist引用读取，增加Gothic/Bullet/表格内容及补充平面字符实际断言、备注标志、循环编辑链/越界拒绝；PPTX新增实际notesSlide关系读取及来源断言。对应43项专项通过（62.21s），首轮完整583报告保留，最终完整回归另行执行。

浏览器截图切换阅读格式后增加等待概览内容稳定，再复核真实桌面截图；原先捕获过“正在读取”状态的图片不作为最终视觉通过证据。最终以legacy-browser-semantic-final.log及其对应截图为准。
T38最终完整回归：586 passed、3既有框架警告、无跳过，500.83s；`.local/legacy-full-final.log`及JUnit `.local/agent-full-reports/legacy-full-final.xml`。它覆盖最终PPT当前引用/备注和PPTX notes逻辑；此前583结果不代替此最终结果。

最终阅读整组8项全过（1.4m，无跳过），使用干净rc.13镜像及真实固定blob样本，日志`.local/legacy-browser-release-final.log`。此前新增UI断言误要求“前两条摘录”必须出现较后段Gothic正文，失败记录为legacy-browser-summary-expectation-first.log；改为核对实际首段表格内容Row 1，同时完整正文API仍强制Gothic/Bullet/表格及Unicode语义断言。没有让后端遗漏正文靠非空判断过关。最终DOC桌面/PPT手机截图已人工查看，等待内容完成后再拍，不用加载态截图作为证据。

测试退出清理发现4个本轮隔离Converter遗留容器：核对image=legacy-dev/无业务挂载后按完整容器名删除。新增SIGTERM→SystemExit处理，确保Uvicorn重放信号时展开worker和容器finally；在rc.13新增用例和最终8项全组退出后均核对无reading-converter遗留。未清理其他容器/镜像/全局缓存。

最终发布镜像验收：`JUANZHAN_SMOKE_IMAGE=juanzhan:0.1.0-rc.13 JUANZHAN_EXTRA_FORMAT_FIXTURES=... .venv/bin/python scripts/smoke_formats.py --persist --external --office --legacy`通过，17类非图片文档（包含旧四格式）的内核只读来源→解析→持久化/文件哈希→鉴权HTTP读取/幂等重解析→源变更拒绝与离线缓存均通过，另强制PPT真实Gothic/表格与非BMP正文内容。全部随机容器/卷/网络退出清理，日志legacy-rc13-image-smoke.log；三类图片及扫描PDF OCR由最终完整回归覆盖。
# T41 OAuth与通用REST定向验收 · 2026-10-21

后续T43～T47（尚未整批验收/部署）：新overview-only浏览器专项1项通过（15.3秒，1440/390截图已检查），真实上传→Converter镜像→SQLite→概览，断言不显示格式选择/候选/历史且不请求后两类接口。0014快照核心最终3项通过（1.94秒）：真实sysfs只读源/SQL/文件/HTTP下载，来源关闭后副本仍可用，GC不删引用副本、备份恢复后离线可读，重复保存幂等、错误哈希与SQL不匹配拒绝。备份/maintenance及初版快照组17项通过（14.37秒）；首轮缺CJK字体挂载导致一个PDF夹具失败，补足既有只读字体挂载后通过。尚需Office阅读、显式来源快照任务/API、存储管理、旧浏览器断言更新和完整回归，不能把专项通过当作新批完成。

真实SQLite/HTTP的OAuth、认证及原Agent专项35项通过（22.09秒）；通用标准库REST客户端另6项通过（3.39秒，首轮误认为catalog含space_id，按既有契约改为四类目录字段断言后重验）。隔离OAuth浏览器1项通过（最终6.6秒），覆盖同意空间、回调state/iss、PKCE换码、REST/MCP、刷新令牌和管理员删除客户端撤销。1440/390截图已检查，复选框改为横向排布；前端构建通过，既有PDF阅读chunk大小提醒保留。

完整后端容器回归595项通过、7项框架警告、无跳过（436.03秒），日志`.local/oauth-full.log`与`.local/agent-full-reports/oauth-full.xml`。新增REST六项在完整组启动后单独验收，不能把595写成已包含REST的完整601项。

最终补充：REST/全部Agent契约（含七路径导入profile）10项通过（4.07秒）；OAuth组加入备份恢复清除授权/代码、跨会话同意隔离后10项通过（5.25秒）。这些专项存在重叠，不相加冒充新的一轮完整测试。业务运行代码未因补充契约/测试改动。

rc.14真实镜像/部署验收已完成：独立新安装→8到13迁移升级→备份/新卷恢复→登录/下载/正文/检索/完整性/CSP，45.57秒通过，私有rc14-release-drill.json；业务实例12→13，4档案/19文件哈希与版本不变。在线Agent9项、实际Word1440/390只读概览通过；公网HTTPS证书校验、401挑战、OAuth签发、Mac REST/MCP HTTP/stdio与撤销后双401通过。真实外部模型读取固定ParseRun全部75块并生成5点带引用概括，私有留证见AGENT-INTEROP；用户Word未重解析，正文不提交Git。

运维验证：18443外部超时而本机TLS正常，切换空闲443后外部健康200及登录/阅读通过；未改云安全组。Nginx首轮只读根下默认fastcgi目录不可写，修正所有temp目录到16MiB tmpfs后健康；Certbot dry-run含deploy-hook/nginx -t/reload成功，timer active。日志见IP-TEST/LOCAL-DEVELOPMENT，未跳过TLS验证。

## T43～T47 源文件管理候选（未部署）

完整后端source-full-backend-final.log：615项/463.36秒通过，无跳过，包含真实Office/ODF/RTF样本。额外契约2项、读取PDF备份恢复2项、确认业务来源保护1项通过。首轮588通过/6失败/20跳过中，1项旧离线预期已更新，5项实际人工匹配错误已修复为新条目读取live原件；修复专项9项通过。不能将首轮当全通过，也不能把各专项重复计数加成新的完整套件总数。

浏览器：更新后的reading整组8项通过；概览/原生XLSX/存储清理2项通过；PDF与原件阅读9项通过；附件流最终调整后当前/历史中文名及精确下载字节2项通过。主界面首轮12通过/1项旧“业务字段”标题断言失败，改为概览不显示该标题后单项复验1项通过；字段管理和整理仍通过真实HTTP及业务值断言验证。中文下载名异常由非UTF8测试浏览器环境独立复现，固定测试launch locale后保持原文件名断言，不放宽为任意名称。日志以source-*.log留在devtest私有.local。

成品候选fbf1aaa：业务与独立renderer均clean source；11项关键接口回归通过，真实只读source_snapshot_drill的相同大小/mtime变化、新旧两版失联可读、人工说明与未变不增版通过。独立发布演练53.71秒实际8→15迁移及一致备份/新卷恢复通过，记录test-instance/rc15-release-drill.json。前端附件流调整尚需重建，不以旧候选代替最终部署镜像。完整交付门槛见BATCH-SOURCE-FILES，当前业务仍rc.14。

最终交付补充：源码045901e双镜像clean构建，最终独立发布演练49.09秒实际8→15升级/备份/新卷恢复通过。devtest实际13→15迁移，source-upgrade-verified.json的原4档案/全部原业务表/19文件不变；公网Word源文件阅读新增1份缓存后，source-final-data-verified.json的旧19文件及业务表仍完全相同。source-public-browser.json真实TLS/1440/390/原生Word/存储入口通过，source-agent-live.json公网REST/MCP9项通过且凭据撤销。另加PNG/JPEG原图浏览器1项/11.3秒通过，未改业务数据。T43～T47逐项验收及边界见BATCH-SOURCE-FILES，当前业务已rc.15；本节之前的“未部署”为过程状态。

## T53 持久 Markdown 专项（2026-10-22）

首轮27项、补充损坏/过期代次后 Agent 联合42项通过：真实 Converter HTTP、20个文件案例（文本/MD/HTML/Word/EPUB/PDF、现代Office/ODF、CSV/TSV/RTF、图片、ZIP/二进制/加密PDF）、版本隔离、同版本失败保留、Unicode字符分段/哈希固定、空间授权、MCP、备份恢复、缺失/损坏显式失败及过期任务不得发布。测试不导入业务库。

任务浏览器初轮3项通过，另1项仍引用旧“重新解析与OCR”展开入口；按现行“整理操作→重新解析”更新后独立复验通过（15.1秒），桌面/390宽截图与无控制台错误断言正常。生产Web构建通过，沿用原有PDF大chunk提示。

初轮环境/实现修复：补齐已有CJK字体路径；macOS归档附带AppleDouble迁移伪文件导致读取失败，移除本轮伪文件并关闭扩展属性归档后恢复；修正副本登记INSERT占位符数量。三项旧MCP工具枚举断言增加新工具后专项通过。完整回归及在线部署结果见后续记录，不把首轮失败宣称为成功。

T53 final verification: complete isolated-container regression had 645 passes, 22 skips, 3 failures from the old MCP tool enumeration. Updated enumeration passed in the 42-test Agent suite; final clean-source Markdown/Agent/backup/contract suite: 60 passed (76.65s). Optional skipped fixtures are not claimed as verified. Web jobs: 3 initial passes and the obsolete-entry test passed after updating it to the existing Operations workflow (15.1s). Fresh migration under read-only root and 512MiB, with all 8 tools imported, passed. Initial smoke command omitted required Settings arguments; corrected command passed without implementation changes.

Actual rc.21 15-to-16 upgrade: backup before-markdown-rc21 retained; all 8 revisions backfilled (28505 bytes), no failed/pending Markdown jobs. TLS-verified scoped REST/MCP reads: 8 each, reassembled SHA256 matched, temporary credential revoked. Existing business tables and 37 files unchanged; 8 new Markdown objects. Post-QA all 45 file hashes and business tables match; SQLite integrity/FK checks and five service health checks passed. Private evidence: test-instance/markdown-before.json, markdown-after.json, markdown-after-qa.json, markdown-deploy.json and markdown-live.json. Rollback requires restoring the pre-upgrade backup into a new volume with rc.20. Other services and their ports were not changed.


## T54 Agent imports / templates (2026-10-24)

Initial real HTTP/SQLite/local-Converter suite: 11 passed; permission, OAuth and protocol suite: 44 passed. Isolated final-extension suite (imports/indexing/Agent/contracts/backup): 52 passed; final compact MCP/concurrent-write handling and contract checks: 30 passed. Browser plugin not available; used existing devtest Playwright. Explicit-grant UI -> raw file -> template discovery -> analysis submission -> desktop/390px cited overview passed (12.0s), original bytes unchanged, no page errors, screenshots visually inspected. No new dependencies.

First browser command failed because npx was absent from the shell PATH; switched to the project's npm script using its existing runtime. No runtime/package installation was needed. Full backend result and live business samples are recorded after deployment below.

T54 full isolated-container regression: 661 passed, 22 skipped (575.98s), no failures. Subsequent extensions were verified independently: 52 passed for imports/indexing/Agent/contracts/backup, then 30 passed for final compact MCP output, serialized submission writes and explicit import-profile contract. Fresh production image under read-only root/512MiB imported five templates/ten MCP tools and migrated a new database successfully.

Actual rc.22 upgrade 16 -> 17: backup before-agent-import-rc22 retained. Existing eight documents, existing business rows and 45 managed/derived files were unchanged during deployment. Five explicit synthetic examples (TXT, DOCX, HTML, MD, PDF) were then uploaded through the opt-in Agent import API, using the generic/contract/invoice/meeting/report templates. Every cited quotation was compared against independently extracted local plaintext; all original downloads matched uploaded bytes. Unknown invoice payment status and unprovided contract terms remained null. No internal model was called. Temporary scoped credentials were revoked.

Public TLS UI verification opened all five Agent overviews and their quotations; desktop 1440 and mobile 390 screenshots inspected, no page errors/overflow. Readonly MCP get_analysis_templates/read_document_analysis also verified online; a readonly import attempt returned 403 and created no file. Post-QA original eight documents/business rows and 45 file hashes preserved; total now 13 documents/69 files, SQLite integrity/FK checks passed, five services healthy. Private evidence and screenshots: test-instance/agent-import-{before,after,after-qa,deploy,live,post-qa,browser-live}.json and agent-import-live-{desktop,mobile}.png. Sample space is explicitly marked removable; no production documents were used as synthetic test inputs.

Rollback to rc.21 requires the pre-upgrade backup restored into a new volume; do not attach the old image directly to the 17-migration database.

## T55 Agent概览优先 · 2026-10-24

真实SQLite/托管原件/HTTP转换集成：tests/test_agent_imports.py、test_parsing.py、test_agents.py、test_agent_contract.py合计52 passed（59.57s）。覆盖五模板、五格式无分析兜底、已有Agent时自动任务跳过且无ParseRun、主动重解析、新Revision本地回退、引文/权限/幂等/备份及只读契约。首轮34 passed/1 failed为未设置已有中文测试字体路径，设置JUANZHAN_TEST_CJK_FONT后包含真实OCR的完整组合通过。

浏览器使用服务器已有Playwright（当前无Browser插件），Agent上传/分点回填/仅单份概览/不请求本地overview/依据展开/原件下载/1440与390布局通过；最终结果见.local/agent-priority-browser-final.log。无新依赖。模板指导提高丰富度和重点要求，不等同模型外语义质量验真；历史分析不自动改写。

T55最终源码323ed2e追加15项Agent集成通过（19.29s），三点概览浏览器1 passed（5.7s）；部署后五种模板公网TLS、单概览、原文依据及1440/390布局通过，page_errors=0。截图存于test-instance/agent-priority-live-{desktop,mobile}.png，桌面已人工查看。

## T56 标签与入库规则 · 2026-10-24

devtest既有环境、真实SQLite/托管存储/HTTP Converter，受限1536MiB/2CPU容器并使用真实只读来源约束：203 passed（194.12s），覆盖import_tags、agent_imports、catalog、documents、agent_contract、batches、backup、parsing、indexing、search、source_initial、source_incremental、foundation。新标签规则带来的文档版本/自动标签已纳入旧断言，升级前旧schema登记仍可执行。初轮主机来源测试不满足只读挂载前提，最终容器复测全部通过；不是放宽来源边界。

当前无Browser插件，使用服务器既有Playwright：标签编辑/两标签全部匹配/服务器保存组合/刷新恢复/删除/390布局，以及Agent内容标签优先与仅Agent概览，2 passed（14秒内）；原4项真实搜索/组合/URL/移动端/不完整内容及精度回归4 passed（37.8s）。首轮标签匹配测试的精确label定位和中文字体测试环境已修正，最终日志见.local/import-tags-{browser-verified,search-browser-verified}.log。桌面/手机截图位于/tmp/juanzhan-import-tags-{desktop,mobile}.png，手机已人工查看并压缩快捷筛选标题/按钮间距。无新增依赖，未把固定关键词规则声称为语义理解。

T56追加5项标签专项（含新策略/保存组合真实备份恢复）全部通过，6.25s。部署后公网TLS验证示例三点概览、Agent两个内容标签替换平台格式标签、原件哈希/字节、全部标签查询、服务器快捷组合、编辑多选及1440/390布局；页面异常0。最终13旧档案/69文件全部保留；示例增加后14档案/71文件，18迁移/integrity=ok/无外键错误。证据test-instance/import-tags-{live,browser-live,post-qa}.json及import-tags-live-{desktop,mobile}.png，桌面成品截图已人工查看。

## T57 导入面板可理解性 · 2026-10-25

空队列变为明确的拖放区和并排文件/文件夹入口，提示合并到标题旁，面板border-box防止窄屏外溢。无后台/接口/迁移/依赖变化。本轮CUA浏览器入口导航测试环境超时并重置，改用服务器既有Playwright执行可重复检查；7 passed（20.9s）。含点击文件夹按钮触发真实chooser并上传22文件、原生混合拖放/空目录/重试、辅助文件选择/拖放排除、1440×1000/390×844/667×375空面板按钮边界、关闭面板及pageerror=0。证据.local/upload-panel-final.log及/tmp/juanzhan-upload-panel-{desktop,mobile,short}.png。未在用户原生macOS文件选择器中自动提交私人文件。

T57成品公网复验已通过三个视口/双入口/关闭/pageerror，截图test-instance/upload-panel-live-desktop.png已人工检查；14档案71文件、18迁移保持不变。
