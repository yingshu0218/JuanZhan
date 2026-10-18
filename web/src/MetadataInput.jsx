const types = { text: "短文本", long_text: "长文本", integer: "整数", decimal: "小数", date: "日期", boolean: "是 / 否", single_select: "单选" };

export function metadataValue(field, raw) {
  if (field.type === "boolean") {
    if (!["true", "false"].includes(raw)) throw Error("请选择是或否。");
    return raw === "true";
  }
  if (field.type === "integer") {
    if (!/^-?\d+$/.test(raw) || !Number.isSafeInteger(Number(raw)))
      throw Error("请输入安全整数；超过 ±9007199254740991 的整数请通过 API 精确写入。");
    return Number(raw);
  }
  if (field.type === "decimal" && !/^-?(?:0|[1-9]\d*)(?:\.\d{1,4})?$/.test(raw))
    throw Error("小数须使用普通十进制格式，最多四位小数。");
  if (["date", "single_select"].includes(field.type) && !raw) throw Error("请填写字段值，或明确选择清空。");
  return raw;
}

export function MetadataInput({ field, value, onChange }) {
  const label = `字段值（${types[field.type]}）`;
  if (field.type === "boolean") return <label>{label}<select value={value} onChange={e => onChange(e.target.value)}>
    <option value="" disabled>请选择</option><option value="true">是</option><option value="false">否</option>
  </select></label>;
  if (field.type === "single_select") return <label>{label}<select value={value} onChange={e => onChange(e.target.value)}>
    <option value="" disabled>请选择</option>{(field.constraints.options || []).map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
  </select></label>;
  if (field.type === "long_text") return <label>{label}<textarea value={value} onChange={e => onChange(e.target.value)} maxLength={65536} /></label>;
  return <label>{label}<input type={field.type === "date" ? "date" : "text"}
    inputMode={field.type === "integer" ? "numeric" : field.type === "decimal" ? "decimal" : undefined}
    value={value} onChange={e => onChange(e.target.value)} maxLength={65536} /></label>;
}
