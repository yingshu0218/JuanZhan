# 生产开发

2026-10-19自动来源扫描：生产来源页展开“自动扫描设置”，输入整分钟1～525600并保存，0关闭。先手动确认首次导入，之后由正常worker每5秒检查到期计划；worker停止时不执行，恢复后仅排一次，不补跑积压。已有扫描不会重复排队；关闭计划不取消已受理任务。数据库保存配置版本/期限/上次自动任务，无系统cron或额外服务。升级后旧配置的正扫描间隔会开始生效，可先核对并关闭不需要的计划。当前9迁移；旧8迁移备份须先用对应旧镜像恢复，再走正常升级，不绕过恢复工具的精确迁移集合校验。

代码在 `services/juanzhan/`，迁移在 `services/migrations/`，测试在 `tests/`。
生产前端在 `web/`；参考原型仍在 `docs/prototype/`，保持独立示例数据。

## 本地依赖与测试

需要 Python 3.12、uv、Node >=22.12 和 npm；SQLite >=3.38，支持 JSON 与 FTS5。
从仓库根目录执行：

```sh
UV_CACHE_DIR=/workspace/.uv-cache uv sync --frozen
python scripts/setup_ocr_models.py
UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q
```

`uv.lock` 固定开发依赖；`requirements.lock` 为容器生产依赖与哈希清单。
依赖更新后用 `uv export --frozen --no-dev --no-emit-project -o requirements.lock` 同步。

## Compose 启动

需要 Docker Engine 和 Compose。首次创建本地 `.env`，勿覆盖已有文件：

```sh
python - <<'PY'
from pathlib import Path
import secrets
p = Path('.env')
if not p.exists():
    p.touch(mode=0o600)
    p.write_text('CONVERTER_SERVICE_TOKEN=' + secrets.token_urlsafe(32) + '\n')
PY
python scripts/setup_ocr_models.py
python -m pip download --no-cache-dir --require-hashes --only-binary=:all: --no-deps -r requirements.lock -d wheelhouse
npm ci --prefix web --cache /workspace/.npm
npm run build --prefix web
DOCKER_CONFIG="$PWD/.local/docker" docker compose up --build -d --wait
python scripts/smoke.py
```

Archive 仅绑定宿主机 loopback 8000；Converter 无宿主机端口，仅内部网络可达。
`/healthz` 是无敏感信息的运维端点，不应经生产公共网关发布。
Converter 除健康检查外要求服务 Bearer Token；T19～T21实现转换协议、六格式基础解析、按需OCR和PDF/图片受限缩略图；业务正文尚未接入。
Archive 已提供认证、分类、上传、档案/元数据/批量业务API及同源生产Web；其余范围见STATUS，服务令牌只从运行环境注入。

Archive 命名卷保存 database/managed/derived；Converter 临时区使用 tmpfs，不挂载业务卷。
外部来源默认未配置；T11～T15已支持只读来源API，T28提供Web入口。接入必须配置只读 bind mount 和别名白名单，不能接受任意客户端路径。
停止用 `docker compose down`，保留数据；不要随意使用 `down -v`。

无需 Docker 时，在根目录设置 `PYTHONPATH=services`，执行：

```sh
JUANZHAN_DATA_DIR=.local/archive .venv/bin/python -m uvicorn juanzhan.archive:app --host 127.0.0.1 --port 8000
# 在另一个终端通过安全环境注入 CONVERTER_SERVICE_TOKEN 后运行：
.venv/bin/python -m uvicorn juanzhan.converter:app --host 127.0.0.1 --port 8001
```

## 迁移规则

0001 是 V0.4 DDL 的逐字副本，保留原参考文件。执行器统一管理连接 PRAGMA 和事务，
以 BEGIN IMMEDIATE 串行化迁移，并在同一事务记录文件 SHA-256。
已应用迁移校验和变化、未知迁移、SQL 错误或外键违规均拒绝启动；失败回滚。
新增结构通过新的编号 SQL 迁移，不修改已应用文件。schema_migrations 保留领域版本，
migration_checksums 记录执行器版本与校验和。每个连接启用 FK、busy_timeout，初始化开启 WAL。

这是空库首次接入，不支持自动接管未知来源的历史数据库；投产前需设计已有库升级策略。

云端构建容器 DNS 受限，因此预先在宿主下载 wheelhouse，再在镜像内离线安装并复核哈希；需在目标 Python 3.12、相同操作系统/架构上准备 wheelhouse，跨平台应重新下载对应 wheel，不复制其他平台的二进制包。

## T03 管理员认证

首次部署没有默认管理员密码，也不开放 HTTP 注册。服务正常启动后，通过宿主机信任边界初始化：

```sh
docker compose exec archive python -m juanzhan.admin set-password
```

交互输入并确认至少 12 字符密码，用户名固定 `admin`。同一命令可重置密码，
会立即撤销全部会话和 API Token；不要将密码写入 shell 参数、仓库或聊天。
本地无容器时使用 `PYTHONPATH=services .venv/bin/python -m juanzhan.admin set-password`，
确保 `JUANZHAN_DATA_DIR` 与服务一致。自动化测试可通过显式 `--stdin` 安全管道注入测试密码。

Cookie 默认 `Secure`、`HttpOnly`、`SameSite=Strict`，路径 `/api/v1`。
生产需 HTTPS 反向代理；开发环境若直接使用 loopback HTTP，可在本地 `.env` 设置
`JUANZHAN_COOKIE_SECURE=false` 后重建容器。此项只用于可信本地开发，生产保持 true。
健康检查不依赖 Cookie，不会因未初始化管理员而失败。

生产登录界面已接入的会话流程：

1. GET `/api/v1/auth/session`，获取匿名 Cookie 和 `csrf_token`（十分钟有效）。
2. POST `/api/v1/auth/login`，JSON 含 username/password，携带 Cookie 和 `X-CSRF-Token`。
3. 成功后 Cookie 和 CSRF 均轮换，返回 `authenticated=true`；会话固定八小时有效。
4. 后续所有 Cookie 写请求携带新 CSRF；POST `/auth/logout` 撤销该会话。
5. Cookie 管理员会话可 GET/POST `/auth/tokens`、DELETE `/auth/tokens/{id}`。
   Token 明文只在创建时返回；默认 90 天，允许 1～365 天，持有者拥有管理员业务 API 权限。
   Token 管理与退出仅接受 Cookie 会话，不允许 Bearer 自行增发 Token。
   Bearer 业务请求免 CSRF；存在无效 Authorization 时不会退回有效 Cookie。

所有路径均有 `/api/v1` 前缀。认证响应禁止缓存；输入验证错误不回显密码或 Token。
数据库只保存 scrypt 密码摘要、SHA-256 会话/API Token 摘要；CSRF 值不是登录凭证，存于会话记录。
认证表由 `0002_auth.sql` 增量建立，不改变已应用的 0001。私有认证表以 Unix 秒计算期限，
对外时间统一 UTC RFC3339。失败登录按单管理员全局窗口限流：一分钟最多五次失败，随后返回 429；
计数持久化，不信任客户端代理 IP。匿名会话总量上限 1000，超出返回 429，过期会话创建时清理。
不提供密码找回邮件、多用户与角色权限。

