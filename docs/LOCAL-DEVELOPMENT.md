# 本机开发依赖与清理记录

T54 delivery cleanup: keep the active rc.22 image, application tables, original files, generated Markdown and pre-upgrade backup. Temporary /tmp/juanzhan-agent-import-*.tgz/bundle, /tmp/agent-import-*.py/mjs, .local/agent-import-extra-src, .local/pytest-agent-import-full, .local/agent-import-*.log and agent-import-before-source-sync.tar.gz can be removed by exact name after review. Private test-instance/agent-import-* reports/screenshots are evidence; do not publish credentials or real document data. The five synthetic documents remain in their clearly removable example space for user review; use normal platform deletion if later unwanted.

2026-10-24 T54：无新增包、模型或系统服务。新增0017迁移、平台自有JSON模板及SQLite分析数据均为源码/业务数据，不可按缓存清理。/tmp/juanzhan-agent-import-*.tgz、后续传输bundle/tar、.local/agent-import-*.log和隔离测试样本可按名称清理；保留原件/现役镜像/业务卷/凭据/备份。

T53 cleanup: no new dependencies. Keep the active rc.21 image, 8 persistent Markdown objects, original data and pre-upgrade backup. Temporary /tmp/juanzhan-markdown-*.tgz, source tar/bundles, sync/deploy/live scripts, .local/markdown-*.log and markdown-before-source-sync.tar.gz may be removed by exact name after review. Private test-instance/markdown-*.json are deployment evidence; do not publish them. All 45 live managed/derived files are business data, not disposable build cache.

2026-10-22 T53：无新增包/系统服务依赖；新增0016迁移及 Markdown 派生对象（受备份/GC保护，属于业务数据，勿当缓存直接删除）。服务器沿用 Python/Node/Docker；/tmp/juanzhan-markdown-*.tgz、私有 .local/markdown-*.log 和隔离 pytest 样本为可清理测试产物，保留原件/业务卷/认证/证书/备份。

2026-10-22 T52版本控制元数据排除：沿用T51共享JSON规则和测试工具，无新增依赖/服务/迁移。原生目录选择/CDP拖放的临时样本仍在/tmp/juanzhan-upload-exclusions-*，测试finally清理；/tmp/juanzhan-git-exclusions.tgz、后续git-exclusions bundle/tar和临时验收脚本/截图可清理。业务卷/原件/私有配置/备份/运行镜像保留，本机未安装包。

2026-10-22 T51辅助文件排除：无新增运行/构建依赖；新增仓库自有JSON规则，由Python标准库和Vite共同读取。测试样本仅在devtest的/tmp/juanzhan-upload-exclusions-*创建并finally清理，真实上传只进入隔离SQLite/存储，未导入业务库。/tmp/juanzhan-exclusions-*的传输包、bundle/tar、测试截图及临时验收脚本可清理；业务数据卷、证书、私有认证、备份和现役镜像保留。未安装本机依赖。

2026-10-22 T50文件夹上传：无新增包/系统依赖，使用浏览器原生目录选择、FileSystemEntry分批读取、XHR、IntersectionObserver和现有逻辑目录/托管上传API。devtest已有Node/Playwright完成真实目录选择及CDP操作系统文件/文件夹混合拖放；样本位于/tmp/juanzhan-upload-folder-*、juanzhan-upload-drag-*，测试finally按批清理，不导入业务空间。源码传输包/tmp/juanzhan-folder-changes.tgz、folder-fixes.tgz和后续folder bundle/tar及验收截图可清理；业务卷/私有认证/证书/升级前备份不清理。本机未安装运行时。

2026-10-21 T48/T49资料列表与系统概览：无新增依赖，在devtest使用已有Node/Python/Playwright构建验证，本机未安装包。系统概览仅复用鉴权统计/档案/任务API，不新增服务或迁移。传输包/tmp/juanzhan-home-changes.tgz以及后续home源码tar/bundle、/tmp/juanzhan-home-*.png和expanded-list截图均为可清理开发文件；私有在线QA报告/截图在test-instance保管。保留业务数据卷、原件、证书、认证配置和升级前备份。

2026-10-21多类型测验：无新增依赖。devtest浏览器因系统/tmp写入/共享内存权限失败导致Compositor崩溃，使用私有/opt/juanzhan-dev/.local/types-browser-tmp作为TMPDIR解决，未改系统/tmp权限。合成样本与隔离SQLite/文件存储由测试退出清理；该私有临时目录下juanzhan-types-*.png、juanzhan-overview-types-results.json及.local/overview-types*.log、types-browser-debug.log在无需复查且无测试运行时可按名删除。新测试源码为web/e2e/overview-formats.spec.mjs和overview_samples.py；无用户文档导入测试或修改。

