import { useEffect, useState } from "react";
import { InfoTip, Notice } from "./ui.jsx";
import { message } from "./api.js";
const fieldLabels={topic:"主题",main_points:"主要内容",conclusions:"结论",open_questions:"待确认问题",parties:"签约方",obligations:"权利义务",payment_terms:"付款条款",term:"期限",breach:"违约条件",termination:"终止条件",issuer:"开具方",recipient:"接收方",billing_period:"账期",line_items:"明细",amount:"金额",currency:"币种",tax:"税额",payment_status:"付款状态",topics:"议题",decisions:"决议",actions:"行动事项",owners:"负责人",deadlines:"截止时间",objective:"目标",arguments:"主要观点",evidence:"论据",plan:"实施安排",limitations:"限制条件"};
const labels = { generic:"通用文档", contract:"合同", invoice:"账单／发票", meeting:"会议记录", report:"方案／报告" };
export function AgentAnalysis({ api, doc }) {
  const [page,setPage]=useState(1),[total,setTotal]=useState(0);
  useEffect(()=>setPage(1),[doc.id]);
  const [result,setResult]=useState(null),[error,setError]=useState(null);
  useEffect(()=>{
    const controller=new AbortController();setResult(null);setError(null);
    api.request(`/agent/documents/${doc.id}/analyses?space_id=${encodeURIComponent(doc.space_id)}&page=${page}`,{signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted){setResult(data.items[0]||false);setTotal(data.total);}})
      .catch(e=>{if(e.name!=="AbortError")setError(e);});
    return()=>controller.abort();
  },[api,doc.id,doc.document_version,doc.current_revision_id,page]);
  if(error)return <Notice error>{message(error)}</Notice>;
  if(!result)return null;
  const finding=(value,index)=><li key={index}><p>{value.text} {value.basis==="inference"&&<small>分析推断</small>}</p><details><summary>Agent 提取正文依据</summary>{value.sources.map((source,i)=><blockquote key={i}>{source.quote}<small> · Markdown 字符 {source.start}–{source.end}</small></blockquote>)}</details></li>;
  return <section aria-label="Agent分析" className="content-state">
    <div className="reader-section-head"><h3>Agent 概览</h3><InfoTip>外部Agent提供，平台校验版本、格式和引文与Agent提取正文的对应关系；未证明提取正文与原件完全一致，也不保证分析判断正确。原件和本地解析独立保留。</InfoTip></div>
    <small>{result.agent_name} · {labels[result.template_id]} v{result.template_version} · {new Date(result.created_at).toLocaleString("zh-CN")}</small>
    {result.stale&&<Notice>这是旧版本的分析，当前原件已更新。</Notice>}
    <ul className="summary-points">{result.analysis.summary.map(finding)}</ul>
    <details><summary>提取字段与补充要点</summary><dl>{Object.entries(result.analysis.fields).map(([key,value])=><div key={key}><dt>{fieldLabels[key]||key}</dt><dd>{value?<ul>{[value].map(finding)}</ul>:"原文未说明"}</dd></div>)}</dl><ul>{result.analysis.additional_points.map(finding)}</ul></details>
    {total>1&&<div className="summary-actions"><button disabled={page<=1} onClick={()=>setPage(value=>value-1)}>上一份分析</button><span>{page} / {total}</span><button disabled={page>=total} onClick={()=>setPage(value=>value+1)}>下一份分析</button></div>}
    <details><summary>Agent 提取原文（Markdown）</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{result.analysis.markdown}</pre></details>
  </section>;
}
