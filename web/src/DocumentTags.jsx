import { useEffect, useState } from "react";
import { InfoTip, Notice } from "./ui.jsx";
import { message } from "./api.js";

export function DocumentTags({api, doc, onSaved, onFilter}) {
  const [tags,setTags]=useState([]),[selected,setSelected]=useState(doc.tag_ids),[editing,setEditing]=useState(false);
  const [name,setName]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
  useEffect(()=>{
    const controller=new AbortController();
    api.request(`/tags?space_id=${encodeURIComponent(doc.space_id)}`,{signal:controller.signal}).then(setTags).catch(e=>{if(e.name!=="AbortError")setError(message(e));});
    setSelected(doc.tag_ids);
    return()=>controller.abort();
  },[api,doc.id,doc.document_version,doc.space_id]);
  async function create(){
    setBusy(true);setError("");
    try {const tag=await api.request('/tags',{method:'POST',body:{space_id:doc.space_id,name:name.trim()}});setTags(old=>[...old,tag]);setSelected(old=>[...old,tag.id]);setName("");}
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  async function save(){
    setBusy(true);setError("");
    try {await api.request(`/documents/${doc.id}`,{method:'PATCH',body:{expected_document_version:doc.document_version,tags_add:selected.filter(id=>!doc.tag_ids.includes(id)),tags_remove:doc.tag_ids.filter(id=>!selected.includes(id))}});setEditing(false);onSaved();}
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <section aria-label="文档标签"><div className="reader-section-head"><h3>标签</h3><InfoTip>可多选。手动保存后，后续自动解析或Agent提交不会改动本文件标签。点击标签可筛选。</InfoTip></div>
    {error&&<Notice error>{error}</Notice>}
    {editing?<>
      <fieldset disabled={busy}><legend>选择文档标签</legend>{tags.map(tag=><label className="check-label" key={tag.id}><input type="checkbox" checked={selected.includes(tag.id)} onChange={e=>setSelected(old=>e.target.checked?[...old,tag.id]:old.filter(id=>id!==tag.id))}/>{tag.name}</label>)}</fieldset>
      <label>新标签<input maxLength={60} value={name} onChange={e=>setName(e.target.value)}/></label>
      <button disabled={busy||!name.trim()} onClick={create}>创建并选择</button>
      <div className="summary-actions"><button className="primary" disabled={busy} onClick={save}>保存标签</button><button disabled={busy} onClick={()=>{setSelected(doc.tag_ids);setEditing(false);setError("");}}>取消</button></div>
    </>:<><div className="tags">{doc.tag_ids.length?doc.tag_ids.map(id=><button key={id} onClick={()=>onFilter?.(id)}>{tags.find(tag=>tag.id===id)?.name||"标签读取中"}</button>):<p className="muted">暂无标签</p>}</div>{!doc.deleted_at&&<button onClick={()=>setEditing(true)}>编辑标签</button>}</>}
  </section>;
}
