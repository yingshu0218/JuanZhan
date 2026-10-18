# 技术架构

## 既有 V0.4 基线

- Archive 应用：Python HTTP API（已采用 FastAPI，当前实现范围见 STATUS）、SQLite + FTS5、本地文件卷、SQLite 持久 Job/worker、Web 前端。
- Converter：独立 Python HTTP 服务，受服务 Token 保护，读取任务输入，产出结构化结果和临时资产，不直接访问 Archive 业务库。
- 两个主服务通过 Docker Compose 部署；MVP 不需要先引入 Redis、消息中间件、向量库或独立搜索集群。
- 生产与原型均采用 React 19 + Vite 6 + Phosphor Icons（ADR-026 实施选择）；原型仍是独立的示例视觉成果。

## 数据流

1. Web/API 上传 → Archive 鉴权/校验/MIME 嗅探 → 临时写、校验、原子落盘 → Document + Revision 事务登记。
2. 或只读 Source 扫描 → SourceEntry → 外部 Revision。首次目录映射仅初始化逻辑分类。
3. Archive Job 创建 ParseRun → 二进制 multipart 发送给 Converter → 轮询任务 → 验证 ParseResult → 拉取受控 artifacts。
4. Archive 保存派生文件、块、候选元数据 → 事务切换当前成功解析 → 增量重建单文档 FTS。
5. UI 默认请求 blocks/metadata → 结构化阅读；点击关联原件时鉴权并校验 Revision 可用性后预览/下载。

## 存储边界

| 存储区域 | 所有者 | 约束 |
|---|---|---|
| database | Archive | SQLite、短事务、每连接 FK ON/WAL，备份一致性 |
| managed | Archive | 原件不可就地覆盖；新字节建新 Revision |
| derived | Archive | 按 ParseRun 隔离，成功切换引用，历史保留 |
| temporary | Converter | 任务隔离、资源限制、TTL 与主动清理 |
| external | 宿主机只读挂载 | 配置别名白名单、真实路径检查、无写回/物理删除 |

Converter 无需直接挂载 Archive 数据库或 managed 写权限；文件经受信 HTTP 边界传递。未来内部集成可以复用纯解析模块，不能让解析库接管业务元数据写入。

## 一致性/异常

上传落盘与数据库并非分布式原子事务，需设计孤儿清理/失败恢复，禁止数据库引用未完成文件。任务 claim/租约/进程数需要 T07 定义；SQLite 多 worker 写竞争以实际测试控制。新解析失败保持旧 current_parse_run_id，UI 由 content_revision_id/stale_for_current_revision 判断展示含义。

## 选型状态（不能误当最终决定）

建议沿用 React 来复用原型；建议 FastAPI 作为 API。ORM/迁移框架、解析依赖、OCR 引擎、中文分词器、文档大小/页数/时间上限、保留配额需在相应任务中选择并记录 ADR。先验证依赖重量、许可证、Apple Silicon 与目标服务器容器兼容性，再定版本；不在无实测时承诺 10 万档案吞吐量。

部署必须区分 UI 会话和服务 Token；Converter 默认仅内网，healthz 仅容器检查。生产运行配置与凭证由部署环境提供，不提交仓库。

T01/T02 已固化选择见 ADR-015，运行步骤见 DEVELOPMENT.md；其余依赖仍按对应任务实测决策。

T03 已提供管理员 Cookie 会话与 API Token 边界；认证表属于 Archive，CLI 密码重置会撤销全部凭据，详见 ADR-016。

T04 已实现本地 managed 对象存储，发布与恢复协议见 ADR-017/DEVELOPMENT。
文件持久化先于数据库引用；崩溃后可以遗留完整孤儿对象，T15 再实现数据库感知清理。
现有存储层不能替代 T06 文档事务或 T08 HTTP 上传，也不接入 external。

T05 分类定义服务位于 catalog.py，复用 SQLite 跨空间约束与 T03 鉴权；写锁内复核凭据，读请求使用一致性事务。非空目录删除依赖文档生命周期，当前明确501，详见 ADR-018。

T06 已实现 DocumentService 内部事务，管理托管文件登记、Revision追加和软删除/恢复；事件统一由 document_events.py 写入，公开接口及状态投影仍待后续，见ADR-019。

T07 Compose增加Archive worker执行容器（非新业务服务），与API共用持久SQLite和托管卷；
Converter仍不访问Archive数据库。worker子进程执行限时，队列恢复与围栏规则见ADR-020。

T08 上传服务位于uploads.py：受限接收、保守MIME与原子落盘后，档案/版本/事件/parse任务同事务登记；解析handler仍未实现，201只代表原件安全归档。详见ADR-021。

