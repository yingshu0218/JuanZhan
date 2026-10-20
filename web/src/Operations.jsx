import { InfoTip } from "./ui.jsx";
import { useEffect, useRef, useState } from "react";
import { Dialog, Notice } from "./ui.jsx";
import { message } from "./api.js";
import { TaskStatus } from "./Tasks.jsx";
import { MetadataInput, metadataValue } from "./MetadataInput.jsx";
const labels = {
  move_folder: "移动目录",
  add_tags: "添加标签",
  remove_tags: "移除标签",
  set_type: "设置文档类型",
  set_triage: "设置整理状态",
  set_favorite: "设置收藏",
  trash: "加入回收站",
  restore: "恢复档案",
  reprocess: "重新解析 / OCR",
  set_metadata: "设置业务字段",
};
const reasons = {
  VERSION_CONFLICT: "档案已被更新，本项未修改，请刷新后重新选择。",
  MISSING_REQUIRED_FIELDS: "缺少归档必填字段，请补齐业务字段。",
  INVALID_METADATA_VALUE: "业务字段不符合当前规则。",
  FIELD_RULES_NOT_IMPLEMENTED: "字段含未知规则，需要先修复字段配置。",
  INACTIVE_FIELD: "字段已停用。",
  INACTIVE_DOCUMENT_TYPE: "文档类型已停用。",
  DOCUMENT_TRASHED: "档案已在回收站，请先恢复。",
  CROSS_SPACE_REFERENCE: "目标不属于原空间。",
  NOT_FOUND: "档案或目标已不存在。",
  PARSE_ALREADY_RUNNING: "当前原件已有解析任务，请在任务中心查看。",
  ALREADY_PARSED: "当前原件已有成功正文；确认重新处理后再提交。",
  REVISION_CONFLICT: "原件版本已变化，请刷新后重新选择。",
  UNKNOWN_FIELD: "业务字段不属于当前空间或已不可用。",
  BATCH_METADATA_SNAPSHOT_LIMIT: "所选字段的撤销快照过大，请减少本次修改的字段。",
  INTEGRITY_CONFLICT: "引用或审计冲突，本项已回滚。",
};
export function useOperations(api, onChanged) {
  const [draft, setDraft] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const delivered = useRef(new Set());
  const [tracking, setTracking] = useState(null);
  const changed = useRef(onChanged);
  changed.current = onChanged;
  const pending =
    busy || Boolean(receipt && ["queued", "running"].includes(receipt.status));
  function prepare(items, context, operation = "move_folder", payload = null) {
    if (pending) {
      setOpen(true);
      return;
    }
    setError("");
    setTracking(null);
    setDraft({
      items: items.map((item) => ({ ...item })),
      ...context,
      operation,
      payload,
    });
    setOpen(true);
  }
  useEffect(() => {
    if (!receipt) return;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const job = await api.request("/jobs/" + receipt.job_id, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setError("");
        setReceipt((current) =>
          current?.job_id === job.id ? { ...current, ...job } : current,
        );
        if (["queued", "running"].includes(job.status))
          timer = setTimeout(poll, 800);
        else if (!delivered.current.has(job.id)) {
          delivered.current.add(job.id);
          changed.current();
        }
      } catch (e) {
        if (e.name !== "AbortError" && !controller.signal.aborted) {
          setError("暂时无法读取操作进度，恢复连接后将继续核对。");
          timer = setTimeout(poll, 2000);
        }
      }
    }
    poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [api, receipt?.job_id]);
  async function submit(operation, payload) {
    setBusy(true);
    setError("");
    try {
      const job = await api.request("/documents/batch", {
        method: "POST",
        body: {
          space_id: draft.spaceId,
          selection_mode: draft.mode || "explicit",
          document_ids: draft.items.map((i) => i.id),
          expected_versions: Object.fromEntries(
            draft.items.map((i) => [i.id, i.document_version]),
          ),
          operation,
          payload,
        },
      });
      setReceipt({ ...draft, ...job, operation, isUndo: false });
      setDraft(null);
      changed.current(false);
    } catch (e) {
      setError(
        e.status === 0
          ? "提交结果尚未确认，请核对档案后再决定是否重新提交。"
          : message(e),
      );
    } finally {
      setBusy(false);
    }
  }
  async function undo() {
    setBusy(true);
    setError("");
    try {
      const job = await api.request("/jobs/" + receipt.job_id + "/undo", {
        method: "POST",
      });
      setReceipt({
        ...receipt,
        ...job,
        status: job.status,
        isUndo: true,
        result: null,
        items: receipt.items.filter((i) =>
          receipt.result.items.some(
            (row) => row.document_id === i.id && row.status === "succeeded",
          ),
        ),
      });
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  function close() {
    setOpen(false);
    if (!busy) setDraft(null);
  }
  return {
    api,
    close,
    draft,
    receipt,
    open,
    setOpen,
    prepare,
    submit,
    undo,
    busy,
    pending,
    error,
    tracking,
    setTracking,
  };
}

export function Operations({ state, catalog }) {
  if (!state.open) return null;
  return (
    <Dialog
      title={
        state.draft
          ? "档案操作"
          : state.receipt?.isUndo
            ? "撤销结果"
            : "操作结果"
      }
      onClose={() => state.close()}
      wide
    >
      <p className="muted">
        {state.draft?.spaceName || state.receipt?.spaceName} · 已固定{" "}
        {state.draft?.items.length ?? state.receipt?.items.length} 份档案
      </p>
      {state.error ? <Notice error>{state.error}</Notice> : null}
      {state.draft ? (
        <OperationForm
          key={
            state.draft.items.map((i) => i.id).join(",") + state.draft.operation
          }
          draft={state.draft}
          catalog={state.draft.catalog || catalog}
          submit={state.submit}
          busy={state.busy}
        />
      ) : (
        <>
          <p role="status">
            {state.receipt?.status === "queued"
              ? "操作已排队，可以收起窗口继续浏览。"
              : state.receipt?.status === "running"
                ? "正在逐项处理…"
                : state.receipt?.status === "completed"
                  ? "逐项处理已结束。"
                  : "任务未完成，请核对档案后再操作。"}
          </p>
          {state.receipt?.operation === "reprocess" && <Notice>成功表示已排入解析队列，不代表正文已更新。请查看每份档案的解析任务；此操作不能撤销。</Notice>}
          {state.receipt?.result ? (
            <>
              <div className="result-counts">
                成功 {state.receipt.result.succeeded} · 无变化{" "}
                {state.receipt.result.skipped} · 失败{" "}
                {state.receipt.result.failed}
              </div>
              <ul className="operation-results">
                {state.receipt.result.items.map((row) => (
                  <li key={row.document_id}>
                    <strong>
                      {state.receipt.items.find((i) => i.id === row.document_id)
                        ?.title || "档案"}
                    </strong>
                    <span>
                      {row.status === "succeeded"
                        ? "成功"
                        : row.status === "skipped"
                          ? "无变化"
                          : "失败"}
                    </span>
                    {row.parse_job_id && <button onClick={() => state.setTracking(row.parse_job_id)}>查看解析任务</button>}
                    {row.status === "failed" ? (
                      <p>
                        {reasons[row.error_code] ||
                          "本项未完成，请刷新后核对。"}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
              {state.tracking && <TaskStatus key={state.tracking} api={state.api} id={state.tracking} />}
              {!state.receipt.isUndo && state.receipt.operation !== "reprocess" && state.receipt.result.succeeded > 0 ? (
                <button
                  className="primary"
                  disabled={state.busy}
                  onClick={state.undo}
                >
                  撤销本次成功变更
                </button>
              ) : null}
            </>
          ) : null}
        </>
      )}
    </Dialog>
  );
}
function OperationForm({ draft, catalog, submit, busy }) {
  const [operation, setOperation] = useState(draft.operation);
  const [target, setTarget] = useState(
    draft.payload && Object.hasOwn(draft.payload, "folder_id")
      ? (draft.payload.folder_id ?? "")
      : (draft.payload?.document_type_id ?? "__choose__"),
  );
  const [tags, setTags] = useState(draft.payload?.tag_ids || []);
  const [triage, setTriage] = useState(draft.payload?.triage_status || "filed");
  const [favorite, setFavorite] = useState(
    draft.payload?.is_favorite === false ? "false" : "true",
  );
  const [ocr, setOcr] = useState(false);
  const [language, setLanguage] = useState("eng,chi_sim");
  const [confirmed, setConfirmed] = useState(false);
  const [fieldId, setFieldId] = useState("");
  const [fieldAction, setFieldAction] = useState("set");
  const [rawValue, setRawValue] = useState("");
  const [formError, setFormError] = useState("");
  const fields = catalog.definitions.filter(field => field.is_active);
  const field = fields.find(item => item.id === fieldId);
  const trashed = draft.items.every((i) => i.deleted_at);
  const options = trashed
    ? ["restore"]
    : Object.keys(labels).filter((key) => key !== "restore");
  function save(e) {
    e.preventDefault();
    setFormError("");
    let payload = {};
    if (operation === "move_folder") payload = { folder_id: target || null };
    if (operation === "set_type")
      payload = { document_type_id: target || null };
    if (["add_tags", "remove_tags"].includes(operation))
      payload = { tag_ids: tags };
    if (operation === "set_triage") payload = { triage_status: triage };
    if (operation === "set_favorite")
      payload = { is_favorite: favorite === "true" };
    if (operation === "reprocess") payload = {
      force: true, ocr, ocr_languages: ocr ? language : "", generate_preview: true,
    };
    if (operation === "set_metadata") {
      if (!field || !confirmed) return;
      try { payload = { values: { [field.key]: fieldAction === "clear" ? null : metadataValue(field, rawValue) }, confirm: true }; }
      catch (error) { setFormError(error.message); return; }
    }
    submit(operation, payload);
  }
  return (
    <form onSubmit={save}>
      <label>
        操作类型
        <select
          value={operation}
          onChange={(e) => {
            setOperation(e.target.value);
            setTarget("__choose__");
            setTags([]);
            setConfirmed(false);
            setFormError("");
          }}
        >
          {options.map((key) => (
            <option key={key} value={key}>
              {labels[key]}
            </option>
          ))}
        </select>
      </label>
      {operation === "move_folder" ? (
        <label>
          目标目录
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="__choose__" disabled>
              请选择目标
            </option>
            <option value="">未分类</option>
            {catalog.folders.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {operation === "set_type" ? (
        <label>
          文档类型
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="__choose__" disabled>
              请选择目标
            </option>
            <option value="">未分类</option>
            {catalog.types
              .filter((t) => t.is_active)
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
          </select>
        </label>
      ) : null}
      {["add_tags", "remove_tags"].includes(operation) ? (
        <fieldset>
          <legend>选择标签（只增删所选标签）</legend>
          {catalog.tags.length ? (
            catalog.tags.map((t) => (
              <label className="check-label" key={t.id}>
                <input
                  type="checkbox"
                  checked={tags.includes(t.id)}
                  onChange={(e) =>
                    setTags((current) =>
                      e.target.checked
                        ? [...current, t.id]
                        : current.filter((id) => id !== t.id),
                    )
                  }
                />
                {t.name}
              </label>
            ))
          ) : (
            <p className="muted">请先在左侧新建标签。</p>
          )}
        </fieldset>
      ) : null}
      {operation === "set_triage" ? (
        <label>
          整理状态
          <select value={triage} onChange={(e) => setTriage(e.target.value)}>
            <option value="filed">已整理</option>
            <option value="needs_review">待整理</option>
          </select>
        </label>
      ) : null}
      {operation === "set_favorite" ? (
        <label>
          收藏状态
          <select
            value={favorite}
            onChange={(e) => setFavorite(e.target.value)}
          >
            <option value="true">加入收藏</option>
            <option value="false">取消收藏</option>
          </select>
        </label>
      ) : null}
      {operation === "set_metadata" && <fieldset disabled={busy}>
        <legend>仅修改选定的业务字段</legend>
        <label>业务字段<select value={fieldId} onChange={e => { setFieldId(e.target.value); setRawValue(""); setConfirmed(false); setFormError(""); }}>
          <option value="" disabled>请选择字段</option>{fields.map(item => <option key={item.id} value={item.id}>{item.label} · {item.type}</option>)}
        </select></label>
        {!fields.length && <p className="muted">当前空间没有可编辑字段，请先创建字段定义。</p>}
        {field && <>
          <label>字段操作<select value={fieldAction} onChange={e => { setFieldAction(e.target.value); setConfirmed(false); setFormError(""); }}>
            <option value="set">设置值</option><option value="clear">清空此字段</option>
          </select></label>
          {fieldAction === "set" && <MetadataInput field={field} value={rawValue} onChange={setRawValue} />}
          <label className="check-label"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />确认对所选档案{fieldAction === "clear" ? "清空" : "设置"}此字段</label>
          <InfoTip>其他业务字段保持原值。每份档案独立校验版本与归档规则；成功项可撤销，后续编辑冲突时不会覆盖。</InfoTip>
        </>}
      </fieldset>}
      {formError && <Notice error>{formError}</Notice>}
      {operation === "reprocess" && <fieldset disabled={busy}>
        <legend>解析选项</legend>
        <label className="check-label"><input type="checkbox" checked={ocr} onChange={e => setOcr(e.target.checked)} />启用 OCR（耗时较长）</label>
        {ocr && <label>OCR 语言<select value={language} onChange={e => setLanguage(e.target.value)}>
          <option value="eng,chi_sim">英文与简体中文</option><option value="chi_sim">简体中文</option><option value="eng">英文</option>
        </select></label>}
        <label className="check-label"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />确认重新处理所选原件，包括已有成功结果</label>
        <InfoTip>保留人工字段和最近成功正文；每份档案独立排队，解析结果可在任务中心找回。提交后不能撤销。</InfoTip>
      </fieldset>}
      <Notice>
        {operation === "trash"
          ? `确认将这 ${draft.items.length} 份档案加入回收站？只改变逻辑状态，保留原件。`
          : operation === "restore"
            ? "恢复档案的原有分类与业务信息；原目录已删除时恢复至未分类。"
            : "提交后逐项校验版本与引用；失败项会单独说明，其他成功项仍保留。"}
      </Notice>
      <div className="form-actions">
        <button
          className="primary"
          disabled={
            busy ||
            (operation === "reprocess" && !confirmed) ||
            (operation === "set_metadata" && (!field || !confirmed)) ||
            (["move_folder", "set_type"].includes(operation) &&
              target === "__choose__") ||
            (["add_tags", "remove_tags"].includes(operation) && !tags.length)
          }
        >
          {busy ? "正在提交…" : "确认提交"}
        </button>
      </div>
    </form>
  );
}
