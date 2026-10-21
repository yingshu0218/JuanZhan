import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Dialog, InfoTip, Notice, formatSize } from './ui.jsx';
import { ApiError, message } from './api.js';
import { TaskStatus } from './Tasks.jsx';
const PDFReader=lazy(()=>import('./PDFReader.jsx'));
const MAX=64*1024*1024;
const nativeText=mime=>['text/plain','text/markdown','text/csv','text/tab-separated-values','text/html'].includes(mime);
const fileUrl=(id,revision)=>`/api/v1/documents/${encodeURIComponent(id)}/download?revision_id=${encodeURIComponent(revision)}`;

async function readBytes(url,signal,limit=MAX){
  const response=await fetch(url,{credentials:'same-origin',signal});
  if(!response.ok){const data=await response.json();throw new ApiError(response.status,data.error);}
  if(Number(response.headers.get('content-length'))>limit){await response.body.cancel();throw Error('SOURCE_TOO_LARGE');}
  const reader=response.body.getReader();const chunks=[];let total=0;
  try { while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>limit){await reader.cancel();throw Error('SOURCE_TOO_LARGE');}chunks.push(value);} }
  finally {reader.releaseLock();}
  const result=new Uint8Array(total);let offset=0;for(const chunk of chunks){result.set(chunk,offset);offset+=chunk.length;}return result;
}
function safeImage(bytes,mime){
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);let width=0,height=0;
  if(mime==='image/png' && bytes.length>=24 && view.getUint32(0)===0x89504e47 && view.getUint32(4)===0x0d0a1a0a){width=view.getUint32(16);height=view.getUint32(20);}
  if(mime==='image/jpeg' && view.byteLength>=4 && view.getUint16(0)===0xffd8){
    let offset=2;
    while(offset+4<bytes.length && offset<262144){
      if(bytes[offset++]!==255)break;let marker=bytes[offset++];while(marker===255 && offset<bytes.length)marker=bytes[offset++];
      if(marker===0xd8 || marker===0x01 || (marker>=0xd0 && marker<=0xd7))continue;
      if(marker===0xd9 || marker===0xda)break;
      const size=view.getUint16(offset);if(size<2 || offset+size>bytes.length)break;
      if([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker) && size>=7){height=view.getUint16(offset+3);width=view.getUint16(offset+5);break;}
      offset+=size;
    }
  }
  if(!width || !height || width>12000000 || height>12000000 || width*height>12000000)throw Error('IMAGE_LIMIT');
}
function DirectSource({id,revision}){
  const [value,setValue]=useState(null),[error,setError]=useState('');
  useEffect(()=>{
    const controller=new AbortController();let url;
    setValue(null);setError('');
    readBytes(fileUrl(id,revision.id),controller.signal,nativeText(revision.mime_type)?4*1024*1024:MAX).then(bytes=>{
      if(controller.signal.aborted)return;
      if(nativeText(revision.mime_type)){
        const encoding=bytes[0]===255 && bytes[1]===254?'utf-16le':bytes[0]===254 && bytes[1]===255?'utf-16be':'utf-8';
        setValue({text:new TextDecoder(encoding,{fatal:true}).decode(bytes)});
      }else{safeImage(bytes,revision.mime_type);url=URL.createObjectURL(new Blob([bytes],{type:revision.mime_type}));setValue({url});}
    }).catch(e=>{if(e.name!=='AbortError')setError(e instanceof ApiError?message(e):e.message==='IMAGE_LIMIT'?'图片超过安全阅读范围，请下载原件。':'无法在平台读取此文件，请下载原件。');});
    return()=>{controller.abort();if(url)URL.revokeObjectURL(url);};
  },[id,revision.id,revision.mime_type]);
  return error?<Notice error>{error}</Notice>:!value?<p role="status">正在打开源文件…</p>:value.url?<img className="source-original-image" src={value.url} alt={revision.original_filename}/>:<pre className="source-original-text">{value.text}</pre>;
}

