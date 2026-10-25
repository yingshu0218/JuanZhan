# 上传格式规则（T59）

2026-10-25用户明确要求：档案库默认排除JSON等非档案文件，并可在后台配置。最新规则覆盖原先保留源码/程序配置的保守选择；不追溯删除已有原件或档案。

## 后台入口与默认选择

系统设置 → 上传格式规则。勾选表示排除；默认选中：

- JSON及程序数据：json/jsonl/ndjson。
- 开发运行配置：yaml/yml/toml/ini/cfg/conf/config/env/lock/properties，以及.env及变体、npm/nvm配置、Dockerfile、Makefile等。
- 源代码与脚本：JS/TS、Python、Shell、Java、C/C++/C#、Go/Rust/Ruby/PHP/Swift/Kotlin等及CSS、源码映射。
- 程序与安装包：exe/dll/so/dylib/app/dmg/pkg/msi/deb/rpm/bin/com/wasm。
- 压缩包和磁盘镜像：zip/rar/7z/tar/gz/tgz/bz2/xz/iso/img。
- 数据库与运行日志：db/sqlite/sqlite3/sql/log/cache。
- 开发依赖/缓存目录：node_modules、.venv/venv、__pycache__、pytest/mypy/ruff缓存、Next/Nuxt缓存等。拖放遍历直接跳过，不读取其内部文件。

构建输出目录build/dist/target、音视频另提供可选排除，默认不勾选，避免误丢业务文件。完整后缀/名称/目录清单以services/juanzhan/upload_formats.json为准（Web与服务共用）。可添加最多100个额外扩展名。常见PDF/Office/文本/Markdown/HTML/EPUB/CSV及图片默认保留；未知后缀/无后缀不因格式猜测自动拒绝。规则按名称和后缀匹配，不是内容鉴定或安全扫描。

原固定.DS_Store、Git等系统/版本控制辅助文件规则仍强制排除，不因关闭可选分类而开放。备份恢复的专用ZIP上传不是档案入库，不受归档上传格式规则影响。

## 一致性和权限

网页每批选择/拖放先读取服务器最新策略再过滤；加载失败不放行新批次。有效文件配额在排除之后计数。被跳过内容及原因在页内展开。目录排除由浏览器目录读取执行，HTTP接口不接收或信任本机路径。客户端预过滤减少请求，服务器multipart和Agent raw原件接口也分别校验文件格式，写入Document事务再次校验，不能靠直接API绕过。并发策略变更时，以提交时当前规则为准；失败不创建档案。共享原件存储若已写但登记回滚，沿用托管GC回收，不删除既有对象。

Agent通过analysis-templates（REST/MCP）看到当前上传规则；配置管理仍仅管理员可用，Agent凭据不获系统配置权限。配置全实例生效，version乐观锁防止覆盖其他窗口的新设置；Cookie写需CSRF。旧已入库JSON/源码保留，不自动移动或删除；只读来源扫描仍按原来源策略运行，本配置只覆盖上传入库入口。

## 持久化与API

0019_upload_policy.sql新增单行version/config_json配置，共19迁移。配置随一致备份保存/恢复，无新依赖。GET/PUT /api/v1/system/upload-policy，契约0.4.38/100路径；PUT包含expected_version、excluded_groups、custom_extensions，409表示需要重新读取；JSON等被当前策略拒绝返回422 UPLOAD_FORMAT_EXCLUDED。GET不缓存。静态系统辅助规则仍返回原UPLOAD_EXCLUDED。

没有增加格式白名单、MIME强制过滤、未知类型自动删档、规则匹配内容模型或既有全库清理。后续若需要只允许指定格式，可再按明确需求增加白名单模式。