2026-10-20通用分点概览：无新增依赖，继续在devtest构建/Playwright验证；临时源码包juanzhan-generic-source.tar.gz、Git同步juanzhan-generic.bundle/clean.tar.gz、.local/generic-*.log和/tmp/juanzhan-generic-overview-*.png在无需复查后可按名清理。实际用户Word截图与验证脚本/JSON仅保存在私有test-instance目录，按私有资料保管。运行数据卷、认证配置及回退镜像保留。

2026-10-20信息提示迭代：无新增依赖，使用已有React/CSS及devtest的Playwright浏览器缓存。临时源码包为/tmp/juanzhan-info-source.tar.gz及服务器.local/同名包；验证日志为.local/info-reading.log、info-jobs.log及本机/tmp/juanzhan-info-broad.log，均可在无需复查后按名删除。保留运行数据卷、私有认证配置及备份。未在本机安装构建依赖。

补充可清理产物：info-rc8-build.log，juanzhan-info.bundle/juanzhan-info-clean.tar.gz，/tmp/juanzhan-info-*-verified.log及/tmp/juanzhan-release-6h1k_xr9构建manifest。test-instance/info-overview-browser.mjs/json/png与本机/tmp/juanzhan-info-*.png包含用户文档截图，按私有资料保管，无需复查后可按名删除；运行中rc.8镜像与数据卷保留。旧rc.7回退镜像在无需回退时单独清理，禁止全局prune。

2026-10-20摘要卡片：无新增依赖，新增npm test:summary使用已有Node原生测试运行器。rc.7镜像、.local/summary-cards-*.log、构建manifest、/tmp/juanzhan-summary-cards-*.png及本轮bundle/source归档为验证产物；无运行引用且无需复查时可按名称清理。实际文档只读验证截图按私有资料处理，不提交Git；原数据/认证/备份保留。

本轮构建manifest为/tmp/juanzhan-release-8x8je1ok，Git中间文件为.local/juanzhan-summary-cards.bundle、juanzhan-summary-cards-source.tar.gz及同前缀evidence归档。私有实例summary-cards-browser.mjs/json/png和本机/tmp/juanzhan-word-summary-cards-*.png含实际文档验证信息，按私有资料保管，无需复查后可单独删除。

2026-10-20内容概览：复用devtest依赖，无新安装。rc.6镜像、.local/content-overview-*.log、构建manifest、阅读/任务截图及本轮Git bundle/source.tar.gz为可按名称清理的验证产物；不删除运行数据卷、私有认证覆盖或备份。用户Word只读检查已有解析结构，无重新解析或改写。

本轮同步文件为.local/juanzhan-content-overview.bundle和juanzhan-content-overview-source.tar.gz；构建manifest在/tmp/juanzhan-release-mgnd6hov。私有实例content-overview-browser.mjs/json/png及本机/tmp/juanzhan-word-overview-*.png含实际文档验证信息/截图，按私有业务资料保管，勿提交Git；无需复查时可按名称删除。

2026-10-20单列布局：无新增依赖。新增rc.5镜像、.local/task-column-*.log、.local/juanzhan-task-column.bundle及juanzhan-task-column-source.tar.gz、/tmp/juanzhan-release-8nsk0677/manifest.json和/tmp/juanzhan-task-column-*.png；无需复查且无运行引用时可按名称清理。私有实例task-column-browser.mjs/json/png为部署验证记录；原数据/备份/认证文件保留。

PDF阅读增量（2026-10-19，专项已通过）：仅在服务器web/安装固定pdfjs-dist6.4.299，npm --save-exact --ignore-scripts；官方registry元数据核对完整性sha512-AVl138zALtfaAPvADulE0PZThbYzCBS79nL4pOSL/6Sm/4AH5A21BD9VHt97OlCuzJuCpmeZtAtkinisF4Vb1g==与锁文件一致，安装沿用已有镜像解析。主包约35MiB、可选间接@napi-rs/canvas1.0.11相关目录约35MiB（浏览器不使用）；项目npm-cache当前约48MiB，可在开发结束后按项目范围清理。构建产物当前约6.2MiB，其中本地PDF字体/CMap/ICC/WASM资源约4MiB；worker约1.3MB、PDF阅读模块约550kB按需加载，不新增Archive运行时Node进程。

记录及可清理产物位于服务器`.local/pdf-reader*.log`、`.local/pdf-web.log/xml`、`.local/pytest-pdf-web/`、`.local/pdf-budget-sample.pdf`和两端`.local/pdfjs-licenses.tar.gz`；截图服务器`/tmp/juanzhan-full-pdf-{desktop,mobile}.png`及本机`/tmp/juanzhan-remote-qa/`副本。源码、package.json/lock、licenses/pdfjs/、licenses/napi-canvas-LICENSE.txt及文本层CSS许可须保留。本机仅同步源码/锁文件/许可，没有安装PDF依赖或新增系统软件；服务器没有新系统服务/模型/数据库迁移，也未覆盖既有候选镜像。完整后端/全部浏览器/新发行验收仍待最终阶段。