export function SourceFileReader({api,doc,revisions=[],onClose,onRefresh}){
  const [inventory,setInventory]=useState(null),[page,setPage]=useState(1),[refresh,setRefresh]=useState(0);
  const [selected,setSelected]=useState(()=>revisions.find(r=>r.id===doc.current_revision_id)||null);
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[job,setJob]=useState(null),[confirmed,setConfirmed]=useState(false);
  const [preview,setPreview]=useState(null),[previewAttempt,setPreviewAttempt]=useState(0);
  const intents=useRef(new Map());
  const retryPreview=useRef(new Set());
  useEffect(()=>{
    const controller=new AbortController();
    api.request(`/documents/${doc.id}/source-files?page=${page}&page_size=20`,{signal:controller.signal}).then(data=>{
      if(controller.signal.aborted)return;setInventory(data);
      setSelected(current=>data.items.find(item=>item.id===(current?.id||doc.current_revision_id))||current||data.items[0]||null);
    }).catch(e=>{if(e.name!=='AbortError')setError(message(e));});
    return()=>controller.abort();
  },[api,doc.id,doc.current_revision_id,page,refresh]);
  useEffect(()=>{
    if(!selected || selected.mime_type==='application/pdf' || selected.mime_type==='image/png' || selected.mime_type==='image/jpeg' || nativeText(selected.mime_type))return;
    const controller=new AbortController();let timer;
    setPreview(null);
    async function load(){
      if(document.hidden){timer=setTimeout(load,1500);return;}
      try {
        const state=await api.request(`/documents/${doc.id}/reading-preview?revision_id=${encodeURIComponent(selected.id)}`,{signal:controller.signal});
        if(controller.signal.aborted)return;setPreview(state);
        if(state.supported && (state.state==='not_generated' || (state.state==='failed' && retryPreview.current.has(selected.id))) && selected.size_bytes<=32*1024*1024 && !doc.deleted_at){
          const key=selected.id+':'+previewAttempt;
          if(!intents.current.has(key))intents.current.set(key,crypto.randomUUID());
          const accepted=await api.request(`/documents/${doc.id}/reading-preview`,{method:'POST',signal:controller.signal,
            body:{expected_document_version:doc.document_version,revision_id:selected.id,request_id:intents.current.get(key)}});
          if(controller.signal.aborted)return;setPreview({...state,state:accepted.status,job_id:accepted.job_id});
          retryPreview.current.delete(selected.id);
          timer=setTimeout(load,1500);
        }else if(['queued','running'].includes(state.state))timer=setTimeout(load,1500);
      }catch(e){if(e.name!=='AbortError')setError(message(e));}
    }
    load();return()=>{controller.abort();clearTimeout(timer);};
  },[api,doc.id,doc.document_version,doc.deleted_at,selected?.id,selected?.mime_type,previewAttempt]);
  function actionFinished(result){
    setJob(current=>current?.id===result.id?{...current,terminal:true}:current);
    setRefresh(n=>n+1);
    if(result.status==='completed' && job?.kind==='snapshot')setSelected(value=>value?.id===job.revision?{...value,server_copy:true}:value);
    if(result.status==='completed' && job?.kind==='delete')onRefresh();
  }
  async function act(kind){
    if(!selected)return;setBusy(true);setError('');
    try {
      const body={expected_document_version:inventory.document_version,revision_id:selected.id,request_id:(()=>{const key=kind+':'+selected.id+':'+inventory.document_version;if(!intents.current.has(key))intents.current.set(key,crypto.randomUUID());return intents.current.get(key);})()};
      if(kind==='delete')body.confirm_revision_id=selected.id;
      const result=await api.request(kind==='delete'?`/documents/${doc.id}/revisions/${selected.id}`:`/documents/${doc.id}/source-snapshot`,{method:kind==='delete'?'DELETE':'POST',body});
      setJob({id:result.job_id,kind,revision:selected.id});setConfirmed(false);
    }catch(e){setError(message(e));}finally{setBusy(false);}
  }
  async function download(){
    if(selected.size_bytes>MAX){window.open(fileUrl(doc.id,selected.id),'_blank','noopener,noreferrer');return;}
    setBusy(true);setError('');
    try{const bytes=await readBytes(fileUrl(doc.id,selected.id),undefined);const url=URL.createObjectURL(new Blob([bytes]));const link=document.createElement('a');link.href=url;link.download=selected.original_filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}
    catch(e){setError(e instanceof ApiError?message(e):'原件超出浏览器下载范围，请使用已鉴权下载API。');}finally{setBusy(false);}
  }
  const direct=selected && (nativeText(selected.mime_type)||['image/png','image/jpeg'].includes(selected.mime_type));
  const nativePDF=selected?.mime_type==='application/pdf';
  return <Dialog title="源文件" wide onClose={onClose}>
    {error && <Notice error>{error}</Notice>}
    {!selected?<p role="status">正在读取源文件…</p>:<>
      <div className="source-file-head"><strong>{selected.original_filename}</strong><span>{formatSize(selected.size_bytes)} · 版本 {selected.revision_no}</span></div>
      <div className="source-file-actions">
        <label>源文件版本<select value={selected.id} onChange={e=>{setSelected(inventory.items.find(item=>item.id===e.target.value));setError('');setConfirmed(false);}}>
          {inventory && !inventory.items.some(item=>item.id===selected.id) && <option value={selected.id}>版本 {selected.revision_no}</option>}
          {(inventory?.items||[selected]).map(item=><option key={item.id} value={item.id}>版本 {item.revision_no}{item.is_current?'（当前）':''}</option>)}
        </select></label>
        <button disabled={busy} onClick={download}>下载原件</button>
        <button onClick={()=>{setRefresh(n=>n+1);setPreviewAttempt(n=>n+1);setError('');}}>刷新文件状态</button>
      </div>
      {inventory?.total>20 && <nav aria-label="原件版本分页"><button disabled={page===1} onClick={()=>setPage(n=>n-1)}>上一页版本</button><span>第 {page} 页</span><button disabled={page*20>=inventory.total} onClick={()=>setPage(n=>n+1)}>下一页版本</button></nav>}
      {selected.source && <p>{selected.source.name} · {selected.server_copy?'服务器已保存副本':'尚未保存服务器副本'}<InfoTip>来源关联仍保留，读取外部目录不会修改源文件。来源失联后，已保存的版本仍可查看。</InfoTip></p>}
      {selected.source && !selected.server_copy && <button disabled={busy||!inventory||(!!job&&!job.terminal)||!!doc.deleted_at} onClick={()=>act('snapshot')}>保存服务器副本</button>}
      {job && <TaskStatus api={api} id={job.id} compact onTerminal={actionFinished}/>}
      <section className="source-file-reading" aria-label="源文件阅读">
        {nativePDF?<Suspense fallback={<p>正在打开源文件…</p>}><PDFReader key={selected.id} documentId={doc.id} revisionId={selected.id} sourceUrl={fileUrl(doc.id,selected.id)}/></Suspense>
          :direct?<DirectSource key={selected.id} id={doc.id} revision={selected}/>
          :preview?.state==='ready'?<Suspense fallback={<p>正在打开阅读预览…</p>}><PDFReader key={selected.id} documentId={doc.id} revisionId={selected.id} preview sourceUrl={`/api/v1/documents/${doc.id}/reading-preview/file?revision_id=${encodeURIComponent(selected.id)}`}/></Suspense>
          :preview?.supported?<>{selected.size_bytes>32*1024*1024?<Notice>文件超过阅读预览上限，可以下载原件。</Notice>:doc.deleted_at && preview.state==='not_generated'?<Notice>请先恢复档案，再生成阅读预览。</Notice>:<><p role="status">{preview.state==='failed'?'阅读预览未完成。':'正在准备源文件阅读预览…'}</p>{preview.job_id && <TaskStatus api={api} id={preview.job_id}/>}</>}{preview.state==='failed' && <button onClick={()=>{retryPreview.current.add(selected.id);setPreviewAttempt(n=>n+1);setError('');}}>重试阅读预览</button>}</>
          :preview && <Notice>此格式暂不能在平台内预览，可以下载原件。</Notice>}
      </section>
      {inventory && selected.id!==doc.current_revision_id && <details className="source-history-cleanup"><summary>清理此历史版本</summary>
        <InfoTip>删除所选历史原件及其缓存，不删除外部文件。当前版本、成功概览和业务字段仍引用的版本会被保护。</InfoTip>
        <label className="check-label"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>确认删除版本 {selected.revision_no}：{selected.original_filename}</label>
        <button className="danger" disabled={!confirmed||busy||(!!job&&!job.terminal)} onClick={()=>act('delete')}>确认删除历史版本</button>
      </details>}
    </>}
  </Dialog>;
}
