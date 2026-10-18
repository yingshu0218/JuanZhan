import { useEffect, useState } from "react";
import { Dialog, Notice, formatSize } from "./ui.jsx";
import { message, ApiError } from "./api.js";
import { TaskStatus } from "./Tasks.jsx";
export function Original({ api, doc, revisions, onClose, onRefresh }) {
  const [data,setData]=useState(null),[error,setError]=useState(""),[downloadError,setDownloadError]=useState(""),[busy,setBusy]=useState(false),[imageError,setImageError]=useState(false);
  const [confirmed,setConfirmed]=useState(false),[adoption,setAdoption]=useState(null);
  const [adoptionRequest]=useState(()=>crypto.randomUUID());
  async function adopt(){
    setBusy(true);setDownloadError("");
    try {
      const value=await api.request(`/documents/${doc.id}/adopt`,{method:"POST",body:{expected_document_version:doc.document_version,expected_revision_id:doc.current_revision_id,request_id:adoptionRequest}});
      setAdoption(value.job_id);
    }catch(e){setDownloadError(message(e));}finally{setBusy(false);}
  }
  const current=revisions.find(r=>r.id===doc.current_revision_id);
  const query="?expected_revision_id="+encodeURIComponent(doc.current_revision_id || "");
  useEffect(()=>{
    const abort=new AbortController();
    api.request(`/documents/${doc.id}/preview${query}`,{signal:abort.signal}).then(value=>{if(!abort.signal.aborted)setData(value);}).catch(e=>{if(!abort.signal.aborted)setError(message(e));});
    return ()=>abort.abort();
  },[api,doc.id,query]);
  async function download(revision=current){
    setBusy(true);setDownloadError("");
    try {
      const downloadQuery=revision.id===doc.current_revision_id ? query : "?revision_id="+encodeURIComponent(revision.id);
      const response=await fetch(`/api/v1/documents/${doc.id}/download${downloadQuery}`,{credentials:"same-origin"});
      if(!response.ok){const value=await response.json();throw new ApiError(response.status,value.error);}
      const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");
      link.href=url;link.download=revision.original_filename || "original";link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
    }catch(e){setDownloadError(message(e));}finally{setBusy(false);}
  }
  return <Dialog title="关联原文件" wide onClose={onClose}>
    <p>{current?.original_filename || doc.title} · {current?.mime_type} · {current ? formatSize(current.size_bytes) : "大小未知"}</p>
    <p>下载前重新核验版本和完整性。历史外部原件若已变化或离线，将明确提示不可用。</p>
    {current?.size_bytes > 64 * 1024 * 1024 && <Notice>当前浏览器下载入口限64 MiB；更大原件请使用已鉴权下载API（上限1 GiB）。</Notice>}
    <button className="primary" disabled={busy || !current || current.size_bytes > 64 * 1024 * 1024} onClick={()=>download()}>{busy ? "正在核验与准备…" : "下载当前原件"}</button>
    {downloadError && <Notice error>{downloadError}</Notice>}
    {current?.storage_kind==="external" && <section aria-label="纳入托管">
      <h3>纳入托管</h3>
      {adoption ? <><Notice>已受理复制任务；成功后生成新的托管原件版本，重新解析结果请跟踪解析子任务。</Notice><TaskStatus api={api} id={adoption} /><button onClick={onRefresh}>关闭并刷新档案</button></> : <>
        <p>校验并复制外部原件，保留此档案编号、人工字段和已有正文。外部文件保持原样；复制失败时不切换原件。</p>
        <label className="check"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} />确认将当前外部原件复制为托管版本</label>
        <button disabled={busy || !confirmed || !!doc.deleted_at} onClick={adopt}>确认纳入托管</button>
      </>}
    </section>}
    <h3>安全预览</h3><p className="muted">显示当前版本已生成的缩略图，可能只覆盖部分内容；图序号不代表原件页码。原件可用性与缓存预览独立。</p>
    {error && <Notice error>{error}</Notice>}
    {imageError && <Notice error>预览暂不可用或原件版本已变化，请关闭并刷新档案。</Notice>}
    {data?.items.length===0 && <Notice>暂无可用缩略图，可下载原件，或在支持的格式上重新解析生成预览。</Notice>}
    <div className="original-previews">{data?.items.map(item=><figure key={item.id}><img loading="lazy" src={`/api/v1/documents/${doc.id}/preview/${item.id}${query}`} alt={`原件预览图 ${item.sequence}`} onError={()=>setImageError(true)} /><figcaption>预览图 {item.sequence}</figcaption></figure>)}</div>
    <details><summary>已登记原件版本</summary>{revisions.map(rev=><p key={rev.id}>{rev.original_filename} · 版本 {rev.revision_no} · {formatSize(rev.size_bytes)} {rev.id!==doc.current_revision_id && <button disabled={busy || rev.size_bytes > 64 * 1024 * 1024} onClick={()=>download(rev)}>下载版本 {rev.revision_no}</button>}</p>)}</details>
  </Dialog>;
}
