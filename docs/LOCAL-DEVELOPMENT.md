# 本机开发依赖与清理记录

2026-10-19，macOS / Apple M5 arm64，仓库 `/Users/infinity/Desktop/Dev/juanzuan`。

## 初始本机开发轮实际使用（c092200）

- 复用原有 uv、Git 和 CPython 3.12.11；未安装系统软件或修改系统 Python。
- 执行 `UV_CACHE_DIR="$PWD/.local/uv-cache" uv sync --frozen`，按既有 uv.lock 安装34个包到 `.venv/`；未新增应用依赖或修改锁文件。
- Python直接依赖及开发依赖以 pyproject.toml 为准，完整版本以 uv.lock 为准；本次实际包清单在 `.local/python-packages.txt`。
- 未安装 npm 包、浏览器、Docker、OCR模型、wheelhouse，未创建正常业务实例、管理员或业务数据卷。

## 生成物与清理边界

以下位置相对仓库根目录；均不提交Git。清理前停止使用该环境的服务/测试。

| 位置 | 本次用途 | 清理后影响 |
|---|---|---|
| `.venv/` | Python隔离环境，约64MiB | 需重新uv sync；不影响系统Python |
| `.local/uv-cache/` | 本项目专用下载/解包缓存，约54MiB | 可删，后续安装可能重新下载 |
| `.local/pytest-*/` | 自动测试生成的SQLite、原件、派生文件、临时转换目录 | 本次均为测试夹具，可删 |
| `.local/baseline/` | HEAD版本的只读对照源码副本 | 可删，正式源码不受影响 |
| `.local/*tests*.log` | 本轮测试日志 | 可删；需保留证据可先移出 |
| `.local/python-packages.txt` | 本次实际Python包清单 | 可删，版本可由uv.lock重建 |
| `.local/implement.py` | 本轮一次性编辑脚本 | 可删 |
| `.pytest_cache/`、各目录`__pycache__/` | pytest及Python缓存 | 可删，运行时自动重建 |

本轮结束前 `.local/` 约160MiB（含缓存与多次测试），会随后续测试变化。
不要无差别删除整个 `.local/`：未来正常实例可能使用 `.local/archive/` 保存业务数据，必须先核对。
原有全局 `~/.cache/uv`、`~/.npm` 未作为本次安装缓存；不属于本项目可直接清理范围。

## 重现验证

```sh
UV_CACHE_DIR="$PWD/.local/uv-cache" uv sync --frozen
UV_CACHE_DIR="$PWD/.local/uv-cache" uv run --frozen pytest -q tests/test_batches.py tests/test_auth.py tests/test_jobs.py --basetemp=.local/pytest-core
```

macOS当前无法通过现有Converter子进程的RLIMIT_AS设置：最小复现设置512MiB时抛出ValueError。不能移除生产资源保护冒充完整通过；真实解析/正文/OCR链路须在受支持Linux环境复验。详见TESTING本轮记录。

## Linux开发测试服务器（2026-10-19）

用户授权使用8.153.19.221，SSH别名devtest，复用本机既有密钥。项目专用根目录为`/opt/juanzhan-dev`，源码快照在`app/`；只同步Git跟踪的当前文件，不同步本机凭证、依赖或业务库。现有服务器服务不变，未开放公网测试端口。

- 复用服务器原有Docker29.7.2、Compose5.4.0、Node24.19.0与npm11.17.0。
- 项目专用uv0.12.3位于`.local/tools/`，Python下载位于`.local/python/`，uv缓存位于`.local/uv-cache/`，Python环境位于`app/.venv/`。安装日志保存在`.local/`。
- 本机此前新增Colima0.10.3、Lima2.2.1、Docker CLI29.9.1、Compose5.6.0，现改用服务器，不再需要本机虚拟机。未设置开机启动，没有成功启动VM。配置目录为仓库`.local/colima/`及首次尝试生成的`~/.colima/juanzhan/`；安装清单见`.local/container-tools-install.log`。
- 本机前端依赖`web/node_modules/`约116MiB，npm缓存`.local/npm-cache/`约24MiB，brew缓存`.local/homebrew-cache/`约99MiB。停止相关进程后可按需清理；不要自动清理其他项目的全局brew依赖。
- 清理服务器项目前先停止该项目测试进程和容器，核对未存业务数据，再删除专用目录；不清理其他`/opt`项目、系统Docker镜像或全局缓存。后续新增模型、镜像与测试数据继续追加记录。
- Python3.12.13已下载到服务器专用目录。PyPI直连下载慢，改用阿里云PyPI镜像安装；输入为`uv export --frozen --no-emit-project`生成的完整版本/哈希清单，再执行`uv pip sync --require-hashes`，未改动uv.lock。
- 服务器前端依赖位于`app/web/node_modules/`，npm缓存位于`.local/npm-cache/`；前端生产构建已通过。
- Playwright Chromium下载到服务器`.local/playwright/`，不覆盖系统浏览器。该Alibaba Cloud Linux平台使用Playwright的Ubuntu回退构建，是否可运行需另行实测。
- 中英文OCR模型约6.3MiB；服务器GitHub连接重置后在本机通过官方锁定脚本下载并校验，再传入服务器`app/ocr-models/`并重新校验。本机`ocr-models/`及`.local/ocr-models.tar.gz`可清理；两端模型均可按清单重新获取。
- 复用服务器已有`/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf`绘制OCR验收样本，设置`JUANZHAN_TEST_CJK_FONT`；不新增系统字体或替换默认字体。

远程验证示例（在服务器项目源码目录执行）：

```sh
JUANZHAN_TEST_CJK_FONT=/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf .venv/bin/python -m pytest -q
PLAYWRIGHT_BROWSERS_PATH=/opt/juanzhan-dev/.local/playwright npm run test:e2e:jobs --prefix web
```

原有8项本机library浏览器测试、服务器38项批量/正文测试及3项任务浏览器测试已通过；完整验收另以TESTING后续执行记录为准。
