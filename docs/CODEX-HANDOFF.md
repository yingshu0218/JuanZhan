# 给 Codex 的开发交接

在 Codex 打开或克隆本仓库后，可直接使用下面任务：

> 阅读根目录 AGENTS.md，再按 docs/README.md 阅读状态、PRD、架构、数据库、API、UI/UX 与开发任务。现有 docs/prototype 是已接受的视觉参考，只有示例数据，不是生产实现。优先落实“默认看结构化内容、点击关联文件才看原件”的最新交互，不复制旧默认原文行为。先执行 M0 的 T01→T02，再依次推进 T03～T07；本轮先完成 T01/T02 并提交可运行两服务骨架、SQLite 迁移与真实测试。保留全部现有资料，不接 LLM，不写入外部目录。实现前记录生产技术选择、未覆盖的契约与最小目录结构；完成后报告启动命令、测试结果、Commit、修改文件、未实现项，并更新 docs/STATUS.md。不要以 UI 假数据或 Mock 通过代替实际完成。

## 初始上下文要点

托管与原地索引共存；首次目录导入以后解耦；一主 Folder 多标签；同哈希可为不同业务档案；人工字段优先；扫描/OCR异步；失败保留旧正文并标 stale；原件不可用与解析失败分开。详细数据/API规则以 reference 为准。

## 参考原型使用

进入 docs/prototype 后 npm ci、npm run dev；构建 npm run build。仅用于视觉与行为参考。生产代码放置在 T01 明确的新目录，不把预览运行时/示例状态照搬为生产安全架构。

## 首轮交付门槛

- Compose 两服务健康检查通过（若 Converter 仅骨架，能力接口如实声明未实现）。
- 实际 SQLite 迁移可重复启动，每连接外键启用；非法跨空间引用/循环目录有失败测试。
- 配置与凭证分离，外部挂载只读；服务不能接受任意路径。
- 如开发环境受限无法跑 Docker/测试，说明未验证，不能声称通过。
- 继续 T03 前补会话/Token 操作 API；继续 T29 前补原件预览与候选映射契约缺口。

## 当前接续点 · T04 后

T01～T04 已完成基础交付，实际证据见 STATUS/TESTING。下一切片为 T05：
Space/Folder/Tag/DocumentType 服务与契约 CRUD；遵循跨空间拒绝、目录防环和同级名称唯一。
复用 T03 鉴权和 T04 ManagedStore，不重建项目、不把旧首轮交接理解为需要重复实现。
T06 再接入 Document/Revision/Event 事务，T07 接任务，T08 实现真实 HTTP 上传。

## 当前接续点 · T05 基础管理后

T05 已交付分类定义接口，下一切片 T06 为 Document/Revision/Event 事务与软删除模型。
不要重复实现旧首轮 T01/T02。目录非空删除两策略仍501，需在 T06/T09 使用文档事务补齐；
标签删除当前已有版本递增与审计，后续统一到文档服务，保持现有行为与测试。

## 当前接续点 · T06 后

接续 T07：SQLite 持久任务、worker、claim/租约、有限重试与幂等，先读 T06 DocumentService 与审计工具。
Doc 服务为内部接口，公开上传/列表/状态投影/回收站路由待 T08/T09；恢复需要 expected_document_version。
不要把 get_record 的内部事实当作完整公开 Document 响应，也不要在重试失败时删除共享文件。
T05 非空目录两策略仍501，需在文档生命周期与T09接口层补齐。

## 当前接续点 · T07 后

下一切片T08：真实单文件HTTP上传、MIME嗅探、重复提示和异步任务返回。
复用ManagedStore、DocumentService和JobQueue，先保证原件安全落盘，再将档案/Revision/事件/任务
同事务登记。现有DocService和Queue的事务边界需按接入需要整理，不得嵌套两个SQLite写事务。
尚未实现的parse handler不能返回伪成功；上传成功与解析能力分离，按实际状态反馈。
之后T09补公开列表/详情/整理/回收站及非空目录策略，M0基础不等于产品已完成。

## 当前接续点 · T08 后

