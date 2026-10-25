import { PendingDocuments } from "./PendingDocuments.jsx";
import { InfoTip } from "./ui.jsx";
import { useEffect, useRef, useState } from "react";
import { Dialog, Notice } from "./ui.jsx";
import { message } from "./api.js";
import { JobProgress } from "./JobProgress.jsx";
const statuses = { queued: "排队中", running: "处理中", paused:"已暂停", completed: "已完成", failed: "失败", cancelled: "已取消" };
function safeResult(value) {
  if (!value || typeof value !== "object") return null;
  const allowed = new Set(["backup_id", "recovery_id", "files", "external_sources_included", "activation_required", "automatic_backup_disabled", "credentials_revoked", "status", "reason", "document_id", "parse_run_id", "parse_job_id", "revision_id", "job_id", "succeeded", "skipped", "failed", "purged", "external_file_deleted", "gc_job_id", "generation", "tokenizer_version", "code", "error_code", "document_version", "text_available", "ocr_used", "source_id", "estimated_files", "estimated_bytes", "discovered", "retained_objects", "deleted_objects", "ignored_files", "items"]);
  return Object.fromEntries(Object.entries(value).filter(([key]) => allowed.has(key)).map(([key, item]) => [key, key === "items" && Array.isArray(item) ? item.slice(0, 100).map(safeResult) : (item === null || ["string", "number", "boolean"].includes(typeof item) ? item : null)]));
}
const resultLabels = { status: "结果状态", reason: "原因代码", document_id: "档案编号", parse_run_id: "解析记录", parse_job_id: "解析任务编号", revision_id: "原件版本", job_id: "任务编号", succeeded: "成功项", skipped: "跳过项", failed: "失败项", purged: "永久清理", external_file_deleted: "外部文件已删除", gc_job_id: "后续清理任务", generation: "索引代次", tokenizer_version: "分词版本", code: "错误代码", error_code: "错误代码", document_version: "档案版本", text_available: "正文可用", ocr_used: "使用 OCR", source_id: "来源编号", estimated_files: "预计文件数", estimated_bytes: "预计字节数", discovered: "发现对象", retained_objects: "保留对象", deleted_objects: "清理对象", ignored_files: "忽略文件" };
Object.assign(resultLabels, { backup_id: "备份编号", recovery_id: "恢复编号", files: "文件数", external_sources_included: "包含外部原件", activation_required: "需管理员激活", automatic_backup_disabled: "已关闭自动备份", credentials_revoked: "已撤销旧凭据" });
function ResultView({ value }) {
  const safe = safeResult(value);
  if (!safe) return <p>没有可显示的结果记录</p>;
  return <div className="task-result">{Object.entries(safe).map(([key, item]) => key === "items" && Array.isArray(item)
    ? <ol key={key}>{item.map((entry, index) => <li key={index}><ResultView value={entry} /></li>)}</ol>
    : <p key={key}>{resultLabels[key] || key}：{item === null ? "未知" : typeof item === "boolean" ? (item ? "是" : "否") : statuses[item] || ({succeeded:"成功",skipped:"跳过",discarded:"未发布"}[item]) || String(item)}</p>)}</div>;
}
const kinds = { upload: "上传", scan: "来源扫描", scan_preview: "预扫描", parse: "解析", ocr: "OCR", reindex: "检索索引", batch: "批量操作", purge: "永久清理", gc: "存储清理" };
function kindLabel(job) { const sourceKinds={revision_markdown:'生成 Markdown 副本',document_snapshot:'保存原件副本',source_snapshot_batch:'来源副本任务',document_reading_preview:'源文件阅读预览',document_revision_cleanup:'清理历史版本',storage_cleanup:'清理存储缓存'}; if(sourceKinds[job.target_type])return sourceKinds[job.target_type]; return job.target_type === "system_backup" ? "系统备份" : job.target_type === "system_recovery" ? "新目录恢复" : kinds[job.kind] || job.kind; }
// One visible-tab poller for the global entry; totals come from real paginated APIs.
export function TaskEntry({ api, onOpen, refreshKey }) {
  const [counts, setCounts] = useState(null), [error, setError] = useState(false);
  useEffect(() => {
    const abort = new AbortController(); let timer;
    async function load() {
      if (!document.hidden) {
        try {
          const [queued, running] = await Promise.all(["queued", "running"].map(status => api.request(`/jobs?status=${status}&page_size=1`, { signal: abort.signal })));
          if (!abort.signal.aborted) { setCounts({ queued: queued.total, running: running.total }); setError(false); }
        } catch { if (!abort.signal.aborted) setError(true); }
      }
      if (!abort.signal.aborted) timer = setTimeout(load, 5000);
    }
    load(); return () => { abort.abort(); clearTimeout(timer); };
  }, [api, refreshKey]);
  return <button className="task-entry" onClick={() => onOpen(null)} aria-label="任务中心" title="查看全部后台任务及处理进度">
    <strong>任务中心</strong><small role="status">{error ? "状态待刷新" : counts ? `排队 ${counts.queued} · 处理中 ${counts.running}` : "读取状态…"}</small>
  </button>;
}
export function TaskStatus({ api, id, onTerminal, compact = false }) {
  const [job, setJob] = useState(null), [error, setError] = useState(""), [refresh, setRefresh] = useState(0), [busy, setBusy] = useState(false);
  const terminal=useRef(onTerminal);
  useEffect(()=>{terminal.current=onTerminal;},[onTerminal]);
  useEffect(() => {
    const abort = new AbortController(); let timer, polls = 0;
    setJob(null); setError("");
    async function load() {
      try {
        const result = await api.request("/jobs/" + id, { signal: abort.signal });
        if (abort.signal.aborted) return;
        setJob(result);
        if(['completed','failed','cancelled'].includes(result.status))terminal.current?.(result);
        if (["queued", "running"].includes(result.status) && ++polls < 60) timer = setTimeout(load, 2000);
      } catch (e) { if (!abort.signal.aborted) setError(message(e)); }
    }
    load(); return () => { abort.abort(); clearTimeout(timer); };
  }, [api, id, refresh]);
  async function retry() {
    setBusy(true); setError("");
    try { await api.request(`/jobs/${id}/retry`, { method: "POST" }); setRefresh(n => n + 1); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <section className="task-status" aria-label="任务详情">
    {error && <Notice error>{error}</Notice>}
    {job && <>
      <JobProgress job={job} />
      {!compact && <p>关联对象：{job.target_id || "系统维护"}</p>}
      <h3>{kindLabel(job)} · {job.status === "completed" && job.result?.failed > 0 ? "已结束（存在失败项）" : statuses[job.status]}</h3>
      {!compact && <p>任务编号：<code>{id}</code></p>}
      {!compact && <p>尝试 {job.attempts} / {job.max_attempts}；已处理 {job.progress_done ?? 0}{job.progress_total == null ? "，总量未知" : ` / ${job.progress_total}`}</p>}
      {job.progress_total > 0 && <progress value={job.progress_done || 0} max={job.progress_total} />}
      {job.status === "queued" && <p>最早可执行：{new Date(job.available_at).toLocaleString()}。受理不代表处理成功。</p>}
      {job.error && <Notice error>错误代码：{job.error.code}。请核对服务和原件后再操作。</Notice>}
      {job.result?.status === "discarded" && <Notice>任务已结束，但结果未发布，请核对当前版本。</Notice>}
      {job.result && !compact && <details><summary>结果记录（可能包含逐项失败）</summary><ResultView value={job.result} /></details>}
      {job.can_retry && <button disabled={busy} onClick={retry}>确认重试（沿用剩余次数）</button>}
    </>}
    <button onClick={() => setRefresh(n => n + 1)}>刷新任务</button>
    <InfoTip>自动跟踪最多两分钟；关闭窗口不取消后台任务，可重新打开查看。</InfoTip>
  </section>;
}
export function TaskCenter({ api, onClose, initialId = null, spaces=[], onOpenDocument }) {
  const [tab,setTab]=useState("jobs"),[selected,setSelected]=useState(new Set()),[busy,setBusy]=useState(false),[confirmation,setConfirmation]=useState(null),[notice,setNotice]=useState("");
  const [status, setStatus] = useState(""), [page, setPage] = useState(1), [data, setData] = useState(null), [id, setId] = useState(initialId), [error, setError] = useState(""), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if(tab!=="jobs")return;
    const abort = new AbortController(); let timer; setData(null); setError("");
    async function load() {
      if (!document.hidden) {
        try {
          const value = await api.request(`/jobs?page=${page}&page_size=20${status ? `&status=${status}` : ""}`, { signal: abort.signal });
          if (!abort.signal.aborted) { setData(value); setError(""); }
        } catch (e) { if (!abort.signal.aborted) setError(message(e)); }
      }
      if (!abort.signal.aborted) timer = setTimeout(load, 3000);
    }
    load(); return () => { abort.abort(); clearTimeout(timer); };
  }, [api, status, page, refresh, tab]);
  async function selectResults(){setBusy(true);setError("");try{const ids=[];for(let number=1;number<=50;number++){const result=await api.request(`/jobs?page=${number}&page_size=100${status?`&status=${status}`:""}`);if(result.total>1000)throw Error('筛选结果超过1000项，请先按状态缩小范围。');ids.push(...result.items.map(job=>job.id));if(number*100>=result.total)break;}setSelected(new Set(ids));}catch(e){setError(message(e));}finally{setBusy(false);}}
  async function control(action){setBusy(true);setError("");setNotice("");try{const result=await api.request('/jobs/control',{method:'POST',body:{action,job_ids:[...selected]}});setNotice(`已操作 ${result.succeeded} 项，未操作 ${result.failed} 项。`);if(result.failed)setError([...new Set(result.items.filter(item=>item.error_code).map(item=>message({code:item.error_code})))].join('；'));setSelected(new Set());setConfirmation(null);setRefresh(n=>n+1);}catch(e){setError(message(e));}finally{setBusy(false);}}
  return <Dialog title="任务中心" wide onClose={onClose}>
    <div className="summary-actions"><button aria-pressed={tab==='jobs'} onClick={()=>setTab('jobs')}>后台任务</button><button aria-pressed={tab==='pending'} onClick={()=>setTab('pending')}>待处理文件</button></div>
    {tab==='pending'?<PendingDocuments api={api} spaces={spaces} onOpenDocument={onOpenDocument}/>:<>
    <InfoTip>全部空间与系统维护任务。每 3 秒自动更新，刷新页面后仍可查询。关闭窗口不会取消任务。暂停会停止后续执行，恢复时解析可能从头运行；已提交的独立转换可能继续至自身超时，但旧结果不会写入档案。取消只停止本次任务，不关闭未来自动计划。删除任务是移除列表记录，审计保留；已完成的业务步骤不撤销，原件和待处理文件保留。</InfoTip><InfoTip>排队中的任务尚未开始；处理中不代表已完成。总量未知时不显示估算百分比。</InfoTip>
    <label>任务状态 <select value={status} onChange={e => { setStatus(e.target.value); setPage(1); setId(null);setSelected(new Set()); }}><option value="">全部状态</option>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <button onClick={() => setRefresh(n => n + 1)}>刷新列表</button>
    <div className="summary-actions"><button disabled={busy} onClick={()=>setSelected(new Set((data?.items||[]).map(job=>job.id)))}>选择本页任务</button><button disabled={busy} onClick={selectResults}>选择筛选结果</button><button disabled={busy||!selected.size} onClick={()=>control('pause')}>批量暂停</button><button disabled={busy||!selected.size} onClick={()=>control('resume')}>批量恢复</button><button disabled={busy||!selected.size} onClick={()=>setConfirmation('cancel')}>批量取消</button><button disabled={busy||!selected.size} onClick={()=>setConfirmation('delete')}>批量删除记录</button><span>已选择 {selected.size} 项</span></div>
    {confirmation&&<section aria-label="确认任务操作"><Notice>{confirmation==='delete'?'取消未完成任务并从任务列表移除记录':'取消所选任务'}，原件、已有结果和待处理文件保留；已经完成的业务步骤不会撤销。</Notice><button disabled={busy||!selected.size} onClick={()=>control(confirmation)}>确认{confirmation==='delete'?'删除任务记录':'取消任务'}</button><button disabled={busy} onClick={()=>setConfirmation(null)}>返回任务列表</button></section>}
    {notice&&<Notice>{notice}</Notice>}
    {error && <Notice error>{error}</Notice>}
    <div className="tasks-layout">
      {id && data && !data.items.some(job => job.id === id) && <TaskStatus key={id} api={api} id={id} />}
      {data?.items.length === 0 && <p>暂无任务</p>}
      {data?.items.map(job => <div className="task-card" key={job.id}>
        <label className="check-label"><input type="checkbox" aria-label={'选择任务 '+job.id} checked={selected.has(job.id)} disabled={busy||(!selected.has(job.id)&&selected.size>=1000)} onChange={e=>setSelected(old=>{const next=new Set(old);if(e.target.checked)next.add(job.id);else next.delete(job.id);return next;})}/>选择任务</label>
        <button className="task-row" onClick={() => setId(id === job.id ? null : job.id)} aria-pressed={id === job.id}>
          {id === job.id ? <strong className="job-filename">{job.document_name || kindLabel(job)}</strong> : <JobProgress job={job} />}
          <strong>{kindLabel(job)} · {statuses[job.status]}</strong><small>{new Date(job.created_at).toLocaleString()} · {job.id}</small>
        </button>
        {id === job.id && <TaskStatus key={id+refresh} api={api} id={id} />}
      </div>)}
      {data && <div className="task-pages"><button disabled={page === 1} onClick={() => setPage(n => n - 1)}>上一页</button><span>第 {page} 页 · 共 {data.total} 项</span><button disabled={page * 20 >= data.total} onClick={() => setPage(n => n + 1)}>下一页</button></div>}
    </div></>}
  </Dialog>;
}
export function Reprocess({ api, doc }) {
  const [open, setOpen] = useState(false), [ocr, setOcr] = useState(false), [language, setLanguage] = useState("eng"), [confirmed, setConfirmed] = useState(false), [intent, setIntent] = useState(null), [job, setJob] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function submit() {
    const body = intent || { expected_document_version: doc.document_version, expected_revision_id: doc.current_revision_id, request_id: crypto.randomUUID(), ocr, ocr_languages: ocr ? language : "", force: true, generate_preview: true };
    setIntent(body); setBusy(true); setError("");
    try { const result = await api.request(`/documents/${doc.id}/reprocess`, { method: "POST", body }); setJob(result.job_id); }
    catch (e) { setError(message(e) + " 重发将复用同一请求；版本冲突请关闭并刷新档案。"); }
    finally { setBusy(false); }
  }
  return <>
    <button disabled={!!doc.deleted_at || !doc.current_revision_id} onClick={() => { setOpen(true); setIntent(null); setJob(null); setError(""); setOcr(false); setConfirmed(false); }}>重新解析 / OCR</button>
    {open && <Dialog title="重新解析档案" onClose={() => setOpen(false)}>
      {job ? <><Notice>任务已受理，请跟踪实际结果。结束后关闭窗口并刷新档案查看正文。</Notice><TaskStatus api={api} id={job} /></> : <>
        <InfoTip>处理当前版本原件，保留人工字段与最近成功正文；失败不会清空已有内容。</InfoTip>
        <fieldset disabled={busy || !!intent}><label><input type="checkbox" checked={ocr} onChange={e => setOcr(e.target.checked)} />启用 OCR（耗时较长）</label>
        {ocr && <label>OCR 语言<select value={language} onChange={e => setLanguage(e.target.value)}><option value="eng">英文</option><option value="chi_sim">简体中文</option><option value="eng,chi_sim">英文与简体中文</option></select></label>}
        <label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />确认对当前原件重新处理，包括已有成功结果</label></fieldset>
        {error && <Notice error>{error}</Notice>}
        <button className="primary" disabled={busy || !confirmed} onClick={submit}>{intent ? "重发同一请求" : "确认并提交任务"}</button>
      </>}
    </Dialog>}
  </>;
}
