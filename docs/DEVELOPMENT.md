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
