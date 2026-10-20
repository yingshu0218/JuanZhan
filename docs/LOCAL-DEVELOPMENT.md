# 本机开发依赖与清理记录

2026-10-20信息提示迭代：无新增依赖，使用已有React/CSS及devtest的Playwright浏览器缓存。临时源码包为/tmp/juanzhan-info-source.tar.gz及服务器.local/同名包；验证日志为.local/info-reading.log、info-jobs.log及本机/tmp/juanzhan-info-broad.log，均可在无需复查后按名删除。保留运行数据卷、私有认证配置及备份。未在本机安装构建依赖。

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
