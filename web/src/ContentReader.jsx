import { InfoTip } from "./ui.jsx";
import { useEffect, useState } from "react";
import { message } from "./api.js";
import { ContentOverview } from "./ContentOverview.jsx";
import { DocumentSummary } from "./DocumentSummary.jsx";
import { Dialog, Notice, processing, availability, formatDate } from "./ui.jsx";

function usePage(api, path) {
  const [result, setResult] = useState({ loading: true });
  useEffect(() => {
    const abort = new AbortController();
    if (!path) return () => abort.abort();
    setResult({ path, loading: true });
    api.request(path, { signal: abort.signal }).then(
      (data) => { if (!abort.signal.aborted) setResult({ path, data }); },
      (error) => { if (!abort.signal.aborted) setResult({ path, error }); },
    );
    return () => abort.abort();
  }, [api, path]);
  if (!path) return { empty: true };
  return result.path === path ? result : { loading: true };
}
function Pager({ page, data, onChange, label }) {
  if (!data || data.total <= data.page_size) return null;
  return <nav className="reader-pager" aria-label={label}>
    <button disabled={page === 1} onClick={() => onChange(page - 1)}>上一页</button>
    <span>第 {page} / {Math.ceil(data.total / data.page_size)} 页 · 共 {data.total} 项</span>
    <button disabled={page * data.page_size >= data.total} onClick={() => onChange(page + 1)}>下一页</button>
  </nav>;
}
function position(locator) {
  if (!locator || locator.kind === "unknown") return "定位未知";
  if (locator.kind === "page") return `原件第 ${locator.page} 页`;
  if (locator.kind === "character") return `字符 ${locator.start}–${locator.end}`;
  if (locator.kind === "epub") return `EPUB 章节 ${locator.spine_index + 1} · ${locator.href}（非物理页码）`;
  return locator.heading_path?.join(" / ") || "章节定位";
}
function Block({ block, annotations = false }) {
  const table = block.structure?.table;
  const Heading = `h${Math.min(6, Math.max(3, (block.structure?.level || 1) + 2))}`;
  return <div className={"content-block block-" + block.type}>
    {annotations && <small className="block-annotation">{position(block.locator)}{block.confidence != null ? ` · 置信度 ${Math.round(block.confidence * 100)}%（需复核）` : ""}</small>}
    {block.type === "table" && table ? <div className="reader-table"><table>
      {table.headers?.length ? <thead><tr>{table.headers.map((cell, i) => <th key={i}>{cell}</th>)}</tr></thead> : null}
      <tbody>{table.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody>
    </table></div> : block.type === "heading" ? <Heading>{block.text}</Heading> : block.type === "page_break" ? <hr /> : <p>{block.text || (block.type === "image" ? "图像尚无可读文本" : "空文本块")}</p>}
  </div>;
}
function Blocks({ blocks, annotations }) {
  const groups = [];
  for (const block of blocks) {
    if (block.type === "list_item") {
      if (groups.at(-1)?.list) groups.at(-1).list.push(block);
      else groups.push({ list: [block], id: block.id });
    } else groups.push({ block, id: block.id });
  }
  return <div className="content-blocks">{groups.map(group => group.list
    ? <ul className="content-list" key={group.id}>{group.list.map(block => <li key={block.id}>{annotations && <small className="block-annotation">{position(block.locator)}</small>}{block.text}</li>)}</ul>
    : <Block key={group.id} block={group.block} annotations={annotations} />)}</div>;
}
function Candidate({ candidate, api, doc, definitions, onChanged }) {
  const [open, setOpen] = useState(false);
  const [field, setField] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = definitions.filter((item) => item.is_active);
  async function adopt(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api.request(`/documents/${doc.id}/metadata/adopt-candidate`, { method: "POST", body: {
        expected_document_version: doc.document_version,
        extracted_metadata_id: candidate.id, field_definition_id: field,
      } });
      setOpen(false); onChanged();
    } catch (e) { setError(e.status === 422 ? "候选值不符合所选字段的类型或规则，请核对字段。" : message(e)); }
    finally { setBusy(false); }
  }
  return <li className="candidate-card">
    <strong>{candidate.key}</strong><pre>{JSON.stringify(candidate.value, null, 2)}</pre>
    <p className="muted">来源：{candidate.provenance?.source || "未提供"} · {position(candidate.provenance?.locator)} · {candidate.confidence == null ? "置信度未提供" : `置信度 ${Math.round(candidate.confidence * 100)}%（需复核）`}</p>
    <details><summary>版本来源</summary><small className="run-reference">解析 {candidate.parse_run_id} · 原件 {candidate.revision_id}</small></details>
    {candidate.adoptable && candidate.value != null && !doc.deleted_at ? <button disabled={!active.length} onClick={() => { setOpen(true); setError(""); setField(""); }}>采纳此候选</button> : <InfoTip>仅供参考，当前不可采纳。</InfoTip>}
    {open ? <Dialog title="确认采纳候选" onClose={() => { if (!busy) setOpen(false); }}>
      <form onSubmit={adopt}>
        <p>采纳后会覆盖所选业务字段的当前值，并标记为已确认。正文与其他字段不变。</p>
        <label>目标业务字段<select required value={field} onChange={(e) => setField(e.target.value)}><option value="">请选择字段</option>{active.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.type}</option>)}</select></label>
        {error ? <Notice error>{error}</Notice> : null}
        <button type="submit" disabled={busy || !field}>{busy ? "正在采纳…" : "确认覆盖并采纳"}</button>
      </form>
    </Dialog> : null}
  </li>;
}
export function ContentReader({ api, doc, definitions, onChanged }) {
  const [run, setRun] = useState(null);
  const [annotations, setAnnotations] = useState(false);
  const [overviewSize, setOverviewSize] = useState(100);
  const [format, setFormat] = useState("summary");
  const [page, setPage] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);
  const [candidatePage, setCandidatePage] = useState(1);
  const root = `/documents/${doc.id}`;
  const selected = run ? `&parse_run_id=${encodeURIComponent(run)}` : "";
  const condensed = format === "summary" || format === "overview";
  const content = usePage(api, doc.current_parse_run_id || run ? format === "summary" ? `${root}/overview?${run ? `parse_run_id=${encodeURIComponent(run)}` : ""}` : `${root}/content?format=${condensed ? "blocks" : format}&page=${format === "blocks" ? page : 1}&page_size=${condensed ? overviewSize : 20}${selected}` : null);
  useEffect(() => {
    if (condensed && overviewSize === 100 && content.error?.code === "CONTENT_RESPONSE_LIMIT") setOverviewSize(20);
  }, [condensed, overviewSize, content.error]);
  const history = usePage(api, `${root}/parse-runs?page=${historyPage}&page_size=10`);
  const candidates = usePage(api, `${root}/candidates?page=${candidatePage}&page_size=10${selected}`);
  function selectRun(value) { setRun(value); setPage(1); setCandidatePage(1); }
  return <>
    <section className="content-state" aria-label="正文阅读">
      <div className="reader-section-head"><h3>{format === "summary" ? "内容概览" : format === "overview" ? "章节摘录" : "正文内容"}</h3><button onClick={onChanged}>刷新内容</button><label>阅读格式<select value={format} onChange={(e) => { setFormat(e.target.value); setPage(1); }}><option value="summary">内容概览</option><option value="overview">章节摘录</option><option value="blocks">完整结构化正文</option><option value="text">纯文本</option><option value="markdown">Markdown 源文本</option></select></label></div>
      {run ? <Notice>正在查看指定历史结果。<button onClick={() => selectRun(null)}>返回当前成功正文</button></Notice> : null}
      {content.empty ? <p>尚无成功解析的正文。{processing[doc.processing_status] || "请刷新处理状态"}；原件和业务字段仍保留。</p> : content.loading ? <p role="status">正在读取正文…</p> : content.error ? content.error.code === "CONTENT_NOT_AVAILABLE" ? <p>尚无成功解析的正文。{processing[doc.processing_status] || "请刷新处理状态"}；原件和业务字段仍保留。</p> : <Notice error>{message(content.error)} 可使用顶部刷新重新读取。</Notice> : <>
        {content.data.stale_for_current_revision ? <Notice>这是已保存的缓存正文，可能来自旧版本或原件当前不可用；不代表当前原件已验证。</Notice> : null}
        {content.data.ocr_used && <Notice>正文含 OCR 识别内容，请复核。</Notice>}
        {!content.data.text_available ? <Notice>此次结果没有可读文本；扫描文件可能需要显式启用 OCR。</Notice> : null}
        {format === "summary" ? <DocumentSummary data={content.data} documentTitle={doc.title} onRead={index => { setPage(Math.floor(index / 20) + 1); setFormat("blocks"); }} onChapters={() => setFormat("overview")} /> : format === "overview" ? <ContentOverview data={content.data} onRead={index => { setPage(Math.floor(index / 20) + 1); setFormat("blocks"); }} /> : format === "blocks" ? <><Blocks blocks={content.data.body} annotations={annotations} />{!content.data.body.length ? <p>此次解析没有正文块。</p> : null}</> : <pre className="plain-content">{content.data.body || "此次解析没有文本。"}</pre>}
        {format === "blocks" ? <Pager page={page} data={content.data} onChange={setPage} label="正文分页" /> : !condensed ? <InfoTip>以安全源文本显示，不执行 HTML 或外部资源。</InfoTip> : null}
        <details className="reader-diagnostics"><summary>正文来源与解析说明{content.data.warnings.length ? `（${content.data.warnings.length} 条提示）` : ""}</summary>
          <p>{availability[content.data.availability_status] || "原件待核验"} · {content.data.ocr_used ? "含 OCR 识别，请复核" : "未使用 OCR"}</p>
          <small className="run-reference">解析 {content.data.parse_run_id} · 原件 {content.data.content_revision_id}</small>
          {content.data.warnings.length ? <ul>{content.data.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul> : null}
          {format === "blocks" && <label className="annotation-toggle"><input type="checkbox" checked={annotations} onChange={e => setAnnotations(e.target.checked)} />显示每段来源定位与置信度</label>}
        </details>
      </>}
    </section>
    <section aria-label="提取候选">
      <h3>提取候选</h3><InfoTip>候选不会自动写入业务字段；请核对来源后再采纳。</InfoTip>
      {candidates.loading ? <p role="status">正在读取候选…</p> : candidates.error ? <Notice error>{message(candidates.error)}</Notice> : <>
        <ul className="candidate-list">{candidates.data.items.map((candidate) => <Candidate key={candidate.id} candidate={candidate} api={api} doc={doc} definitions={definitions} onChanged={onChanged} />)}</ul>
        {!candidates.data.total ? <p className="muted">此次结果没有提取候选。</p> : null}
        <Pager page={candidatePage} data={candidates.data} onChange={setCandidatePage} label="候选分页" />
      </>}
    </section>
    <section aria-label="解析历史">
      <h3>解析历史</h3>
      {history.loading ? <p role="status">正在读取历史…</p> : history.error ? <Notice error>{message(history.error)}</Notice> : <>
        <ol className="parse-history">{history.data.items.map((item) => <li key={item.id}>
          <strong>{processing[item.status] || item.status}{item.is_current ? " · 当前成功正文" : ""}</strong>
          <p>{formatDate(item.created_at)} · {item.parser_name} · {item.ocr_used ? "OCR" : "非 OCR"}</p>
          <small className="run-reference">解析 {item.id} · 原件 {item.revision_id}</small>
          {item.error ? <p role="status">失败代码：{item.error.code || "未知"}</p> : null}
          {item.warnings.length ? <details><summary>处理提示</summary><ul>{item.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details> : null}
          {item.status === "completed" ? <button disabled={run === item.id} onClick={() => selectRun(item.id)}>查看此次结果</button> : <span className="muted">此尝试没有成功正文</span>}
        </li>)}</ol>
        {!history.data.total ? <p className="muted">暂无解析尝试。</p> : null}
        <Pager page={historyPage} data={history.data} onChange={setHistoryPage} label="解析历史分页" />
      </>}
    </section>
  </>;
}
