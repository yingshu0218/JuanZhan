import {
  FileText,
  SquaresFour,
  List,
  CaretLeft,
  CaretRight,
} from "@phosphor-icons/react";
import { Empty, Notice, InfoTip, processing, formatDate } from "./ui.jsx";
import { useState } from "react";
function Thumbnail({ doc, view }) {
  const [failed, setFailed] = useState(null);
  const asset = doc.thumbnail_asset_id;
  const url = asset ? `/api/v1/documents/${encodeURIComponent(doc.id)}/preview/${encodeURIComponent(asset)}?expected_revision_id=${encodeURIComponent(doc.current_revision_id)}` : null;
  const extension = doc.title.match(/\.([a-z0-9]{1,8})$/i)?.[1]?.toUpperCase() || 'FILE';
  return <div className="thumbnail" title={doc.origin_kind === 'external' ? '外部来源' : '上传原件'}>
    {view === 'grid' && url && failed !== url ? <img loading="lazy" src={url} alt="" onError={() => setFailed(url)} /> : <><FileText size={view === 'grid' ? 32 : 24} weight="thin" /><span>{extension}</span></>}
  </div>;
}
function sizeText(value) {
  if (value == null) return '';
  return value < 1024 ? `${value} B` : value < 1048576 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1048576).toFixed(1)} MB`;
}
export function Library({
  searchPanel,
  searching,
  relevanceAvailable,
  multiType,
  indexState,
  documents,
  total,
  page,
  setPage,
  sort,
  setSort,
  types,
  type,
  setType,
  view,
  setView,
  selected,
  onSelect,
  title,
  loading,
  error,
  retry,
  importFiles,
  checked,
  toggle,
  selectPage,
  selectResults,
  clearSelection,
  snapshotBusy,
  operate,
  operationPending,
  onDragStart,
  onDragEnd,
}) {
  return (
    <section className="library" aria-label="档案列表">
      <div className="section-head">
        <h1>
          {title}
          <small>{total} 份</small>
        </h1>
        <div className="view-switch">
          <button
            aria-label="网格视图"
            aria-pressed={view === "grid"}
            onClick={() => setView("grid")}
          >
            <SquaresFour size={19} />
          </button>
          <button
            aria-label="列表视图"
            aria-pressed={view === "list"}
            onClick={() => setView("list")}
          >
            <List size={20} />
          </button>
        </div>
      </div>
      {searchPanel}
      <div className="filters">
        <label className="sr-only" htmlFor="type-filter">
          筛选文档类型
        </label>
        <select
          disabled={multiType}
          id="type-filter"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">{multiType ? "高级类型范围" : "全部类型"}</option>
          {types.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
              {t.is_active ? "" : "（已停用）"}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="sort">
          排序
        </label>
        <select
          id="sort"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          {searching ? <option value="-relevance" disabled={!relevanceAvailable}>按相关性排序</option> : null}
          <option value="-imported_at">最新导入</option>
          <option value="imported_at">最早导入</option>
          <option value="title">按标题排序</option>
          <option value="-document_date">业务日期</option>
        </select>
      </div>
      {searching && indexState && !loading && !error ? <div className="search-status" aria-label="检索范围状态">
        {indexState.incomplete ? <Notice>当前结果可能不完整：范围内{indexState.total}份档案，未建索引{indexState.missing}份、索引待更新{indexState.pending}份、索引失败{indexState.failed}份。部分正文可能仍在处理、缺少文本或来自旧版本；这些状态可能重叠。</Notice> : <p className="muted">已在所选范围 {indexState.total} 份档案中检索。</p>}
        <button onClick={retry}>刷新检索结果</button>
      </div> : null}
      <div className="selection-controls">
        <label className="check-label">
          <input
            type="checkbox"
            aria-label="全选当前页"
            ref={(node) => {
              if (node)
                node.indeterminate =
                  documents.some((d) => checked.has(d.id)) &&
                  !documents.every((d) => checked.has(d.id));
            }}
            disabled={loading || !documents.length}
            checked={
              documents.length > 0 && documents.every((d) => checked.has(d.id))
            }
            onChange={(e) => selectPage(e.target.checked)}
          />
          当前页
        </label>
        <button
          disabled={loading || !total || snapshotBusy}
          onClick={selectResults}
        >
          {snapshotBusy ? "正在固定范围…" : "选择筛选结果"}
        </button>
      </div>
      {checked.size ? (
        <div className="selection-bar" role="region" aria-label="已选档案">
          <span>已选 {checked.size} 份</span>
          <button
            className="primary"
            disabled={operationPending}
            onClick={operate}
          >
            批量操作
          </button>
          <button onClick={clearSelection}>清除选择</button>
        </div>
      ) : null}
      {error ? (
        <div className="list-notice">
          <Notice error>{error}</Notice>
          <button onClick={retry}>重新加载</button>
        </div>
      ) : null}
      <div className={"file-collection " + view} aria-busy={loading}>
        {loading ? (
          <p className="loading-text" role="status">
            正在加载档案…
          </p>
        ) : error ? (
          <Empty title="档案暂时无法读取">
            <p>恢复连接后请重新加载。</p>
          </Empty>
        ) : documents.length ? (
          documents.map((doc) => (
            <div className="file-entry" key={doc.id}>
              <input
                className="file-select"
                type="checkbox"
                aria-label={"选择档案 " + doc.title}
                checked={checked.has(doc.id)}
                onChange={(e) => toggle(doc, e.target.checked)}
              />
              <button
                draggable={!doc.deleted_at}
                onDragStart={(e) => onDragStart(e, doc)}
                onDragEnd={onDragEnd}
                className={
                  "file-tile" + (selected === doc.id ? " selected" : "")
                }
                aria-pressed={selected === doc.id}
                onClick={() => onSelect(doc.id)}
              >
                <Thumbnail doc={doc} view={view} />
                <div className="file-caption">
                  <strong>{doc.title}</strong>
                  {doc.overview_excerpt ? <p className="file-excerpt" title={doc.overview_excerpt}>{doc.overview_excerpt}</p> : null}
                  <small title="文件大小 · 导入日期">{[sizeText(doc.size_bytes), formatDate(doc.imported_at)].filter(Boolean).join(' · ')}</small>
                  <div className="badges">
                    {doc.triage_status !== 'filed' ? <span>待整理</span> : null}
                    {doc.processing_status !== 'completed' ? <span>
                      {processing[doc.processing_status] || "状态未知"}
                    </span> : null}
                    {doc.content_stale ? <span>旧版本概览</span> : null}
                    {doc.search_index && doc.search_index.status !== "current" ? <span>{doc.search_index.status === "failed" ? "索引更新失败" : "索引尚未更新"}</span> : null}
                    {doc.search_index?.content_incomplete ? <span>正文可能不完整</span> : null}
                  </div>
                </div>
              </button>
            </div>
          ))
        ) : (
          searching ? <Empty title={indexState?.incomplete ? "暂未找到匹配档案" : "没有匹配的档案"}><p>{indexState?.incomplete ? "处理或索引尚未完整，不能据此确认没有匹配内容。请稍后刷新。" : "请调整关键词或过滤条件，或清除搜索。"}</p></Empty> : <Empty title="这里还没有档案">
            <InfoTip>导入原文件，开始整理资料。</InfoTip>
            <button onClick={importFiles} className="text-action">
              导入文件
            </button>
          </Empty>
        )}
      </div>
      <footer className="list-footer">
        <span>
          第 {page} 页 / 共 {Math.max(1, Math.ceil(total / 30))} 页
        </span>
        <div>
          <button
            aria-label="上一页"
            disabled={page === 1 || loading}
            onClick={() => setPage(page - 1)}
          >
            <CaretLeft size={18} />
          </button>
          <button
            aria-label="下一页"
            disabled={page * 30 >= total || loading}
            onClick={() => setPage(page + 1)}
          >
            <CaretRight size={18} />
          </button>
        </div>
      </footer>
    </section>
  );
}