浏览器资源估算：输入最多64MiB并转移到worker，画布最多8×1024²像素（RGBA约32MiB），解码大图和字体/操作缓存另计，典型阅读可达数十至数百MiB；这是预算估算，不是峰值实测或浏览器硬内存隔离承诺。关闭/损坏/超限后worker终止已有真实浏览器证据，见TESTING。

人工匹配增量（2026-10-19）：无新依赖、迁移或系统服务。开发镜像juanzhan:source-matching-dev，最终专项ID sha256:a5ca0c3fb88251522e0771b34647838ed14a0accf7dafa0f5be08d8786483a10，仅测试且dirty。报告/夹具在服务器`.local/source-match*.log/xml`、`.local/source-matching*.log/xml`、`.local/pytest-source-matching*`；截图服务器`/tmp/juanzhan-source-match-mobile.png`及本机`/tmp/juanzhan-remote-qa/`同名副本。正常退出已清理随机测试容器、卷和来源目录；仅保留原有nginx-proxy/simple-shell服务。清理开发镜像前核对引用，不删除源码或普通业务资源。

来源计划时间显示修正后，juanzhan:source-schedule-dev标签指向sha256:7b2af5d345b228fdc93b9ff47c18a249cf0adb08d7e47068abb3bb4f2b3bade1；下述4456eca为此前完整来源组测试时的镜像ID。开发标签可重建变化，清理时须以当前引用核对，不能根据旧ID直接批量删除。

来源定时扫描增量（2026-10-19）：没有安装依赖、系统服务或cron。新增数据库迁移0009及源码需保留，不作缓存清理。服务器测试产物`.local/source-schedul*.log/xml`、`.local/pytest-source-schedul*`，截图`/tmp/juanzhan-source-schedule-mobile.png`及本机`/tmp/juanzhan-remote-qa/`副本可按需清理。独立dirty镜像juanzhan:source-schedule-dev，测试时ID为sha256:4456eca1367e8fe77860587726bb785cae21c6f2a758f138416275dc080fc953；清理前核对无实例引用。测试随机容器/卷/目录退出清理，最终仅既有nginx-proxy/simple-shell运行；旧RC及foundation标签未覆盖。

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
- 初始uv工具安装使用服务器原有pip，可能写入共享`/root/.cache/pip/`；该共享目录不属于项目可整体删除范围。后续生产wheelhouse下载已明确no-cache-dir。
- Playwright Chromium下载到服务器`.local/playwright/`，不覆盖系统浏览器。该Alibaba Cloud Linux平台使用Playwright的Ubuntu回退构建，是否可运行需另行实测。
- 中英文OCR模型约6.3MiB；服务器GitHub连接重置后在本机通过官方锁定脚本下载并校验，再传入服务器`app/ocr-models/`并重新校验。本机`ocr-models/`及`.local/ocr-models.tar.gz`可清理；两端模型均可按清单重新获取。
- 复用服务器已有`/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf`绘制OCR验收样本，设置`JUANZHAN_TEST_CJK_FONT`；不新增系统字体或替换默认字体。

远程验证示例（在服务器项目源码目录执行）：

```sh
JUANZHAN_TEST_CJK_FONT=/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf .venv/bin/python -m pytest -q tests/test_batches.py tests/test_content.py
PLAYWRIGHT_BROWSERS_PATH=/opt/juanzhan-dev/.local/playwright npm run test:e2e:jobs --prefix web
```

原有8项本机library浏览器测试、服务器38项批量/正文测试及3项任务浏览器测试已通过；完整验收另以TESTING后续执行记录为准。

完整后端使用专用`juanzhan-backend-tests`容器（退出自动删除），复用项目锁定的`python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1`基础镜像；容器内只读sysfs满足来源边界夹具，不改宿主挂载。容器内存上限1.5GiB、CPU上限2核。基础镜像进入服务器Docker存储，清理前需确认无其他项目引用。生产wheelhouse位于`app/wheelhouse/`约22MiB，浏览器目录`.local/playwright/`约924MiB。

宿主机完整pytest的32项来源测试因`/sys`可写而失败；不能关闭只读检查来适配。完整后端在容器中执行418项全部通过。重现命令（服务器上执行）：