构建后运行 `python scripts/smoke_auth.py`，自动创建独立测试容器及数据卷，
通过 CLI 初始化随机测试密码，验证真实 HTTP 登录/CSRF/Token/撤销/退出与重启持久化，
最后删除测试容器与卷；不会修改正常 Compose 实例管理员。

## T04 托管文件存储

`services/juanzhan/storage.py` 提供内部 `ManagedStore`：

```python
store = ManagedStore(settings.data_dir / 'managed')
store.initialize()
result = store.put(binary_stream, max_bytes=explicit_limit,
                   expected_sha256=optional_hash, expected_size=optional_size)
# 仅在 put 成功返回后，后续业务事务才能登记 result.storage_key/sha256/size_bytes。
with store.open(result.storage_key) as original:
    consume(original)
```

调用者显式给出字节上限；本轮不预设最终上传配额，T08 再结合实际格式与请求层限制确定。
固定 64 KiB 分块读取，过程中计算 SHA-256/size；超限、预期哈希/大小不符、读取中断均不发布。
临时文件在 managed/.staging，完成后 flush、文件 fsync；通过同卷硬链接原子发布到
`sha256/<前两位>/<完整哈希>-<字节数>`，随后 fsync 目标目录并清理临时文件。
目标已存在时重新验证内容，不覆盖；新字节生成新键，不更改原件。文件权限为 0440，
应用不提供覆写方法；拥有卷权限的系统管理员仍能修改物理文件，不将此误称为 WORM 存储。

相同 hash+size 复用物理对象不等于合并 Document；Document/Revision 登记由 T06/T08 实现。
存储层不自行写数据库；后续调用顺序为“完整持久化文件 → 数据库事务引用”。
若文件发布后进程退出或数据库事务失败，可以留下完整孤儿文件，禁止立即删除：
另一个事务可能已引用同一对象。数据库感知的孤儿/引用 GC 留在 T15，届时需与写入协议共同设计。
当前不会自动删除任何已发布对象。

路径仅接受服务生成的存储键，拒绝绝对路径、遍历、URL 和不匹配的分桶键。
目录/文件通过目录描述符与 O_NOFOLLOW 打开，不跟随 staging、分桶或最终文件的符号链接。
这只覆盖托管区，不代表 T11 外部来源白名单和只读扫描已经实现。

所有写入共享卷内 `.store.lock` 的 flock 共享锁；恢复获取非阻塞排他锁。
服务启动自动清理至少一小时前、名称符合规范的普通临时文件；存在活跃写入则延期。
未知文件/符号链接保持原样，不跟随；活跃操作不会被年龄清理误删。
同一存储实例的所有写入和清理必须使用此实现并保留锁文件，不能用外部脚本直接删 staging。
需要手动重试恢复时，在可信本地环境调用 `store.recover_staging()`。
依赖本地 POSIX 文件系统的硬链接、flock 和目录 fsync；不支持对象存储或任意 NAS 作为托管卷，
也未验证断电/硬盘损坏恢复，只验证应用异常与进程中断。

`python scripts/smoke_auth.py` 还验证隔离容器中 SQLite 引用的托管对象跨重启保留，
以及启动恢复能清除预置的过期临时文件。上传/下载 HTTP API 尚未开放；测试中的私有 HTTP
适配器不属于产品接口，未据此宣称 T08 上传完成。

## T05 分类管理接口

当前已实现以下 `/api/v1` 路径，均要求管理员 Cookie 或 Bearer，Cookie 写操作要求 CSRF：

- GET/POST `/spaces`：列出与创建空间。名称不要求唯一，不提供空间编辑/删除接口。
- GET/POST `/folders`、PATCH `/folders/{id}`：创建、重命名、移动目录。
  GET 返回含 parent_id 的扁平树，未传 parent_id 返回全部，传入则只返回直属子项。
- POST `/folders/{id}/delete`：当前仅 `only_if_empty` 可用；子目录、档案（含回收站档案）
  或 Source 目标引用均阻止删除，返回 409。不触碰任何物理文件。
  `move_contents_to_parent`、`trash_contents` 明确返回 501，待 T06/T09 文档事务接入再完成。
- GET/POST `/tags`、PATCH/DELETE `/tags/{id}`：删除标签在同一事务内解除绑定，
  为受影响档案递增 document_version、更新时间并记录 tag_deleted 事件，保留原件与 Revision。
- GET/POST `/document-types`、PATCH `/document-types/{id}`：类型 key 固定不可改，
  通过 is_active=false 停用，保留历史档案引用。fields 未传保留模板，显式 [] 清空模板；
  替换模板校验字段存在、同空间、无重复，失败整笔回滚；不删除 metadata_values。
  自定义字段定义 CRUD 和必填归档验证仍属于 T17/T18，当前可引用已有字段定义。

folders/tags/document-types 的 space_id 为可选过滤条件；缺失时返回全部空间数据，
未知空间/资源 404，跨空间引用 422，规范名称/类型 key 冲突与目录循环 409。
单管理员对全部 Space 有访问权，Space 隔离指关系约束，不代表已实现多用户空间权限。
列表按稳定键排序，尚无生产设置页面。首次需显式 POST /spaces 创建空间，无隐式用户数据生成。

名称去掉两端空白，NFC 保存，控制字符/空名拒绝；最长255字符。
文件夹同父级与标签同空间按 NFKC+casefold 判重，Space 名称可重复。
类型 key 使用 `[a-z][a-z0-9_]*`，最长255字符；请求拒绝未知字段及空 PATCH。
颜色为可清空的显示字符串（最长100字符），描述最长4096字符；未来 UI 应作为纯文本使用，
不将字符串直接拼成 HTML/CSS。类型字段列表最多1000项，display_order 为有符号32位整数。

写事务使用 BEGIN IMMEDIATE，并在持有数据库写锁后重新验证登录凭据与 CSRF，
避免撤销或密码重置和分类写入产生竞态；列表使用一致性读事务。
分类层实现位于 catalog.py，未新增表或修改已应用迁移；T06 可复用或收敛档案审计操作。

## T06 档案生命周期内部事务

`DocumentService` 在 Archive 启动后可由 `app.state.documents` 访问；它是后续上传、扫描和
档案路由调用的内部服务，不直接接受客户端路径或未验证的对象描述符：

- `register_managed(StoredObject, Registration)`：确认文件真实存在且哈希/大小匹配，
  在同一事务登记/复用 managed_objects、创建 Document、Revision 1、当前版本引用与创建事件。
  默认为 needs_review，即使已选文件夹也不会自动完成整理。
- 相同空间任一当前/历史版本（含回收站档案）的 hash+size 命中时，默认返回
  409 DUPLICATE_DETECTED，details.duplicates 为稳定排序的 Document ID 数组。
  显式 keep_separate 创建不同 Document/Revision；不同空间不互相返回重复提示，
  仍可共享物理对象。不会用哈希当作 Document ID。
- `append_managed_revision(id, object, RevisionChange)`：要求 expected_document_version，
  在写锁内检查版本、分配下一 revision_no，保持 Document ID，更新当前原件引用并递增文档版本，
  与 revision_added 事件一起提交。旧原件、人工字段、标签、旧成功 ParseRun 均保留。
  旧 ParseRun 与当前 Revision 不同的 stale 状态由后续公开投影计算，不能据当前服务返回值称已完成解析。
