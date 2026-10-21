import { useEffect, useRef, useState } from 'react';
import { Dialog, InfoTip, Notice, formatSize } from './ui.jsx';
import { message } from './api.js';
import { TaskStatus } from './Tasks.jsx';

export function StorageManager({api,onClose}){
  const [usage,setUsage]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[epoch,setEpoch]=useState(0);
  const [kind,setKind]=useState('reading_previews'),[confirmed,setConfirmed]=useState(false),[job,setJob]=useState(null);
  const intent=useRef(null);
  useEffect(()=>{
    const controller=new AbortController();
    api.request('/system/storage',{signal:controller.signal}).then(setUsage).catch(e=>{if(e.name!=='AbortError')setError(message(e));});
    return()=>controller.abort();
  },[api,epoch]);
  async function cleanup(event){
    event.preventDefault();setBusy(true);setError('');
    if(!intent.current)intent.current={kind,confirm:true,request_id:crypto.randomUUID()};
    try{const result=await api.request('/system/storage/cleanup',{method:'POST',body:intent.current});setJob(result.job_id);setConfirmed(false);intent.current=null;}
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <Dialog title="存储管理" wide onClose={onClose}>
    {error && <Notice error>{error}</Notice>}
    <h3>已登记文件占用</h3>
    <InfoTip>去重总量按已登记物理对象计算，不含文件系统开销或未登记文件。当前、历史和外部副本是交叉分类，不能直接相加。</InfoTip>
    {!usage?<p role="status">正在统计存储…</p>:<dl className="storage-accounting">
      <dt>原件总量（去重）</dt><dd>{formatSize(usage.physical_original_bytes)}</dd>
      <dt>解析与阅读缓存（去重）</dt><dd>{formatSize(usage.physical_derived_bytes)}</dd>
      <dt>当前版本原件</dt><dd>{formatSize(usage.current_original_bytes)}</dd>
      <dt>历史版本原件</dt><dd>{formatSize(usage.historical_original_bytes)}</dd>
      <dt>外部文件服务器副本</dt><dd>{formatSize(usage.external_snapshot_bytes)}</dd>
      <dt>可重建阅读预览</dt><dd>{formatSize(usage.reading_preview_bytes)} · {usage.reading_preview_count} 份</dd>
      <dt>尚无服务器副本的外部版本</dt><dd>{usage.external_revisions_without_snapshot}</dd>
      <dt>原件版本总数</dt><dd>{usage.original_revisions}</dd>
    </dl>}
    <button onClick={()=>{setEpoch(n=>n+1);setError('');}}>刷新存储统计</button>
    <form onSubmit={cleanup} className="storage-cleanup-form">
      <h3>清理缓存</h3>
      <label>清理范围<select value={kind} onChange={e=>{setKind(e.target.value);setConfirmed(false);intent.current=null;}}>
        <option value="reading_previews">可重建的阅读预览</option><option value="unused_objects">已无档案引用的闲置文件</option>
      </select></label>
      <InfoTip>不删除仍被引用的原件、历史版本或业务字段。预览登记清理后可按需重建，实际文件通过引用检查并至少保留24小时后回收。每次最多清理1000份阅读预览，历史版本在对应源文件窗口明确选择清理。</InfoTip>
      <label className="check-label"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>确认清理所选缓存，保留所有已登记原件版本</label>
      <button className="danger" disabled={!confirmed||busy}>{busy?'正在提交…':'开始清理'}</button>
    </form>
    {job && <TaskStatus api={api} id={job} compact onTerminal={data=>{if(data.status==='completed')setEpoch(n=>n+1);}}/>}
  </Dialog>;
}
