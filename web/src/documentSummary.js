// Bounded, source-only excerpts for every document type. No inferred business fields.
const MAX_POINTS = 8;
const shorten = (text, limit = 140) => text.length > limit ? text.slice(0, limit).trimEnd() + '…' : text;
const normalize = text => text.replace(/[ \t]+/g, ' ').trim();
const compact = blocks => ({ ...blocks[0], text: blocks.map(block => block.text).join('；'), sourceBlocks: blocks });
function textOf(block) {
  const table = block.structure?.table;
  if (block.type === 'table' && table) return table.rows.slice(0, 2).map(row => row.map((cell, index) => `${table.headers?.[index] ? table.headers[index] + '：' : ''}${cell}`).join('；')).join('。');
  return block.text || '';
}
function excerpt(text) {
  const first = text.match(/^.*?[。！？!?]/u)?.[0] || text;
  return shorten(first.trim());
}
export function summarizeDocument(data, documentTitle = '文档') {
  const input = data.body.slice(0, 100);
  const blocks = input.map(block => ({ ...block, text: normalize(textOf(block).slice(0, 4000)) })).filter(block => block.text);
  const points = [];
  const seen = new Set();
  let omitted = false;
  function add(label, candidates, anchor) {
    const unique = candidates.filter(block => block.text !== label && !seen.has(block.text));
    const selected = unique.slice(0, 2);
    if (!label && !selected.length) return;
    if (points.length >= MAX_POINTS) { omitted = true; return; }
    selected.forEach(block => seen.add(block.text));
    points.push({ label: shorten(label, 100), details: selected.map(block => excerpt(block.text)),
      index: anchor.index, sources: [anchor, ...selected.flatMap(block => block.sourceBlocks || [block])].filter((block, index, all) => all.findIndex(other => other.index === block.index) === index).map(block => ({ index: block.index, text: shorten(block.text, 400) })) });
    if (unique.length > selected.length || selected.some(block => excerpt(block.text) !== block.text)) omitted = true;
  }
  const firstHeading = blocks.findIndex(block => block.type === 'heading');
  const title = documentTitle.replace(/\.[A-Za-z0-9]{1,8}$/, '');
  const lead = blocks.slice(0, firstHeading < 0 ? blocks.length : firstHeading);
  if (firstHeading < 0) {
    for (const block of lead) {
      // Preserve paragraph/list boundaries; long plain-text blocks contribute ordered sentences.
      const sentences = block.text.split(/(?<=[。！？!?])\s*|\n+/u).filter(Boolean);
      for (const text of sentences) add('', [{ ...block, text }], block);
    }
  } else {
    if (lead.length) add('', [compact(lead.slice(0, 4))], lead[0]);
    const headings = blocks.filter(block => block.type === 'heading');
    let level = Math.min(...headings.map(block => block.structure?.level || 1));
    const roots = headings.filter(block => (block.structure?.level || 1) === level);
    // A sole enclosing title is presentation, not a separate empty summary point.
    if (roots.length === 1 && blocks[0] === roots[0] && headings.length > 1) {
      const next = headings.filter(block => block !== roots[0]);
      level = Math.min(...next.map(block => block.structure?.level || 1));
      const intro = blocks.slice(1, blocks.findIndex(block => block === next[0]));
      if (intro.length) add('', [compact(intro.slice(0, 4))], intro[0]);
    }
    const sections = blocks.map((block, index) => ({ block, index })).filter(({ block }) => block.type === 'heading' && (block.structure?.level || 1) === level);
    for (let sectionIndex = 0; sectionIndex < sections.length; sectionIndex++) {
      const { block, index } = sections[sectionIndex];
      const children = blocks.slice(index + 1, sections[sectionIndex + 1]?.index ?? blocks.length);
      const prose = children.filter(child => child.type !== 'heading');
      const topics = children.filter(child => child.type === 'heading');
      const candidates = [];
      // Show actual subtopics as one compact point detail, then a representative source sentence.
      if (topics.length) candidates.push(compact(topics.slice(0, 4)));
      if (prose.length) candidates.push(...prose);
      add(block.text, candidates, block);
    }
  }
  return { title, points, omitted, partial: data.total > input.length || input.some(block => textOf(block).length > 4000), covered: input.length, total: data.total };
}
