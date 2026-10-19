# 本地候选版本与升级恢复手册

当前候选版本由根目录`VERSION`定义：`0.1.0-rc.1`。这是实施用候选编号，不代表已推送Git标签、GitHub Release或容器仓库，也未替换当前开发实例。发布用Compose为[deploy/compose.yaml](../deploy/compose.yaml)，开发Compose保持原样。支持范围和已知缺口见STATUS/ACCEPTANCE；性能观察见PERFORMANCE。

## 构建与追溯

在仓库根目录，先按DEVELOPMENT准备同架构Python3.12哈希wheelhouse、OCR模型与前端锁定依赖；然后运行：

```sh
.venv/bin/python scripts/build_release.py
```

命令构建生产前端和本地`juanzhan:0.1.0-rc.1`，不启动现有服务、不发布镜像。基础镜像按digest固定，pip离线安装/哈希校验、OCR模型验证保留。OCI标签记录版本、源码commit和source-dirty；外部/tmp manifest记录完整image ID、架构及published=false。开发验证允许dirty构建，但正式分发只使用提交后重新构建的source_dirty=false产物。tag可被本地重建覆盖，不把tag本身当不可变证据；保存测试通过的image ID，外部分发后固定仓库digest。

当前只实测Linux x86_64/amd64，不能把这一wheelhouse或镜像宣称为已支持arm64。Python包内部版本仍为0.1.0，候选编号用于镜像/发行交付，不改变Archive/Converter HTTP版本。

## 首次部署

以下命令从仓库根目录执行。先复制`deploy/.env.example`为未跟踪的`deploy/.env`并设权限600；通过安全编辑器填入私有随机CONVERTER_SERVICE_TOKEN，不能沿用示例空值。设置JUANZHAN_IMAGE为测试过的本地版本（核对image ID）或已发布的不可变仓库digest。仓库不会生成或提交生产密码。

```sh
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml up -d --wait --no-build
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml exec archive python -m juanzhan.admin set-password
```

第二条通过终端无回显初始化管理员，也会撤销旧会话/token；仅首次安装或明确重置时执行，不把它放入升级启动脚本。自动化可通过已有`--stdin`安全管道提供密码，不在命令行参数/日志中写入密码。生产管理员和开发实例各用独立项目/卷；不要把`juanzhan-prod`误换成现有开发项目名。

服务默认只绑定127.0.0.1:8000，Converter和worker不公开端口；需管理员的HTTPS反向代理对外提供服务。Secure Cookie默认true：普通HTTP登录不会维持安全会话，只有明确的本机隔离测试才设false，不把测试配置直接公开。反向代理需配置请求体/超时预算，避免记录Cookie、Authorization或私有正文。当前不提供域名、证书或外部代理自动部署。

运行容器UID10001、根文件系统只读、cap_drop ALL与no-new-privileges；只允许数据卷及私有/tmp写入。Archive临时空间默认256MiB，转换/worker为128MiB；大文件有效额度还受可用临时空间约束（外部原件固定复制会用更多空间），超过预算如实失败，不把HTTP1GiB上限当默认容器一定能下载1GiB。需要大文件时先按实际并发和磁盘/内存预算调整临时挂载并重新验证。

## 只读外部来源

默认无来源挂载。需要时由管理员另建Compose override，将可信宿主目录以`:ro`同时挂给archive与archive-worker，并在同一私有环境中设置别名到容器内路径的JUANZHAN_SOURCE_MOUNTS JSON。只允许别名从Web选择，不接收Web用户任意宿主路径。仅chmod只读不等于内核只读挂载；挂载可写、路径含软链或来源失联会被拒绝。不把外部目录挂到managed、backups、recovery或Converter中。

外部目录本身不在本地备份包中；其字节、目录身份、挂载映射和权限需独立保存。恢复只有索引与业务信息时，来源应如实显示离线，不能宣称外部原件已恢复。

## 备份与恢复到新卷

本Compose提供maintenance profile与独立持久archive_backups、archive_recovery卷，镜像内对应目录归UID10001；不用容器可写层存唯一备份。

```sh
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml stop archive-worker
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml run --rm maintenance python -m juanzhan.backup create --output /backups/before-upgrade
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml start archive-worker
```

推荐暂停用户写入的维护窗口。CLI本身通过两store排他锁+DB写屏障建立一致副本；忙/缺原件/损坏会失败，先确认命令退出0及COMPLETE，不把备份目录存在当成功。输出目录必须全新，重跑使用新名字。再由管理员把整个私有包安全复制到独立介质；Docker命名卷与原机同盘不能抵御整机丢失。包内含业务内容和密码哈希，无内建加密/签名，只有可信管理员备份可恢复。

```sh
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml run --rm maintenance python -m juanzhan.backup restore --input /backups/before-upgrade --output /recovery/restore-check
```

恢复要求与备份精确匹配的应用迁移集合，不进行自动跨版本迁移，绝不覆盖当前archive_data。恢复保留管理员密码，撤所有旧会话/API token/worker租约；运行任务沿原预算处理。若RESTORE_IN_PROGRESS遗留，不手动删标记启动，保留原包并在另一个新目录重新恢复。

验证新实例时另建override，例如：

```yaml
volumes:
  archive_data:
    external: true
    name: juanzhan-prod_archive_recovery
```