下一切片T09：公开Document详情/列表/状态投影、属性/标签/整理、版本冲突与回收站接口，
并接续T05非空目录删除策略。上传已接通，保持201 saved与解析结果分离，不重建旧骨架。
复用DocumentService/ManagedStore/JobQueue，先核对原件实际可用性和旧ParseRun stale规则，
不把内部get_record直接当完整公开Document。T18完整字段类型验证尚未实现，应如实限制依赖操作。

## 当前接续点 · T09 后（优先于上文历史交接）

T01～T09已完成，下一切片为T10：按路线图/契约实现批量操作，明确选择快照、每项版本与错误、撤销边界。
复用现有DocumentService/事务与审计；不得让失败项被宣称成功，或撤销覆盖后续人工编辑。
M1后续仍含T17/T18自定义字段与完整归档验证、T26/T27生产界面。
T09已实现非空目录两种策略，Source引用返回409；q搜索/复杂归档约束返回501，外部未验证原件返回unknown。
112项测试及真实容器验证见TESTING，OpenAPI版本0.4.6；未修改已应用迁移或外部原件。

## 当前接续点 · T10 后（优先于上文历史交接）

T01～T10已完成。下一切片为M1的T17自定义字段定义/管理，复用现存field_definitions和类型模板；
接续T18七种字段类型/约束/完整归档校验，再接T26/T27生产列表/上传/整理界面。
批量操作已接持久队列，支持七种逻辑操作；POST documents/batch必须提供1～100个不重复ID及完整expected_versions。
snapshot仅代表调用者已枚举的集合，服务端持久化后不重新查询。全部异步，64KiB任务JSON上限。
POST jobs/{id}/undo幂等地创建一次撤销，检查原执行后版本和当前引用，冲突只失败该项。
126项测试与真实HTTP/worker/重启验证见TESTING，OpenAPI0.4.7、44paths。未新增迁移、未写外部原件。
reprocess/set_metadata仍501；T17/T18实现时接入真实字段服务，不复制简化的存储规则。

## 当前接续点 · T17 后（优先于上文历史交接）

已完成T01～T10及T17。下一切片T18：接入metadata_values七类型验证、精确Decimal×10000、日期/false/null、版本冲突和候选采纳。
复用fields.py字段定义、catalog模板和DocumentService事务/审计；切类型/停用不得删除历史值，候选不得自动覆盖人工确认字段。
T17的constraints目前为开放词汇有界JSON（紧凑16KiB、深度8），没有求值；T18必须明确规则词汇/选项ID形状和兼容策略，未知规则不得静默忽略。
带复杂约束的归档当前501，T18接入统一值验证后替换；字段停用不隐式去掉原必填模板要求，管理员需显式调整模板。
原模板可保留/调整停用字段绑定，但新增绑定拒绝；字段key/type/space在API不可修改，未提供硬删除。
144项测试和真实HTTP/重启验证见TESTING，OpenAPI0.4.8、44paths。T11～T16仍待来源里程碑，不因跳到T17而视为完成。

## 当前接续点 · T18 后（优先于上文历史交接）

T01～T10及T17/T18完成，下一切片T26生产Web导航、档案列表/网格、真实上传队列与结构化详情外壳，接续T27。
读最新UI-UX/DECISIONS，沿用用户接受的视觉原型但不直接把假数据App改成生产状态；默认结构化数据，关联原件按需进入。
登录/CSRF/metadata/任务/管理已有真实接口；转换/正文/下载/预览未实现，界面如实展示状态，不伪造解析正文或下载成功。
metadata.py和metadata_values.py已统一值/归档校验；已filed写值、单项/批量切类型及整理复用同规则。
constraints新配置仅接受已知词汇；历史未知键501，需显式修复。Decimal普通十进制字符串、最多4位、±9000000000000.0000，按×10000存储。
候选采纳仅接受当前Revision/current_parse_run_id的completed候选，事件保留候选ID；原候选不删除，不自动改写人工值。
批量set_metadata/reprocess仍501，生产UI不得假装支持；真实候选生成留T19/T23。
169项测试及HTTP/容器重启验证见TESTING；OpenAPI0.4.9、44paths，无新迁移。T11～T16仍待来源里程碑。

## 当前接续点 · T26 后（优先于上文历史交接）

