import { summarizeDocument } from "./documentSummary.js";

function Sources({ items, onRead }) {
  if (!items.length) return null;
  const unique = items.filter((item, index) => items.findIndex(other => other.index === item.index && other.text === item.text) === index);
  return <details className="fact-sources"><summary>原文依据（{unique.length}）</summary>{unique.map((item, index) => <blockquote key={index}>
    <p>{item.text}</p><button className="text-action" onClick={() => onRead(item.index)}>查看对应正文</button>
  </blockquote>)}</details>;
}
export function SummaryCards({ data, documentTitle, onRead, onChapters }) {
  const result = summarizeDocument(data, documentTitle);
  return <div className="summary-view" aria-label="摘要与关键信息">
    <div className="document-abstract"><span className="abstract-label">文档摘要</span><h4>{result.title}</h4>
      <p>{result.summary || "当前没有足够的明确表述可整理摘要，请阅读原文。"}</p>
      <Sources items={result.summarySources} onRead={onRead} />
    </div>
    <h4 className="facts-heading">关键信息</h4>
    <div className="fact-grid">{Object.entries(result.facts).map(([key, fact]) => <article className={"fact-card fact-" + key} key={key} aria-label={fact.label}>
      <h5>{fact.label}</h5>
      {!fact.values.length ? <p className="fact-missing">{result.missing}</p> : fact.values.length === 1 ? <p className="fact-value">{fact.values[0]}</p> : <ul>{fact.values.map(value => <li key={value}>{value}</li>)}</ul>}
      {key === "price" && fact.values.length > 1 && <p className="fact-note">文中有多个价格表述，请核对适用条件。</p>}
      {fact.truncated && <p className="fact-note">另有表述未列出，请查阅原文。</p>}
      <Sources items={fact.sources} onRead={onRead} />
    </article>)}</div>
    <p className="summary-method">依据原文明确表述整理，未说明的信息不补写；不自动填入业务字段。</p>
    {result.partial && <p className="muted">本摘要覆盖前 {result.covered} 个内容块（全文 {result.total} 个），长内容块最多读取前4000字；后续信息请查看完整正文。</p>}
    <div className="summary-actions"><button onClick={onChapters}>查看章节摘录</button><button onClick={() => onRead(0)}>阅读完整正文</button></div>
  </div>;
}
