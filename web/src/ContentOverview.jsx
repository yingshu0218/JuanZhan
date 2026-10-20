import { InfoTip } from "./ui.jsx";
// An extractive view of actual blocks, with no generated claims or inferred fields.
function excerpt(block) {
  const text = block.text?.trim() || "";
  return text.length > 220 ? text.slice(0, 220) + "…" : text;
}
function Excerpt({ block }) {
  const table = block.structure?.table;
  if (block.type === "table" && table) return <div className="reader-table overview-table"><table>
    {table.headers?.length > 0 && <thead><tr>{table.headers.map((cell, index) => <th key={index}>{cell}</th>)}</tr></thead>}
    <tbody>{table.rows.slice(0, 4).map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody>
  </table>{table.rows.length > 4 && <InfoTip>表格摘录前 4 行，完整表格见正文。</InfoTip>}</div>;
  return <p>{block.type === "list_item" ? "• " : ""}{excerpt(block)}</p>;
}
export function ContentOverview({ data, onRead }) {
  const blocks = data.body;
  const sections = [];
  const lead = [];
  let section, topic;
  for (const block of blocks) {
    if (block.type === "heading") {
      const level = block.structure?.level || 1;
      if (!section || level <= section.level) {
        section = { title: block.text, level, index: block.index, blocks: [], topics: [] };
        sections.push(section); topic = null;
      } else {
        topic = { title: block.text, blocks: [] };
        section.topics.push(topic);
      }
    } else if (["paragraph", "list_item", "table"].includes(block.type)) {
      (topic ? topic.blocks : section ? section.blocks : lead).push(block);
    }
  }
  return <div className="content-overview" aria-label="内容概览">
    <InfoTip>按原文章节整理的内容摘录，可继续阅读完整正文。</InfoTip>
    {lead.length > 0 && <div className="overview-intro">{lead.slice(0, 6).map(block => <Excerpt key={block.id} block={block} />)}</div>}
    {sections.map(item => <div className="overview-section" key={item.index}>
      <h4>{item.title}</h4>
      {item.blocks.slice(0, 3).map(block => <Excerpt key={block.id} block={block} />)}
      {item.topics.length > 0 && <ul>{item.topics.map((entry, topicIndex) => <li key={topicIndex}>
        <strong>{entry.title}</strong>
        {entry.blocks.slice(0, 2).map(block => <Excerpt key={block.id} block={block} />)}
      </li>)}</ul>}
      <button className="text-action" onClick={() => onRead(item.index)}>阅读本节完整内容</button>
    </div>)}
    {!sections.length && lead.length > 6 && <InfoTip>以上为开篇摘录，更多内容请阅读完整正文。</InfoTip>}
    {data.total > blocks.length && <InfoTip>此概览覆盖前 {blocks.length} 个内容块，全文共 {data.total} 个；后续章节请在完整正文中查看。</InfoTip>}
    <button onClick={() => onRead(0)}>阅读完整正文</button>
  </div>;
}