T01～T10、T17/T18、T26完成。下一切片T27：收件箱整理、文件夹移动/标签/收藏与回收恢复、批量操作栏、OS/内部拖拽。
复用web/既有ApiClient/CSRF/组件，不改docs/prototype假数据应用；任务结果和版本冲突要逐项可见，撤销不覆盖新编辑。
保持默认真实结构化字段/状态，关联原件信息按需dialog；下载/预览/正文尚无真实接口，不能画出成功按钮或示例页码。
生产构建先npm ci --prefix web、npm run build --prefix web，再Compose build/up；产物不提交，Dockerfile只复制web/dist，不需要镜像内联网Node构建。
Browser插件当前不可用，已用Playwright+系统Chromium；测试命令、隔离临时服务/随机密码、视觉差异记录见TESTING。
171项Python测试、3条E2E与三容器通过；OpenAPI0.4.10共47路径，新增的三组仅公开Web资源，业务API鉴权不变。
云环境install_script/start_skill草稿已更新但未发布；进程不会跨任务保留，按保存步骤重新启动，不擅自设置/重置正常实例管理员。

## 当前接续点 · T27 后（优先于上文历史交接）

T01～T10、T17/T18、T26/T27完成；下一切片T11只读Source/SourceEntry与挂载别名，外部原件零写入。
保留web/现有设计及结构化优先交互。Operations统一单项/批量请求，固定选择ID/版本/空间与分类资源上下文；成功提交后才清空选择。
当前页与筛选结果快照有别，后者最多100份，超过明确拒绝；导航/筛选变化清空选择，不把后来上传混入旧任务。
restore已加入批量契约，恢复保留字节/可用目录并可版本保护撤销；失败项独立，不覆盖更新。
OS Files进入真实上传队列，内部拖放用页面私有令牌+同空间快照，仅改逻辑引用；跨页面/跨空间不承诺支持。
操作结果仅本页面生命期保留，刷新恢复/任务中心留T31；写请求网络失败不自动重试，读轮询可重试，关闭弹窗不终止已接受任务。
174项Python及8项真实E2E通过；OpenAPI0.4.11/47paths，无新迁移或依赖。构建/安装/云配置步骤不变，已有草稿仍未发布。

## 当前接续点 · T11 后（优先于上文历史交接）

T01～T11、T17/T18、T26/T27完成。下一切片T12：Source/SourceEntry数据访问、预扫描持久任务与独立来源健康；预扫描不创建档案，离线不批量标missing。
source_paths.py是外部读取唯一入口；客户端只传已授权alias和严格相对路径，绝不能调用Path.resolve后直接open或复用客户端绝对路径。
管理员JUANZHAN_SOURCE_MOUNTS是JSON别名→容器绝对根路径，默认{}，API/worker须配置同一别名及只读bind。配置坏值启动失败且不回显路径。
逐段openat+NOFOLLOW，O_PATH先查普通文件再通过/proc/self/fd固定inode打开字节；每层fstatvfs检查ST_RDONLY，拒绝嵌套可写挂载。
Unicode/大小写保留磁盘精确名称，不把不同规范形式合并。所有符号链接（包括内部链接）、FIFO/目录/设备、绝对/盘符/反斜杠/空段/dot/dotdot路径拒绝。
GET /source-mounts鉴权/no-store，仅alias/status/error_code，状态是即时探测不是成功扫描证明；读取仍重新验证。
202项Python通过；scripts/smoke_sources.py用隔离真实bind/SQLite/HTTP验证，无用户目录或正常密码改动。OpenAPI0.4.12/48paths，无新迁移/依赖；web未改。
云环境安装/启动命令不变，不为默认开发环境自动配置用户来源；已有配置草稿未发布状态不变。

## 当前接续点 · T12 后（优先于上文历史交接）

