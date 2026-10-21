import { useEffect, useState } from 'react';
import { Dialog, InfoTip, Notice } from './ui.jsx';
import { message } from './api.js';

export function AgentManager({ api, spaces, onClose }) {
  const [items,setItems]=useState([]),[selected,setSelected]=useState([]),[name,setName]=useState(''),[days,setDays]=useState(7);
  const [clients,setClients]=useState([]);
  const [secret,setSecret]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
  const endpoint=location.origin+'/api/v1/agent/mcp';
  async function reload() { const data=await api.request('/agent-tokens');setItems(data); }
  useEffect(()=>{let active=true;api.request('/agent-tokens').then(data=>{if(active)setItems(data);}).catch(e=>{if(active)setError(message(e));}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[api]);
  useEffect(()=>{let active=true;api.request('/oauth/clients').then(data=>{if(active)setClients(data);}).catch(e=>{if(active)setError(message(e));});return()=>{active=false;};},[api]);
  async function removeClient(id) {
    setBusy(true);setError('');
    try { await api.request('/oauth/clients/'+id,{method:'DELETE'});setClients(values=>values.filter(item=>item.id!==id));await reload(); }
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  async function create(event) {
    event.preventDefault();setBusy(true);setError('');setSecret(null);
    try { const data=await api.request('/agent-tokens',{method:'POST',body:{name,space_ids:selected,expires_in_days:Number(days)}});setSecret(data);setName('');await reload(); }
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  async function revoke(id) {
    setBusy(true);setError('');
    try { await api.request('/agent-tokens/'+id,{method:'DELETE'});if(secret?.id===id)setSecret(null);await reload(); }
    catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <Dialog title="Agent 接入" onClose={onClose} wide>
    <InfoTip>Agent只能读取勾选空间中的档案、概要和正文，不能修改或删除。模型由外部agent提供。凭据仅显示一次，请保存在agent的私有配置中；关闭窗口后不会保留明文。</InfoTip>
    <label>MCP 地址<input readOnly value={endpoint} onFocus={event=>event.target.select()} /></label>
    <label>REST 地址<input readOnly value={location.origin+'/api/v1/agent'} onFocus={event=>event.target.select()} /></label>
    {clients.length>0 && <section><h3>OAuth 客户端</h3><InfoTip>删除客户端会撤销该客户端的全部授权。访问令牌1小时，刷新授权最长30天。</InfoTip><ul className="agent-credentials">{clients.map(client=><li key={client.id}><strong>{client.name}</strong><span style={{overflowWrap:'anywhere'}}>{client.redirect_uris.join('、')}</span><button disabled={busy} onClick={()=>removeClient(client.id)}>删除客户端 {client.name}</button></li>)}</ul></section>}
    {error && <Notice error>{error}</Notice>}
    {secret && <section className="agent-secret" aria-label="新建Agent凭据"><h3>新凭据</h3><InfoTip>仅当前窗口可见。使用Authorization: Bearer配置；不要填写到文档正文或公开链接。可以随时撤销。</InfoTip><label>Agent Token<input readOnly value={secret.token} autoComplete="off" spellCheck="false" onFocus={event=>event.target.select()} /></label><button onClick={()=>setSecret(null)}>隐藏凭据</button></section>}
    <form onSubmit={create} aria-busy={busy}>
      <h3>创建只读凭据</h3>
      <label>名称<input required maxLength={100} value={name} onChange={event=>setName(event.target.value)} /></label>
      <label>有效天数<input type="number" required min={1} max={30} value={days} onChange={event=>setDays(event.target.value)} /></label>
      <fieldset disabled={busy}><legend>允许访问的空间</legend>{spaces.map(space=><label className="check-label" key={space.id}><input type="checkbox" checked={selected.includes(space.id)} onChange={event=>setSelected(values=>event.target.checked?[...values,space.id]:values.filter(value=>value!==space.id))} />{space.name}</label>)}</fieldset>
      <button className="primary" disabled={busy || !selected.length || selected.length>50}>{busy?'正在处理…':'创建凭据'}</button>
    </form>
    <h3>有效凭据</h3>
    {loading?<p role="status">正在读取凭据…</p>:!items.length?<p>暂无凭据</p>:<ul className="agent-credentials">{items.map(item=><li key={item.id}><strong>{item.name}</strong><span>{item.space_ids.map(id=>spaces.find(space=>space.id===id)?.name||'空间不可用').join('、')}</span><time dateTime={item.expires_at}>{new Date(item.expires_at).toLocaleString('zh-CN')} 到期</time><button disabled={busy} onClick={()=>revoke(item.id)} aria-label={'撤销'+item.name}>撤销</button></li>)}</ul>}
  </Dialog>;
}
