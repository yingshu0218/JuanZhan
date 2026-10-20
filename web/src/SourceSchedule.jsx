import { InfoTip } from "./ui.jsx";
import {useEffect,useState} from "react";
import {Notice} from "./ui.jsx";
import {message} from "./api.js";

export function SourceSchedule({api,source,onSaved}) {
  const [minutes,setMinutes]=useState(String(source.scan_interval_minutes || 0));
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[saved,setSaved]=useState(false);
  useEffect(()=>{setMinutes(String(source.scan_interval_minutes || 0));setError("");setSaved(false);},[source.id,source.scan_schedule.version]);
  async function submit(event){
    event.preventDefault();setError("");setSaved(false);
    const value=Number(minutes);
    if(!/^\d+$/.test(minutes) || !Number.isSafeInteger(value) || value>525600){setError("请输入0至525600的整分钟数；0表示关闭。");return;}
    setBusy(true);
    try {
      await api.request(`/sources/${source.id}/schedule`,{method:"PATCH",body:{expected_schedule_version:source.scan_schedule.version,scan_interval_minutes:value}});
      setSaved(true);onSaved();
    }catch(e){setError(message(e));}finally{setBusy(false);}
  }
  return <details><summary>自动扫描设置</summary>
    <form aria-label="自动扫描设置" onSubmit={submit}>
      <label>扫描间隔（分钟，0为关闭）<input type="number" min="0" max="525600" step="1" value={minutes} onChange={event=>setMinutes(event.target.value)} required /></label>
      <InfoTip>仅在首次导入完成后执行增量扫描；worker运行时生效，重启保留计划，不重复补跑错过的间隔。关闭只停止后续排队，已受理任务继续执行。</InfoTip>
      <p>下次计划：{source.scan_interval_minutes>0 && source.scan_schedule.next_run_at ? <time dateTime={source.scan_schedule.next_run_at}>{new Date(source.scan_schedule.next_run_at).toLocaleString("zh-CN")}</time> : "已关闭"}</p>
      {!source.initial_import_completed_at && <Notice>请先手动完成首次导入；自动扫描不会代替首次导入确认。</Notice>}
      <button disabled={busy}>{busy ? "正在保存…" : "保存扫描计划"}</button>
      {error && <Notice error>{error}</Notice>}{saved && <Notice>扫描计划已保存。</Notice>}
    </form>
  </details>;
}
