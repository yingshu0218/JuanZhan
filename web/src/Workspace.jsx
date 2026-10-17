import { useEffect, useMemo, useRef, useState } from "react";
import {
  FileText,
  Books,
  UploadSimple,
  SignOut,
  Folder,
  Folders,
  Star,
  Tray,
  Trash,
  Plus,
  CaretRight,
  List,
} from "@phosphor-icons/react";
import { message } from "./api.js";
import { Dialog, Notice, Empty } from "./ui.jsx";
import { Library } from "./Library.jsx";
import { Detail } from "./Detail.jsx";
import { Uploads, useUploads } from "./Uploads.jsx";
const views = {
  all: "全部档案",
  inbox: "收件箱",
  favorite: "已收藏",
  trash: "回收站",
};
const navIcons = { all: FileText, inbox: Tray, favorite: Star, trash: Trash };

export function Workspace({ api, logout, authError }) {
  const [spaces, setSpaces] = useState([]);
  const [space, setSpace] = useState("");
  const [catalog, setCatalog] = useState({
    folders: [],
    types: [],
    tags: [],
    definitions: [],
  });
  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [view, setView] = useState("grid");
  const [section, setSection] = useState("all");
  const [folder, setFolder] = useState("");
  const [selected, setSelected] = useState(null);
  const [mobileDetail, setMobileDetail] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("-imported_at");
  const [type, setType] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [dialog, setDialog] = useState(null);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef(null);
  const queue = useUploads(api, () => setRefresh((n) => n + 1));
  useEffect(() => {
    const controller = new AbortController();
    api
      .request("/spaces", { signal: controller.signal })
      .then((rows) => {
        setSpaces(rows);
        setSpace(rows[0]?.id || "");
        setReady(true);
        setLoading(false);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(message(e));
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [api]);
  useEffect(() => {
    if (!space) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const params = new URLSearchParams({
      space_id: space,
      page: String(page),
      page_size: "30",
      sort,
    });
    if (folder) params.set("folder_id", folder);
    if (type) params.set("document_type_id", type);
    if (section === "inbox") params.set("triage_status", "needs_review");
    if (section === "favorite") params.set("is_favorite", "true");
    if (section === "trash") params.set("trash", "only");
    Promise.all([
      api.request("/documents?" + params, { signal: controller.signal }),
      ...["folders", "document-types", "tags", "field-definitions"].map(
        (path) =>
          api.request("/" + path + "?space_id=" + encodeURIComponent(space), {
            signal: controller.signal,
          }),
      ),
    ])
      .then(([result, folders, types, tags, definitions]) => {
        if (controller.signal.aborted) return;
        setDocuments(result.items);
        setTotal(result.total);
        setCatalog({ folders, types, tags, definitions });
        setSelected((current) =>
          result.items.some((doc) => doc.id === current) ? current : null,
        );
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(message(e));
          setDocuments([]);
          setTotal(0);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, space, page, sort, type, folder, section, refresh]);
  function chooseSection(next, nextFolder = "") {
    setSection(next);
    setFolder(nextFolder);
    setPage(1);
    setSelected(null);
    setMobileDetail(false);
    setNavOpen(false);
  }
  function chooseSpace(id) {
    setSpace(id);
    setCatalog({ folders: [], types: [], tags: [], definitions: [] });
    setDocuments([]);
    setTotal(0);
    setType("");
    chooseSection("all");
  }
  function openDialog(kind) {
    setDialog(kind);
    setFormError("");
    setSaving(false);
  }
  async function create(event) {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    const name = new FormData(event.currentTarget).get("name");
    try {
      if (dialog === "space") {
        const result = await api.request("/spaces", {
          method: "POST",
          body: { name },
        });
        setSpaces((rows) => [...rows, result]);
        setReady(true);
        chooseSpace(result.id);
      } else {
        await api.request("/folders", {
          method: "POST",
          body: { space_id: space, parent_id: folder || null, name },
        });
        setRefresh((n) => n + 1);
      }
      setDialog(null);
    } catch (e) {
      setFormError(message(e));
    } finally {
      setSaving(false);
    }
  }
  const title = folder
    ? catalog.folders.find((f) => f.id === folder)?.name || "逻辑目录"
    : views[section];
  const importFiles = () => {
    if (space) {
      queue.setOpen(true);
      inputRef.current?.click();
    }
  };
  const folderRows = useMemo(() => {
    const byParent = new Map();
    for (const item of catalog.folders) {
      const children = byParent.get(item.parent_id) || [];
      children.push(item);
      byParent.set(item.parent_id, children);
    }
    const rows = [];
    const stack = [...(byParent.get(null) || [])]
      .reverse()
      .map((item) => ({ ...item, depth: 0 }));
    while (stack.length) {
      const item = stack.pop();
      rows.push(item);
      for (const child of [...(byParent.get(item.id) || [])].reverse())
        stack.push({ ...child, depth: item.depth + 1 });
    }
    return rows;
  }, [catalog.folders]);
  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <button
            className="mobile-nav-toggle"
            aria-label="打开导航"
            onClick={() => setNavOpen(!navOpen)}
          >
            <List size={23} />
          </button>
          <Books size={27} weight="duotone" />
          <strong>档案库</strong>
        </div>
        <div className="breadcrumb">
          <span>{spaces.find((s) => s.id === space)?.name || "个人资料"}</span>
          <CaretRight size={15} />
          <span>{title}</span>
        </div>
        <div className="header-actions">
          <button className="primary" disabled={!space} onClick={importFiles}>
            <UploadSimple size={18} />
            <span>导入文件</span>
          </button>
          <button aria-label="退出登录" title="退出登录" onClick={logout}>
            <SignOut size={22} />
          </button>
        </div>
      </header>
      <input
        ref={inputRef}
        aria-label="选择上传文件"
        type="file"
        multiple
        hidden
        onChange={(e) => {
          queue.enqueue(e.target.files, space, folder);
          e.target.value = "";
        }}
      />
      {authError ? <Notice error>{authError}</Notice> : null}
      <main className={mobileDetail ? "show-detail" : ""}>
        <nav
          className={navOpen ? "sidebar open" : "sidebar"}
          aria-label="档案导航"
        >
          <label className="space-label" htmlFor="space-select">
            当前空间
          </label>
          <select
            id="space-select"
            value={space}
            onChange={(e) => chooseSpace(e.target.value)}
          >
            {spaces.length ? (
              spaces.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))
            ) : (
              <option value="">尚无空间</option>
            )}
          </select>
          <div className="nav-top">
            {Object.entries(views).map(([key, name]) => {
              const Icon = navIcons[key];
              return (
                <button
                  key={key}
                  className={!folder && section === key ? "active" : ""}
                  aria-current={!folder && section === key ? "page" : undefined}
                  onClick={() => chooseSection(key)}
                >
                  <Icon size={19} />
                  {name}
                </button>
              );
            })}
          </div>
          <div className="nav-heading">
            <span>逻辑目录</span>
            <button
              aria-label="新建目录"
              disabled={!space}
              onClick={() => openDialog("folder")}
            >
              <Plus size={17} />
            </button>
          </div>
          <div className="folder-tree">
            {folderRows.map((f) => (
              <button
                key={f.id}
                className={
                  "depth-" +
                  Math.min(f.depth, 5) +
                  (folder === f.id ? " active" : "")
                }
                aria-current={folder === f.id ? "page" : undefined}
                onClick={() => chooseSection("all", f.id)}
              >
                <Folder size={18} />
                <span>{f.name}</span>
              </button>
            ))}
            {!catalog.folders.length ? (
              <small className="folder-empty">尚无逻辑目录</small>
            ) : null}
          </div>
          <div className="nav-bottom">
            <button onClick={() => openDialog("space")}>
              <Plus size={18} />
              新建空间
            </button>
            {queue.items.length ? (
              <button onClick={() => queue.setOpen(true)}>
                <UploadSimple size={18} />
                上传队列
              </button>
            ) : null}
          </div>
        </nav>
        {!ready && error ? (
          <div className="workspace-empty">
            <Notice error>{error}</Notice>
            <button onClick={() => window.location.reload()}>重新连接</button>
          </div>
        ) : !space && ready ? (
          <div className="workspace-empty">
            <Empty title="建立你的第一个空间">
              <p>按工作、项目或生活，将资料归入独立空间。</p>
              <button className="primary" onClick={() => openDialog("space")}>
                <Folders size={18} />
                新建空间
              </button>
            </Empty>
          </div>
        ) : (
          <>
            <Library
              documents={documents}
              total={total}
              page={page}
              setPage={(n) => {
                setPage(n);
                setSelected(null);
              }}
              sort={sort}
              setSort={(value) => {
                setSort(value);
                setPage(1);
                setSelected(null);
              }}
              types={catalog.types}
              type={type}
              setType={(value) => {
                setType(value);
                setPage(1);
                setSelected(null);
              }}
              view={view}
              setView={setView}
              selected={selected}
              onSelect={(id) => {
                setSelected(id);
                setMobileDetail(true);
              }}
              title={title}
              loading={loading}
              error={error}
              retry={() => setRefresh((n) => n + 1)}
              importFiles={importFiles}
            />
            <Detail
              key={selected || "empty"}
              api={api}
              id={selected}
              types={catalog.types}
              folders={catalog.folders}
              tags={catalog.tags}
              definitions={catalog.definitions}
              onBack={() => setMobileDetail(false)}
              refreshKey={refresh}
            />
          </>
        )}
      </main>
      <Uploads queue={queue} api={api} inputRef={inputRef} />
      {dialog ? (
        <Dialog
          title={dialog === "space" ? "新建空间" : "新建目录"}
          onClose={() => {
            if (!saving) setDialog(null);
          }}
        >
          <form onSubmit={create}>
            <label>
              {dialog === "space" ? "空间名称" : "目录名称"}
              <input name="name" autoFocus required maxLength="255" />
            </label>
            {formError ? <Notice error>{formError}</Notice> : null}
            <div className="form-actions">
              <button
                type="button"
                disabled={saving}
                onClick={() => setDialog(null)}
              >
                取消
              </button>
              <button className="primary" disabled={saving}>
                {saving ? "正在创建…" : "创建"}
              </button>
            </div>
          </form>
        </Dialog>
      ) : null}
    </div>
  );
}