T01～T12、T17/T18、T26/T27完成，下一切片T13首次tree/flat导入、逻辑目录复制、事务入库与首扫幂等。
source_api.py已支持外部来源POST/GET、详情、entries分页与preview-scan；/scan和exclusions尚未实现。SourceEntry当前仅读取，T13扫描负责写入，严禁preview偷偷创建条目或档案。
SourceCreate只收别名；same_space校验初始/后续目标目录，重叠检查全局生效。source_paths.identity用私有inode/dev及mountinfo根路径检测不同bind别名，根不可用时不能证明分离，拒绝新注册；绝不将私有身份键返回HTTP。
source_scans.preview通过T11描述符边界统计已知候选扩展名，不读取解析正文；默认访问100000项、深度64、120秒和最多3次尝试。上限属于实施保护默认，未宣称大规模吞吐验收。
Job.target_type=source_preview，target_id=scan_runs.id，payload={}。同来源queued/running请求返回原Job；终态后显式POST新建。Worker显式传递settings.source_mounts到spawn子进程，不依赖偶然继承环境。
JobQueue在claim/failure/complete中同事务同步scan_runs和来源状态，包含租约过期/耗尽/超时；complete仍受租约围栏保护。preview不写last_successful_scan_at或initial_import_completed_at。
来源即时health与最后扫描状态分开：挂载ready但上一预扫描失败时status可为error。离线读取库存照常，不改available/suspected_missing/missing；后续T14再实现缺失确认。
entries.relative_prefix为完整目录段，无尾斜杠，%/_字面匹配；按规范路径/ID稳定分页，每页最多100。未知字段与任意根路径均拒绝。
209项Python及真实容器HTTP/worker/RO挂载/重启验证见TESTING；OpenAPI0.4.13/48paths，无新迁移/依赖/前端改动。云配置安装启动不变，不新增用户挂载或发布既有草稿。

## 当前接续点 · T13 后（优先于上文历史交接）

T01～T13、T17/T18、T26/T27完成，下一切片T14增量、可信重关联、失联二次确认与离线处理。incremental当前明确501，不把initial重复请求当成增量。
source_initial.initial在写锁外只读遍历/分块hash/sniff，匿名TemporaryFile只暂存相对路径/hash/统计等元数据（64MiB上限，无原件字节），退出/kill自动清除。
同一fenced complete事务publish逻辑目录、SourceEntry/Document/外部Revision、document_created(actor=source_scan)、幂等parse Job，随后Job/scan_runs与sources两个完成时间一起提交。失去租约/异常整次回滚，不保留半套首扫。
共享source_scans.inventory验证root/逐层只读、NOFOLLOW、普通文件、前后dev/ino/size/mtime/ctime；目录前后也检查变化。100000访问项/64层，initial限300秒/3次尝试；写入长于剩余租约会回滚，不允许绕过围栏。
tree在initial_target_folder_id下创建所有安全相对目录（含空目录），规范名碰撞或现有同名目录SOURCE_FOLDER_CONFLICT，不合并；flat不复制目录。根文件放初始目标。临时映射表随事务/连接消失，不形成后续物理镜像。
初始配置triage可filed或needs_review；同hash不同路径各自Document，无managed_objects。SourceEntry保存精确Unicode路径/mtime_ns/identity_hint及last_seen_scan_id，Revision只存相对历史路径，不承诺旧字节可恢复。
首扫成功后重放返回原completed Job，保持后续人工改名/逻辑移动/版本，也不导入后来文件；preview与initial活动互斥。已有遗留条目而完成标记为空时SOURCE_INITIAL_STATE_CONFLICT，不能盲目覆盖。
解析仅排持久任务，真实handler仍未实现；原件availability维持unknown，不把登记成功画成已转换/可预览。来源UI仍留T28，安装/云配置步骤不变，无新迁移或依赖。

T13验收：216项Python通过，scripts/smoke_initial.py与smoke_sources.py真实容器验收通过，正常Compose三容器健康；OpenAPI0.4.14/48paths。T14必须延续这些契约与原件零写入边界。

## 当前接续点 · T14 后（优先于上文历史交接）

