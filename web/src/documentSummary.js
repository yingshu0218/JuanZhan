// Source-bound extraction. Never writes business fields or invents audience/claims.
const courseSignal = /课程|实战营|训练营|培训班|工作坊|教学大纲/;
const summaryHeading = /总结|小结|结语|一句话/;
const cleanHeading = text => text.replace(/^\s*(?:第?[一二三四五六七八九十百\d]+[、.．）)]|[（(][一二三四五六七八九十\d]+[）)])\s*/u, "").trim();
const money = /[¥￥]\s*\d[\d,]*(?:\.\d{1,4})?(?:\s*[-–—~～至]\s*[¥￥]?\s*\d[\d,]*(?:\.\d{1,4})?)?|\d[\d,]*(?:\.\d{1,4})?(?:\s*[-–—~～至]\s*\d[\d,]*(?:\.\d{1,4})?)?\s*(?:人民币|美元|港元|欧元|元)(?:\s*[\/／]\s*(?:人|位|期|年|月|次|节|课))?/g;
const duration = /(?:\d+(?:\.\d+)?|[一二三四五六七八九十百两]+)\s*(?:小时|分钟|个月|天|周|月)/g;
const sessions = /(?<![第\d一二三四五六七八九十百两])(?:\d+|[一二三四五六七八九十百两]+)\s*(?:节|次|场)\s*(?:直播课|课程|课|直播)/g;
const audienceLabel = /^(?:适合人群|适合对象|适合谁|适用人群|适用对象|目标学员|目标人群|招生对象|面向人群|面向对象)\s*[:：]?\s*/;
const contentLabel = /课程内容|课程大纲|学习内容|教学内容|课程安排|教学安排|核心模块|掌握的.*技能|学到什么|学习目标/;

