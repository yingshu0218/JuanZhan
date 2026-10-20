import { InfoTip } from "./ui.jsx";
import {useEffect,useMemo,useState} from 'react';
import {Dialog,Notice} from './ui.jsx';
import {message} from './api.js';
import {metadataValue} from './MetadataInput.jsx';

const kinds={text:'短文本',long_text:'长文本',integer:'整数',decimal:'小数',date:'日期',boolean:'是 / 否',single_select:'单选'};
const allowed={text:['min_length','max_length','regex'],long_text:['min_length','max_length','regex'],integer:['min','max'],decimal:['min','max'],date:['min','max'],boolean:[],single_select:['options']};
function empty(){return {key:'',label:'',type:'text',constraints:{},fields:[],searchable:false,filterable:false,is_active:true};}
function constraints(field){
  const result={};
  for(const [key,value] of Object.entries(field.constraints)){
    if(value==='' || value===undefined)continue;
    if(['min_length','max_length'].includes(key)){
      const parsed=Number(value);if(!/^\d+$/.test(String(value)) || !Number.isSafeInteger(parsed) || parsed>65536)throw Error('长度范围须为0至65536的整数。');result[key]=parsed;
    }else if(['min','max'].includes(key))result[key]=metadataValue({type:field.type},String(value));
    else if(key==='options'){
      if(!value.length || value.some(option=>!option.id.trim() || !option.label.trim()))throw Error('每个单选项都须填写标识和名称。');
      if(new Set(value.map(option=>option.id)).size!==value.length)throw Error('单选项标识不能重复。');
      result.options=value;
    }else result[key]=value;
  }
  return result;
}