T01～T14、T17/T18、T26/T27完成。下一切片T15排除/取消索引、回收清理与托管GC，外部字节零写入/删除。来源UI留T28，人工匹配写接口、自动扫描调度尚未实现。
新增0004_source_observations.sql（已应用，不得改动）：source_root_baselines保存私有root_digest，source_missing_observations保存entry→scan_run确认凭据；升级保留前三迁移checksum和旧来源事实。
source_initial.prepare复用安全遍历/全量hash与匿名元数据清单；首扫保存根摘要。source_incremental准备后在围栏事务用临时SQLite观测/旧库存表分类发布，内存不缓存全部条目，300秒/3次、100000访问项/64层/64MiB清单边界不变。
同来源preview/initial/incremental活动互斥，同模式活动请求复用Job；incremental必须已完成首扫，成功后新请求产生独立扫描。Job.target_type=source_incremental，target_id=scan_runs.id；last_successful_scan_at更新，initial_import_completed_at不改。
既有路径全量hash比较当前Revision，改变则追加新外部Revision、版本/审计/parse Job，保留current_parse_run_id及所有人工字段/分类/删除标记；统计unchanged不增Document版本。改路径不重写历史source_path_at_capture。
只有旧来源全部条目与新观测中hash+size均唯一才自动改路径，inode仅作提示，重复hash永不据此自动匹配。歧义旧条目和新无document_id条目均needs_match，后续扫描保持待人工处理，不擅自建重复档案。
未观测到的既有Entry需两个独立completed增量才missing；失败会清除确认凭据但不改Entry。preview不推进确认；重现清凭据并恢复available。状态/路径/Revision变化递增文档版本并写source_updated，未覆盖人工内容。
根摘要比较dev/inode/物理根（只存hash，不外露）。不同只读空挂载SOURCE_ROOT_CHANGED；旧库无摘要，只有精确路径+hash+size+inode锚点或原库存为空可建立，否则SOURCE_ROOT_UNVERIFIED，不能判整库missing。已有摘要变化不自动重置，需恢复/核实部署根。
Document投影实时检查挂载，来源离线独立于条目状态和解析；正常外部字节仍unknown，不承诺当前可下载或历史字节恢复。228项Python及真实容器回归见TESTING；OpenAPI0.4.15/48paths。
安装/启动命令无变化，启动自动应用新迁移；不新增用户挂载/凭据或发布云配置草稿。

## 当前接续点 · T15 后（优先于上文历史交接）

T01～T15、T17/T18、T26/T27完成，下一切片T28生产来源向导/预扫描/源树/离线与失联界面；保持结构化优先及既有暖白/墨绿设计，不改参考原型。T16为P1.1，真实转换/OCR/检索/预览仍未完成。
新增0005_maintenance.sql（已应用勿改）：排除epoch、取消索引intent屏障、永久清理最小回执、managed GC候选。前三/四迁移不变，启动按checksum升级至5份迁移。
maintenance.router已接GET exclusions、POST exclude-entry、DELETE exclusion、POST document purge。有关联Document的取消索引需expected_document_version，无关联的needs_match条目可省略；活动请求复用首个任务快照。屏障入队即生效，成功同事务变为规则+逻辑回收，终态失败移除屏障。
exclusions.py提供epoch/blocked/verify，安全遍历在打开字节前跳过精确路径，准备期持只读SQLite快照；发布复核epoch并再次过滤观测/旧库存，过期则SOURCE_CHANGED重试，不能把漏掉的排除文件判失联。移除规则不自动恢复Trash Document；永久清理后移除规则可重新建档。
purge需confirm_document_id及expected_document_version，API和worker均校验Trash/版本；完成同一围栏事务清Doc/Entry/Revision/ParseRun/元数据/搜索记录，外部路径留排除规则，取消活动文档任务，最小receipt保留ID/版本/Job/时间，支持完成重放。派生物理文件暂保留，不按未定义storage_key删除。
GC仅managed，全部Revision（含旧版本/回收）仍有引用就保留。最后引用解除或孤儿首次发现后至少86400秒；候选只存服务端键和eligible_after。物理unlink在独占store锁与围栏DB写事务中，崩溃回滚可留无引用缺文件记录，下次安全回收。
所有托管登记/追加都持shared store锁贯穿verify与DB提交，锁顺序固定store→SQLite，避免GC删除已验证待提交对象。不要把GC调用放进已持DB写锁的上传路径，也不绕过锁调用注册。
`python -m juanzhan.maintenance gc`仅排持久任务，worker执行；purge自动排至少24小时后的GC，发现新孤儿会排后续任务。无放宽保留期的公开选项。测试时只改一次性fixture候选时间，不改变正常数据保留策略。
OpenAPI0.4.16/48paths；无新依赖或云安装启动步骤。不声称派生物理GC、来源UI、人工匹配/自动调度或正式生产部署完成。

