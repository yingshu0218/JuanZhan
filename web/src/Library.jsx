import {
  FileText,
  SquaresFour,
  List,
  CaretLeft,
  CaretRight,
} from "@phosphor-icons/react";
import { Empty, Notice, processing, formatDate } from "./ui.jsx";
export function Library({
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
      <div className="filters">
        <label className="sr-only" htmlFor="type-filter">
          筛选文档类型
        </label>
        <select
          id="type-filter"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">全部类型</option>
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
          <option value="-imported_at">最新导入</option>
          <option value="imported_at">最早导入</option>
          <option value="title">按标题排序</option>
          <option value="-document_date">业务日期</option>
        </select>
      </div>
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
                <div className="thumbnail">
                  <FileText size={view === "grid" ? 52 : 26} weight="thin" />
                  <span>
                    {doc.origin_kind === "external" ? "关联档案" : "托管档案"}
                  </span>
                </div>
                <div className="file-caption">
                  <strong>{doc.title}</strong>
                  <small>{formatDate(doc.imported_at)}</small>
                  <div className="badges">
                    <span>
                      {doc.triage_status === "filed" ? "已整理" : "待整理"}
                    </span>
                    <span>
                      {processing[doc.processing_status] || "状态未知"}
                    </span>
                  </div>
                </div>
              </button>
            </div>
          ))
        ) : (
          <Empty title="这里还没有档案">
            <p>导入原文件，开始整理资料。</p>
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