export function CatalogManager({api,spaceId,spaceName,onClose,onChanged}){
  const [mode,setMode]=useState('fields'),[fields,setFields]=useState([]),[types,setTypes]=useState([]),[draft,setDraft]=useState(null);
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
  const [rulesDirty,setRulesDirty]=useState(false),[templateDirty,setTemplateDirty]=useState(false),[addField,setAddField]=useState(''),[filter,setFilter]=useState('');
  const byId=useMemo(()=>new Map(fields.map(field=>[field.id,field])),[fields]);
  useEffect(()=>{
    const abort=new AbortController();
    Promise.all([api.request(`/field-definitions?space_id=${spaceId}`,{signal:abort.signal}),api.request(`/document-types?space_id=${spaceId}`,{signal:abort.signal})])
      .then(([definitions,templates])=>{if(!abort.signal.aborted){setFields(definitions);setTypes(templates);setLoading(false);}})
      .catch(e=>{if(!abort.signal.aborted){setError(message(e));setLoading(false);}});
    return ()=>abort.abort();
  },[api,spaceId]);
  function edit(value){setDraft(value ? {...value,constraints:structuredClone(value.constraints||{}),fields:structuredClone(value.fields||[])} : empty());setRulesDirty(false);setTemplateDirty(false);setAddField('');setError('');setNotice('');}
  function update(values){setDraft(current=>({...current,...values}));}
  function rule(key,value){setRulesDirty(true);update({constraints:{...draft.constraints,[key]:value}});}
  const unsupported=draft && mode==='fields' && Object.keys(draft.constraints).some(key=>!allowed[draft.type].includes(key));
  const unsafe=draft?.type==='integer' && ['min','max'].some(key=>typeof draft.constraints[key]==='number' && !Number.isSafeInteger(draft.constraints[key]));
  async function save(event){
    event.preventDefault();setError('');setNotice('');
    try{
      const body={label:draft.label};
      if(draft.id)body.is_active=draft.is_active;else Object.assign(body,{space_id:spaceId,key:draft.key});
      if(mode==='fields'){
        Object.assign(body,{searchable:draft.searchable,filterable:draft.filterable});
        if(!draft.id)body.type=draft.type;
        if(!draft.id || rulesDirty)body.constraints=constraints(draft);
      }else if(!draft.id || templateDirty)body.fields=draft.fields.map((field,index)=>({...field,display_order:index}));
      setBusy(true);
      const path=mode==='fields'?'/field-definitions':'/document-types';
      const result=await api.request(path+(draft.id?'/'+draft.id:''),{method:draft.id?'PATCH':'POST',body});
      const setter=mode==='fields'?setFields:setTypes;setter(current=>[...current.filter(item=>item.id!==result.id),result].sort((a,b)=>a.key.localeCompare(b.key)));
      setDraft(null);setNotice('已保存，现有业务字段值保持原样。');onChanged();
    }catch(e){setError(e.code ? message(e) : e.message);}finally{setBusy(false);}
  }
  function move(index,delta){const next=[...draft.fields];const [value]=next.splice(index,1);next.splice(index+delta,0,value);update({fields:next});setTemplateDirty(true);}
  const rows=(mode==='fields'?fields:types).filter(item=>(item.label+' '+item.key).toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
  const selected=new Set(draft?.fields?.map(field=>field.field_definition_id)||[]);
  return <Dialog title="字段与类型管理" wide onClose={onClose}>
    <p>当前空间：{spaceName}</p>
    <div className="catalog-tabs" role="group" aria-label="管理类别">
      <button disabled={busy} aria-pressed={mode==='fields'} onClick={()=>{setMode('fields');setDraft(null);setFilter('');setError('');}}>业务字段</button>
      <button disabled={busy} aria-pressed={mode==='types'} onClick={()=>{setMode('types');setDraft(null);setFilter('');setError('');}}>文档类型与模板</button>
    </div>
    {error && <Notice error>{error}</Notice>}{notice && <Notice>{notice}</Notice>}
    {loading ? <p>正在读取配置…</p> : draft ? <form className="catalog-editor" aria-busy={busy} inert={busy ? true : undefined} onSubmit={save}>
      <h3>{draft.id?'编辑':'新增'}{mode==='fields'?'业务字段':'文档类型'}</h3>
      <label>{mode==='fields'?'字段名称':'类型名称'}<input value={draft.label} maxLength={255} required onChange={event=>update({label:event.target.value})} /></label>
      <label>{mode==='fields'?'字段标识':'类型标识'}<input value={draft.key} pattern="[a-z][a-z0-9_]*" maxLength={255} required disabled={!!draft.id} onChange={event=>update({key:event.target.value})} /></label>
      <InfoTip>标识以小写字母开头，可含数字和下划线；创建后固定。</InfoTip>
      {mode==='fields' ? <>
        <label>字段类型<select value={draft.type} disabled={!!draft.id} onChange={event=>{update({type:event.target.value,constraints:event.target.value==='single_select'?{options:[{id:'',label:''}]}:{}});setRulesDirty(true);}}>{Object.entries(kinds).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label>
        <label className="check-label"><input type="checkbox" checked={draft.searchable} onChange={event=>update({searchable:event.target.checked})} />允许文字检索</label>
        <label className="check-label"><input type="checkbox" checked={draft.filterable} onChange={event=>update({filterable:event.target.checked})} />允许条件筛选</label>
        <fieldset disabled={unsupported || unsafe}><legend>字段规则（可选）</legend>
          {['text','long_text'].includes(draft.type) && <>
            <label>最短长度<input type="number" min="0" max="65536" value={draft.constraints.min_length??''} onChange={event=>rule('min_length',event.target.value)} /></label>
            <label>最长长度<input type="number" min="0" max="65536" value={draft.constraints.max_length??''} onChange={event=>rule('max_length',event.target.value)} /></label>
            <label>匹配表达式<input maxLength={512} value={draft.constraints.regex||''} onChange={event=>rule('regex',event.target.value)} /></label>
          </>}
          {['integer','decimal','date'].includes(draft.type) && !unsafe && <>
            <label>最小值<input type={draft.type==='date'?'date':'text'} value={draft.constraints.min??''} onChange={event=>rule('min',event.target.value)} /></label>
            <label>最大值<input type={draft.type==='date'?'date':'text'} value={draft.constraints.max??''} onChange={event=>rule('max',event.target.value)} /></label>
            {draft.type==='decimal' && <InfoTip>小数最多四位，按原文本精确提交。</InfoTip>}
          </>}
          {draft.type==='boolean' && <InfoTip>是 / 否字段无需额外规则。</InfoTip>}
          {draft.type==='single_select' && <>
            <InfoTip>选项标识须唯一且稳定；更改标识或移除选项会影响已有值的有效性。</InfoTip>
            {(draft.constraints.options||[]).map((option,index)=><div className="catalog-option" key={index}>
              <label>选项标识 {index+1}<input value={option.id} maxLength={255} required onChange={event=>rule('options',draft.constraints.options.map((item,i)=>i===index?{...item,id:event.target.value}:item))} /></label>
              <label>选项名称 {index+1}<input value={option.label} maxLength={255} required onChange={event=>rule('options',draft.constraints.options.map((item,i)=>i===index?{...item,label:event.target.value}:item))} /></label>
              <button type="button" aria-label={`移除选项 ${index+1}`} onClick={()=>rule('options',draft.constraints.options.filter((_,i)=>i!==index))}>移除</button>
            </div>)}
            <button type="button" disabled={(draft.constraints.options||[]).length>=1000} onClick={()=>rule('options',[...(draft.constraints.options||[]),{id:'',label:''}])}>添加单选项</button>
          </>}
        </fieldset>
        {(unsupported||unsafe) && <Notice>此字段含旧版未知规则或超出浏览器精度的整数边界。可修改名称/状态，原规则保持；请通过API精确核对和修复规则。</Notice>}
      </> : <>
        <fieldset><legend>类型字段模板</legend>
          <label>添加模板字段<select value={addField} onChange={event=>setAddField(event.target.value)}><option value="">请选择</option>{fields.filter(field=>field.is_active&&!selected.has(field.id)).map(field=><option key={field.id} value={field.id}>{field.label} · {kinds[field.type]}</option>)}</select></label>
          <button type="button" disabled={!addField || draft.fields.length>=1000} onClick={()=>{update({fields:[...draft.fields,{field_definition_id:addField,required_for_filing:false,display_order:draft.fields.length}]});setTemplateDirty(true);setAddField('');}}>加入模板</button>
          <ol className="catalog-template">{draft.fields.map((field,index)=><li key={field.field_definition_id}>
            <strong>{byId.get(field.field_definition_id)?.label||'字段已不可用'}{byId.get(field.field_definition_id)?.is_active===false?'（已停用）':''}</strong>
            <label className="check-label"><input type="checkbox" checked={field.required_for_filing} onChange={event=>{update({fields:draft.fields.map((item,i)=>i===index?{...item,required_for_filing:event.target.checked}:item)});setTemplateDirty(true);}} />归档时必填</label>
            <button type="button" disabled={index===0} aria-label={`上移字段 ${index+1}`} onClick={()=>move(index,-1)}>上移</button>
            <button type="button" disabled={index===draft.fields.length-1} aria-label={`下移字段 ${index+1}`} onClick={()=>move(index,1)}>下移</button>
            <button type="button" aria-label={`移除模板字段 ${index+1}`} onClick={()=>{update({fields:draft.fields.filter((_,i)=>i!==index)});setTemplateDirty(true);}}>移除</button>
          </li>)}</ol>
        </fieldset>
        <InfoTip>模板指定显示顺序和归档必填项；不会自动覆盖已有档案值。</InfoTip>
      </>}
      {draft.id && <label className="check-label"><input type="checkbox" checked={draft.is_active} onChange={event=>update({is_active:event.target.checked})} />启用此{mode==='fields'?'字段':'类型'}</label>}
      <InfoTip>停用保留历史引用；更改规则不会自动重写业务字段。</InfoTip>
      <div className="form-actions"><button type="button" disabled={busy} onClick={()=>setDraft(null)}>取消编辑</button><button className="primary" disabled={busy}>保存{mode==='fields'?'字段':'类型'}</button></div>
    </form> : <>
      <label>查找配置<input value={filter} onChange={event=>setFilter(event.target.value)} /></label>
      <button className="primary" onClick={()=>edit(null)}>新增{mode==='fields'?'业务字段':'文档类型'}</button>
      <ul className="catalog-list">{rows.map(row=><li key={row.id}><div><strong>{row.label}</strong><small>{row.key} · {mode==='fields'?kinds[row.type]:`${row.fields.length}个模板字段`} · {row.is_active?'启用':'停用'}</small></div><button onClick={()=>edit(row)} aria-label={`编辑${row.label}`}>编辑</button></li>)}</ul>
      {!rows.length && <p>暂无符合条件的配置。</p>}
    </>}
  </Dialog>;
}
