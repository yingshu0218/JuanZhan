# devtest 测试实例

2026-10-22 rc.19/T51部署：源码aaa8fa2，业务image sha256:f1d6470dfd636e5a738e4ce0bce73eeb2a94a7e4051c99b60bc516841998b12b，Office仍rc.15，五服务healthy。入口https://8.153.19.221:443/，test/111不变。升级前备份before-exclusions-rc19；私有exclusions-before/after/after-qa.json、exclusions-deploy.json、exclusions-live.json、exclusions-desktop/mobile.png在test-instance。部署前已有8档案/37文件（不同于上一批历史4/20），部署和公网拒绝/跳过QA后全部业务表及文件哈希一致，15迁移不变。未清理已导入的辅助文件，后续上传按新规则排除。辅助文件测试均在隔离存储执行，公网仅验证跳过和422拒绝，无新档案。临时exclusions bundle/tar/tgz、/tmp/exclusions-deploy.py和exclusions-live.mjs可清理，原件卷/私有配置/备份/镜像不自动删除。

2026-10-22 rc.18/T50部署：运行源码e19fc8c，业务image sha256:048c942e516b76ccd2caf493f3d166564fb5cefc9df025e2f602c37aa1f871cc，Office仍rc.15；五服务healthy。https://8.153.19.221:443/，test/111不变。“导入文件”面板提供文件和文件夹选择，亦可混合拖入。升级前备份before-folder-rc18；私有folder-before/after/after-qa.json、folder-deploy.json、folder-live.json和folder-entry-desktop/mobile.png在test-instance。所有实际样本仅在隔离浏览器测试库执行并清理，业务原4档案/20文件及15迁移不变。前端相对路径仅用于映射逻辑目录，multipart始终只传原文件名及folder_id，不接收客户端磁盘路径。无新增依赖；临时folder bundle/tar/tgz、/tmp/folder-deploy.py、folder-live.mjs及测试截图可清理，备份/镜像/认证/原件卷保留。

2026-10-21 rc.17/T49已部署：业务源码be797b8，image sha256:06fa97cb221b607172424b2037273d05936dc940d7f9d3b8e635658f1146ccd3，Office保留rc.15，五服务healthy。入口https://8.153.19.221:443/，test/111不变。升级前备份before-home-rc17；私有证据home-before/after/after-qa.json、home-deploy.json、home-live.json和home-desktop/mobile及expanded-list截图在test-instance。原4档案、业务表、20文件不变，15迁移不变。全局概览复用/system/summary、全局最近6档案和排队/处理中任务计数，进入具体列表仍遵循当前空间；近期档案可跨空间打开。无新增依赖/服务。home传输tar/tgz/bundle及/tmp/home-live.mjs、home-deploy.py为可清理临时文件，备份/镜像/数据卷不自动清理。

2026-10-21 rc.16紧凑资料列表部署：运行源码7f55ab0，业务image sha256:b99f259d9164615758fb85833dd66c005c56cce024e8a4b5ddf7e1c92aea7063；Office沿用rc.15，五服务healthy。https://8.153.19.221:443/，账号test/111。备份before-library-rc16；私有证据library-before/after.json、library-deploy.json、library-live.json和library-desktop/mobile.png位于test-instance。升级前后原4档案、业务表及20文件哈希完全一致，无迁移、无新增依赖、本机未安装开发运行时。已有显式URL view=grid会继续显示网格，点击列表即可保存新偏好。

清理记录：本轮仅新增rc.16业务镜像、升级前备份、私有QA报告/截图；旧镜像及备份保留供回退。/tmp/juanzhan-library*.tar/tgz/bundle、library-live.mjs、library-deploy.py为传输/验收临时文件，用后可删除；不要删除业务卷、原件、现役镜像、证书或.env。依赖仍使用既有Node/Python/Playwright与锁定wheelhouse，未新增包。

当前为rc.15，T43～T47已交付。最终源码045901e，15迁移、Archive0.4.32/93路径；原4档案及业务表和19文件不变，按需阅读仅新增1份缓存。双镜像、备份和公网验收详情见本文末尾“当前rc.15源文件管理”。以下rc.14为历史记录。

## 历史 rc.14 · 2026-10-21