## T09 公开管理投影

Document API复用DocumentService写事务与共享快照/版本检查；Folder删除以同连接完成子树档案和审计更新。
读API返回字段白名单，独立投影原件可用性、当前版本处理状态及旧内容stale；不输出托管键或来源文件路径。

## T10 批量处理

Batch API把已枚举选择ID与精确版本映射持久化到JobQueue；worker子进程在租约围栏事务中执行结果回调。
有界批量的业务失败用逐项savepoint隔离，档案/事件/最终结果与任务完成原子提交。Undo复用原事件快照和版本校验。
重新解析/元数据批改不接占位成功handler，暂返回501，等待对应业务服务。

## T17 字段定义边界

Field API共享catalog空间检查、写锁内认证和唯一性冲突处理；存储字段定义与模板配置，保留已有文档值。
资源界限在Pydantic输入和写锁内总量检查实施；不启动索引/解析，不将开放约束JSON当成已执行规则。T18负责实际值类型与归档校验。

## T18 统一字段值校验

类型/约束与filing检查集中metadata_values.py，HTTP、整理、批量类型/状态与撤销均复用；metadata.py提供版本化人工值与显式采纳。
规则配置更新也验证已知词汇，旧未知配置保留但使用时拒绝；regex匹配具独立超时。候选生成/索引仍与人工事实写入隔离。

## T26 Web运行边界

web/生产React组件分为会话入口、工作区导航、列表、详情、上传队列、API/通用UI；数据请求并发获取并在切换/卸载时取消。
Vite开发时/api代理到Archive；生产由Archive公开编译静态资源同源承载，Cookie/CSRF只在内存与HttpOnly Cookie中流转。
HTML提供CSP/no-store/nosniff，静态路径不能访问业务卷；API鉴权在middleware保留，仅GET/HEAD的根HTML/favicon/assets豁免。
Docker不运行Node前端进程，构建在宿主按锁生成dist；生产仍为两个业务服务和独立worker进程。无数据库迁移。

## T27 整理与拖放

web/src/Operations.jsx集中操作草稿、持久任务提交/轮询、逐项结果与一次撤销；Workspace管理固定选择及OS/内部拖放，Library只承载选择和拖动入口。
分类上下文随草稿固定，导航不改变已接受任务。关闭弹窗可继续浏览，完成后刷新当前资源且不清除后来产生的选择。
复用现有REST、worker、SQLite与托管存储，无新服务/依赖/迁移；内部拖放不操作物理文件。

## T11 外部读取边界

source_paths.py提供SourceMounts，输入仅管理员白名单中的alias和严格相对路径；不提供写入/重命名/删除方法。source_api.py只提供鉴权别名发现，不访问业务源表。
按目录描述符遍历并拒绝符号链接，根和每层后代检查ST_RDONLY；普通文件通过固定inode描述符读取，避免路径换成符号链接后逃逸。
Linux的O_PATH、/proc/self/fd与fstatvfs为运行前提；无额外服务/依赖。外部来源须分别只读挂载到API和worker，Converter不挂载。

## T12 来源与预扫描数据流

source_api负责别名配置、健康投影与库存查询，source_scans负责有界只读遍历；所有字节访问仍经过source_paths，无外部写回。
创建预扫描事务内登记scan_runs及Job；队列claim/failure/complete在同一事务同步关联扫描状态/结果，租约恢复同样适用。
worker将设置中的白名单显式送入spawn子进程；子进程仅读取并返回小型计数结果，parent围栏完成落库。目录栈最多64层，流式scandir，不收集完整文件列表，不将私有路径放进错误/结果。
即时挂载health、扫描状态与已有条目状态独立；来源健康失败不执行批量missing。首扫/增量、规则和来源前端待后续。

## T13 首扫准备与原子发布

source_scans.inventory供预扫描与首扫复用，描述符逐段访问/只读校验，流式scandir及文件/目录观察前后指纹校验；预扫描仅计数，首扫读取字节并hash/sniff。
source_initial将元数据流式写入匿名TemporaryFile，不缓存完整列表或复制原件；准备成功后，子handler在受租约保护的JobQueue.complete回调中原子publish，parent只接收committed确认。
publish以临时SQLite映射表将相对目录映射到逻辑Folder，注册外部SourceEntry/Revision与稳定Document，排幂等parse并写审计；Job/scan_runs/来源完成标记同事务。所有失败回滚，匿名清单由进程/内核清理。
长期数据库不保存持续目录映射；first完成后重放原任务，后续增量不得重建物理层级。无新服务/依赖/迁移，Converter未获外部卷访问。

