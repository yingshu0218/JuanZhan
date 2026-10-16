# 生产开发（T01～T03）

代码在 `services/juanzhan/`，迁移在 `services/migrations/`，测试在 `tests/`。
参考原型仍在 `docs/prototype/`，不连接本骨架。

## 本地依赖与测试

需要 Python 3.12、uv；SQLite >=3.38，支持 JSON 与 FTS5。
从仓库根目录执行：

```sh
UV_CACHE_DIR=/workspace/.uv-cache uv sync --frozen
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
python -m pip download --no-cache-dir --require-hashes --only-binary=:all: --no-deps -r requirements.lock -d wheelhouse
DOCKER_CONFIG="$PWD/.local/docker" docker compose up --build -d --wait
python scripts/smoke.py
```

Archive 仅绑定宿主机 loopback 8000；Converter 无宿主机端口，仅内部网络可达。
`/healthz` 是无敏感信息的运维端点，不应经生产公共网关发布。
Converter 除健康检查外要求服务 Bearer Token；能力列表为空，任务请求返回 501。
Archive 已提供 T03 认证接口，暂未提供档案业务路由；服务令牌只从运行环境注入。

Archive 命名卷保存 database/managed/derived；Converter 临时区使用 tmpfs，不挂载业务卷。
尚无外部来源接入；T11 引入时必须配置只读 bind mount 和别名白名单，不能接受任意客户端路径。
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

浏览器客户端流程（当前尚无生产登录 UI）：

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
本轮不提供密码找回邮件、多用户、角色权限或生产登录页面。

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
内部创建当前不接受直接 filed 参数；必填字段验证与整理操作留到 T09/T18。

审计插入统一到 document_events.py，T05 标签删除也复用它。Archive OpenAPI 0.4.3
补齐 restore 的 expected_document_version 请求体；此公开路由仍待 T09 实现。
`python scripts/smoke_auth.py` 在独立容器中验证创建→追加版本→软删除→重启→恢复与审计一致性。
