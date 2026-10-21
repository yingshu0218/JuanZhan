# devtest IP HTTPS测试入口（T42 已验收）

用户决定暂用IP＋端口，不进行正式域名上线。现有127.0.0.1:18080保留；当前公网入口为 `https://8.153.19.221:443/`，发行者为 `https://8.153.19.221`。18443监听正常但外部连接超时，改用空闲443后Mac外部TLS验证和HTTP200成功；未修改云安全组或其他Nginx/终端服务。配置为 `deploy/ip-test.yaml` 与 `ip-test-nginx.conf`，私有.env设置JUANZHAN_TLS_PORT=443，gateway使用不可变digest。

已实际完成80端口外部可达校验、Certbot staging及可信IP证书签发。证书SAN为8.153.19.221，签发者YE1，notAfter为2026-10-27T21:49:29Z，私钥仅保存在服务器私有目录。已部署TLS入口，未使用忽略证书验证；公网未授权Agent接口返回401及resource_metadata挑战，真实登录/阅读/REST/MCP均通过。

独立工具Certbot5.4.0及依赖共18包，哈希锁在deploy/certbot.lock；约23MiB，仅服务器私有venv。gateway为官方nginx1.30.6，digest `sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5`，镜像28545847字节，运行内存观察约2.2MiB，限额64MiB/0.5CPU；这不是压力峰值。Archive/Converter/worker同次观察约42/41/30MiB，业务镜像rc.14为102527348字节（rc.13为102519467字节）。

发布Compose追加 `-f deploy/ip-test.yaml`，配置JUANZHAN_PUBLIC_URL、JUANZHAN_PROXY_CIDR（实际隔离网络目前172.22.0.0/16）、JUANZHAN_GATEWAY_IMAGE、JUANZHAN_TLS_DIRECTORY和JUANZHAN_TLS_PORT。仅信任该Compose子网的转发头；公网代理覆盖X-Forwarded-Proto与客户端IP，保留Host/Origin，HTTPS Cookie增加Secure。普通HTTP只在loopback开放。

证书serving目录只复制fullchain与server key，不挂载ACME账户。root执行deploy/renew-ip-tls.sh准备权限及原子替换，Nginx运行uid101。juanzhan-ip-tls.timer已实际安装并active，每12小时检查续期；service首次检查Result=success、ExecMainStatus=0。Certbot standalone临时使用80端口，deploy hook检验并重载专用gateway。`renew --dry-run --run-deploy-hooks`实际成功，含nginx -t与reload；日志`.local/certbot-renew-dry-run.log`。请保留80校验端口可达，服务失败或证书过期时检查专用unit日志。

停用时先停止/禁用专用timer，再移除gateway override并重建本项目；确认无服务引用后清理serving证书和Certbot私有目录/venv/项目日志。不要删除业务卷、原件、备份或其他服务/全局Docker资源。

官方依据：[Certbot IP与短期证书](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)。证书仅约6天，需要持续续期；所有厂商客户端账户兼容性不在已验收范围内。