function evidence(block, quote = block.text) {
  return { index: block.index, text: quote.trim().slice(0, 400), block_id: block.id };
}
function add(fact, value, block, quote) {
  value = value.trim();
  if (!value || value.length > 240) return;
  if (!fact.values.includes(value)) {
    if (fact.values.length >= 8) { fact.truncated = true; return; }
    fact.values.push(value);
  }
  const source = evidence(block, quote);
  if (fact.sources.length < 8 && !fact.sources.some(item => item.index === source.index && item.text === source.text)) fact.sources.push(source);
}
function sectionEnd(blocks, index) {
  const level = blocks[index].structure?.level || 1;
  let end = index + 1;
  while (end < blocks.length && !(blocks[end].type === "heading" && (blocks[end].structure?.level || 1) <= level)) end++;
  return end;
}
export function summarizeDocument(data, documentTitle = "文档") {
  const input = data.body.slice(0, 100);
  const blocks = input.map(block => ({ ...block, text: (block.text || "").slice(0, 4000) }));
  const partial = data.total > input.length || input.some(block => (block.text || "").length > 4000);
  const firstHeading = blocks.findIndex(block => block.type === "heading");
  let lead = blocks.slice(0, firstHeading < 0 ? Math.min(6, blocks.length) : Math.min(firstHeading, 6));
  if (firstHeading === 0 && courseSignal.test(blocks[0].text)) {
    const nextHeading = blocks.findIndex((block, index) => index > 0 && block.type === "heading");
    lead = blocks.slice(0, Math.min(nextHeading < 0 ? 6 : nextHeading, 6));
  }
  const headings = blocks.filter(block => block.type === "heading");
  const course = courseSignal.test([...lead, ...headings.slice(0, 6)].map(block => block.text).join("\n"));
  const titleBlock = lead.find(block => block.text.length <= 100 && courseSignal.test(block.text) && !/价格|学费|报名费|时长|课次|[:：]/.test(block.text)) || (!course ? headings[0] : null);
  const title = titleBlock?.text || documentTitle.replace(/\.[A-Za-z0-9]{1,8}$/, "");
  const facts = {
    price: { label: course ? "课程价格" : "明确标价", values: [], sources: [] },
    duration: { label: course ? "课程时长" : "明确时长", values: [], sources: [] },
    sessions: { label: course ? "课次与形式" : "安排", values: [], sources: [] },
    audience: { label: "适合人群", values: [], sources: [] },
    content: { label: course ? "课程内容" : "内容要点", values: [], sources: [] },
  };
  for (const block of blocks) {
    for (const line of block.text.split(/\r?\n/).slice(0, 60)) {
      const inLead = course && lead.some(item => item.id === block.id);
      const priceLabel = /(?:课程价格|课程费用|报名费|学费|售价|价格|报名价格|费用)\s*[:：\t|｜]\s*(.+)/.exec(line);
      const quotedRate = /报价参考|服务报价|收益|营收|收入|预算|成本|[\/／]集|每集/.test(line);
      if (!quotedRate && (inLead || priceLabel)) {
        const context = priceLabel ? priceLabel[1] : line;
        const prices = context.match(money) || [];
        if (priceLabel && prices.length) add(facts.price, context, block, line);
        else for (const value of prices) add(facts.price, value, block, line);
        if (priceLabel && /^免费\s*$/.test(context.trim())) add(facts.price, "免费", block, line);
      }
      const timeLabel = /(?:课程时长|总时长|总课时|学习时长|培训时长|活动时长|时长)\s*[:：\t|｜]\s*(.+)/.exec(line);
      const openingDuration = inLead && ((line.match(sessions) || []).length > 0 || new RegExp(`^\\s*(?:${duration.source})\\s*$`).test(line) || /总计|课时|时长/.test(line));
      if ((openingDuration || timeLabel) && !/(?:视频|镜头|短片|成片)时长/.test(line)) {
        for (const value of (timeLabel ? timeLabel[1] : line).match(duration) || []) add(facts.duration, value, block, line);
      }
      if (inLead || /(?:课次|课程安排|上课安排|课时安排)\s*[:：\t|｜]/.test(line)) {
        for (const value of line.match(sessions) || []) add(facts.sessions, value, block, line);
      }
      if (block.type !== "heading" && audienceLabel.test(line.trim())) {
        add(facts.audience, line.trim().replace(audienceLabel, ""), block, line);
      }
    }
  }
  for (let index = 0; index < blocks.length; index++) {
    const block = blocks[index];
    if (block.type !== "heading") continue;
    const label = cleanHeading(block.text);
    const children = blocks.slice(index + 1, sectionEnd(blocks, index));
    if (audienceLabel.test(label)) {
      const inline = label.replace(audienceLabel, "");
      if (inline) add(facts.audience, inline, block);
      else for (const child of children.filter(item => item.type === "paragraph" || item.type === "list_item").slice(0, 4)) add(facts.audience, child.text, child);
    }
    if (!facts.content.values.length && contentLabel.test(label)) {
      const subheads = children.filter(item => item.type === "heading");
      const childLevel = Math.min(...subheads.map(item => item.structure?.level || 1));
      const topics = subheads.length ? subheads.filter(item => (item.structure?.level || 1) === childLevel) : children.filter(item => ["paragraph", "list_item"].includes(item.type));
      for (const child of topics.slice(0, 6)) add(facts.content, child.type === "heading" ? cleanHeading(child.text) : child.text, child);

    }
  }
  const minLevel = Math.min(...headings.map(block => block.structure?.level || 1));
  const main = headings.filter(block => (block.structure?.level || 1) === minLevel && !summaryHeading.test(block.text));
  if (!facts.content.values.length) for (const block of main.slice(0, 6)) add(facts.content, cleanHeading(block.text), block);
  else if (course) for (const block of main) {
    if (block !== titleBlock && !contentLabel.test(block.text) && /技能|能力|实践|实操|社群|支持|答疑|交付|训练|练习/.test(block.text)) add(facts.content, cleanHeading(block.text), block);
  }
  const summarySources = titleBlock ? [evidence(titleBlock)] : [];
  const phrases = [];
  if (facts.content.values.length) {
    phrases.push(`文中介绍的${course ? "课程内容" : "内容要点"}包括${facts.content.values.slice(0, 4).join("、")}。`);
    summarySources.push(...facts.content.sources);
  } else {
    const text = lead.find(block => block !== titleBlock && block.text.trim());
    if (text) { phrases.push(text.text.slice(0, 220) + (text.text.length > 220 ? "…" : "")); summarySources.push(evidence(text)); }
  }
  const logistics = [facts.sessions, facts.duration, facts.price].filter(fact => fact.values.length);
  if (logistics.length) {
    phrases.push(`文中列明：${logistics.map(fact => `${fact.label}${fact.values.join(" / ")}`).join("，")}。`);
    summarySources.push(...logistics.flatMap(fact => fact.sources));
  }
  return { title, course, partial, facts, summary: phrases.join(""), summarySources,
    missing: partial ? "当前读取范围未说明" : "未说明", covered: input.length, total: data.total };
}
