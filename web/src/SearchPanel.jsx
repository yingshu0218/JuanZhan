import { InfoTip } from "./ui.jsx";
import { useState } from "react";
import { blankSearch, searchBody } from "./searchState.js";
import { Notice } from "./ui.jsx";
const names = { eq: "等于", in: "任选其一", contains: "包含文字", gte: "大于等于", lte: "小于等于", between: "闭区间", is_null: "未填写" };
function operators(kind) { return ["eq", ...(["boolean", "single_select"].includes(kind) ? [] : ["in"]), ...(["text", "long_text"].includes(kind) ? ["contains"] : []), ...(["integer", "decimal", "date"].includes(kind) ? ["gte", "lte", "between"] : []), "is_null"]; }
export function SearchPanel({ applied, catalog, onApply, onClear }) {
  const [draft, setDraft] = useState(() => applied || blankSearch());
  const [error, setError] = useState("");
  function set(key, value) { setDraft((old) => ({ ...old, [key]: value })); }
  function row(index, change) { setDraft((old) => ({ ...old, metadata: old.metadata.map((item, i) => i === index ? { ...item, ...change } : item) })); }
  function submit(event) {
    event.preventDefault(); setError("");
    try { searchBody(draft); onApply(draft); } catch (e) { setError(e.message); }
  }
  const fields = catalog.definitions.filter((field) => field.is_active && field.filterable);
  return <form className="search-panel" role="search" aria-label="档案检索" noValidate onSubmit={submit}>
    <label className="sr-only" htmlFor="archive-search">搜索正文、标题和字段</label>
    <div className="search-input-row"><input id="archive-search" type="search" maxLength={512} placeholder="搜索正文、标题和字段" value={draft.text} onChange={(e) => set("text", e.target.value)} /><button className="primary" type="submit">搜索</button></div>
    {error ? <Notice error>{error}</Notice> : null}
    <details><summary>组合过滤{applied ? " · 已应用检索" : ""}</summary>
      <label className="check-label"><input type="checkbox" checked={draft.descendants} onChange={(e) => set("descendants", e.target.checked)} />所选目录包含后代目录</label>
      <label>来源方式<select value={draft.source_kind} onChange={(e) => set("source_kind", e.target.value)}><option value="">全部方式</option><option value="managed">托管原件</option><option value="external">只读来源</option></select></label>
      <label>指定来源<select value={draft.source_id} onChange={(e) => set("source_id", e.target.value)}><option value="">全部来源</option>{(catalog.sources || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <div className="search-dates"><label>业务日期起<input type="date" value={draft.date_from} onChange={(e) => set("date_from", e.target.value)} /></label><label>业务日期止<input type="date" value={draft.date_to} onChange={(e) => set("date_to", e.target.value)} /></label></div>
      <label>原件可用性<select value={draft.availability_status} onChange={(e) => set("availability_status", e.target.value)}><option value="">不限</option><option value="available">原件可用</option><option value="source_offline">来源离线</option><option value="missing">已确认失联</option><option value="suspected_missing">待确认失联</option><option value="unknown">待核验</option><option value="needs_match">待匹配</option></select></label>
      <label>处理状态<select value={draft.processing_status} onChange={(e) => set("processing_status", e.target.value)}><option value="">不限</option><option value="not_started">尚未处理</option><option value="queued">等待处理</option><option value="running">正在处理</option><option value="completed">处理完成</option><option value="failed">处理失败</option><option value="unsupported">暂不支持</option></select></label>
      <fieldset><legend>高级类型范围（任选其一）</legend>{catalog.types.map((item) => <label className="check-label" key={item.id}><input type="checkbox" checked={(draft.type_ids || []).includes(item.id)} onChange={(e) => set("type_ids", e.target.checked ? [...(draft.type_ids || []), item.id] : (draft.type_ids || []).filter((id) => id !== item.id))} />{item.label}</label>)}</fieldset>
      <fieldset><legend>标签</legend><label>标签匹配<select value={draft.match} onChange={(e) => set("match", e.target.value)}><option value="any">任意一个</option><option value="all">同时包含全部</option></select></label>
        {catalog.tags.map((tag) => <label className="check-label" key={tag.id}><input type="checkbox" checked={draft.tag_ids.includes(tag.id)} onChange={(e) => set("tag_ids", e.target.checked ? [...draft.tag_ids, tag.id] : draft.tag_ids.filter((id) => id !== tag.id))} />{tag.name}</label>)}
        {!catalog.tags.length ? <p className="muted">此空间暂无标签。</p> : null}
      </fieldset>
      <fieldset><legend>业务字段（所有条件同时满足）</legend>
        {draft.metadata.map((condition, index) => {
          const field = fields.find((item) => item.key === condition.key);
          return <div className="search-condition" key={index}>
            <label>筛选字段 {index + 1}<select required value={condition.key} onChange={(e) => { const field = fields.find((item) => item.key === e.target.value); row(index, { key: field?.key || "", kind: field?.type || "text", operator: "eq", value: "", upper: "" }); }}><option value="">请选择字段</option>{fields.map((item) => <option key={item.id} value={item.key}>{item.label}</option>)}</select></label>
            {!field && condition.key ? <p role="alert">此字段已不可筛选，请移除此条件。</p> : null}
            <label>比较方式 {index + 1}<select value={condition.operator} onChange={(e) => row(index, { operator: e.target.value, value: "", upper: "" })}>{operators(condition.kind).map((op) => <option key={op} value={op}>{names[op]}</option>)}</select></label>
            {condition.operator === "is_null" ? null : <label>筛选值 {index + 1}{condition.operator === "in" ? <textarea maxLength={2000} placeholder="每行一个值" value={condition.value} onChange={(e) => row(index, { value: e.target.value })} /> : condition.kind === "boolean" ? <select required value={condition.value} onChange={(e) => row(index, { value: e.target.value })}><option value="">请选择</option><option value="true">是</option><option value="false">否</option></select> : condition.kind === "single_select" ? <select required value={condition.value} onChange={(e) => row(index, { value: e.target.value })}><option value="">请选择选项</option>{field?.constraints?.options?.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select> : <input type={condition.kind === "date" ? "date" : "text"} inputMode={["integer", "decimal"].includes(condition.kind) ? "decimal" : "text"} maxLength={1000} value={condition.value} onChange={(e) => row(index, { value: e.target.value })} />}</label>}
            {condition.operator === "between" ? <label>范围上限 {index + 1}<input type={condition.kind === "date" ? "date" : "text"} maxLength={1000} value={condition.upper} onChange={(e) => row(index, { upper: e.target.value })} /></label> : null}
            <button type="button" onClick={() => set("metadata", draft.metadata.filter((_, i) => i !== index))}>移除条件 {index + 1}</button>
          </div>;
        })}
        <button type="button" disabled={!fields.length || draft.metadata.length >= 8} onClick={() => set("metadata", [...draft.metadata, { key: "", kind: "text", operator: "eq", value: "", upper: "" }])}>添加字段条件</button>
        {!fields.length ? <p className="muted">尚无启用且可筛选的业务字段。</p> : null}
      </fieldset>
      <InfoTip>提交后与当前空间、目录、类型及导航范围一起检索。</InfoTip>
    </details>
    {applied ? <button type="button" onClick={onClear}>清除搜索</button> : null}
  </form>;
}
