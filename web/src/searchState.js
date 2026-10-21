const sections = ["home", "all", "inbox", "favorite", "trash", "sources"];
const sorts = ["-imported_at", "imported_at", "title", "-document_date", "-relevance"];
export function preferredView() {
  try { return localStorage.getItem('juanzhan.library-view.v1') === 'grid' ? 'grid' : 'list'; }
  catch { return 'list'; }
}
export function rememberView(view) {
  try { localStorage.setItem('juanzhan.library-view.v1', view); } catch { /* Storage may be disabled. */ }
}
export const blankSearch = () => ({ text: "", type_ids: [], tag_ids: [], match: "any", descendants: false, source_kind: "", source_id: "", availability_status: "", processing_status: "", date_from: "", date_to: "", metadata: [] });
const string = (value, max = 1000) => typeof value === "string" && value.length <= max;
export function searchBody(search) {
  if (!search || !string(search.text, 512) || !Array.isArray(search.tag_ids) || search.tag_ids.length > 100 || !search.tag_ids.every((id) => string(id, 255)) || !["any", "all"].includes(search.match) || typeof search.descendants !== "boolean" || !Array.isArray(search.metadata) || search.metadata.length > 8) throw Error("搜索条件不符合要求，请重新填写。");
  const body = {};
  const types = search.type_ids || [];
  if (!Array.isArray(types) || types.length > 100 || !types.every((id) => string(id, 255))) throw Error("文档类型范围无效。");
  if (types.length) body.document_type_ids = types;
  if (search.text) body.text = search.text;
  if (search.tag_ids.length) body.tags = { ids: search.tag_ids, match: search.match };
  const choices = { source_kind: ["", "managed", "external"], availability_status: ["", "available", "missing", "suspected_missing", "source_offline", "unknown", "needs_match"], processing_status: ["", "not_started", "queued", "running", "completed", "failed", "unsupported", "discarded"] };
  for (const [key, values] of Object.entries(choices)) {
    if (!values.includes(search[key])) throw Error("搜索状态选项无效。");
    if (search[key]) body[key] = search[key];
  }
  if (!string(search.source_id, 255)) throw Error("来源条件无效。");
  if (search.source_id) body.source_id = search.source_id;
  for (const [key, raw] of [["document_date_from", search.date_from], ["document_date_to", search.date_to]]) {
    if (!string(raw, 10) || (raw && !/^\d{4}-\d{2}-\d{2}$/.test(raw))) throw Error("请输入有效业务日期。");
    if (raw) body[key] = raw;
  }
  if (search.date_from && search.date_to && search.date_from > search.date_to) throw Error("业务日期起点不能晚于终点。");
  if (search.metadata.length) body.metadata = search.metadata.map((row) => {
    if (!row || !string(row.key, 255) || !/^[a-z][a-z0-9_]*$/.test(row.key) || !["text", "long_text", "single_select", "integer", "decimal", "date", "boolean"].includes(row.kind) || !["eq", "in", "contains", "gte", "lte", "between", "is_null"].includes(row.operator) || !string(row.value, 2000) || !string(row.upper, 1000)) throw Error("请完成业务字段条件。");
    function scalar(value) {
      if (row.kind === "integer") {
        if (!/^-?\d+$/.test(value) || !Number.isSafeInteger(Number(value))) throw Error("整数筛选须使用安全整数（绝对值不超过9007199254740991）。");
        return Number(value);
      }
      if (row.kind === "boolean") {
        if (!["true", "false"].includes(value)) throw Error("请选择是或否。");
        return value === "true";
      }
      if (row.kind === "decimal" && !/^-?\d+(\.\d{1,4})?$/.test(value)) throw Error("金额或小数须用最多4位小数的十进制值。");
      if (row.kind === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw Error("请输入有效日期。");
      return value;
    }
    const result = { key: row.key, operator: row.operator };
    if (row.operator !== "is_null") {
      if (row.operator === "in") {
        const values = row.value.split("\n");
        if (!values.length || values.length > 100 || values.some((v) => !v.length)) throw Error("任选其一的条件须每行一个值，最多100行，不留空行。");
        result.value = values.map(scalar);
      } else result.value = row.operator === "between" ? [scalar(row.value), scalar(row.upper)] : scalar(row.value);
    }
    return result;
  });
  return body;
}
export function encodedState(state) {
  const hash = "#library=" + encodeURIComponent(JSON.stringify({ v: 1, ...state }));
  if (hash.length > 16000) throw Error("搜索条件过长，请减少条件后再保存到链接。");
  return hash;
}
export function readLocation() {
  if (!location.hash) return { state: {} };
  try {
    if (!location.hash.startsWith("#library=") || location.hash.length > 16000) throw Error();
    const value = JSON.parse(decodeURIComponent(location.hash.slice(9)));
    if (value.v !== 1 || !string(value.space, 255) || !sections.includes(value.section) || !string(value.folder, 255) || !string(value.type, 255) || !sorts.includes(value.sort) || !["grid", "list"].includes(value.view) || !Number.isInteger(value.page) || value.page < 1 || value.page > 2147483647) throw Error();
    if (value.search !== null) searchBody(value.search);
    if (value.type && value.search?.type_ids?.length) throw Error();
    if (value.sort === "-relevance" && !value.search?.text) throw Error();
    return { state: value };
  } catch { return { state: {}, error: "链接中的检索条件无效，已回到默认列表。" }; }
}
