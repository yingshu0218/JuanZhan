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