```sh
docker run --rm --name juanzhan-backend-tests --label io.juanzhan.dev=true \
  --memory=1536m --cpus=2 \
  --mount type=bind,src=/opt/juanzhan-dev,dst=/opt/juanzhan-dev \
  --mount type=bind,src=/usr/share/fonts/google-noto-cjk,dst=/usr/share/fonts/google-noto-cjk,readonly \
  -w /opt/juanzhan-dev/app \
  -e JUANZHAN_TEST_CJK_FONT=/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf \
  python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 \
  /opt/juanzhan-dev/app/.venv/bin/python -m pytest -q \
  --basetemp=/opt/juanzhan-dev/.local/pytest-container
```

本次候选镜像为`juanzhan:0.1.0-rc.1`及开发标签`juanzhan-foundation:dev`；均只在该服务器Docker存储中构建，无推送发布。源码与Git历史同步在专用app目录，当前源提交838fa07；后续文档提交不改变该构建追溯。项目专用镜像清理前需先核对有无后续正常实例引用。

最终占用快照：本机`.local/`约287MiB、`.venv/`约65MiB、`web/node_modules/`约115MiB、`ocr-models/`约6.3MiB；不含Homebrew工具本体。服务器专用目录约1.8GiB（含依赖/浏览器/测试夹具和报告），Docker镜像及构建缓存另计，服务器根分区仍约50GiB可用。测试容器与本轮具名卷均已自动清理，现有nginx-proxy/simple-shell未改动。

最终证据在服务器`.local/reports/838fa07/`；各阶段调试日志在`.local/`。浏览器截图与发布工具原始输出还位于本轮创建的服务器`/tmp/juanzhan-*`，构建manifest原目录`/tmp/juanzhan-release-dyc8vvfn/`，恢复报告原目录`/tmp/juanzhan-release-drill-qy3u2v7y/`；关键JSON已复制到项目报告目录。清理/tmp时只移除确认属于本轮的文件，不泛删其他项目目录。本机截图副本在`/tmp/juanzhan-remote-qa/`。

## 批量业务字段开发增量 · 2026-10-19

T16增量：无新依赖/系统软件/迁移。独立开发镜像juanzhan:adoption-dev（dirty，仅测试）保留；既有juanzhan:0.1.0-rc.1与juanzhan-foundation:dev未改标签。报告和夹具在服务器`.local/adoption*.log/xml`、`.local/adoptions.log/xml`、`.local/pytest-adoption*`；截图服务器`/tmp/juanzhan-adoption-mobile.png`及本机`/tmp/juanzhan-remote-qa/`。来源测试随机容器/具名卷/只读fixture正常退出删除；清理镜像前先确认无实例引用，不触碰既有nginx-proxy/simple-shell服务。

历史下载开发增量：无新依赖、系统locale安装或迁移。SSH默认POSIX，中文下载验收须指定进程环境LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8，使用服务器已有locale，不改变系统配置。可清理产物为服务器`.local/history-*.log/xml`、`.local/pytest-history-*`，服务器`/tmp/juanzhan-history-original-mobile.png`及本机`/tmp/juanzhan-remote-qa/`同名副本。测试pointer为/tmp/juanzhan-files-pointer-随机值.txt，正常退出删除；异常中断按具体文件核对清理。容器--rm，无新增镜像。

没有安装新依赖、系统软件或数据库迁移；复用上述服务器Python/Node/Playwright。新增可清理测试产物位于`/opt/juanzhan-dev/.local/`：batch-fields*.log/xml、pytest-batch-fields*测试目录；截图位于服务器`/tmp/juanzhan-batch-fields-{desktop,mobile}.png`及本机`/tmp/juanzhan-remote-qa/`同名副本。清理前如需复查应保存证据，不删除app源码或共享服务资源。既有0.1.0-rc.1镜像尚未重建为本次代码。

## 管理界面开发增量 · 2026-10-19

没有新增依赖、系统安装或数据库迁移，使用服务器现有Node/Python/Playwright。可清理证据：服务器.local/catalog-*.log/xml、catalog-library*.log、catalog-reading*.log及pytest-catalog*目录；截图在服务器/tmp/juanzhan-catalog-*.png和本机/tmp/juanzhan-remote-qa/同名副本。确认无需复查后按具体文件删除，不泛删共享/tmp、依赖或其他项目资源。本机没有为本轮运行安装包，生产候选镜像未替换。

备份传输基础增量：复用Python标准库zipfile，无新包/服务/镜像/迁移。服务器可清理.local/backup-archive*.log/xml、backup-transport-final.log/xml及pytest-backup-archive*/pytest-backup-transport-final夹具；其中包含测试备份数据库，只存私有测试目录。正常业务数据与现有实例未改变。

## Web备份管理开发增量 · 2026-10-20

