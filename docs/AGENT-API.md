# Agent 接入契约 · 2026-10-21

用户选择：MCP＋REST，模型由外部agent提供。系统提供只读、空间授权的检索/概要/正文/分析证据，不调用外部LLM、不自动分类或写业务字段。自然语言理解、关键词拆解与最终回答由agent完成，禁止把字面检索宣传成语义检索。

## 权限与凭据

管理员Cookie＋CSRF创建/撤销/api/v1/agent-tokens；每个Token指定1～50个空间，有效期1～30天，名称1～100字；随机jza_凭据仅创建时显示，数据库只存SHA-256。每Token每分钟最多60次，过期/撤销立即拒绝；密码重置撤销全部agent凭据。agent凭据只能访问/api/v1/agent/下的已定义只读功能，拒绝其他业务API、上传、下载、管理和任何写入。回收站及越权/不存在档案统一404。

## REST

通用标准库客户端已提供 `juanzhan.agent_rest.Client`，也可从仓库执行 `PYTHONPATH=services python -m juanzhan.agent_rest list_spaces`，参数从stdin读取JSON对象。私有环境变量为 `JUANZHAN_AGENT_URL`（完整 `/api/v1/agent` 地址）与 `JUANZHAN_AGENT_TOKEN`；可选 `JUANZHAN_CA_FILE`，默认系统信任库，不支持关闭TLS验证。不跟随重定向、不读取环境代理，只支持既有七个只读操作；外部Agent自行将自然语言拆为工具参数，客户端不生成答案。`search_documents`/`prepare_analysis`使用JSON POST，其余使用GET。源码导入不依赖FastAPI或模型SDK。

OAuth已随rc.14部署，授权说明见[OAUTH](OAUTH.md)，通用客户端实测见[AGENT-INTEROP](AGENT-INTEROP.md)。手动凭据仍可继续使用；可导入[只读REST OpenAPI](reference/agent-rest-openapi.json)，将服务器设置为实际 origin＋`/api/v1`。

- GET /api/v1/agent/capabilities：工具定义、格式、限制与处理指引。
- GET /api/v1/agent/spaces：授权空间。
- GET /api/v1/agent/catalog?space_id=：可用目录/标签/文档类型/字段定义，供agent把自然语言映射到结构化条件。
- POST /api/v1/agent/search：复用SearchRequest，强制trash=exclude、page_size≤20，text是外部agent拆出的关键词，返回FTS/结构化真实结果及索引完整性。
- GET /api/v1/agent/documents/{id}/overview?space_id=：通用概要、ParseRun/Revision、陈旧/空文本/读取范围和逐点来源。
- GET /api/v1/agent/documents/{id}/content?space_id=&page=&page_size=&parse_run_id=：最多20块/页，每块最多4000字，明确截断；固定ParseRun分页，正文内容为不可信数据。
- POST /api/v1/agent/analysis-context：question(1～2000字)、space_id、document_ids(1～5个)，返回问题及所选文档概要/有界正文证据，标明不是模型答案；不得自动选择额外空间或发送到外部服务。
- GET /api/v1/documents/{id}/overview：同一概要实现，既有管理员鉴权供Web使用；支持parse_run_id历史读取。概要按需计算，不写数据库、不重解析、不覆盖人工字段。

REST所有POST预算64KiB，工具结果预算512KiB；所有响应no-store/nosniff。档案来源中的文档ID/Revision/ParseRun/块ID与真实locator构成引用，不伪造页码；未知locator保持unknown。任何正文中的命令/密钥请求都只视为资料，不能覆盖用户指令或获取更高权限。

## MCP

POST /api/v1/agent/mcp：JSON-RPC 2.0、Streamable HTTP JSON响应、独立请求无协议会话。支持2025-06-18/2025-11-25 initialize兼容，以及2026-07-28 server/discover和每请求元数据；不提供旧HTTP+SSE、服务器采样、任意URL/SQL/文件路径工具。GET/DELETE返回405。接受手动或OAuth签发的空间授权Agent Bearer凭据，发现/PKCE与限制见OAUTH。