T15最终验收：238项Python通过（新增10项），smoke_maintenance真实容器通过，Archive/worker/Converter升级健康且smoke.py通过；OpenAPI0.4.16/48路径唯一键/引用验证通过。无用户来源或正常卷清理测试。

## 当前接续点 · T28 后（优先于上文历史交接）

T01～T15、T17/T18与T26～T28已交付。Sources/SourceWizard沿用既有Web视觉，使用真实来源/任务/排除API；不修改参考原型。分段目录导航显示库存文件，30项稳定分页，没有目录枚举/空目录接口，不能把当前页当完整树。
下一切片T19：先读CONVERTER/ARCHITECTURE/API和独立Converter OpenAPI，补齐真实输入输出、资源限制与归档worker适配；按路线图接T20/T21/T22，不用空能力声明或假解析结果宣称转换完成。默认结构化内容优先和人工字段保护继续适用。
Sources回执仅当前空间页面生命周期，离开来源导航保留，切空间/刷新需凭Job ID调用已有接口；T31才提供完整中心。自动调度/人工匹配/来源配置编辑API均不存在，不加假入口。取消索引版本冲突应重新读取并确认，不自动重试写请求。
来源浏览器验收需先build web和Archive镜像，再运行npm run test:e2e:sources --prefix web；使用一次性Docker卷/随机管理员/真实只读bind/worker，不接正常卷，清理仅针对本次夹具。现有8项浏览器套件仍用独立主机临时API，无新增依赖。

## 当前接续点 · T19 后（优先于上文历史交接）

T19独立转换协议和最小UTF-8 TXT已实现。接续T20真实六格式基础转换；先读CONVERTER、最新Converter OpenAPI0.4.1与conversion_*模块。不要重复搭建协议，不把最小TXT或unsupported当作完整格式支持。字段只生成候选且人工值优先，定位未知不伪造。
Converter临时spool是独立SQLite+文件、默认/tmp/juanzhan-converter，在Compose128MiB tmpfs内；非Archive迁移/持久业务库。单uvicorn进程持排他锁、单runner、每任务子进程一次；已完成未清理任务也占容量2。清理失败可重试；默认TTL3600秒，活跃任务不被TTL删除。Docker重建tmpfs后任务可能404，原件仍在Archive；同spool重启仅queued继续，running失败不擅自重复。
ConverterClient.from_env读取Compose worker的既有Token及CONVERTER_URL，不把上游未验证产物交给调用者；T22才接管parse handler/ParseRun/DerivedAsset/ContentBlock与围栏提交，现有上传parse仍HANDLER_NOT_AVAILABLE。T19不修改人工字段/当前成功解析，也不提供Web正文或下载入口。
验证：pytest全量253项；scripts/smoke_converter.py独立容器/网络/数据卷真实上传→客户端→Converter→字节验证/清理，正常实例不动。脚本不要求新凭证或依赖；正常Compose升级/新冒烟见TESTING。

## 当前接续点 · T20 后（优先于上文历史交接）

T19/T20独立转换协议与六格式基础解析已完成，接续T21按需OCR/受限预览，不重复搭服务或把基础格式当全部保真。解析代码conversion_formats/conversion_html由受限conversion_child调用，产物生成与协议/临时Store分离，真实文件夹具在tests/format_samples.py。
依赖通过uv.lock/requirements.lock及wheelhouse哈希离线构建：pypdf6.21.1/markdown-it-py4.2.0/defusedxml0.7.1/mdurl0.1.2，许可与范围见THIRD-PARTY。新增资源默认200页、1024 ZIP成员、16MiB膨胀/累计读取、8MiB单成员/PDF解码流、200压缩比，保留T19 CPU/地址空间/墙钟保护；严格XML拒绝DTD/实体，不读取远程资源。
Converter OpenAPI0.4.2/6路径，Archive0.4.16/48路径及5次迁移不变。客户端保持规范/身份/hash核验。T20仅在独立服务输出，尚不创建业务ParseRun/DerivedAsset/ContentBlock，不切current_parse_run_id；T22才能接parse handler、重试/围栏与旧成功正文保留。HTML不返回可执行原始HTML，Markdown由安全块生成，T32仍需负责最终预览/下载安全。
pytest全量279项通过；scripts/smoke_formats.py真实上传六格式→Archive客户端→Converter→结果/资产/清理，SQLite和原件不变，运行需uv run以便生成pypdf真实样本。T19 smoke_converter保留并更新能力/unsupported二进制期望；浏览器9项证据仍属T28，本轮UI未改。


