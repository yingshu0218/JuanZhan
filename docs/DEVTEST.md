# devtest 测试实例

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
