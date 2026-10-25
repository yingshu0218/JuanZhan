import { InfoTip } from "./ui.jsx";
import {useEffect,useRef,useState} from 'react';
import {Dialog,Notice,formatDate,formatSize} from './ui.jsx';
import {message} from './api.js';
const states={queued:'排队中',running:'处理中',ready:'可用',failed:'失败',cancelled:'已取消',deleted:'已删除',unavailable:'文件不可用'};
const origins={manual:'手动',automatic:'自动',imported:'上传'};
const pending=items=>items.some(item=>['queued','running'].includes(item.status));

export function BackupManager({api,onClose}){
  const [backups,setBackups]=useState({items:[],total:0}),[recoveries,setRecoveries]=useState({items:[],total:0});
  const [page,setPage]=useState(1),[recoveryPage,setRecoveryPage]=useState(1),[refresh,setRefresh]=useState(0);
  const [plan,setPlan]=useState(null),[draft,setDraft]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
  const [file,setFile]=useState(null),[confirm,setConfirm]=useState(null),[checked,setChecked]=useState(false);
  const createId=useRef(crypto.randomUUID().replaceAll('-','')),uploadId=useRef(crypto.randomUUID().replaceAll('-',''));
  const uploadAbort=useRef(null),confirmRef=useRef(null);
  useEffect(()=>{if(confirm){confirmRef.current?.scrollIntoView({block:"nearest"});confirmRef.current?.querySelector("input")?.focus();}},[confirm]);
  useEffect(()=>()=>uploadAbort.current?.abort(),[]);
  useEffect(()=>{
    const abort=new AbortController();let timer;
    async function load(){
      try{
        const [items,restored,schedule]=await Promise.all([
          api.request(`/system/backups?page=${page}&page_size=25`,{signal:abort.signal}),
          api.request(`/system/recoveries?page=${recoveryPage}&page_size=25`,{signal:abort.signal}),
          api.request('/system/backup-schedule',{signal:abort.signal})]);
        if(abort.signal.aborted)return;
        setBackups(items);setRecoveries(restored);setPlan(schedule);setDraft(current=>current||schedule);
        if(pending(items.items)||pending(restored.items))timer=setTimeout(load,1500);
      }catch(e){if(!abort.signal.aborted)setError(message(e));}
    }
    load();return()=>{abort.abort();clearTimeout(timer);};
  },[api,page,recoveryPage,refresh]);
  async function act(callback){
    setError('');setNotice('');setBusy(true);
    try{await callback();setRefresh(value=>value+1);}catch(e){if(e.name!=='AbortError')setError(e.code?message(e):e.message);}finally{setBusy(false);}
  }
  function ask(kind,item){setConfirm({kind,item,request_id:crypto.randomUUID().replaceAll('-','')});setChecked(false);}
  return <Dialog title="备份与恢复" wide onClose={onClose}>
    <InfoTip>全实例管理。备份包含业务数据库、托管原件和派生文件；不包含外部目录原件、环境配置、模型或容器镜像。ZIP内含敏感数据库，请保存在可信位置。</InfoTip>
    {error&&<Notice error>{error}</Notice>}{notice&&<Notice>{notice}</Notice>}
    <section aria-label="创建和上传备份" className="backup-section">
      <h3>手动备份</h3>
      <button className="primary" disabled={busy||pending(backups.items)||pending(recoveries.items)} onClick={()=>act(async()=>{
        await api.request('/system/backups',{method:'POST',body:{request_id:createId.current}});createId.current=crypto.randomUUID().replaceAll('-','');setPage(1);setNotice('备份任务已受理，完成后可下载ZIP。');
      })}>创建备份</button>
      <label>上传备份ZIP<input type="file" accept=".zip,application/zip" disabled={busy} onChange={event=>{setFile(event.target.files[0]||null);uploadId.current=crypto.randomUUID().replaceAll('-','');}} /></label>
      <button disabled={busy||!file} onClick={()=>act(async()=>{
        if(file.size>8*1024**3+100002*1024)throw Error('备份ZIP超过当前传输上限。');
        const abort=new AbortController();uploadAbort.current=abort;
        try{await api.request(`/system/backups/import?request_id=${uploadId.current}`,{method:'POST',body:file,signal:abort.signal});
          uploadId.current=crypto.randomUUID().replaceAll('-','');setPage(1);setNotice('上传已受理，正在校验备份；校验完成前不可恢复。');
        }finally{uploadAbort.current=null;}
      })}>{busy&&uploadAbort.current?'正在上传…':'上传并校验'}</button>
      <InfoTip>同时最多一个备份或恢复任务。展开上限8 GiB、100000个数据成员；接收最多一小时，仍受磁盘和代理限制。关闭窗口会中止尚未完成的上传，已受理任务继续运行。</InfoTip>
    </section>
    {confirm&&<section ref={confirmRef} className="backup-confirm" aria-label={confirm.kind==='restore'?'确认恢复':'确认删除备份'}>
      <h3>{confirm.kind==='restore'?'恢复到新目录':'删除备份文件'}</h3>
      <p>备份编号：{confirm.item.id}</p>
      <p>{confirm.kind==='restore'?'将校验并生成独立恢复目录，不覆盖当前实例。旧会话与Token失效，自动备份关闭；管理员仍须按运维手册切换数据位置。':'删除此备份的ZIP文件，保留操作记录。已经恢复出的数据目录和当前实例保持不变。'}</p>
      <label className="check-label"><input type="checkbox" checked={checked} onChange={event=>setChecked(event.target.checked)} />我已了解并确认此操作</label>
      <div className="form-actions"><button disabled={busy} onClick={()=>setConfirm(null)}>取消</button><button className="primary" disabled={busy||!checked} onClick={()=>act(async()=>{
        const value=confirm;
        if(value.kind==='restore'){await api.request(`/system/backups/${value.item.id}/restore`,{method:'POST',body:{request_id:value.request_id}});setRecoveryPage(1);setNotice('恢复任务已受理，请等待新目录校验完成。');}
        else{await api.request(`/system/backups/${value.item.id}`,{method:'DELETE'});setNotice('备份文件已删除。');}
        setConfirm(null);
      })}>{confirm.kind==='restore'?'开始恢复':'确认删除'}</button></div>
    </section>}
    <section aria-label="备份记录" className="backup-section">
      <h3>备份记录</h3><button disabled={busy} onClick={()=>setRefresh(value=>value+1)}>刷新记录</button>
      <ul className="backup-list">{backups.items.map(item=><li key={item.id}>
        <strong>{origins[item.origin]} · {states[item.status]||item.status}</strong><time>{formatDate(item.created_at)}</time>
        <small>备份编号：{item.id}</small>{item.bytes!==null&&<small>{formatSize(item.bytes)} · SHA-256：{item.sha256}</small>}
        {item.error&&<Notice error>{message({code:item.error.code,status:400})}（{item.error.code}）</Notice>}
        <div className="backup-actions">
          {item.available&&<a className="button" href={`/api/v1/system/backups/${item.id}/download`}>下载ZIP</a>}
          <button disabled={busy||!item.available} onClick={()=>ask('restore',item)}>恢复此备份</button>
          <button disabled={busy||['queued','running','deleted'].includes(item.status)} onClick={()=>ask('delete',item)}>删除备份文件</button>
        </div>
      </li>)}</ul>
      {!backups.items.length&&<p>尚无备份记录。</p>}
      <Pager page={page} total={backups.total} busy={busy} change={setPage} />
    </section>
    <section aria-label="自动备份计划" className="backup-section">
      <h3>自动备份</h3>
      {draft?<form onSubmit={event=>{event.preventDefault();act(async()=>{
        const body={expected_version:draft.version,...Object.fromEntries(['interval_minutes','keep_count','max_age_days'].map(key=>[key,Number(draft[key])]))};
        if(Object.values(body).some(value=>!Number.isSafeInteger(value)))throw Error('计划配置须为有效整数。');
        const saved=await api.request('/system/backup-schedule',{method:'PATCH',body});setDraft(saved);setPlan(saved);setNotice(saved.interval_minutes?'自动备份计划已保存。':'自动备份已关闭，已受理的任务继续运行。');
      });}}>
        <label>备份间隔（分钟，0关闭）<input type="number" min="0" max="525600" required value={draft.interval_minutes} disabled={busy} onChange={event=>setDraft({...draft,interval_minutes:event.target.value})} /></label>
        <label>最多保留自动备份数<input type="number" min="1" max="100" required value={draft.keep_count} disabled={busy} onChange={event=>setDraft({...draft,keep_count:event.target.value})} /></label>
        <label>自动备份最长天数<input type="number" min="1" max="3650" required value={draft.max_age_days} disabled={busy} onChange={event=>setDraft({...draft,max_age_days:event.target.value})} /></label>
        <InfoTip>仅清理成功的自动备份，始终保留最近成功一次；手动和上传备份需手动删除。worker停止期间不运行，恢复后不补跑积压。修改保留规则在下一次成功自动备份时生效。</InfoTip>
        <p>下次计划：{plan?.next_run_at?new Date(plan.next_run_at).toLocaleString():'未启用'}</p>
        <div className="form-actions"><button type="button" disabled={busy||!plan} onClick={()=>act(async()=>{const latest=await api.request('/system/backup-schedule');setPlan(latest);setDraft(latest);setNotice('已重新读取服务器计划。');})}>重载计划</button><button className="primary" disabled={busy}>保存备份计划</button></div>
      </form>:<p>正在读取计划…</p>}
    </section>
    <section aria-label="恢复记录" className="backup-section">
      <h3>恢复记录</h3>
      <ul className="backup-list">{recoveries.items.map(item=><li key={item.id}><strong>{states[item.status]||item.status}</strong><small>恢复编号：{item.id}</small><small>来源备份：{item.backup_id}</small>
        {item.status==='ready'&&<p>新目录已验证，尚未切换当前实例。请由管理员使用恢复编号按运维手册激活；外部原件需单独恢复挂载。</p>}
        {item.error&&<Notice error>{message({code:item.error.code,status:400})}（{item.error.code}）</Notice>}
      </li>)}</ul>
      {!recoveries.items.length&&<p>尚无恢复记录。</p>}<Pager page={recoveryPage} total={recoveries.total} busy={busy} change={setRecoveryPage} />
    </section>
    <InfoTip>后台任务详情和有限重试可在任务中心查看。恢复目录与历史测试文件的清理步骤见运维手册。</InfoTip>
  </Dialog>;
}
function Pager({page,total,busy,change}){return <div className="task-pages"><button disabled={busy||page===1} onClick={()=>change(page-1)}>上一页</button><span>第{page}页 · 共{total}条</span><button disabled={busy||page*25>=total} onClick={()=>change(page+1)}>下一页</button></div>;}