## T21 更新 · 2026-10-17

当前接续点T21之后：按ADR-036/CONVERTER实现的真实OCR与受限缩略图已验收；下一项T22接ParseRun/派生store/ContentBlock/候选和事务围栏，失败保留旧成功正文，不能直接信任远端artifact路径或未校验字节。模型安装先python scripts/setup_ocr_models.py；容器非root读取权限和哈希校验必须保留。Archive0.4.16/48路径、5条迁移保持。T23内容API/T29结构化阅读/T32用户下载尚未实现，生产Web没有正文/OCR UI。


## T22 更新 · 2026-10-17

当前接续点T22之后（优先于历史交接）：parsing.py/derived.py已接worker，0006迁移新增请求顺序/尝试/资产顺序/派生GC，0007补齐关联作用域约束，当前共7条迁移。下一T23公开正文、解析历史与候选读取/显式采纳/重解析入口，先读现行OpenAPI和内容规范，不把已实现入库当公开API已完成。状态与发布都按请求顺序和尝试数围栏；失败/不支持保留旧成功，GC保护全部历史引用。正常Compose启动自动迁移，无新依赖或凭证；原5迁移和.env/管理员/数据卷保留。用smoke_formats.py --persist、--persist --ocr、--persist --external验证；后者实际只读来源API首扫→自动解析，并验证源内容变更拒绝。不得重跑用户旧失败任务或把原件写回。


## T23 更新 · 2026-10-18

当前接续点T23之后（优先于历史交接）：content.py已实现正文/历史/候选分页与版本+Revision+request_id保护的reprocess；Archive OpenAPI0.4.18/49路径、7迁移，Converter0.4.3/6路径。下一T24锁定中文分词引擎/字典及许可，FTS单文档增量重建与tokenizer版本，不能把q示例过滤当全文检索。读写都取真实持久数据；不可在T29前添加假正文。reprocess已成功需force=true，不同活动请求409；同请求编号重发复用。来源离线正文缓存可读且stale，候选采纳仍需显式typed/versioned操作。测试content专项及smoke_formats --persist/--persist --ocr/--persist --external（含真正离线第二实例）。无安装/环境变量/迁移新增，保留.env/管理员/正常数据卷。


## T24 已交付 · 2026-10-18

版本化Han单字/双字词元、繁简及全半角归一、英文数字混排、真实FTS5单档案增量与显式重建已实现；不是语义分词。SQLite触发器持久脏代次，worker自动调度并避免积压饿死，发布受租约/代次保护，失败保留旧成功索引。升级新增0008（总8条），不修改旧7条或重跑旧失败解析；新增OpenCC锁定依赖及Apache-2.0许可。算法、限制和恢复见ADR-039/DEVELOPMENT。

下一切片T25公开检索API：消费真实FTS并实现空间/回收过滤、结果新鲜度、类型安全过滤/排序；当前q仍501，没有搜索UI。T29阅读、T31任务界面、T32下载/预览/备份等仍未完成。Archive0.4.18/49路径、Converter0.4.3/6路径保持。验证结果见TESTING。


## T25 已交付 · 2026-10-18

GET简单/POST高级搜索接真实FTS、繁简中文与混排，支持空间、目录后代、标签any/all、类型范围、来源/状态、日期和七类型元数据过滤；Decimal精确整数缩放、false与空值区分。相关性/多键排序和id次级排序保证固定快照稳定，范围索引/内容不全摘要在零命中时也返回；实时状态过滤有观察预算。首页summary已实现。详细限制及恢复见ADR-040/API/DEVELOPMENT，验证见TESTING。

Archive OpenAPI0.4.19/49路径，Converter0.4.3/6路径；8迁移不变，无新依赖/凭证。下一切片T29：生产结构化正文/元数据阅读及历史/候选来源，按既有分页缓存API接入，安全文本/Markdown呈现；不要重建解析/搜索后端。T30搜索界面、T31任务、T32下载/预览/备份等仍未完成，不将后端检索当完整产品。


## T29 已交付 · 2026-10-18