- `trash/restore(id, VersionChange)`：仅更新 deleted_at/版本/时间及审计事件，
  保留原件、Revision、元数据、标签与整理状态；恢复时无有效目录则回到未分类。
  已处于目标状态且版本匹配时不重复记事件或递增版本；过期版本始终409。
- `get_record/revisions` 是内部事实读取，不是带原件可用性/解析状态的完整公开 Document 响应。
  当前没有新增公开 Document 创建、详情、原件替换或回收站路由；T08/T09 再接入完整契约。

写事务 BEGIN IMMEDIATE；若传入 Request，持锁后复核认证/CSRF。内部 worker 可不传 Request，
但这只适用于可信代码，不能由 HTTP 路由绕过 T03 鉴权。409 VERSION_CONFLICT 返回
current_document_version；统一错误体现在保留受控 details/版本信息，不回显存储路径。

文件持久化先于数据库引用；新对象、Revision、Document 和事件任一数据库步骤失败均整笔回滚。
完整已发布孤儿文件保留，不在异常路径删除，等待 T15 的数据库感知 GC。
未来 GC 接入时必须协调“文件验证—数据库引用”窗口，不得直接扫描删除暂时未引用的对象。
文件名只接收不含路径分隔符的名称；MIME 由后续服务器嗅探逻辑提供，本轮不声称已实现 MIME 嗅探。

外部档案的软删除/恢复只改数据库，不打开、移动或修改源文件。外部来源登记与扫描留到 T11～T14；
给外部档案追加托管 Revision 会明确501，避免提前绕过 T16 的“纳入托管”流程。
T08起内部创建支持显式filed；新档案若关联类型仍缺必填字段则拒绝，完整字段验证与整理操作留到T09/T18。

审计插入统一到 document_events.py，T05 标签删除也复用它。Archive OpenAPI 0.4.3
补齐 restore 的 expected_document_version 请求体；此公开路由仍待 T09 实现。
`python scripts/smoke_auth.py` 在独立容器中验证创建→追加版本→软删除→重启→恢复与审计一致性。

## T07 持久任务与 Archive worker

Compose 现在运行三个进程容器：Archive API、Archive worker、Converter；仍是两个业务服务，
worker 只是 Archive 的执行进程，复用同一镜像和数据卷，不引入 Redis。
原启动命令 `docker compose up --build -d --wait` 会一并启动 worker。
独立本地运行可在同样的 PYTHONPATH/JUANZHAN_DATA_DIR 下执行：

```sh
PYTHONPATH=services .venv/bin/python -m juanzhan.worker
# 只处理至多一次尝试，用数据库任务状态判断成败，不把命令退出0当作任务成功：
PYTHONPATH=services .venv/bin/python -m juanzhan.worker --once
```

每个 worker 同时执行一个任务，handler 在 spawn 子进程内运行。默认租约30秒，
运行时至少每2秒续租；单次执行默认60秒（按任务可配置，最多3600秒），超过截止会终止子进程。
正常退出会中止子进程并按可重试错误处理；崩溃遗留的 running 任务在租约到期后由下一次认领恢复。
Compose worker 有独立心跳健康检查，10秒内无心跳视为不健康；不发布网络端口。
本地手工 SIGKILL 后队列可恢复，文件/远程副作用仍需自身幂等，不能依赖 Python finally 保障。

JobQueue/JobSpec 为内部入队接口，所有新任务必须提供幂等键；键与有效请求的规范JSON摘要绑定。
同键同请求返回原任务，异请求409；幂等键不能复用于不同操作。payload/result 各限64KiB且拒绝NaN。
可通过 enqueue(spec, db=transaction_connection) 将入队与业务写入同事务提交，调用者负责事务。
不提供任意客户端 POST /jobs 入队，也不接受用户指定 handler 或服务器路径。

任务认领使用 BEGIN IMMEDIATE，累计 attempts 在认领时递增，默认3次、最大10次。
每次重认领分配新租约令牌；过期 worker 的续租、进度或完成写入均被拒绝。
可重试错误按1/2/4…最多60秒退避；不可重试直接failed。预算耗尽后不再认领，
手动 retry 也不能重置次数或绕过上限。auto_retry=false 的任务在失败后等待手动重试；
等待自动退避的任务也可通过重试接口提前唤醒，但不获得额外预算。

公开 GET `/api/v1/jobs/{id}` 与 POST `/api/v1/jobs/{id}/retry` 已实现；都要求鉴权，
Cookie 重试要求CSRF，Bearer不要求。运行中/完成/不可重试/耗尽预算重试返回409。
公开响应不返回payload、幂等键、请求摘要、租约令牌或worker身份。错误仅保存固定分类与安全消息，
不保存异常原文或堆栈。result 由可信 handler 产生，新增handler必须排除敏感路径和凭据。

当前只实现真实 `gc + managed_staging` handler，payload 可选 minimum_age_seconds（默认3600）；
仅调用 T04 临时文件安全恢复，不删除已发布对象，不等同 T15 完整GC。
其他任务种类明确失败 HANDLER_NOT_AVAILABLE，不能伪称解析/扫描/上传已完成。
维护任务内部示例（从可信维护代码执行，同一操作重试复用同一 operation_key）：

```python
queue = JobQueue(settings)
job = queue.enqueue(JobSpec(kind='gc', target_type='managed_staging',
    idempotency_key=operation_key))
```

数据库业务副作用应通过 `queue.complete(id, lease_token, result, effect=callback)` 提交，
callback 必须使用传入的同一 db 连接，不调用自行开启写事务的 DocumentService 方法，
也不在事务内做长时间文件/网络操作。callback和任务完成标记同事务提交；失败或过期则回滚。
同一完成任务不会再次运行callback。T08等后续handler接入时必须遵守这一约束。

整体语义是“至少执行一次”，不是对文件或网络请求承诺 exactly-once。
远程转换请求未来要使用稳定任务标识实现服务端幂等；本轮仅证明SQLite原子副作用和
临时文件清理的幂等重跑。租约基于UTC机器时钟，部署主机需保持时钟正常。

`0003_jobs.sql` 增加租约、调度、请求摘要与worker心跳，保留既有任务和业务数据；
API契约扩展0.4.4，数据库迁移版本0.4.2，两者独立编号。
`python scripts/smoke_auth.py` 验证任务跨容器重启保留、真实CLI worker执行、HTTP查询与重试；
`python scripts/smoke.py` 同时验证独立worker心跳。生产任务中心UI和业务handler尚未实现。

## T08 真实单文件上传

POST `/api/v1/documents/upload` 接收 multipart 单文件 `file` 与必填 `space_id`，可选
`folder_id`、`triage_status`（needs_review/filed）、`duplicate_policy`（reject/keep_separate）。
需先完成管理员初始化和登录，Cookie 写入携带 CSRF，自动化调用可用 Bearer。
未提供文件夹则未分类；选择文件夹不自动改变默认 needs_review。

请求流按64KiB交给受限 multipart 解析器；每个API进程最多两个并发上传，超出立即429。
默认单文件64MiB，总请求体额外允许64KiB multipart/元数据开销；接收默认限时60秒。
最多一个文件和四个元数据字段，每字段4KiB，每部分头8KiB；拒绝重复、未知、路径式文件名和截断表单。
超过64KiB的文件spool到操作系统临时文件，随后由ManagedStore复制到托管卷并原子发布。
因此需为同时存在的spool与托管临时文件预留磁盘空间；这不是全局配额，部署多API进程时并发限额按进程累计。
建议反向代理也设置有限请求体与接收超时，生产容量/空间保留策略仍需后续实测。

