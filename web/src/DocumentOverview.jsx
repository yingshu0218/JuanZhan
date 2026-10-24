import { AgentAnalysis } from "./AgentAnalysis.jsx";
import { useEffect, useState } from "react";
import { DocumentSummary } from "./DocumentSummary.jsx";
import { Notice, processing, InfoTip } from "./ui.jsx";
import { message } from "./api.js";

export function DocumentOverview({ api, doc }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    setResult(null); setError(null);
    if (doc.current_parse_run_id) api.request(`/documents/${doc.id}/overview`, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setResult(data); })
      .catch(e => { if (e.name !== "AbortError") setError(e); });
    return () => controller.abort();
  }, [api, doc.id, doc.current_parse_run_id, doc.document_version]);
  return <><AgentAnalysis api={api} doc={doc} /><section className="content-state" aria-label="文档概览">
    <div className="reader-section-head"><h3>内容概览</h3><InfoTip>根据原文提炼内容要点，完整内容请使用右侧“查看源文件”。</InfoTip></div>
    {!doc.current_parse_run_id ? <p role="status">{processing[doc.processing_status] || "等待解析"}，暂无内容概览。</p>
      : error ? <Notice error>{message(error)}</Notice>
      : !result ? <p role="status">正在读取概览…</p>
      : <>
        {result.stale_for_current_revision && <Notice>当前显示上一个版本的概览，新版本尚未解析完成。</Notice>}
        {!result.text_available && <Notice>未提取到可读文字，请查看源文件。</Notice>}
        <DocumentSummary data={result} minimal />
      </>}
  </section></>;
}
