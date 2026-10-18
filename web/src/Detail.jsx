import { Reprocess } from "./Tasks.jsx";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  FileText,
  Paperclip,
  ArrowClockwise,
} from "@phosphor-icons/react";
import { ContentReader } from "./ContentReader.jsx";
import { message } from "./api.js";
import {
  Dialog,
  Empty,
  Notice,
  processing,
  availability,
  formatDate,
  formatSize,
} from "./ui.jsx";
export function Detail({
  api,
  id,
  types,
  folders,
  tags,
  definitions,
  onBack,
  refreshKey,
  onOperate,
  operationPending,
}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [original, setOriginal] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setData(null);
    setError("");
    setOriginal(false);
    if (id)
      Promise.all([
        api.request("/documents/" + id, { signal: abort.signal }),
        api.request("/documents/" + id + "/metadata", { signal: abort.signal }),
        api.request("/documents/" + id + "/revisions", {
          signal: abort.signal,
        }),
      ])
        .then(([doc, metadata, revisions]) => {
          if (!abort.signal.aborted) setData({ doc, metadata, revisions });
        })
        .catch((e) => {
          if (e.name !== "AbortError") setError(message(e));
        });
    return () => abort.abort();
  }, [api, id, refreshKey, attempt]);
  if (!id)
    return (
      <section className="detail-shell">
        <Empty title="选择一份档案">
          <p>在左侧选择资料，查看结构化信息。</p>
        </Empty>
      </section>
    );
  if (error)
    return (
      <section className="detail-shell">
        <button
          className="back-button"
          aria-label="返回档案列表"
          onClick={onBack}
        >
          <ArrowLeft size={20} />
          返回列表
        </button>
        <Notice error>{error}</Notice>
        <button onClick={() => setAttempt((n) => n + 1)}>重新加载</button>
      </section>
    );
  if (!data)
    return (
      <section className="detail-shell" aria-busy="true">
        <button
          className="back-button"
          aria-label="返回档案列表"
          onClick={onBack}
        >
          <ArrowLeft size={20} />
          返回列表
        </button>
        <p className="loading-text" role="status">
          正在加载详情…
        </p>
      </section>
    );
  const { doc, metadata, revisions } = data;
  const current = revisions[0];
  const type = types.find((t) => t.id === doc.document_type_id);
  const folder = folders.find((f) => f.id === doc.folder_id);
  return (
    <section className="detail-shell" aria-label="档案详情">
      <div className="reader-toolbar">
        <div className="read-title">
          <button
            className="back-button"
            aria-label="返回档案列表"
            onClick={onBack}
          >
            <ArrowLeft size={20} />
          </button>
          <FileText size={22} />
          <strong>{doc.title}</strong>
        </div>
        <div className="read-tools">
          <button
            className="manage-button"
            disabled={operationPending}
            onClick={() => onOperate(doc)}
          >
            {doc.deleted_at ? "恢复档案" : "整理操作"}
          </button>
          <button
            aria-label="刷新档案详情"
            onClick={() => setAttempt((n) => n + 1)}
          >
            <ArrowClockwise size={18} />
          </button>
          <button className="original-button" onClick={() => setOriginal(true)}>
            <Paperclip size={17} />
            关联原文件
          </button>
        </div>
      </div>
      <div className="detail-columns">
        <article className="reader">
          <div className="paper">
            <div className="paper-label">结构化信息</div>
            <h2>{doc.title}</h2>
            <div className="paper-rule" />
            <div className="state-line">
              <span className="status">
                {doc.triage_status === "filed" ? "已整理" : "待整理"}
              </span>
              <span>{processing[doc.processing_status] || "状态未知"}</span>
            </div>
            {doc.content_stale ? (
              <Notice>当前处理未替代最近成功正文：可能是原件已更新或最近一次解析失败。</Notice>
            ) : null}
            <Reprocess key={doc.id} api={api} doc={doc} />
            <ContentReader api={api} doc={doc} definitions={definitions} onChanged={() => setAttempt((n) => n + 1)} />
            <section className="business-fields">
              <h3>业务字段</h3>
              {metadata.length ? (
                <dl>
                  {metadata.map((field) => (
                    <div key={field.field_definition_id}>
                      <dt>
                        {definitions.find(
                          (d) => d.id === field.field_definition_id,
                        )?.label || field.key}
                        <small>
                          {field.is_confirmed ? "已确认" : "未确认"} ·{" "}
                          {field.origin === "extracted"
                            ? "采纳候选"
                            : field.origin === "manual"
                              ? "人工填写"
                              : "导入值"}
                        </small>
                      </dt>
                      <dd>
                        {typeof field.value === "boolean"
                          ? field.value
                            ? "是"
                            : "否"
                          : definitions
                              .find((d) => d.id === field.field_definition_id)
                              ?.constraints?.options?.find(
                                (option) => option.id === field.value,
                              )?.label || String(field.value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="muted">尚未填写业务字段。</p>
              )}
            </section>
            {doc.description ? (
              <section>
                <h3>描述</h3>
                <p className="description">{doc.description}</p>
              </section>
            ) : null}
          </div>
        </article>
        <aside className="inspector">
          <h2>档案属性</h2>
          <section className="identity">
            <FileText size={29} weight="thin" />
            <div>
              <strong>{current?.original_filename || doc.title}</strong>
              <small>
                {current ? formatSize(current.size_bytes) : "大小未知"}
              </small>
            </div>
          </section>
          <section>
            <h3>分类与位置</h3>
            <dl>
              <dt>文档类型</dt>
              <dd>{type?.label || "未分类"}</dd>
              <dt>逻辑目录</dt>
              <dd>{folder?.name || "未分类"}</dd>
              <dt>业务日期</dt>
              <dd>{doc.document_date || "未设置"}</dd>
            </dl>
          </section>
          <section>
            <h3>标签</h3>
            <div className="tags">
              {doc.tag_ids.length ? (
                doc.tag_ids.map((tag) => (
                  <span key={tag}>
                    {tags.find((t) => t.id === tag)?.name || "未知标签"}
                  </span>
                ))
              ) : (
                <p className="muted">暂无标签</p>
              )}
            </div>
          </section>
          <section>
            <h3>文件状态</h3>
            <dl>
              <dt>处理状态</dt>
              <dd>{processing[doc.processing_status] || "未知"}</dd>
              <dt>原件状态</dt>
              <dd>{availability[doc.availability_status] || "待核验"}</dd>
              <dt>存储方式</dt>
              <dd>{doc.origin_kind === "managed" ? "托管" : "只读来源"}</dd>
              <dt>原件版本</dt>
              <dd>{current ? "版本 " + current.revision_no : "未知"}</dd>
              <dt>导入日期</dt>
              <dd>{formatDate(doc.imported_at)}</dd>
            </dl>
          </section>
        </aside>
      </div>
      {original ? (
        <Dialog title="关联原文件" onClose={() => setOriginal(false)}>
          <p className="muted">
            原件预览与下载尚未开放。以下为已保存的原件信息。
          </p>
          <div className="revisions">
            {revisions.map((rev) => (
              <section key={rev.id}>
                <FileText size={26} />
                <div>
                  <strong>{rev.original_filename}</strong>
                  <p>
                    版本 {rev.revision_no} · {formatSize(rev.size_bytes)}
                  </p>
                  <small>
                    {rev.mime_type} ·{" "}
                    {rev.binary_available ? "原件可用" : "原件待核验或不可用"}
                  </small>
                </div>
              </section>
            ))}
          </div>
        </Dialog>
      ) : null}
    </section>
  );
}
