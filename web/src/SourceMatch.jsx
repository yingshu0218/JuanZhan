import {useEffect,useState} from "react";
import {Dialog,Notice,formatSize} from "./ui.jsx";
import {TaskStatus} from "./Tasks.jsx";
import {message} from "./api.js";

export function SourceMatch({api,sourceId,entry,onClose,onDone}){
  const [data,setData]=useState(null),[page,setPage]=useState(1),[selected,setSelected]=useState(null);
  const [action,setAction]=useState('match'),[confirmed,setConfirmed]=useState(false);
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[job,setJob]=useState(null);
  const [requestId]=useState(()=>crypto.randomUUID());
  useEffect(()=>{
    const abort=new AbortController();setData(null);setSelected(null);setConfirmed(false);setError('');
    api.request(`/sources/${sourceId}/entries/${entry.id}/matches?page=${page}`,{signal:abort.signal})
      .then(value=>{if(!abort.signal.aborted)setData(value);})
      .catch(e=>{if(!abort.signal.aborted)setError(message(e));});
    return ()=>abort.abort();
  },[api,sourceId,entry.id,page]);
  async function submit(){
    setBusy(true);setError('');
    const body={action,expected_entry_updated_at:data.entry.updated_at,request_id:requestId};
    if(action==='match')Object.assign(body,{document_id:selected.document_id,expected_document_version:selected.document_version,expected_revision_id:selected.revision_id});
    try {setJob((await api.request(`/sources/${sourceId}/entries/${entry.id}/resolve`,{method:'POST',body})).job_id);}
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <Dialog title="处理待匹配文件" wide onClose={onClose}>
    <p>{entry.relative_path} · {formatSize(entry.size_bytes)}</p>
    {error && <Notice error>{error}</Notice>}
    {job ? <><Notice>已受理，后台会重新核验原件和版本；失败不会改变既有档案或外部文件。</Notice><TaskStatus api={api} id={job} /><button onClick={onDone}>关闭并刷新来源</button></> : data ? <>
      <label>处理方式<select disabled={busy} value={action} onChange={e=>{setAction(e.target.value);setConfirmed(false);}}>
        <option value="match">关联已有档案</option><option value="new_document">登记为新档案</option>
      </select></label>
      {action==='match' ? <>
        <p>候选具有相同已记录哈希和大小，请明确选择。只在旧路径已不存在且当前字节核验通过时重新关联；保留档案编号、人工字段与已有正文。</p>
        <fieldset disabled={busy}><legend>选择原档案</legend>
          {data.items.map(candidate=><label className="check-label source-match-choice" key={candidate.document_id}>
            <input type="radio" name="match-document" checked={selected?.document_id===candidate.document_id} onChange={()=>{setSelected(candidate);setConfirmed(false);}} />
            <span>{candidate.title} · 原路径 {candidate.previous_path}</span>
          </label>)}
          {data.total===0 && <Notice>没有当前可关联的档案。可刷新来源核对，或明确选择登记为新档案。</Notice>}
        </fieldset>
        <p>第 {page} 页 · 共 {data.total} 个候选</p>
        <button disabled={busy || page===1} onClick={()=>setPage(value=>value-1)}>上一页候选</button>
        <button disabled={busy || page*data.page_size>=data.total} onClick={()=>setPage(value=>value+1)}>下一页候选</button>
      </> : <Notice>将建立独立的新档案并进入收件箱，不与相同哈希档案合并；原有待匹配档案保持原样。</Notice>}
      <label className="check-label"><input type="checkbox" disabled={busy} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} />确认此选择，外部文件保持不变</label>
      <button className="primary" disabled={busy || !confirmed || (action==='match' && !selected)} onClick={submit}>确认处理待匹配文件</button>
    </> : !error && <p>正在读取候选…</p>}
  </Dialog>;
}