Compose可配置 `JUANZHAN_UPLOAD_MAX_BYTES`（1字节～1GiB，默认67108864）和
`JUANZHAN_UPLOAD_TIMEOUT_SECONDS`（正数～3600秒，默认60）。默认值是本轮保守配置，
不是宣称已通过1GiB容量或吞吐量验收。本轮验证恰好边界/超限、小配置请求、约254KiB中文文件和真实网络spool上传；
T04另有64MiB存储流实验，不能把它等同完整HTTP容量测试。

MIME忽略客户端声明，按文件头识别PDF/PNG/JPEG/GIF/TIFF；仅在有界ZIP目录内识别DOCX结构和EPUB mimetype。
不展开归档内容；ZIP64、目录过大、复杂/坏ZIP保守返回通用ZIP。UTF-8文本按内容识别HTML，
纯文本以md扩展名辅助区分Markdown；其他情况为text/plain或application/octet-stream。
这只是保守类型嗅探，不是解析、恶意文件检测或HTML消毒；所有原件仍是不可信输入。

原件成功发布并重验后，Document、Revision、managed_objects、审计事件与 parse Job 在一个事务中提交。
返回201包含 document_id/revision_id/job_id/upload_status=saved。Job幂等键为该Revision的稳定标识；
原件保存成功与解析成功分开。当前parse handler未实现，会明确HANDLER_NOT_AVAILABLE，
GET /jobs/{id}可查看真实失败，原件与业务档案不因解析失败丢失。

默认同空间重复返回409与已有档案ID，未新增档案或任务；显式keep_separate创建独立档案但复用物理对象。
未知格式仍可归档。数据库或入队失败整笔回滚，但完整孤儿字节保留等待T15清理；
接收中断/超时/超限则关闭spool，不产生档案引用。内容返回值和错误体均不暴露服务器路径。

状态码：400非法或中断multipart，408接收超时，413超限，422元数据/重复表单字段非法，
429容量满，503存储不可用；鉴权/CSRF/重复等沿用401/403/409。
公开列表、详情、下载和回收站接口仍留T09及安全相关任务，不把上传接通视为完整档案库可用。

## T09 档案管理与目录删除

公开管理端点见API.md/OpenAPI 0.4.6。列表使用id次序打破排序平局，默认排除回收站，分页上限100。
PATCH只修改显式字段，标签使用增删集合；无事实变化不增加版本。日期只接受有效YYYY-MM-DD。
所有写入复用认证、CSRF、版本锁和审计事务；跨空间引用拒绝，回收档案须先恢复才能编辑/整理。
filed检查模板必填值存在（布尔false仍为有效存在），带复杂约束时明确501待T18。

非空目录删除要求confirm_folder_id确认。move_contents_to_parent把整棵子树档案移至被删根目录的父目录；
trash_contents把子树档案设为无目录并软删除，原有回收时间保留。二者均提升受影响档案版本并审计，按子目录优先删除目录。
任何Source目标/初始目录引用都会阻止整个事务，不隐式更改来源设置；触发器/审计失败全量回滚，不操作文件。

托管原件状态用不跟随符号链接的类型/大小/可读探测，列表不逐个计算全文件哈希；完整读取仍验证哈希。
外部来源离线独立显示source_offline，未验证挂载显示unknown。处理状态取当前Revision最新解析/任务，旧正文保留且可标stale。
当前没有下载/预览、全文检索、真实解析或生产界面。

## T10 批量任务和最小撤销

批量接口见API/OpenAPI0.4.7。客户端应先明确选择范围，再提交已枚举ID和各自版本；服务端不运行动态过滤。
默认每批最多100项且任务JSON64KiB，所有批量走异步202，与原有AsyncJob契约一致；更大的集合需显式分批。
这属于本轮实施上限，未来大规模快照/同步快速路径需单独评估。

Worker子进程调用JobQueue.complete的可信结果回调，在围栏写事务内处理逐项savepoint、审计、结果和完成标记。
预期业务/完整性错误只回滚该项；基础设施故障或租约过期回滚整次事务，安全恢复，不保留未完成结果。
各项逻辑结果独立，但成功项在整个有界任务提交时一起持久化；进度只在完成时发布，不提供实时逐项进度。

撤销以原batch_job_id关联事件的before/after快照为依据，版本须等于原after版本；恢复引用需仍有效。
通过稳定batch-undo键最多创建一个撤销任务；成功项递增版本并有独立审计。后续编辑的档案保留原状并报告冲突。
标签增删保留其他标签，所有操作只改数据库；原件、Revision和旧解析内容不变。
重新解析和元数据批改仍501，须待T19/T18业务接入；未实现生产UI、筛选结果快照生成或复杂历史回滚。

## T17 字段定义维护

fields.py复用catalog鉴权事务/空间校验，接口见API/OpenAPI0.4.8。定义创建后key/type/space固定，停用保留引用和历史值。
更新只修改显式属性，constraints整体替换；不重写metadata_values、不改档案版本或自动执行全文索引。
每空间1000定义（包含停用），约束配置按紧凑UTF-8 JSON计16KiB、嵌套深度8、禁止非有限数字；属于本轮可调整实施默认上限。
constraints沿用契约开放对象，仅保存有界JSON，不宣称已验证规则语义或字段值，T18需先明确词汇及兼容处理。

document_type_fields已有模板替换事务复用：新绑定要求字段启用且同空间，现存停用绑定允许保留/重排/改必填/移除。
字段停用不隐式解除必填模板；管理员需显式调整模板，避免无意绕过归档要求。切类型/移除模板字段始终保留历史值。
无新迁移；后续T18接七类型/规则/候选采纳与归档服务，不能以当前定义API冒充完整字段值能力。

## T18 元数据与规则服务

metadata_values.py负责七类型转换/约束/归档验证；metadata.py负责认证写事务、局部保存、来源与版本审计、显式候选采纳。
现有Document API和batch的整理/切类型复用同一filing检查；已filed写值也检查现模板，不允许清空必填值。
未filed档案允许不完整元数据但提交值仍须类型/规则正确；历史值不因换类型或定义更新删除，未来归档重新验证。

规则词汇、选项形状及范围见API/OpenAPI0.4.9。regex为锁定生产依赖，匹配完整字符串且20ms超时，512字符模式与量词数值上限65536。
Decimal最大绝对缩放整数9×10^16，无float中转；API固定4位字符串，SQLite真实范围比较见测试。
配置兼容：T17开放JSON历史未知键不静默忽略，写值/归档501；管理员以已知规则显式替换配置，新配置不再接未知键。
API限制1000键/256KiB JSON、文本65536字符；停用字段不允许写入或删除，需先显式恢复定义。

采纳只接受同档案当前成功ParseRun/Revision候选，按目标类型验证，不接受null擦除；版本检查保护后续编辑。
显式采纳的前后值和候选ID进审计，候选行保持原样；解析器不会通过此接口自动采纳。生产解析仍未实现。
批量set_metadata仍501，后续需接同服务及批量撤销语义，不绕过版本/确认/规则。无新迁移与文件副作用。

## T26 生产前端构建、开发与验收

