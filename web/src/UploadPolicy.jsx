import {useEffect,useState} from 'react';
import {Dialog,Notice,InfoTip} from './ui.jsx';
import {message} from './api.js';
export function UploadPolicy({api,onClose}){
 const [policy,setPolicy]=useState(null),[extensions,setExtensions]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[saved,setSaved]=useState(false);
 useEffect(()=>{const controller=new AbortController();api.request('/system/upload-policy',{signal:controller.signal}).then(data=>{setPolicy(data);setExtensions(data.custom_extensions.join('\n'));}).catch(e=>{if(e.name!=='AbortError')setError(message(e));});return()=>controller.abort();},[api]);
 async function save(event){event.preventDefault();setBusy(true);setError('');setSaved(false);try{const custom=[...new Set(extensions.split(/[\s,，;；]+/).map(v=>v.replace(/^\./,'').toLowerCase()).filter(Boolean))];const result=await api.request('/system/upload-policy',{method:'PUT',body:{expected_version:policy.version,excluded_groups:policy.excluded_groups,custom_extensions:custom}});setPolicy(result);setSaved(true);}catch(e){setError(message(e));}finally{setBusy(false);}}
 return <Dialog title="上传格式规则" onClose={onClose}><form onSubmit={save}>
 <InfoTip>勾选表示排除。规则全站生效，网页、拖放和Agent上传都会校验；不删除已有档案。系统辅助文件与版本控制元数据始终排除。普通文档、表格、演示、图片、Markdown/HTML/TXT、CSV默认保留。未知或无扩展名文件不按格式猜测，仍保留；此规则不是安全扫描。</InfoTip>
 {error&&<Notice error>{error}</Notice>}{saved&&<Notice>上传规则已保存，对之后的上传生效。</Notice>}
 {policy?<><fieldset disabled={busy}><legend>默认排除的格式与目录</legend>{policy.groups.map(group=><div key={group.id}><label className="check-label"><input type="checkbox" checked={policy.excluded_groups.includes(group.id)} onChange={e=>{setSaved(false);setPolicy(old=>({...old,excluded_groups:e.target.checked?[...old.excluded_groups,group.id]:old.excluded_groups.filter(id=>id!==group.id)}));}}/>{group.label}</label><small className="muted">{[...(group.extensions||[]).map(v=>'.'+v),...(group.files||[]),...(group.directories||[]).map(v=>v+'/')].join(' · ')}</small></div>)}</fieldset>
 <label>额外排除的扩展名<textarea rows={4} maxLength={2100} placeholder="每行一个，例如 psd" value={extensions} onChange={e=>{setExtensions(e.target.value);setSaved(false);}}/></label><button className="primary" disabled={busy} type="submit">保存上传规则</button></>:<p role="status">正在读取上传规则…</p>}
 </form></Dialog>;
}
