import { useEffect, useState } from "react";
import { Dialog, InfoTip, Notice } from "./ui.jsx";
import { message } from "./api.js";
import { searchBody } from "./searchState.js";

export function QuickFilters({api, space, draft, onApply}) {
  const [open,setOpen]=useState(false);
  const [items,setItems]=useState([]),[name,setName]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();
    api.request(`/saved-filters?space_id=${encodeURIComponent(space)}`,{signal:controller.signal}).then(setItems).catch(e=>{if(e.name!=='AbortError')setError(message(e));});
    return()=>controller.abort();
  },[api,space]);
  async function save(){
    setError('');setBusy(true);
    try{searchBody(draft);const item=await api.request('/saved-filters',{method:'POST',body:{space_id:space,name:name.trim(),criteria:draft}});setItems(old=>[...old.filter(value=>value.id!==item.id),item]);setName('');}
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  async function remove(item){
    setError('');setBusy(true);
    try{await api.request(`/saved-filters/${item.id}`,{method:'DELETE'});setItems(old=>old.filter(value=>value.id!==item.id));}
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <><button type="button" onClick={()=>setOpen(true)}>快捷筛选</button>{open && <Dialog title="快捷筛选" onClose={()=>setOpen(false)}><div className="quick-filters"><div className="quick-filter-head"><strong>快捷筛选</strong><InfoTip>组合保存在当前空间，支持跨浏览器使用。保存标签、匹配方式、关键词和高级筛选；同名覆盖，最多20组。目录和列表分区沿用当前选择。</InfoTip></div>
    {error&&<Notice error>{error}</Notice>}
    <div className="quick-filter-list">{items.map(item=><div className="summary-actions" key={item.id}><button type="button" disabled={busy} onClick={()=>{try{searchBody(item.criteria);setOpen(false);onApply(item.criteria);}catch(e){setError(e.message);}}}>{item.name}</button><button type="button" disabled={busy} aria-label={`删除筛选 ${item.name}`} onClick={()=>remove(item)}>×</button></div>)}</div>
    <div className="search-input-row"><input aria-label="筛选组合名称" placeholder="组合名称" maxLength={40} value={name} onChange={e=>setName(e.target.value)}/><button type="button" disabled={busy||!name.trim()} onClick={save}>保存组合</button></div>
  </div></Dialog>}</>;
}
