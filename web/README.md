# 生产 Web

此目录连接真实 Archive API；`docs/prototype/` 是独立视觉参考，保持不动。
React 19、Vite 6、Phosphor 图标，包版本和安装完整性由 package-lock.json 固定。

在根目录：

```sh
npm ci --prefix web --cache /workspace/.npm
npm run build --prefix web
```

然后按 [运行说明](../docs/DEVELOPMENT.md) 构建/启动 Compose。Archive 根路径承载编译产物；无默认管理员密码，保留原有初始化/HTTPS规则。
开发可在此目录执行 `npm run dev -- --port 5174 --strictPort`，Vite 仅绑定 loopback，`/api` 代理到 Archive；可用 `JUANZHAN_API_URL` 覆盖目标。

测试：先构建，再在根目录执行 `JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e --prefix web`（本机存在 Chromium 时）。
默认也支持 Playwright 安装的浏览器。测试自动启动一次性 Archive/SQLite/真实worker/随机管理员，未使用正常实例或假业务响应；截图和结果放 `/tmp`。

组件边界：App（会话）、Workspace（导航/资源）、Library（列表）、Detail（真实字段/属性/关联信息）、Uploads（顺序队列）、Operations（操作/结果/撤销）、api（CSRF/请求）、ui（通用组件）。
色彩沿用原型：主色 `#164634`、顶栏 `#fdfdfb`、侧栏 `#fbfcf9`、阅读底 `#f4f5f2`，桌面主栏 194/355/297px；窄屏改列表与详情切换。

T27 已提供整理/批量/拖放/恢复操作，当前页与全部筛选结果选择分开，最多100份且超限明确拒绝；操作固定ID/版本，结果可逐项查看与受保护撤销。结果入口仅保留当前页面生命周期，刷新恢复留T31。
OS文件拖入走上传队列，内部拖放仅作同空间逻辑整理并先确认。正文、缩略图、预览、下载或搜索仍未实现；字段/日期/文件大小全部来自实际API。