## T14 增量与缺失确认

source_initial.prepare为首扫/增量提供相同只读hash清单；source_incremental使用临时SQLite观测表与旧库存表按路径/hash分类，在JobQueue.complete围栏事务内发布。
新增文件复用register_external；内容更新只追加外部Revision及parse Job，移动只更新Entry真实路径，逻辑目录/人工值不变。needs_match允许新Entry尚无Document，避免歧义自动合并。
持久root_digest拒绝错误/替换挂载，missing证据绑定来源和独立completed增量。JobQueue失败状态同步同时清除未完成凭据，原Entry状态不动；完成事务更新成功扫描时间，不更新首次完成时间。
Document列表/详情/版本投影即时探测已授权挂载，不把扫描错误等同于解析失败，也不把正常外部文件冒充可下载字节。服务/依赖数不变，无前端改动。

## T15 排除、永久清理与managed GC

exclusions.py集中精确路径规则/待处理屏障/epoch，inventory在文件打开前过滤；prepare持读取快照并传递epoch，publish校验后过滤观测与旧Entry，保持缺失证据语义。
maintenance.py提供接口、围栏exclude/purge处理、GC与本地排队CLI。清理任务不调用任何外部文件写入/删除函数；外部来源永久清理会先写排除规则再删除系统引用。
GC仅遍历managed/sha256合法键，以store独占锁+数据库写锁检查全部Revision引用后unlink/fsync；注册/追加持shared锁直到DB提交，统一store→SQLite锁序。候选持久化使24小时延迟/孤儿恢复可跨重启。
无新服务/依赖；派生字节GC待其安全存储协议，当前原件外部卷不受清理器访问。

## T28 来源Web边界

Sources负责当前空间来源/库存/排除读取与任务回执，SourceWizard负责两步只读别名配置；关联档案复用Detail。相对路径导航直接使用现有relative_prefix完整段查询和稳定分页，不枚举无界全树。
读请求在条件变化时abort，写操作捕获来源/条目/版本快照且不自动网络重试。任务串行有界轮询独立于来源选择，完成后刷新当前空间资源；切空间卸载仅停止浏览器查询，持久worker任务仍执行。OpenAPI/数据库保持T15版本，未新增端点或迁移。

## T19 独立转换传输

conversion_api负责受限multipart/任务读取/流式受控产物；conversion_store拥有私有临时SQLite和文件、排他进程锁/单runner/容量/TTL；conversion_child执行有资源限制的最小TXT解析；conversion_models验证规范结构。子进程仅获必要PATH/LANG/固定包路径，不继承服务Token，限CPU/地址空间/文件大小/描述符和墙钟，stdout/stderr不泄露原文。
converter_client是Archive内部纯HTTP客户端，二进制流上传/有限轮询、严格结果/身份/有界JSON、临时下载校验后开放；拒绝代理环境继承及重定向，不接客户端服务URL。Compose仅给worker既有Token及内部URL，Converter仍没有Archive数据库/managed/external卷。当前parse handler及正式持久化不接入，留T22实现幂等/版本/租约围栏/旧成功正文保留。
临时任务单次执行，幂等作用域为当前spool生命周期。崩溃running失败不重放，queued同spool可恢复；容器tmpfs丢失可返回404，由Archive未来按持久任务预算协调，不宣称远端exactly-once。

## T20 六格式适配

conversion_formats提供共用Output预算、SafeZip、确定性文本解码及DOCX/PDF/MD/EPUB适配，conversion_html只提取安全文本结构，conversion_child分发并生成带hash的plain_text/Markdown。解析始终在资源受限子进程中，主进程对结果/身份/所有产物逐个校验，非跟随打开并先检查普通文件，避免产物路径/特殊文件越界。
新增纯Python依赖与锁定许可见THIRD-PARTY，无系统工具/模型运行依赖；PDF页数/内容流与ZIP成员/膨胀/单成员/比率由服务配置公布，源码和模型保持真实定位。HTML/Markdown不运行浏览器或下载资源，不发布原始活动HTML。T22的正式派生store和事务管线仍未实现。


## T21 更新 · 2026-10-17

T21：转换子进程内增加受限PDFium/Pillow栅格解码与按需Tesseract OCR，模型只读固定哈希；PNG缩略图经过重新编码，按源页/帧顺序且有页数/像素/输出预算。服务能力不等于Archive已持久化结果，数据流第3～5步仍待T22/T23/T29。技术选择ADR-036。


## T22 持久解析事务