以独立`juanzhan-verify`项目、不同本机端口（例如18000）、`JUANZHAN_DATA_DIR=/data/restore-check`启动同版本镜像，叠加上述override。外部来源未核对前不要挂入或对外服务。重新登录，核对管理员/档案ID/人工字段/标签/下载哈希/正文/预览/中文检索/任务，执行SQLite integrity_check和foreign_key_check后，再计划人工切换数据卷。脚本不执行生产切换。

## 升级与回退

1. 记录当前镜像完整ID/digest、Compose/env/来源配置和8条已应用迁移校验；保留旧镜像及可读备份。不要在升级中重设管理员或删卷。
2. 先用隔离备份恢复副本验证目标版本；确认其迁移兼容与API变化。当前候选只演练了8迁移到同8迁移的真实镜像替换，不承诺任意旧版本升级。
3. 在维护窗口创建一致备份，停止worker并暂停写入，更新私有env中的JUANZHAN_IMAGE为已验证目标digest/tag；`up -d --wait --no-build`。Archive自动应用新增迁移并校验旧迁移不可变，启动失败保留原库，不手工改migration_checksums。
4. 验证服务健康、worker心跳、登录、真实上传/正文/检索/原件；成功后恢复正常访问。出现错误先停写并保存诊断，不反复重启产生额外工作。
5. 若数据库已被新版迁移，不把旧镜像直接连新版库。用旧版本匹配的恢复命令把升级前备份恢复到新目录/卷，按上述独立实例验证后切回；不要覆盖新版库，保留失败现场。数据切回可能丢失备份后写入，先核对再决定，不承诺自动无损回退。

## 本地发布演练

先保留已有`juanzhan-foundation:dev`作为同schema升级起点，并构建候选，然后：

```sh
.venv/bin/python scripts/release_drill.py
```

脚本为自己创建不可预测的隔离项目/卷和随机凭证，实际跑初装→上传/解析→检索→替换候选镜像→备份→新目录恢复→新实例登录/下载/正文/检索/DB完整性；还检查根只读、UID和Web资源/CSP。只删除带本次随机项目label的测试卷，不使用down -v，不修改正常项目或其.env/管理员。输出私有/tmp报告，不代表真实业务生产卷已切换。

## 对外发布仍未执行

当前只交付本地候选。后续需明确目标镜像仓库/命名空间与授权，使用平台已有认证验证后再推送版本镜像、记录registry digest；Git标签/GitHub Release也需单独执行。不可在缺少目标时假称已发布，不能提交凭证或把本地image ID写成registry RepoDigest。RC验证通过不等于稳定版承诺。

## 新开发版本：Web备份与恢复目录激活 · 2026-10-20

以下步骤针对含0010迁移/backup_admin的新代码或镜像；历史0.1.0-rc.1不具备这些能力。尚未替换该历史候选，当前构建信息以最新验证记录为准。配置/backups独立持久卷，archive/worker共享，权限700且归运行UID10001；旧版维护卷若为755，应由目录所有者改为700。不要将备份卷、恢复卷或外部来源挂到活数据内部。

管理员登录后，系统设置→备份与恢复→创建备份，等记录可用再下载ZIP。可上传兼容版本的ZIP并后台完整校验；受理不等于可恢复。ZIP含数据库敏感信息，保存在可信私有位置；备份卷和原数据在同一磁盘时不能抵抗磁盘损坏，下载副本仍需独立保存。外部原件、挂载映射、环境配置/凭证、模型、镜像另行保存。

恢复此备份只生成并验证独立恢复目录。记下页面的恢复编号（32位小写十六进制ID）；服务端绝对路径仅通过管理员CLI查询，不在网页显示。下例将其再次校验并暂存到maintenance的全新恢复目录；把RECOVERY_ID替换为实际编号，不填服务器路径：

```sh
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml run --rm maintenance python -m juanzhan.backup_admin locate-recovery --id RECOVERY_ID
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml run --rm maintenance python -m juanzhan.backup_admin stage-recovery --id RECOVERY_ID --output /recovery/restored
```

/recovery/restored必须不存在；失败不得清空或覆盖已有目标。暂存完成后，沿用本手册“备份与恢复到新卷”的独立Compose项目/卷切换流程，将原项目archive_recovery卷挂为新实例archive_data、设置JUANZHAN_DATA_DIR=/data/restored，并为新实例使用独立archive_backups卷。先停旧worker/实例，再启动新实例；重新登录验证下载、正文/检索、迁移/integrity/FK及只读来源状态，确认后切换代理。验证失败停止新实例，按旧镜像/旧卷回退，不把新数据卷交给旧迁移集合镜像。CLI不会自动改Compose、代理或活实例。

恢复后的旧会话/API Token失效，管理员密码哈希保留；正常重新登录。自动备份默认关闭，确认新备份卷和保留配置后再开启。复制来的旧备份记录不意味着原ZIP也已复制到新备份卷，缺文件时会如实显示不可用。

清理：页面删除备份只删除对应ZIP并留记录，不删除活数据或已生成恢复目录。确认恢复目录不再需要且没有实例使用它后，操作员可显式清理：

```sh
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml run --rm maintenance python -m juanzhan.backup_admin remove-recovery --id RECOVERY_ID --confirm
docker compose --env-file deploy/.env -p juanzhan-prod -f deploy/compose.yaml run --rm maintenance python -m juanzhan.backup_admin cleanup-orphans
```

孤儿清理只处理严格内部ID命名、无引用、非软链产物；work在独占锁下清理，上传/最终孤儿需满一天，每次最多200项。不要泛删/backups、数据卷或共享/tmp。自动保留只影响成功自动备份，始终保留最近一次，手动/上传备份需明确删除。
