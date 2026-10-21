# devtest IP HTTPS测试入口（T42配置中）

用户决定暂用IP＋端口，不进行正式域名上线。现有127.0.0.1:18080保留；计划增加HTTPS 18443，发行者为 `https://8.153.19.221:18443`。配置为 `deploy/ip-test.yaml` 与 `ip-test-nginx.conf`，gateway镜像必须使用不可变digest。不修改服务器其他Nginx/终端服务。

已实际完成80端口外部可达校验、Certbot staging签发及Let's Encrypt可信IP证书签发。证书SAN为8.153.19.221，签发者YE1，notAfter为2026-10-27T21:49:29Z，私钥仅保存在服务器私有目录；入口尚未部署，不能宣称18443已可用。

独立工具Certbot5.4.0和依赖哈希锁在deploy/certbot.lock；约23MiB，仅服务器私有venv。gateway已拉取官方nginx:stable-alpine，digest `sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5`，实际版本/体积及资源占用待入口验收记录。

发布Compose追加 `-f deploy/ip-test.yaml`，配置JUANZHAN_PUBLIC_URL、JUANZHAN_PROXY_CIDR（实际隔离网络目前172.22.0.0/16）、JUANZHAN_GATEWAY_IMAGE、JUANZHAN_TLS_DIRECTORY和JUANZHAN_TLS_PORT。仅信任该Compose子网的转发头；公网代理覆盖X-Forwarded-Proto与客户端IP，保留Host/Origin，HTTPS Cookie增加Secure。普通HTTP只在loopback开放。

证书serving目录只复制fullchain与server key，不挂载ACME账户。root执行deploy/renew-ip-tls.sh准备权限及原子替换，Nginx运行uid101。待安装的juanzhan-ip-tls.timer每12小时检查续期，service调用Certbot standalone临时使用80端口，deploy hook检验并重载专用gateway。请保留80校验端口可达；服务启动失败或证书过期应检查专用unit日志。配置文件存在不代表timer已经安装/运行。

停用时先停止/禁用专用timer，再移除gateway override并重建本项目；确认无服务引用后清理serving证书和Certbot私有目录/venv/项目日志。不要删除业务卷、原件、备份或其他服务/全局Docker资源。

官方依据：[Certbot IP与短期证书](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)。证书仅约6天，需要持续续期；所有厂商客户端账户兼容性不在已验收范围内。
