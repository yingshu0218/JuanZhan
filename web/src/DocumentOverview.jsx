import { AgentAnalysis } from "./AgentAnalysis.jsx";
import { useEffect, useState } from "react";
import { DocumentSummary } from "./DocumentSummary.jsx";
import { Notice, processing, InfoTip } from "./ui.jsx";
import { message } from "./api.js";

export function DocumentOverview({ api, doc }) {
  return <Overview key={`${doc.id}:${doc.current_revision_id}:${doc.document_version}`} api={api} doc={doc} />;
}

function Overview({ api, doc }) {
  const [agent, setAgent] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    setResult(null); setError(null); setAgent(null);
    async function load() {
      try {
        const data = await api.request(`/agent/documents/${doc.id}/analyses?space_id=${encodeURIComponent(doc.space_id)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setAgent(data);
        if (!data.items[0] || data.items[0].stale) {
          if (doc.current_parse_run_id) {
            const overview = await api.request(`/documents/${doc.id}/overview`, { signal: controller.signal });
            if (!controller.signal.aborted) setResult(overview);
          }
        }
      } catch (e) { if (!controller.signal.aborted) setError(e); }
    }
    load();
    return () => controller.abort();
  }, [api, doc.id, doc.current_parse_run_id, doc.document_version, doc.current_revision_id, doc.space_id]);
  if (error) return <Notice error>{message(error)}</Notice>;
  if (!agent) return <p role="status">正在读取概览…</p>;
  if (agent.items[0] && !agent.items[0].stale) return <AgentAnalysis key={doc.id + doc.current_revision_id} api={api} doc={doc} firstPage={agent} />;
  return <><section className="content-state" aria-label="文档概览">
    <div className="reader-section-head"><h3>内容概览</h3><InfoTip>根据原文提炼内容要点，完整内容请使用右侧“查看源文件”。</InfoTip></div>
    {!doc.current_parse_run_id ? <p role="status">{processing[doc.processing_status] || "等待解析"}，暂无内容概览。</p>
      : !result ? <p role="status">正在读取概览…</p>
      : <>
        {result.stale_for_current_revision && <Notice>当前显示上一个版本的概览，新版本尚未解析完成。</Notice>}
        {!result.text_available && <Notice>未提取到可读文字，请查看源文件。</Notice>}
        <DocumentSummary data={result} minimal />
      </>}
  </section>{agent.items[0] && <details><summary>历史分析</summary><AgentAnalysis key={doc.id + doc.current_revision_id} api={api} doc={doc} firstPage={agent} /></details>}</>;
}