生产Detail已接真实分页结构化正文、纯文本/Markdown源文本、候选与解析历史；缓存过期/原件状态/OCR和转换警告、定位/置信度均来自API。成功历史可切换，失败历史仅显示实际状态与失败代码；历史/旧Revision候选不提供采纳。当前可用候选需显式选择业务字段并确认覆盖，业务版本/类型验证沿用后端，成功后刷新人工字段。手机返回列表保留父级筛选/页码和选择；正文/历史请求失败不遮住业务字段。

实现与约束见ADR-041/DEVELOPMENT，真实浏览器/SQLite/文件/Converter验证见TESTING。无后端/迁移/依赖/接口变更，Archive0.4.19/49路径、Converter0.4.3/6路径及8迁移保持。下一T30生产搜索界面：接T25 GET/POST及范围不全提示，组合过滤/URL状态/真实空结果；不要重搭FTS后端。T31任务与重解析界面、T32原件预览/下载/备份仍待交付。


## T30 已交付 · 2026-10-18

生产列表接真实关键词与组合搜索，支持标签any/all、多类型、目录后代、来源/状态/日期和七类型业务字段；结果相关性排序、范围不全提示及三种空/错语义已接T25。提交条件和空间/目录/视图/排序/页码可从版本化URL片段恢复，重载/后退支持；草稿不即时查询。批量选择复用同一真实条件，不能扩大到未匹配档案。

边界与输入精度见ADR-042/API/DEVELOPMENT；无新后端/迁移/应用依赖，Archive0.4.19/49路径、Converter0.4.3/6路径与8迁移保持。界面整数仅安全整数范围，不静默舍入64位值；无高亮摘要/复杂语义搜索或保存视图承诺。下一T31持久任务界面、进度/错误/重试与版本保护的显式重解析/OCR开关；沿用既有Job/content API，不重搭解析管线。T32原件预览/下载/备份仍未实现，具体验证见TESTING。


## T31 交接 · 2026-10-18

任务中心与显式单档案重解析/OCR已实现，语义及边界见ADR-043；当前Archive0.4.20/50路径，Converter0.4.3/6路径，8迁移。真实验证见TESTING。本地提交不推送；保留.env、管理员、数据卷及原迁移。下一T32安全原件下载/预览与备份恢复，先核对原件访问/路径/鉴权/备份一致性约束，不重搭任务或解析后端。


## T32 已交付 · 2026-10-18

安全当前原件下载、受限PNG预览和生产关联原件弹窗已接真实数据；HTML/SVG/PDF原件均附件下载，不执行活动原件。外部文件只读/白名单/哈希/Revision核验失败不返回不确定字节，旧快照预览明确拒绝。管理员目录包备份/恢复命令已实现，一致SQLite+引用对象、私有权限/校验/新目录保护、恢复旧凭证及租约撤销；真实恢复后下载、预览、正文及中文搜索通过。

详见ADR-044/DEVELOPMENT/TESTING。Archive0.4.21/52路径，Converter0.4.3/6路径，8迁移；无新依赖或安装配置。备份不含外部原件/.env/模型/镜像，需独立保存；无Web恢复、自动调度/加密、原生PDF查看器或历史原件下载承诺。下一T33整体验收与故障注入，然后T34性能/发布/升级恢复手册。T16托管接管及批量reprocess仍未实现，不声称完整产品已验收。


## T33 已交付 · 2026-10-18

新增可重复执行的整体验收入口、30项UX/META机器清单及可追溯映射，实际JUnit区分passed/failed/not_run；报告保存在仓库外，不以清单存在/构建通过替代业务验收。新增真实Converter不可达→同Job有限重试恢复、实际只读来源离线缓存、OCR排队→真实识别并保留人工编号的跨功能测试。完整后端/六组浏览器、既有故障注入、恢复演练及现有容器冒烟证据见TESTING与ACCEPTANCE。

无应用/HTTP/依赖/迁移变化，Archive0.4.21/52路径、Converter0.4.3/6路径及8迁移保持；保留.env/管理员/原件/正常数据卷，仅本地提交。下一T34性能基线、版本化镜像及发布/升级恢复手册；T16托管接管、批量reprocess/set_metadata仍未实现，不把功能验收范围等同全部产品发布范围。