公网测试入口 [https://8.153.19.221:443/](https://8.153.19.221:443/)，同时保留127.0.0.1:18080；测试账号test/111仍仅私有auth覆盖，已从新auth.py重新生成覆盖，生产密码规则不变。20种输入MIME/OCR可用；Archive0.4.31/85路径/13迁移。正式域名和正式上线由用户延期。

业务镜像`juanzhan:0.1.0-rc.14`，ID `sha256:2d704cbf11bb60b3b0302bd7755c8833f436f72694ee81a99cf819b040f6c59c`，干净源码90a08407815d6b0af39f8ab57f4120b47b3a4c2e，source_dirty=false，私有rc14-manifest.json。Nginx外置配置修正为9694604，实际1.30.6/digest与证书工具见IP-TEST。四个本项目容器健康，其他既有服务保留。无公开镜像/Git标签/Release发布。

升级前rc.13私有备份 `/backups/before-oauth-rc14`，18份引用对象；实际12→13迁移。oauth-before/final.json中的4份档案版本/Revision/ParseRun及19份managed/derived文件哈希一致，integrity=ok、无FK错误，Word未重解析。新13迁移库不能让rc.13直接接管；回退须用rc.13及升级前12迁移备份恢复到新卷。

验收：595项完整后端，新增REST/导入契约/恢复与会话隔离专项；真实OAuth浏览器1项；在线Agent9项；公网Word1440/390只读概览、依据跳转、无数字卡片/溢出/控制台错误通过。外部模型与REST/MCP/stdio、撤销后401见AGENT-INTEROP。TLS证书验证未跳过，未授权401带固定resource_metadata。IP证书续期timer已启用，模拟续期/配置检验/reload成功。

rc.14独立发布演练45.57秒通过：旧8迁移实例实际导入/检索→候选13迁移升级，保持登录/数据→一致备份→新目录/新卷恢复→登录/下载/正文/检索/完整性；uid10001、只读根、cap_drop ALL、CSP通过，随机测试项目/卷退出清理。私有rc14-release-drill.json留证。后续历史记录不能覆盖本段现状。

2026-10-21 rc.10：十份六格式概要实测后修复首章名称误省略。镜像sha256:8fc85cbf73f4ddc356c15d9fccbfabe297a6fe72002fe6a284bcb5e6654705a7，干净源码281b929，私有rc10-manifest.json；新测试在隔离数据库/文件存储执行并清理，原测试卷及test认证覆盖保留。无新依赖/迁移，rc.9保留同卷回退。目标和当前概要前端计算边界见ARCHITECTURE，实测结果见TESTING。

rc.10部署后三服务健康，实际用户Word1440/390只读核对通过，无重解析或版本变化。本轮GitHub HTTPS push多次连接超时，远端main当时仍2e35c82；修复提交281b929及后续文档保存在本地和devtest，不能声称已同步GitHub。后续网络恢复后正常fast-forward推送，勿强推。

最新rc.9：通用分点内容概览，取消数字/领域专用卡片，原文标题/标签加粗着色，数字保留普通文本。最终源码7168700，镜像sha256:83776d5283eead7eabca8da5d147664137209092aa5abe4027647fee42b27349，manifest私有rc9-manifest.json；三个服务及原数据/认证覆盖保留。实际Word桌面/手机只读核对、依据跳转与文档不变验证见TESTING。无新依赖/API/迁移，rc.8保留同卷回退。

最新rc.8：默认摘要概览及各页面信息图标，鼠标悬浮/键盘聚焦/手机点击显示说明。干净源码b0e903c，镜像sha256:8956c1a0aaa6dbbe0fc0cc0297310b8e5142fd5e9ca43b8d57a2116addfcdd2b；私有rc8-manifest.json保留构建来源。原测试卷、test认证覆盖及SSH隧道访问保留，无新增依赖或迁移。实际Word1440/390只读浏览器核对通过，未重解析，细节见TESTING。rc.7保留用于同卷回退。下文旧版本记录仅为历史。

最新rc.7已部署：默认“摘要与关键信息”，含价格/时长/课次/适合人群/课程内容及原文依据；章节摘录/全文仍可进入。干净源码e04653c，镜像sha256:f23eb175eb8f9badb0f6f3d77b00856a3fc56afa6513e825dfb255928e3af9b2。7项规则、8项浏览器及实际Word桌面/手机只读核对通过；原件/解析记录/版本/人工字段保留，未重新解析。无后台/迁移变化，仍11条，可用rc.6同卷回退；私有test认证覆盖继续沿用。

最新rc.6已部署：详情默认原文章节摘录概览，完整正文按需进入，来源定位/转换说明默认折叠，重新解析为次级操作。镜像sha256:e53f7680c63a70ea039b791cf14ef94c80a4f77abeab675378eb629e5c44a36d，干净源码e9484b8；7项阅读/任务浏览器及实际Word桌面/手机只读核对通过。无迁移变化，仍11条；原件/正文/业务字段保留，无重新解析。可用rc.5相同数据卷回退，私有test认证覆盖仍需叠加。

最新运行rc.5：任务中心已统一单列竖向，详情在原任务下展开。镜像sha256:ccb4ae85cc237372697d9806ef3f94f43c87fe2560600422e7de2d5d152b31e6，干净源码3f81626；三个服务健康，实际1440/390浏览器及4项任务回归通过，原4份档案保留。访问/私有认证覆盖继续沿用。以下rc.4及更早记录为历史，无新迁移，必要时可用rc.4原卷回退。

当前运行：0.1.0-rc.4（2026-10-20），11迁移，文件名及五步独立进度已实际验证。以下rc.2/rc.3为历史部署；访问地址与私有test认证覆盖继续保留。

rc.4镜像sha256:cbd33b3d2f91d5f380b1fd3144ef22d6d1ce2a2116879fd97b574530f78d937e，干净源码f951bff。升级前10迁移一致备份在/backups/before-step-progress-rc4（操作员路径），新增0011后10条旧校验及原4档案ID/Revision/正文引用/版本完全保留，integrity/FK通过。只重跑原虚构welcome.txt验证五步完成，未重跑用户Word。

迁移后不能直接用rc.3连接当前11迁移卷。回退须用rc.3与升级前备份恢复到新卷，验证后切换，见RELEASE；旧备份/镜像保留。旧任务没有步骤记录，页面明确说明；新解析或显式重解析才会记录五步。

2026-10-20按用户要求先推送代码，再部署测试实例。功能提交39ec01a已推送GitHub main；实例使用已验收的juanzhan:0.1.0-rc.2，镜像ID为sha256:9b4b6025a19a5fac45c6390f5f95e130cbaed261fcd6247f3bd76d7f0e33237d。后续文档提交不改变镜像源码追溯。

## 访问

Compose项目juanzhan-test，配置在服务器/opt/juanzhan-dev/test-instance/.env（权限600），使用仓库deploy/compose.yaml及服务器私有test-auth.yaml覆盖；三个服务健康，restart为unless-stopped。原有服务保持运行。仅绑定服务器127.0.0.1:18080，通过SSH隧道访问本机 http://127.0.0.1:18080 。隧道已启动，连接中断后执行：

```sh
ssh -NT -L 127.0.0.1:18080:127.0.0.1:18080 -o ExitOnForwardFailure=yes devtest
```

测试用户名test，密码在本机未跟踪的.local/devtest-access/admin-password（权限600），服务器私有实例目录也保留admin-password。密码及.env不得提交。回环HTTP隧道测试设置Cookie Secure=false；对外HTTPS应改回true。转换器不公开端口。

## 数据与验证

保留“开发验收示例（可删除）”空间及welcome.txt、meeting.md、invoice.html三个虚构档案，均经真实上传和常驻worker/Converter解析完成。部署HTTP冒烟验证登录、正文、逐字节原件下载、中文检索、持久备份成功及自动备份默认关闭。服务器deployment-smoke.json保留结果，seed.py为一次性导入脚本，不应重复执行。此前完整481项后端/39项浏览器/30项映射结果见TESTING，本次没有重跑完整套件。

启动后容器合计约157MiB内存，这是瞬时观测，解析/OCR高峰可能更高。无新增依赖、系统服务、定时任务；未公开Release或推送镜像仓库。

## 停止与清理

本机SSH隧道退出不影响服务器实例。临时停止：

```sh
cd /opt/juanzhan-dev/app
docker compose --env-file /opt/juanzhan-dev/test-instance/.env -p juanzhan-test -f deploy/compose.yaml -f /opt/juanzhan-dev/test-instance/test-auth.yaml stop
```

再次启动使用同参数up -d --wait --no-build。专属持久卷juanzhan-test_archive_data及juanzhan-test_archive_backups包含测试数据及备份，不作为缓存删除。maintenance运行时另建juanzhan-test_archive_recovery卷。确认不再需要时才移除本项目容器及对应卷，勿全局prune。私有配置/密码/报告与本机.local/devtest-access可单独按需清理；通用依赖边界见LOCAL-DEVELOPMENT。

2026-10-20后续迭代：rc.3增强任务中心入口/真实活动计数/自动更新与上传任务直达，保留原测试数据卷及test认证覆盖。启动/更新也须叠加上面的test-auth.yaml；只对测试实例生效，上线前撤销覆盖并通过admin CLI设置正式密码。原rc.2镜像ID与验收记录为历史部署追溯。

rc.3已于本日实际切换完成，镜像ID sha256:31b24ade3211667c943f6c2d33022dc0b756755c76f5d8112d11f8182902515c，干净构建提交c1f0a02。切换前一致备份保存在本实例备份卷/backups/before-progress-rc3（仅操作员路径）。部署后1440/390真实浏览器验证通过，原空间4份档案保留；三个服务健康。回退可将私有.env镜像改回rc.2并用两个Compose文件启动（本次无迁移变化）。
# 2026-10-21 rc.11：MCP＋REST 与后端概要

代码已推送 GitHub main：`bcf0cc76ad71c213dd94db688756643570098488`。使用本机已有 HTTP 代理进行单次 Git 传输，未修改全局 Git/代理设置，之前待推送提交已同步。

devtest 从干净提交构建并部署 `juanzhan:0.1.0-rc.11`，镜像 `sha256:a153dc5acea1c0013e04de8d336f069c8dc0ca5244982292f9d436dad9fd1585`；manifest `/tmp/juanzhan-release-5t548sn5/manifest.json`（私有副本 `test-instance/rc11-manifest.json`），source_dirty=false，未发布镜像或公开站点。使用原 Compose 项目/数据卷与两份配置，认证私有覆盖从新 auth.py 重新生成，仅保留测试用户名差异；测试登录不变。

升级前一致性备份：业务备份卷 `/backups/before-agent-rc11`，18个文件。实际11→12迁移，旧11份 SQL 校验和不变；4份档案的 ID、当前 Revision/ParseRun/document_version 及19份托管/派生文件哈希完全一致；SQLite integrity=ok，无FK错误。迁移前后核验记录 `test-instance/agent-before.json`、`agent-after.json`、`agent-upgrade-verified.json`。schema_migrations 是早期业务版本表（3条），文件迁移数以 migration_checksums 为准。回退需 rc.10 配合升级前备份恢复到新卷，不可将旧代码连接已迁移库。

在线 Agent 实测9项通过：授权空间、检索、共享概要、自然语言问题的分析证据、两代 MCP、写入/全局API拒绝、撤销。临时凭据在 finally 中撤销，数据库无遗留Agent凭据；未保存明文。报告 `test-instance/agent-live-smoke.json`。用户 Word 默认分点概要、内联数字、章节强调、来源跳转、1440/390无溢出/控制台错误、档案未变通过；未重解析。报告 `test-instance/generic-overview-smoke.json`，截图同目录 generic-overview-desktop/mobile.png。

三个生产容器健康；回环/SSH隧道 healthz=200，旧隧道失效后仅重建本项目转发。观测空闲内存约 archive46.6MiB、converter40.8MiB、worker29.7MiB（瞬时值，非峰值保证）。原 nginx-proxy 和 simple-shell-terminal-1 保留运行。依赖与可清理产物见 LOCAL-DEVELOPMENT；完整回归见 TESTING。
## 2026-10-21 rc.12 原生Office与CSV/TSV

功能提交1d2a8e7dbfeb725a270f8e22237e4b394278bf7d已推送；干净候选`juanzhan:0.1.0-rc.12`，镜像`sha256:0b182686ddfd78de091ad7ff52adc49225092a7e25ad6f01903cc4c100614a3a`，source_dirty=false；manifest `/tmp/juanzhan-release-x95cdeiu/manifest.json`，私有副本test-instance/rc12-manifest.json。完整后端/浏览器/13类只读来源镜像实测通过后升级原Compose实例。SQL仍12迁移，Archive0.4.30/74路径、Converter0.4.4/6路径，无新增运行依赖。

升级前备份`/backups/before-office-rc12`（18个文件）；test-instance/office-before.json与office-after.json完全一致：4份档案当前Revision/ParseRun/版本、19份文件哈希、完整性ok/无FK错误。认证私有覆盖逐字验证只含原测试用户名差异，不改密码。上线后Converter实际声明16种输入MIME；原Word1440/390默认概览与来源跳转只读验证通过，未重解析，Agent在线9项通过且临时凭据已撤销（office-agent-live-smoke.json）。三个容器healthy，两个无关服务保留。rc.11镜像和升级前备份保留可回退，镜像未对外发布。

用户最新选择先devtest/IP端口测试，暂不正式域名/发布；公网IP入口配置在后续任务中，当前18080仍为回环/SSH隧道，不虚称已经外网可达。
## 2026-10-21 rc.13 旧Office/RTF与PPT备注

功能提交`f697ec81c0317c052d44e0ed9108b2a2c71ca3cd`已推送GitHub main；干净候选`juanzhan:0.1.0-rc.13`，镜像`sha256:f65cc713840261349d3d6cd4226d3790d796f7fbf9ae6de3a918ffa534cd4c1d`，source_dirty=false，manifest `/tmp/juanzhan-release-24u78le4/manifest.json`（私有副本test-instance/rc13-manifest.json）。Docker逻辑镜像大小由rc.12的101271340变为102519467字节，新增1248127字节（约1.2MiB），无Java/LibreOffice/新OCR模型。运行新增三包及catdoc/对应源码见THIRD-PARTY，主机系统未安装原生工具。

完整586项/最终8项阅读浏览器/17类文档镜像只读来源实测通过。备份`/backups/before-legacy-rc13`（18文件）后升级原Compose三服务与原私有test-auth覆盖，三服务healthy。Archive仍0.4.30/74路径、12迁移，Converter0.4.5/6路径，在线capabilities实际20种输入MIME。API源字段/原SQL未改。

test-instance/legacy-before.json与legacy-after.json完全一致：4份原档案ID/当前Revision/ParseRun/业务版本、19份文件哈希、数据库完整性ok且无FK错误。在线Agent9项、旧Word1440/390只读概览/来源跳转/无控制台错误均通过，未重解析，临时Agent凭据已撤销；报告legacy-agent-live-smoke.json及generic-overview-smoke.json。两个原有无关服务保持运行，阅读Converter退出清理已复验。最新证据提交只改测试退出清理/文档，不改变已构建运行源码。

当前18080仍是回环/SSH隧道，IP公网入口待后续配置；不把测试实例当正式上线，不发布镜像或GitHub Release。rc.12及升级前备份保留作回退，依赖/测试产物清理边界见LOCAL-DEVELOPMENT。

## 当前rc.15源文件管理 · 2026-10-21（覆盖上文rc.14现状）

入口仍为[https://8.153.19.221:443/](https://8.153.19.221:443/)，测试test/111，原私有auth覆盖逐字核对仅用户名不同，密码/生产规则不改。最终构建源码045901e3978fb18879af2f257ad4731daa52833c已推送，source_dirty=false；业务镜像sha256:33e6e75f2f8ad89211a9cb7f4218ce67552df83dcc399c82893f7494e000513f，原生阅读镜像sha256:b692c95aff4fc62ae85fa63dfbd88692ce1d122fa96046499e930d68b41fc0dd，私有rc15-final-manifest.json。Archive0.4.32/93路径/15迁移，Converter仍20种MIME。

切换前一致备份/backups/before-source-rc15-final（18引用对象），source-before-final.json留存原档案/Revision/ParseRun/人工字段/目录标签/来源表及文件哈希。实际13→15迁移后source-upgrade-verified.json证明4档案及原业务表/19文件完全不变，integrity=ok，FK=0。原生Word预览后source-final-data-verified.json证明所有旧19文件完整保留，现20文件，只新增1份可重建PDF；业务表/文档版本/原ParseRun仍相同，未重解析。

公网source-public-browser.json经真实TLS、1440/390概览/实际Word四页源文件阅读与存储入口通过，无控制台错误/溢出；未执行生产清理。source-agent-live.json公网REST/MCP9项通过且临时凭据撤销。源码完整615后端/契约与备份/确认来源专项、多格式阅读8项/PDF9项/PNG-JPEG1项/主界面12+1复验通过，详见TESTING。最终成品独立发布恢复演练49.09秒通过，见rc15-final-release-drill.json。

五个项目服务均健康。Office仅私有Docker网络，不挂业务卷/宿主端口，uid10001、只读根、无capabilities、768MiB/1CPU/128进程和192MiB临时区实查通过；现有nginx-proxy/simple-shell-terminal-1未修改。两个专用测试Office容器、测试网络与preview-dev镜像已清理，保留rc.14和最终rc.15。rc.14不能直接连接15迁移库；回退须旧镜像配合升级前13迁移备份恢复到新卷，不能仅回退.env标签。压缩和正式发布延期，无Mac新依赖。