无新Python/Node包、系统软件、字体、cron或常驻服务。新增0010迁移和独立私有备份卷配置；仅仓库配置已变，未实际替换现有Compose实例或业务卷。服务器juanzhan:backup-dev为本轮独立dirty测试镜像，旧RC/foundation及其他开发镜像未覆盖。确认无容器引用且无需复查后可删除该标签；不要全局docker prune或删除共享镜像/卷。

可清理测试报告/夹具在/opt/juanzhan-dev/.local：backup-management*.log/xml、backup-release-ready.log/xml、backup-*-web*.log、backup-*-library.log、backup-*-jobs.log、backup-*-build.log、backup-*-browser.log、backup-runtime-drill.log、pytest-backup-management*/pytest-backup-release-ready目录。浏览器原生下载测试ZIP在服务器/tmp/juanzhan-backup-browser.zip，含测试数据库，确认无需复查后删除；截图服务器/tmp/juanzhan-backup-{desktop,mobile}.png和本机/tmp/juanzhan-remote-qa/同名副本。运行脚本.local/run-backup-runtime.sh、各backup-*-work.tar.gz、本机.local/update-backup-openapi.py/minimize-backup-openapi.py/base-openapi.yaml也属开发中间文件，可按具体文件清理。不要泛删.local、/tmp或测试之外的备份目录。

独立运行时演练只创建随机juanzhan-backup-check-*容器和带本轮标签的三只测试卷，退出自动删除；既有nginx-proxy/simple-shell服务未改。首轮tar带入macOS ._旁文件，已按本轮tar清单逐个删除，之后使用COPYFILE_DISABLE=1；不是忽略未知迁移。业务备份卷的文件保留/恢复目录清理参照RELEASE及backup_admin，不按测试产物处理。

## 本阶段最终资源与清理快照 · 2026-10-20

本机仅编辑、读文件、Git和同步，重型依赖/调试/构建继续在授权服务器；本轮无新增本机软件包或VM。实测本机.local约304MiB、.venv约65MiB、web/node_modules约112MiB、ocr-models约6.3MiB；此前Colima/Lima/Docker CLI/Compose的安装与未启动VM记录见上文，不把共享Homebrew工具目录当项目缓存删除。

服务器/opt/juanzhan-dev约2.9GiB（含保留的测试数据库/夹具/报告），项目浏览器924MiB、web/node_modules186MiB、.venv86MiB、wheelhouse22MiB、web/dist6.2MiB；根分区约48GiB可用。Docker另计：新juanzhan:0.1.0-rc.2和backup-dev逻辑大小各约358MB，实际层共享，不能直接相加；旧rc.1/foundation及各开发镜像保留，均未覆盖旧候选。当前候选manifest与镜像ID见TESTING，无新常驻服务。

本阶段额外可清理产物：服务器.local/final-features-*.log/xml、pytest-final-features和pytest-final-features-verified两个测试目录、.local/reports/final-features-*报告；保留报告便于追溯，确认无需复查后再删。首轮failed原报告与最终provenance均在这些明确目录中。原构建manifest位于/tmp/juanzhan-release-mprm8mo9/，最终升级演练报告/tmp/juanzhan-release-drill-jnyh188e/，均为本轮专用；不要泛删其他/tmp。

两端本轮Git同步中间文件可按名称清理：.local/catalog-history.bundle、catalog-source.tar.gz、backup-management-history.bundle、backup-management-source.tar.gz、rc2-history.bundle、rc2-source.tar.gz；服务器对应文件位于/opt/juanzhan-dev/.local/。两端backup*-work.tar.gz/backup-work*.tar.gz、.local/run-backup-runtime*.sh、aggregate-final-evidence.py、verify-final-contract.py及上述OpenAPI一次性脚本也可在无需重现后清理；不删除跟踪源码、锁文件、licenses、迁移、业务卷或真实备份。

容器清理采用本轮随机名称及退出trap，最终无本轮服务遗留；保留原有nginx-proxy/simple-shell服务。后续删除镜像前先核对没有实例引用，仅选择本项目明确标签，禁止全局prune。业务/backups卷、恢复目录与测试夹具不同，按RELEASE操作，不能按本段缓存清理。

最终同步使用的.local/final-history.bundle、final-source.tar.gz（两端）也可在无需复核后删除；final-audit.py属于只读核验脚本。本机/tmp/juanzhan-final-evidence仅保存本阶段报告副本，确认无需复查后可清理，不影响源码、依赖或业务数据。

## 2026-10-20 任务进度中心迭代

复用devtest现有npm/Python/Playwright/Docker，无安装依赖。新增rc.3镜像、.local/progress-*.log与/tmp/juanzhan-progress-center-*.png为本轮构建/验证产物；保留rc.2可回退。测试实例数据卷及私有认证覆盖保留，见DEVTEST，不能当缓存删除。