web/使用React19/Vite6/Phosphor图标，与已接受原型同一视觉语言；不引入第二套生产框架或第三个业务服务。
`npm ci --prefix web --cache /workspace/.npm`按锁安装，`npm run build --prefix web`生成web/dist，之后才能构建Docker镜像。
本次初始JS gzip约82KiB；dist/node_modules不提交，Dockerfile离线复制编译产物，镜像不带npm或前端开发服务器。
未构建时Python API仍可运行，根路径返回503 WEB_NOT_BUILT；不要用空壳成功替代真实构建。

开发启动API后，在web/运行`npm run dev -- --port 5174 --strictPort`。Vite绑定loopback，/api同源代理默认Archive8000，
可通过JUANZHAN_API_URL指定已运行API；不启用任意源CORS，不把令牌放浏览器localStorage。可信本地HTTP Cookie配置见认证节。
生产Archive根路径提供公开HTML及/assets；HTML no-store、同源CSP、禁止嵌入。仅GET/HEAD静态资源免鉴权，所有业务API仍鉴权。
管理员无默认密码，使用既有交互CLI初始化；UI只调用现有登录API，不代设管理员或显示服务端路径。

上传默认顺序执行，每次一份原件，最多20份等待/上传项；入队时固定空间/目录，切导航不改变上传目的地。
进度取真实XHR发送量，100%仍等服务器确认；201 saved才显示保存，解析任务状态另行轮询，不声称解析成功。
取消正在传输或网络中断可能发生在服务端提交之后，提示刷新核对，不自动重试；重复原件只允许显式另存为独立档案。
会话失效会卸载工作区并中止请求；导航/详情请求有取消保护，失败与空结果区分，移动端返回保留列表滚动位置。

E2E：先构建，再`JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e --prefix web`（存在系统Chromium时）。
也可用Playwright安装的默认浏览器省略该变量；当前云环境已有系统Chromium，无需关闭TLS/签名校验或另下载浏览器。
测试自动启动一次性Archive/SQLite/随机管理员，不接正常Compose卷；产物默认放/tmp，服务端测试上传限32KiB用于验证真实413。
后续T27增加整理/拖拽/批量/恢复，T29接正文/预览/字段编辑等真实能力；当前只读详情外壳如实提示未实现功能。

## T27 整理界面运行边界

安装/构建/Compose启动命令沿用T26，无新依赖。先编译web/dist再构建archive镜像；正常管理员和数据卷保持不变。
选择当前页或全部筛选结果后打开批量操作；筛选结果最多100份，超限请缩小范围，绝不静默截断。快照固定ID和版本，后来上传不会加入。
操作支持移动、标签增减、类型、整理状态、收藏、回收与恢复；逐项失败独立显示，撤销只覆盖原成功且版本未变化项。恢复保留原件。
OS文件拖到列表/目录进入真实上传队列；内部文档拖到目录/标签/回收站打开逻辑操作确认。私有页面令牌只支持同页面同空间，不接受任意路径/URL。
关闭弹窗仍轮询任务，可从侧栏返回结果；刷新后的结果恢复留任务中心T31。网络失败不自动重试写入，避免不确定提交重复执行。
E2E临时Archive同时启动真实worker；SIGTERM时停止线程/子进程并清理临时数据。正常实例不设置测试密码。字段编辑UI/正文/预览仍待后续。

## T11 可选只读来源配置

默认JUANZHAN_SOURCE_MOUNTS={}，无需额外目录、凭据或安装；正常Compose不会自动接入宿主机资料。JSON格式为{"records":"/sources/records"}，值仅由管理员配置，API和worker需同一配置与容器路径。不要把真实根路径提交到仓库。
外部目录必须使用真正只读bind，而不是chmod。可在本地未跟踪的Compose覆盖文件中为archive和archive-worker各添加：

```yaml
volumes:
  - type: bind
    source: /administrator-selected/existing-directory
    target: /sources/records
    read_only: true
    bind:
      create_host_path: false
```

这段为待替换的配置示例，不是自动执行步骤；保留原有/data卷并确保容器UID10001有读取/目录遍历权限。Converter不挂载。缺目录不能通过自动创建空目录假装在线。
匿名GET /api/v1/source-mounts拒绝，登录后只显示别名和即时状态；实际读取再次检查根及嵌套挂载只读标志。所有符号链接默认拒绝，根祖先也不能是符号链接。
路径必须精确相对路径，无绝对路径/反斜杠/盘符/空段/./../控制字符；保留Unicode与大小写，不将不同磁盘名称合并。Linux O_PATH和/proc/self/fd为要求。
只读bind不阻止宿主机更新原件；本层不声称提供历史快照或稳定hash，扫描一致性后续实现。Source/SourceEntry、预扫描/增量扫描尚未开放。
验收先构建archive镜像，再运行`python scripts/smoke_sources.py`；脚本仅创建一次性测试目录/容器，校验真实RO/RW/嵌套挂载/HTTP，结束清理，不接触正常卷或管理员。

## T12 来源API与预扫描

沿用T11的可选JUANZHAN_SOURCE_MOUNTS及API/worker同路径只读bind，无新增依赖、构建步骤或默认用户挂载。GET /source-mounts获取可选别名，POST /sources保存配置；同空间目标目录与全局根重叠校验由事务执行。
POST /sources/{id}/preview-scan需要Cookie CSRF或Bearer，返回持久job_id；同来源活动预扫描复用原任务，轮询GET /jobs/{id}看结果。queue/scanning不等于完成，更不等于已导入。
扫描只统计可读普通文件的候选扩展名；不解析、不hash整文件、不创建库存/档案/目录。忽略数量含特殊文件、符号链接与不支持类型，符号链接目录按一项计。不可读子树/嵌套可写/资源超限明确失败。
默认100000访问项、64层、120秒、最多3次尝试；SOURCE_OFFLINE/SOURCE_CHANGED/SOURCE_FILE_MISSING可有限重试，安全拒绝不可重试。任务结束后显式POST可新建独立预扫描。
Source.health反映当前挂载，Source.status也反映最后预扫描错误/当前任务；挂载恢复不等于已有成功导入。GET entries读取持久库存，来源离线也可用，不修改available/missing。
scan_interval_minutes仅保存配置，尚无自动调度；/scan首次导入、增量/忽略规则、目录冲突预检与来源UI后续交付。1千真实文件资源基线只用于当前开发机，不代表大规模性能承诺。
`python scripts/smoke_sources.py`已扩展隔离来源配置/真实worker预扫描、嵌套可写失败、重启持久化与资源上限检查；仅处理一次性测试目录/卷/容器，结束清理。Docker重启可能重分配临时主机端口，脚本重新查询后等待就绪。

## T13 首次外部导入

