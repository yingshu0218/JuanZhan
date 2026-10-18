# 本机开发依赖与清理记录

2026-10-19，macOS / Apple M5 arm64，仓库 `/Users/infinity/Desktop/Dev/juanzuan`。

## 本轮实际使用

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