## 2026-10-20 文件名与分步进度

最终报告/夹具还包括.local/step-progress-full-verified.log/xml、.local/pytest-step-progress-verified、.local/step-progress-final-targeted.log、step-progress-browser-final.log及/tmp/juanzhan-release-se57y0ix、/tmp/juanzhan-release-drill-ka7sgrhr。同步中间文件.local/step-progress.bundle与step-progress-source.tar.gz可在无需复查时按名称清理。实例目录step-*.py/mjs、step-progress-*.json/png为私有验证记录，不能连同数据卷或升级前备份一起删除。

复用devtest已有依赖/浏览器/Docker，无新增安装。rc.4镜像、.local/step-progress-*.log/xml、.local/pytest-step-progress、构建manifest和/tmp/juanzhan-step-progress-*.png为本轮产物，可在无需复查且无实例引用时按名称清理；运行数据卷/私有认证覆盖/升级前备份不可按缓存删除。0011迁移后不能直接用rc.3连接11迁移库；需按RELEASE使用rc.3与升级前备份恢复到新卷回退。
# 2026-10-21 Agent 接入开发产物

无新增本机或服务器运行依赖；复用 devtest Python/npm/Docker/Playwright。额外下载仅测试数据：`.local/juanzhan-office-fixtures`（约112KB，来源/哈希见 reference/format-fixture-sources.json），不进入运行镜像。可清理本轮 `.local/agent-*.log`、`.local/agent-full-reports`、专用 `.local/types-browser-tmp`、`/tmp/juanzhan-agent-settings-*.png` 与明确命名的 agent bundle/source 中间包。保留源码、迁移、锁文件、测试实例业务卷、私有认证文件和升级前备份；镜像仅在无容器引用后按明确标签清理，不运行全局 prune。

## 2026-10-21 Office 原生解析迭代

XLSX/PPTX/ODF/CSV/TSV复用既有SafeZip、defusedxml和Python标准库，无新增依赖/系统办公套件。测试仅在devtest隔离容器与临时HTTP服务执行。专用产物包括`.local/office-*.log`、`.local/agent-full-reports/office-full.xml`、`.local/juanzhan-office-*-work.tar.gz`、私有TMPDIR下的`juanzhan-office-*.png`；无需复查后可按明确名称清理，不删除业务卷/备份或共享浏览器缓存。固定版本Office夹具沿用上批约112KB测试数据。

## 2026-10-21 OAuth与通用REST客户端开发

后续源文件管理批次（T43～T47）进行中：本轮初版UI/快照仍复用既有Python/React/Docker/Playwright，没有本机新增依赖。服务器日志`.local/source-ui-build.log`、`.local/source-ui-browser.log`、`.local/source-snapshot-target.log`及`.local/source-snapshot-core-final.log`，两端`/tmp/juanzhan-overview-only-*.png`、`.local/juanzhan-source-*-wip.tar.gz`可复查后按名清理。业务实例仍rc.14/13迁移，0014尚未应用。

Office预览已进入隔离服务验证阶段，尚未部署到业务实例。新增独立镜像`juanzhan-office:preview-dev`（356059267字节），只在容器内安装LibreOffice Writer/Calc/Impress、字体及系统依赖，未安装Mac或服务器全局办公软件/Java。187个Debian包共207581860字节，精确来源、版本、大小与SHA256锁在`office-preview-tools.lock.json`；`scripts/setup_office_preview.py`验证/按需恢复。缓存`app/office-packages/`约199MiB，需保留至最终构建完成，之后可按锁恢复；部分旧缓存`.local/office-preview-debs`约2MiB可复核后删除。初始APT下载容器已停止。构建全程network=none，依赖校验保留；初轮安装顺序及APT离线路径问题已修正，详见`.local/office-preview-build.log`。

专用测试容器`juanzhan-office-preview-test`及网络`juanzhan-source-office-test`由本批创建；容器只读根目录、用户10001、cap-drop ALL、no-new-privileges、768MiB内存/1CPU/128进程、192MiB临时区，代码只读挂载，不挂业务数据。使用完成且无后续联调后，可按这两个确切名称停止删除，禁止全局prune。镜像未被其他容器引用后可单独删除。锁文件、Dockerfile、服务代码及许可文件属于可重建产品来源，不能当作缓存清理。新服务最终再分发许可/对应源码检查尚未完成。

本轮真实SQLite/文件/HTTP回归日志`.local/source-files-protection-tests.log`为7项通过（含真实原生DOCX预览、来源副本分页和历史概要/活跃任务保护）；前端构建`.local/source-files-web-build.log`成功但仍有既有PDF chunk体积警告。首轮宿主机测试因sysfs并非只读挂载失败，已在只读sysfs容器重验；原生DOCX初始测试样本缺少OPC内容类型声明，补齐合法声明后通过。日志、合成阅读PDF、测试归档均可在无需复查后按名称清理，不包含用户原件；业务仍rc.14/13迁移。