先沿用T11配置真正只读bind与别名、通过T12 POST /sources保存tree/flat、初始目标及filed/needs_review；再POST /sources/{id}/scan body={"mode":"initial"}，以既有CSRF或Bearer调用，轮询Job。
首扫300秒/最多3次尝试、100000访问项/64层；匿名元数据清单最多64MiB（只含相对路径/文件事实，无原件字节）。准备阶段不持有业务写锁，发布阶段原子且受剩余租约限制；大型导入未作吞吐承诺。
tree将相对目录（含空目录）创建到初始目标下，flat所有候选文件放初始目标。tree不合并现有同名或规范化冲突目录，SOURCE_FOLDER_CONFLICT时可通过现有目录改名/移动解决后重新提交；源目录自有规范名碰撞需调整来源布局/后续配置，不对外部目录自动改名。
成功后反复initial只返回原completed任务，不导入新文件、不覆盖人工改名/分类/版本。新增文件与失联确认留T14；当前incremental为501。解析任务真实排队，但handler尚未实现，原件状态unknown不代表可预览/下载。
原件不复制/移动/删除，managed对象为零；匿名清单退出/kill后消失，任何发布异常/租约丢失全部回滚。原件被宿主机更改时指纹检查拒绝当前观察，不承诺跨文件原子快照或历史字节保存。
镜像构建后运行`python scripts/smoke_initial.py`验证真实tree/flat、冲突恢复、重放/重启、hash/审计/解析任务不变量和1千文件原子发布；该脚本仅使用一次性测试挂载/卷/随机管理员，不接触正常管理员或用户来源。

## T14 增量与升级

重建Archive镜像并启动，迁移器自动应用0004新增根摘要/缺失凭据表；不修改旧迁移，不重置正常管理员或数据卷。安装/Compose/云启动命令不变。
首扫完成后POST /sources/{id}/scan {"mode":"incremental"}，轮询Job；活动同模式复用，preview/initial/incremental互斥。新增文件进入needs_review和配置的后续目标，不创建新逻辑层级。
每轮全量hash，大小/mtime保持也能发现字节变化；新Revision保留人工字段/分类/旧解析，rename仅在hash+size双方唯一时重关联。重复hash标needs_match，可能出现无Document的新路径条目，显式匹配界面/写接口尚未实现。
两个独立成功在线增量确认missing；离线/失败不修改Entry且重置未完成确认凭据。恢复文件回到available；首扫完成时间不改，成功扫描时间更新。普通外部字节仍unknown，不代表支持预览/下载。
根digest改变（包括换成另一个空只读根）会SOURCE_ROOT_CHANGED，需恢复或核实原部署根，不提供自动重置。旧T13来源无摘要时以同路径/hash/size/inode锚点建立；若文件全部已变/已失踪而无锚点，则SOURCE_ROOT_UNVERIFIED，不能自动判全库缺失。跨机器/文件系统恢复需后续受审计的重新验证流程，不绕过保护。
预算沿用300秒/3次/100000访问项/64层/64MiB匿名元数据。尚无自动调度、排除规则/取消索引（T15）、来源UI（T28）和真实转换器，不把API手动增量描述成自动扫描。
镜像构建后`python scripts/smoke_incremental.py`验证真实RO挂载/HTTP/worker/SQLite、离线及错误空根、重启后继续扫描；只操作一次性测试目录/卷/随机管理员，不接触用户来源。

## T15 排除与安全清理

启动自动应用0005迁移，共5份，安装/Compose步骤不变。取消索引通过POST /sources/{id}/exclude-entry传Entry ID、有关联Doc时的版本及可选reason，轮询Job；GET/DELETE exclusions管理已提交规则，待处理屏障直到成功或终态失败。
规则是精确文件路径，不影响其他同hash副本。排除不会物理删文件；移除规则不自动恢复Trash Doc。Purge后规则仍防重导，主动移除才允许重新建档。
POST /documents/{id}/purge必须已Trash，并明确confirm_document_id和expected_document_version；执行复核，恢复/编辑后的旧任务拒绝。永久业务记录无法恢复，源字节保留。派生数据库记录删除，派生物理文件保留待其安全store协议，不走任意路径清理。
托管原件GC默认至少24小时宽限，仍被任何历史/回收Revision引用都保留。Purge自动排延迟任务，孤儿发现排后续任务；本地管理员可`python -m juanzhan.maintenance gc`排队，由正常worker执行。无强制缩短保留期选项，不在正常卷运行测试时间快进。
GC独占store锁且持DB写锁，注册/追加共享store锁贯穿验证与提交；不得颠倒锁序。上传繁忙时GC可能有限重试/失败，应查看真实Job结果，不把排队当成已删。
`python scripts/smoke_maintenance.py`使用一次性RO挂载、数据卷、随机管理员，验证排除/扫描/外部purge、托管共享引用/宽限/实际unlink、恢复竞态与重启回执；只快进fixture候选时间，不触碰用户文件或正常管理员。

## T28 来源浏览器验收

先执行前端构建及Archive镜像构建，再运行：

```sh
JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium DOCKER_CONFIG="$PWD/.local/docker" npm run test:e2e:sources --prefix web
```

需可用Docker及本机Chromium；不新增前端依赖。测试使用8768业务端口和8769夹具就绪端口，临时只读来源/随机管理员/独立卷及真实worker；SIGTERM时删除仅本次容器/卷/临时目录。普通`test:e2e`仍为原8项主机临时服务回归，两个套件可独立运行。正常Compose挂载/管理员/环境启动配置未变，默认来源别名为空。

## T19 Converter运行与验证

正常Compose仍使用既有CONVERTER_SERVICE_TOKEN，无新凭证；worker新增CONVERTER_URL=http://converter:8000并复用该Token供内部客户端使用，尚未自动接入parse handler。Converter保留独立128MiB tmpfs、没有Archive卷，单uvicorn进程运行（多进程共享spool会因排他锁拒绝）。前端无改动，无新依赖/安装步骤。
默认临时目录/tmp/juanzhan-converter；可通过CONVERTER_ROOT、CONVERTER_MAX_FILE_BYTES、CONVERTER_MAX_OUTPUT_BYTES、CONVERTER_MAX_JOBS、CONVERTER_TTL_SECONDS、CONVERTER_WALL_SECONDS、CONVERTER_CPU_SECONDS、CONVERTER_MEMORY_BYTES、CONVERTER_MAX_BLOCKS、CONVERTER_RECEIVE_SECONDS调整受验证上限。提高容量/输入/输出额度时须同步安排临时卷预算，默认参数针对当前128MiB tmpfs；RLIMIT_AS是子进程地址空间。默认4MiB/16MiB、2任务、TTL3600秒、30秒墙钟/10秒CPU/256MiB地址空间/10000块/60秒接收。
在根目录运行`UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen pytest -q`；构建Archive镜像后运行`DOCKER_CONFIG="$PWD/.local/docker" python scripts/smoke_converter.py`。后者自动创建独立Archive/Converter容器、网络及卷，用随机临时凭证通过真实上传、SQLite、HTTP转换/规范结果/字节校验和DELETE验证，最后仅清理本次夹具。正常管理员、卷与.env保持。
ConverterClient可通过from_env创建，仅用于服务内部；使用submit→wait→result(预期Revision/ParseRun)→artifact校验流→delete。未完成/失败不应切换业务成功指针；T22负责正式持久化与重试预算。不要把Converter临时SQLite纳入Archive业务迁移或声称重建tmpfs可保留远端Job。

## T20 六格式依赖与验收

