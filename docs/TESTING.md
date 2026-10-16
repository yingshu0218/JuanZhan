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