parsing.begin在租约事务中创建独立ParseRun与attempt映射，parse_requests顺序由入队事务确定，不能用完成时间决定胜者。托管原件通过安全store核验；外部原件只从管理员别名/当前条目路径用O_NOFOLLOW只读打开，复制到私有临时文件并复核大小/hash/读取前后身份，绝不因同大小/mtime就接受不同内容。转换器HTTP和产物下载在DB写事务之外，远端规范身份/字节预算/hash继续由ConverterClient验证。

派生store位于data/derived，复用ManagedStore的no-follow、普通文件、限额、fsync、原子无覆盖和内容地址key；锁独立于原件store。先落字节，再在同一JobQueue.complete事务中插入块/候选/资产顺序并切current_parse_run_id，人工业务字段不变。共享store锁跨落盘到注册，GC独占store后再取DB写锁。中断允许留孤儿，绝不回滚时删除可能被并发引用的字节。parse_asset_order保留相同图像帧的逻辑顺序，derived_assets复用物理对象。

失败/租约过期/父worker超时钩子关闭当前尝试，不清空旧正文。过期Revision、回收档案或非最新请求结果discarded，任务与丢弃原因一起提交；状态查询也按请求代次/尝试排序。每次有限重试使用新ParseRun，不跨丢失tmpfs承诺exactly-once。远端任务ID持久留证，完成时主动DELETE；异常/被杀留下的任务依赖Converter墙钟上限+TTL兜底，不谎称跨容器主动取消。


## T23 缓存读取与显式重解析

content.py以SQLite只读快照查询当前成功指针/历史/候选，分别返回有界分页对象；history不嵌套所有候选，避免历史×候选放大。读取前用SQLite length(CAST(... AS BLOB))聚合所选页预算，序列化前复核16MiB总响应。blocks来自持久结构/真实locator；text/markdown经安全派生store核对描述符及实际字节后返回JSON字符串，不运行原件解析或HTML。

来源当前健康只用于availability/stale投影，正文仍读本地缓存；缺失源不会消灭旧内容。重解析在鉴权写事务复核document_version/Revision与回收状态，以档案+request_id生成内部幂等键；同请求复用、不并行排同Revision的不同活动请求。force用于明确重跑已有成功，不绕过活动任务冲突或版本/租约围栏。只新增持久Job，不先清空正文或人工字段；后续仍由T22负责原件/hash/资源验证与晋升。候选采纳沿用T18，而不自动映射同名字段。


## T24 版本化FTS增量索引

见ADR-039。tokenizer.py生成确定词元；indexing.py以SQLite持久脏代次、有限JobQueue和租约围栏完成单档案增量/显式重建。普通worker自动发现提交后的脏记录，交替优先索引避免解析积压时饿死；--once仍只处理已有任务，便于受控维护。索引仅读数据库缓存与人工业务字段，来源离线不要求重新打开原件。失败/失去租约/新编辑不能清除最近成功索引。公开搜索与过滤排序由T25接续，阅读界面仍T29。


## T25 统一检索查询

search.py共用GET简单与POST高级查询，复用tokenizer字面词元AND、真实FTS5/bm25及空间校验；数值/日期元数据使用既有typed列索引的无关联子查询，标签/类型/目录范围作用于业务SQL。索引范围统计、命中数和分页在同一读事务；不读原件重新解析。状态筛选仅观察已有投影（真实managed probe/来源挂载健康与任务状态），请求内最多5000档案并缓存状态，外部文件系统不享有SQLite快照。3秒SQLite预算/1MiB请求/16MiB响应及先验页预算，明确失败不静默截断。见ADR-040与OpenAPI0.4.19。


## T29 生产阅读组件

ContentReader.jsx以完整请求路径隔离结果、AbortController取消过期读取；正文/候选/历史独立并行，各自加载/错误/分页，不向全局挂载无限正文。Detail负责业务字段/版本读取和刷新，采纳复用既有CSRF ApiClient与版本保护API。React文本与语义table显示块，Markdown源文本不走HTML转换器。阅读测试使用独立临时Archive/store、真实TCP Converter与worker；生产服务/数据库未改。


## T30 查询状态与一致范围

searchState.js处理有界UI类型转换及版本化URL片段校验，SearchPanel.jsx只维护草稿，Workspace用同一fetchDocuments读取可见页/100项批量快照，Library分别展示范围摘要/结果/错误。列表条件变化Abort旧请求、清除批量选择；URL恢复先验证空间，popstate/自动页码修正replace而非产生循环历史。普通GET及高级POST复用既有ApiClient鉴权/CSRF，不改数据库或索引算法。