新增纯Python依赖，沿用既有冻结安装与哈希wheelhouse流程，不增加系统服务/模型：先`UV_CACHE_DIR=/workspace/.uv-cache uv sync --frozen`，再`python -m pip download --require-hashes --only-binary=:all: --no-deps -r requirements.lock -d wheelhouse`刷新容器依赖，然后原Compose构建/启动/冒烟。当前机器已实际安装、下载并离线构建验证；无需新增凭证或环境变量。新环境沿用相同通用安装/启动命令，保留既有.env和数据卷。
六格式网络验收在根目录执行`DOCKER_CONFIG="$PWD/.local/docker" UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen python scripts/smoke_formats.py`；脚本通过已安装pypdf生成真实PDF和实际DOCX/EPUB/文本文件，独立容器/网络/卷真实HTTP上传后，从Archive内部客户端调用Converter，校验结果、两种资产及原件/业务状态。测试资源仅夹具，退出即清理。
可选CONVERTER_MAX_PAGES、CONVERTER_MAX_ARCHIVE_ENTRIES、CONVERTER_MAX_ARCHIVE_BYTES、CONVERTER_MAX_ARCHIVE_MEMBER_BYTES、CONVERTER_MAX_COMPRESSION_RATIO分别默认200/1024/16MiB/8MiB/200；仍受T19输入/输出/块数/CPU/地址空间/墙钟保护，提高上限必须同时评估tmpfs与容器资源。没有引入系统pdftotext运行依赖；本轮仅用本机已有命令独立核对中文PDF样本。
Archive自动parse/业务正文仍待T22，因此现有上传界面不会因本轮能力扩充自动展示正文；勿改前端为伪成功。


## T21 OCR模型与缩略图

安装/刷新依赖后运行`python scripts/setup_ocr_models.py`：仅下载ocr-models.lock.json所列官方tessdata_fast固定提交的eng/chi_sim文件，验证TLS、大小和SHA256后原子替换；重复运行复用有效文件。`--verify`只校验，不联网。模型目录忽略Git，但镜像构建必须COPY并再次验证；镜像内模型/清单可由非root服务读取，模型和许可证不能漏出发布产物。Docker不再需要apt/system tesseract/poppler；tesserocr和pypdfium2使用哈希锁定的Linux wheels。已验证Linux x86_64，不声称其他平台可用。

请求ocr_enabled默认false；CONVERTER_ENABLE_OCR=false可关闭服务OCR，缺少模型时仍可解析文本层与生成缩略图。可用语言由实际模型校验决定；服务初始化后变更模型需重启。CONVERTER_OCR_MODELS_DIR为管理员可信模型目录，不能来自请求。其他可选上限：CONVERTER_MAX_IMAGE_PIXELS=12000000、MAX_OCR_PAGES=10、MAX_PREVIEW_PAGES=5、RENDER_DPI=120（均加CONVERTER_前缀）；地址空间默认提升到512MiB，CPU10秒/墙钟30秒和128MiB tmpfs不变，OMP线程固定1。复杂/大页可明确失败，不承诺任意PDF都能识别。

`DOCKER_CONFIG="$PWD/.local/docker" UV_CACHE_DIR=/workspace/.uv-cache uv run --frozen python scripts/smoke_formats.py --ocr`使用真实中英文图片、扫描PDF，验证Archive上传→内部客户端→真实OCR/缩略图/资产校验→清理；正常卷/管理员不参与。测试样本绘制需要本机Noto CJK字体`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`（Debian包fonts-noto-cjk），生产OCR/渲染不需要该字体包。


## T22 更新 · 2026-10-17

T22无新依赖/模型/凭证，既有冻结安装、哈希wheelhouse和Compose重建/启动命令不变，启动自动执行新增0006/0007迁移。worker复用现有CONVERTER_URL/CONVERTER_SERVICE_TOKEN；未配置时CONVERTER_NOT_CONFIGURED，不可达时有限重试CONVERTER_UNAVAILABLE。原件上传64MiB上限不等于默认Converter4MiB解析上限，大文件仍可归档并如实报解析额度失败。

运行uv run --frozen python scripts/smoke_formats.py --persist验证六格式自动入库；加--ocr验证真实OCR持久化，加--external验证实际内核只读挂载、来源API首扫、真实worker转换入库及源内容变更拒绝。均带DOCKER_CONFIG=$PWD/.local/docker，使用独立卷/随机凭证，退出只清理夹具。原smoke_formats无--persist模式仍用于独立Converter，不自动启动worker。

派生GC自动于解析尝试/永久清理时排延迟任务，可通过python -m juanzhan.maintenance gc --store derived手动排队；从首次发现无引用起至少24小时宽限，全部历史/回收引用均保护。保留data/derived完整字节及DB的一致备份，备份恢复演练仍T32。既有失败HANDLER_NOT_AVAILABLE任务升级不会自动重排，公开重解析入口随T23完成。


## T23 更新 · 2026-10-18

T23无依赖、环境变量或迁移新增，沿用冻结安装、现有镜像构建/Compose启动。pytest包含test_content.py；smoke_formats.py --persist现在同时验证三格式正文/分页历史/候选和公开幂等重解析，--ocr覆盖OCR结果，--external额外验证第二Archive实例没有来源可访问时仍返回相同缓存且source_offline/stale。所有夹具独立网络/随机凭证/卷，退出清理；正常卷不参与。

调用POST /api/v1/documents/{id}/reprocess须附当前业务版本、当前Revision和客户端request_id（UUID可用）；成功缓存明确force=true，语言白名单及严格布尔，Cookie CSRF或Bearer。GET content默认blocks，text/markdown仍是JSON而非文件/HTML。公开内容不代表阅读界面或用户原件下载已完成；无新的环境配置步骤。


## T24 更新 · 2026-10-18

新增哈希锁定opencc-python-reimplemented==0.1.7，沿用uv sync --frozen及requirements.lock哈希wheelhouse下载、现有镜像构建流程；无新环境变量/凭证/模型下载。许可证在licenses/opencc，详细算法/字典摘要见ADR-039。Archive启动应用0008，当前8条迁移；保留.env/管理员/数据卷及既有7条迁移。

在已初始化Archive环境中（本地用uv run --frozen，容器可docker compose exec archive）：

```sh
python -m juanzhan.indexing queue --limit 100
python -m juanzhan.indexing rebuild --document DOCUMENT_ID
python -m juanzhan.indexing rebuild --all
```

rebuild需要明确单档案或全量选择，只标脏并排有限批次；普通持续worker继续排剩余。--once不自动发现脏记录，需先queue。生产worker交替处理普通/索引队列，活动索引上限100。每文档输入8MiB、50万词元/16MiB输出；子进程512MiB地址空间/60 CPU秒、Job120墙钟秒，超限last_error且保留旧索引，不无限重试；修复后显式rebuild。版本变动重新生成索引，运行不下载/接受自定义词典路径。

smoke_formats.py --persist --index --daemon --external验证六格式、自动调度及离线缓存；--persist --index --ocr验证真实OCR索引。所有夹具隔离，正常卷不参与。无公开搜索API变化，q仍501。


## T25 更新 · 2026-10-18

无新依赖/环境变量/凭证/迁移，沿用冻结依赖和既有Compose镜像构建/启动流程。search.py直接消费T24索引；持续worker需运行以自动推进脏代次，API不会同步排队/解析来掩盖索引缺失。GET /documents?q=与POST /documents/search已实现，详见API/ADR-040；系统摘要同样已接真实数据。

