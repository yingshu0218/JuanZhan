import { InfoTip } from "./ui.jsx";

function Emphasis({ text }) {
  // Only explicit source markup / short colon labels are emphasized. Numbers have no special treatment.
  const label = /^([^：:]{1,24}[：:])(.+)$/u.exec(text);
  const parts = value => value.split(/(\*\*[^*]+\*\*)/g).map((part, index) => part.startsWith('**') && part.endsWith('**') ? <strong key={index}>{part.slice(2, -2)}</strong> : part);
  return label ? <><strong className="summary-label">{parts(label[1])}</strong>{parts(label[2])}</> : parts(text);
}
export function DocumentSummary({ data, documentTitle, onRead, onChapters }) {
  const result = data;
  return <div className="summary-view" aria-label="内容概览">
    <ul className="summary-points">{result.points.map((point, index) => <li key={index} className={/^(注意|风险|警告|禁止|重要)(?:[：:\s]|$)/u.test(point.label || point.details[0] || '') ? 'summary-caution' : ''}>
      {point.label && <strong className="summary-topic"><Emphasis text={point.label} /></strong>}
      {point.details.map((text, detailIndex) => <p key={detailIndex}><Emphasis text={text} /></p>)}
      <details className="summary-sources"><summary>原文依据</summary>{point.sources.map((source, sourceIndex) => <blockquote key={sourceIndex}><p>{source.text}</p><button className="text-action" onClick={() => onRead(source.index)}>查看对应正文</button></blockquote>)}</details>
    </li>)}</ul>
    {!result.points.length && <p>暂无可提炼的文本内容。</p>}
    <InfoTip>按原文标题、段落和列表提炼分点摘录，不补写未说明的信息，不自动填入业务字段。</InfoTip>
    {(result.partial || result.omitted) && <InfoTip>概览为选取的内容要点，并非全文。当前读取 {result.covered} / {result.total} 个内容块；最多展示8点，每点保留简短摘录，完整信息请阅读正文。</InfoTip>}
    <div className="summary-actions"><button onClick={onChapters}>查看章节摘录</button><button onClick={() => onRead(0)}>阅读完整正文</button></div>
  </div>;
}
