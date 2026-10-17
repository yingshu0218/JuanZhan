# 测试与交付验收

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