业务运行复用既有Python/FastAPI/Pydantic/SQLite/React与Playwright，无新运行包、模型或数据库服务。迁移0013与OAuth/REST客户端源码属于产品文件，须保留。服务器`.local/oauth-build.log`、`.local/oauth-full.log`、`.local/agent-full-reports/oauth-full.xml`、`.local/juanzhan-oauth-*.tar.gz`及两端`/tmp/juanzhan-oauth-*.png`为可复查后按名称清理的开发产物；临时OAuth浏览器库由TemporaryDirectory退出清理，未挂生产卷。测试实例原件、卷、备份和私有认证文件继续保留。

IP HTTPS运维工具单独安装在服务器`.local/certbot-venv`，Certbot5.4.0及依赖共18包，约23MiB；精确版本/所有分发哈希见`deploy/certbot.in`与`deploy/certbot.lock`，不进入Archive镜像、不安装本机/全局Python。TLS校验使用独占空闲80端口的standalone服务；开发80端口连通探测仅收到本次404请求后已关闭。测试证书私有目录`test-instance/tls-staging`可在无续期用途后清理；正式证书/ACME账户/私钥目录`test-instance/tls`须保留到HTTPS停用，不提交Git。运维工具Apache-2.0，间接包许可以各固定分发元数据为准；不捆绑分发这些工具。工具及证书配置的卸载需先停用续期与HTTPS入口，不能按普通缓存删除。

最终HTTPS gateway为独立Nginx1.30.6固定digest镜像，约27.2MiB，运行观察约2.2MiB、限额64MiB/0.5CPU；来源/证书与续期记录见IP-TEST。专用juanzhan-ip-tls.service/timer已安装；停止HTTPS后可先用 `systemctl disable --now juanzhan-ip-tls.timer` 停用，再移除对应unit并daemon-reload。按IP-TEST停止gateway引用后才能删除证书和venv。Mac未安装依赖/根证书或新增系统服务。

模型联调私有证据在服务器test-instance的model-answer.json、overview.json、content-page1～4.json、analysis-context.json及mcp/revocation-report；Mac `/tmp/juanzhan-model-interop` 为相应副本、目录0700。包含用户正文，复查后可按目录清理，不上传Git；两端临时令牌配置已删除，临时客户端/授权全部撤销。OAuth发布/续期日志、tar/bundle和Mac `/tmp/juanzhan-oauth-*.png` 可复查后按名清理；业务卷/原件/备份/当前证书及工具不能作为缓存删除。

## 2026-10-21 旧Office/RTF依赖与清理

仅devtest项目venv新增olefile0.47/xlrd2.0.2/striprtf0.0.33，wheel总219566字节；容器新增catdoc1:0.95-6（.deb86248字节，安装字符表约608KiB）及约183KiB对应源码/通知。无本机新依赖、无服务器全局pip/系统包安装，无LibreOffice/Java。uv固定现有依赖，只新增三个包；工具沿用项目.local/tools/bin/uv0.12.3。

准备工具的临时Docker容器已退出（APT索引随容器删除）；`.local/legacy-debs`仅保留一份约84KiB的验证下载副本，可在无需复核后删除。构建缓存`app/native-packages/`含工具和源码，可按legacy-tools.lock.json重建；新wheel保存在既有wheelhouse，按锁文件恢复。运行镜像含许可证与对应源码，不能作为不必要产物从发行镜像剔除。

本轮`.local/legacy-*.log`、`.local/agent-full-reports/legacy-full.xml`、中间legacy-work归档和私有TMPDIR的juanzhan-legacy-*.png可在无需复查后按明确名称清理。固定blob测试数据`.local/juanzhan-extra-format-fixtures`现为13份/463988字节（约453KiB），来源/哈希见reference/extra-format-fixture-sources.json；不进入运行镜像。测试镜像juanzhan:legacy-dev无容器引用后可清理，禁止全局prune。业务卷、私有认证文件、备份和原件不在缓存清理范围。

本批真实来源版本演练脚本scripts/source_snapshot_drill.py只创建随机juanzhan-source-drill-*容器/卷/网络及合成临时目录，退出按名称回收；不访问业务卷或凭据。源目录对容器只读，宿主只改合成测试文件，验证相同大小/mtime变化、幂等扫描、历史版本离线读取与人工说明保护。source-snapshot-real-drill.log为成功证据，可复核后清理。source-full-backend-final.log最终615通过/无跳过，source-contract.log额外2项通过，source-reading-backup.log额外2项通过。新代码已分后端/前端提交，尚未推送/部署；发布脚本将另建rc.15业务与原生阅读两个镜像，均带源码追溯标签。