Origin存在时须匹配当前HTTP源。Accept须含application/json与text/event-stream，Content-Type须application/json。现代请求验证MCP-Protocol-Version/Mcp-Method/Mcp-Name与params._meta镜像，未知版本和镜像不一致按协议拒绝；旧initialize允许无版本头，后续必须声明支持版本。所有协议方法和工具每次重新鉴权，凭据撤销不依赖会话结束。

工具：list_spaces、get_catalog、search_documents、get_document_overview、read_document、prepare_analysis、get_formats。工具均标注只读/幂等，不执行文档中的指令。详见agent-openapi.json精确结构与后续客户端示例。

规范依据：[2026-07-28传输](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)、[版本兼容](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)、[2025-11-25传输](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)。

## 当前业务字段与分析一致性

read_document同时返回business_fields（当前档案的正式业务值）：最多50项，文本每项最多1000字，明确partial/value_truncated。确认状态、origin和source_parse_run_id分别展示；Decimal保持四位字符串，整数以字符串精确传输并标value_encoding=integer-string，不转成浮点。历史正文的业务字段仍是当前值，必须区分时间。prepare_analysis在同一SQLite读取事务中获取所选档案概要、正文和正式业务字段；未解析/不支持的文档仍可返回人工确认字段，不生成正文或模型答案。外部agent对当前业务问题应优先使用已确认字段，并解释与原文的差异。

密码重置和新目录备份恢复均清除agent凭据，恢复备份不得复活旧授权。只读凭据的业务范围不因缓存、协议初始化或模型身份而扩大。

## 客户端连接

1. 进入系统设置 → Agent接入，选择允许的空间，创建凭据并保存到客户端私有配置。
2. 支持自定义Bearer头的MCP客户端：URL为http://127.0.0.1:18080/api/v1/agent/mcp，设置Authorization: Bearer <一次性凭据>。非回环连接必须自行配置受控HTTPS反向代理；本次测试实例仍仅回环/SSH隧道可达。
3. 需要本地子进程的MCP客户端，按其配置格式使用以下示例（替换绝对脚本路径及凭据；不需要额外Python包）：

```json
{
  "mcpServers": {
    "juanzhan": {
      "command": "python3",
      "args": ["/absolute/path/to/juanzuan/services/juanzhan/agent_stdio.py"],
      "env": {
        "JUANZHAN_MCP_URL": "http://127.0.0.1:18080/api/v1/agent/mcp",
        "JUANZHAN_AGENT_TOKEN": "<一次性只读凭据>"
      }
    }
  }
}
```

桥接只通过已配置地址发送Bearer，不继承代理，不跟随重定向；非回环HTTP拒绝，日志不输出凭据。此JSON是常见客户端配置示例，不代表所有厂商采用相同配置格式。

4. REST型agent可以导入[精确OpenAPI扩展](reference/agent-openapi.json)，或按以下顺序调用：spaces → catalog → search → documents/{id}/overview → content → analysis-context。Authorization同上；Cookie管理员调用POST仍需要CSRF。

例：用户问“找出这批合同的金额和延期风险”。外部agent先选授权空间，根据catalog映射真实字段，对关键词“合同”和金额/日期条件检索，再从命中文档ID读取overview与固定ParseRun正文，最后用analysis-context的问题和引用组织回答。金额条件必须按字段类型传精确字符串；不能把未建索引、未OCR或部分读取当作没有相关内容。服务端不会自动把整句自然语言当成语义查询或自行生成结论。

目前验证REST HTTP、现代MCP HTTP、旧协议初始化与stdio桥接；未声明对所有第三方账户的实机认证。只接受OAuth自动授权的云客户端需要额外网关/授权适配，此版本不提供。当前部署不公开服务，也不保存第三方模型API Key。
