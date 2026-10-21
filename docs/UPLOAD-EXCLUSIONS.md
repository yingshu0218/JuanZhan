# 上传辅助文件排除

2026-10-22用户要求明确排除`.DS_Store`并检查类似辅助文件。实施采用保守文件名清单，唯一规则源为[upload_exclusions.json](../services/juanzhan/upload_exclusions.json)，浏览器与Python读取同一文件，不使用用户上传内容或路径作为代码。

| 类别 | 默认排除 |
|---|---|
| 系统元数据/缓存文件 | `.DS_Store`、`.localized`、`Thumbs.db`、`ehthumbs.db`、`ehthumbs_vista.db`、`desktop.ini` |
| AppleDouble资源分叉辅助文件 | `._`开头且后面有名称的文件 |
| Office临时锁文件 | `~$`开头且扩展名属于清单中的Word/Excel/PowerPoint格式 |
| LibreOffice临时锁文件 | `.~lock.`开头并以`#`结束 |
| Vim交换文件 | 点号开头且以`.swp`或`.swo`结束 |
| 系统辅助目录及其内容 | `__MACOSX`、`.AppleDouble`、`.Spotlight-V100`、`.Trashes`、`.fseventsd`、`.TemporaryItems`、`$RECYCLE.BIN`、`System Volume Information` |

名称匹配不区分ASCII大小写。不是“一律忽略隐藏文件”：`.env`、`.gitignore`、普通隐藏文档、`.tmp`、`.bak`、`文件名~`继续保留；不按通用临时/备份扩展名推断无用内容，不默认排除代码、依赖目录、图片、零字节文件或压缩包。

选择单文件、文件夹以及混合拖入共用过滤；拖入已知系统目录时不再枚举其内容。目录选择器由浏览器枚举文件，应用只过滤用户已选文件，不读取其内容。上传队列累计显示已跳过项目数和最近20项相对名称/原因；被跳过目录按1项计，其内部文件数量未知。不为排除目录创建逻辑目录；未排除的原生空目录拖入规则保持不变。扫描最多10000个项目，实际入队仍最多1000项，任何扫描/读取超限不部分入队。

服务端`POST /documents/upload`在元数据校验后、内容嗅探与托管保存前执行文件名过滤，返回`422 UPLOAD_EXCLUDED`，Cookie和Bearer一致；multipart接收依旧受既有大小/超时限制，临时接收文件由既有生命周期关闭。HTTP不接收用户本地目录路径，因此辅助目录过滤位于浏览器；API直接指定既有逻辑folder_id仍按原目录权限规则处理。

既有档案/外部来源库存不追溯删除。外部只读来源扫描排除机制保持原状，本批不改变扫描语义。规则变更需同步测试与说明，实际部署/验收见STATUS、TESTING和DEVTEST。