PDF专项发现服务器继承的非UTF8 locale会使测试Chromium把中文下载名统一退为download，独立英文/中文Blob探针复现；仅测试浏览器launchOptions设置LANG/LC_ALL=C.UTF-8，未安装/修改主机locale。source-files-pdf-utf8.log最终9项通过，保留中文名和原件字节断言。source-download-{diagnostic,probe}.log仅含合成测试正文/文件名，可复核后清理。rc15初次双镜像ID及干净来源见test-instance/rc15-manifest.json，恢复演练见rc15-release-drill.json，后续前端附件流调整需重建，不在此时切换业务实例。

## rc.15最终运行与清理状态 · 2026-10-21

业务已升级13→15迁移并公网验收。最终源码045901e（source_dirty=false）的业务33e6e75f...、Office b692c95a...镜像保留，精确ID见DEVTEST和私有rc15-final-manifest.json。业务Word首次阅读新增约302.7KiB可重建PDF（存储页显示值），原件不压缩、不替换；全站旧19文件和全部原业务表保持。阅读缓存现有1份，不自动清理用户内容。

运行瞬时观测约Archive46.98MiB、Converter33.28MiB、worker41.82MiB、Office94.85MiB、gateway4.613MiB；非峰值保证。Office硬上限768MiB/1CPU/128进程、192MiB临时区，原件下载在数据卷准备私有匿名临时文件，并发两路最大约2GiB磁盘暂存预算；服务器实际内存约3.477GiB，应按这些硬上限和临时磁盘预算配置并发。

本次两个测试renderer容器juanzhan-office-preview-test/juanzhan-office-rc15-verify、juanzhan-source-office-test网络、preview-dev镜像已按确切名称删除。最终业务五服务、rc.14回退镜像、原件卷/备份卷/证书/续期工具继续保留。app/office-packages约199MiB可在不构建时清理，凭187包锁恢复；旧.local/office-preview-debs约2MiB、source-*.log/pytest-source-*合成测试目录、源码tar/bundle/传输AppleDouble备份可复核后按名清理，禁止全局Docker prune。用户正文截图/状态报告和source-before.env在test-instance为私有资料，权限与现有0700目录一致，不提交Git。source-before.env含部署凭据，仅在不需要操作回溯且当前.env已保留时按名删除。

未新增Mac依赖、压缩器、Java、模型或主机全局包。独立Office依赖及字体187包的copyright在成品镜像全部存在，许可与将来再分发边界见THIRD-PARTY。

2026-10-24 T55无新增依赖。本轮devtest日志为.local/agent-priority-*.log，源码传输临时包.local/agent-priority.tar.gz可清理；rc.23镜像和升级前备份按回滚保留策略清理。原件、分析记录和现有Markdown不属于临时开发文件。


2026-10-24 T56无新依赖，构建/真实集成和Playwright在devtest已有环境执行；.local/import-tags-*.log和本轮传输tar为可清理开发文件，test-instance/import-tags-*部署证据和升级前备份按保留策略管理。原件/持久标签/保存组合不属临时文件。

2026-10-25 T57无新增依赖。devtest .local/upload-panel-*.log和传输tar为本轮可清理文件；rc.25与/backups/before-upload-panel-rc25按回滚策略保留。没有删除旧档案、辅助文件历史记录或原件。

2026-10-25 T58无新增依赖。.local/upload-count-*.log/传输tar与/tmp计数测试目录可清理；原件/档案保留。rc.26与升级前备份按回滚策略保留。

2026-10-25 T59无新依赖，.local/upload-policy-*日志/传输包与/tmp浏览器证据可清理；rc.27及升级前备份按回滚策略保留，业务原件/配置非临时文件。

2026-10-25 T60: User requested bulk task controls and unfinished files retained until verified processed. Implementation, completion criteria, lease fencing, soft deletion, migration 0020, API 0.4.39 and cleanup boundaries are recorded in TASK-CONTROLS. No new dependencies.

T60 final frontend candidate rc.29 adds no dependencies. The navigation build logs and before-job-controls-navigation-rc29 backup follow the same cleanup/rollback policy. Existing originals, task control state, audit and upload policy are durable business data.

2026-10-25 T61：无新依赖，构建及浏览器验证沿用devtest Node/Playwright；临时包/脚本为devtest /tmp/compact-filters-*，截图和备份记录在/opt/juanzhan-dev/test-instance/compact-filters-*，构建日志在/opt/juanzhan-dev/.local/compact-filters-build.log。保留当前镜像与升级备份用于回滚。