专项：uv run --frozen pytest -q tests/test_search.py。容器：smoke_formats.py --persist --index --daemon --external及--persist --index --ocr现在同时经鉴权HTTP验证简单/高级中文搜索、相关性/索引摘要/首页聚合及离线过滤。全部夹具隔离正常卷；新版本不重放旧失败任务。查询预算3秒SQLite/状态观察5000档案，POST 1MiB及响应16MiB；超限请收窄筛选/分页，不改安全限额绕过验证。无前端变更，搜索界面仍T30。


## T29 前端阅读验证

沿用npm ci --prefix web、npm run build --prefix web和既有Compose流程，无新依赖/凭证/模型/迁移。新增npm run test:e2e:reading --prefix web，需已安装Chromium（本环境JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium）。Playwright缺省库/整理测试和reading专项共享8767端口，必须依次运行；sources独立8768。reading-server.py生成临时Archive/store及随机服务Token、启动真实TCP Converter与worker，退出清理，不使用正常Compose卷或管理员。

reading专项验证真实DOCX正文/表格/候选显式采纳/冲突保护、历史切换和手机返回，以及多页TXT/源文本格式切换/恶意标签不执行/失败解析及过期会话。截图、日志与报告均放/tmp；Browser plugin not available，因此使用仓库Playwright。正文/候选/历史分别20/10/10项分页，不添加服务端原件读取或下载接口。


## T30 搜索界面验证

无新依赖/迁移/环境凭证，沿用npm ci/build --prefix web及Compose镜像构建/启动。npm run test:e2e:search --prefix web使用search.playwright.config.mjs：复用隔离reading-server，只有此配置注入JUANZHAN_E2E_INDEXING=1让测试worker自动排真实FTS，真实TCP Converter/SQLite/store保持，不改生产worker。search、reading和默认库/整理套件共享8767端口须顺序运行，sources用独立8768。

当前Browser plugin not available，以已安装/usr/bin/chromium配合JUANZHAN_CHROMIUM_PATH运行仓库Playwright。截图/日志在/tmp；不使用正常管理员/卷。URL片段最多16000字符、最多8字段/标签100/类型100，整数只安全范围，不要用浮点绕过验证。未知空间/非法链接明确恢复默认范围；字段停用/HTTP预算/网络失败显示错误，不静默扩大条件或返回假空结果。现有安装/启动草稿不需更改。


## T31 更新 · 2026-10-18

任务中心列表手动刷新，打开单项最多轮询两分钟，网络错误停止；重试不重置预算。重新解析需确认，OCR默认关闭；网络重发沿用被冻结的request_id/版本/选项，冲突关闭并刷新。结束后刷新档案读取新正文。新增npm run test:e2e:jobs，真实Converter/SQLite/文件环境；无依赖/启动/配置变化，沿用现有冻结安装及Compose构建。

## T32 原件访问与管理员备份恢复 · 2026-10-18

当前原件下载为鉴权GET `/api/v1/documents/{id}/download?expected_revision_id=...`，核验后固定字节；不支持Range/历史原件/内嵌HTML。安全预览仅已生成的PNG缩略图，旧Revision预览拒绝；无图不等于原件不存在。HTTP最多1GiB，生产浏览器为控制Blob内存限64MiB；超限可使用已鉴权API客户端下载。不要把API token放URL或提交到仓库。新增`npm run test:e2e:files`，真实TCP Converter/Archive/worker。

备份为管理员本地目录包，不经过Web上传、归档解压或在线原库替换。必须使用私有可信本地POSIX目录，父目录由管理员预先建立，输出目录必须不存在，且不得位于现有data_dir内。示例（在同版本镜像/依赖环境，选择实际数据/私有备份目录）：

```sh
JUANZHAN_DATA_DIR=/data python -m juanzhan.backup create --output /private-backups/archive-20261018
python -m juanzhan.backup restore --input /private-backups/archive-20261018 --output /private-recovery/archive-20261018
```

Docker内路径必须为管理员预先正确挂载且应用UID可写的私有目录；当前Compose没有额外备份挂载，不能把容器层当持久备份。需要传出时由管理员安全复制目录包，保留完整内容和COMPLETE；不自动修改Compose卷、.env或绑定任意宿主路径。

1. 推荐维护窗口暂停归档写入和worker。CLI也会按managed→derived排他存储锁和DB写屏障取得一致副本，包含WAL已提交事实；忙则失败，不转成不一致成功。
2. 备份DB和所有被Revision引用的托管对象、被ParseRun引用的派生产物。清单核验存储身份，最后落盘COMPLETE；无完整标记不可恢复。不复制staging、无引用孤儿或外部来源字节。
3. 恢复只写全新不存在目录；校验哈希、引用、SQLite integrity/外键和精确迁移版本。不支持自动升级旧包、不覆盖现有库。运行中留RESTORE_IN_PROGRESS，进程被强杀/断电遗留标记时Archive启动拒绝；保留包并删除/隔离失败的新恢复目录，再选择全新目录重做，不手工删标记冒充完成。
4. 完成后先以恢复目录启动隔离实例，使用原管理员密码重新登录；所有旧Cookie和API token已撤销，需要重发token。运行中任务清旧租约，沿原预算重试，已完成任务不重跑。不要让原实例和恢复实例同时扫描同一业务来源并对外服务。
5. 校验档案/人工字段、下载哈希、正文/预览、中文搜索与任务后，再由管理员计划切换服务数据卷。原库、.env和原件始终保留；本命令不执行切换。

包内含业务内容和管理员密码哈希，权限必须私有（根700、DB600）；无内建加密或签名，校验只检测损坏，不证明来源可信。外部来源目录、挂载映射、.env/转换token、模型/镜像版本需独立保存和恢复；本地数据备份不是外部原件备份。新恢复实例未配来源时如实显示离线，不把业务记录存在当外部字节已恢复。

无新依赖/凭证/迁移，既有安装启动命令保持；Archive0.4.21/52路径，Converter0.4.3/6路径，8条不可变迁移。云环境无需新增setup草稿。

## T33 整体验收入口 · 2026-10-18

完整命令与30项验收/故障映射见[ACCEPTANCE](ACCEPTANCE.md)。在既有uv冻结依赖、OCR模型和当前Compose镜像准备好后运行：

```sh
UV_CACHE_DIR=/workspace/.uv-cache JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium .venv/bin/python scripts/acceptance.py
```

默认结果写入新的私有/tmp目录，报告不进仓库；`--phase backend`/`browser`可分阶段跑，`--phase assess --reports <本次后端报告目录> <本次浏览器报告目录>`核验全部证据。后端所有参数都需通过；浏览器六套件全部项需通过，未跑的映射明确not_run。测试无新增依赖/初始化/服务配置，不需要新的云setup草稿。只读来源fixture使用随机容器/卷，不复用正常Compose业务卷；勿把fixture准备与其他Chromium导航并发，运行器已串行隔离。


## T34 本地候选与运维 · 2026-10-18

开发继续用根compose.yaml；deploy/compose.yaml是独立发布配置，不自动改变现有云安装/启动说明。build_release.py从现有冻结依赖/哈希wheelhouse与模型构建本地候选，release_drill.py只操作随机fixture项目/卷；benchmark.py仅临时合成库，候选容器可用--stdout将JSON直接保存到私有宿主报告目录，避免tmpfs停机后报告丢失。安装、权限、TLS、外部来源只读override、备份导出与新卷恢复及回退见RELEASE，实际性能见PERFORMANCE。本轮无新增依赖/凭证/迁移，不需要新的云setup草稿。
