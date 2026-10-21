import { AgentManager } from "./AgentManager.jsx";
import { StorageManager } from "./StorageManager.jsx";
import { InfoTip } from "./ui.jsx";
import { TaskCenter, TaskEntry } from "./Tasks.jsx";
import { BackupManager } from './BackupManager.jsx';
import { CatalogManager } from './CatalogManager.jsx';
import { useEffect, useMemo, useRef, useState } from "react";
import {
  HardDrives,
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
  Gear,
} from "@phosphor-icons/react";
import { SearchPanel } from "./SearchPanel.jsx";
import { encodedState, readLocation, searchBody, preferredView, rememberView } from "./searchState.js";
import { message } from "./api.js";
import { Dialog, Notice, Empty } from "./ui.jsx";
import { Sources } from "./Sources.jsx";
import { Library } from "./Library.jsx";
import { SystemOverview } from "./SystemOverview.jsx";
import { Detail } from "./Detail.jsx";
import { Operations, useOperations } from "./Operations.jsx";
import { Uploads, useUploads } from "./Uploads.jsx";
const views = {
  home: "系统概览",
  all: "全部档案",
  inbox: "收件箱",
  favorite: "已收藏",
  trash: "回收站",
  sources: "来源",
};
const navIcons = {
  home: Books,
  all: FileText,
  inbox: Tray,
  favorite: Star,
  trash: Trash,
  sources: HardDrives,
};

export function Workspace({ api, logout, authError }) {
  const [tasksOpen, setTasksOpen] = useState(false);
  const [taskId, setTaskId] = useState(null);
  function openTasks(id) { setTaskId(id); setTasksOpen(true); }
  const [catalogOpen,setCatalogOpen]=useState(false);
  const [agentOpen,setAgentOpen]=useState(false);
  const [settingsOpen,setSettingsOpen]=useState(false),[backupOpen,setBackupOpen]=useState(false);
  const [storageOpen,setStorageOpen]=useState(false);
  const [initial] = useState(readLocation);
  const urlStarted = useRef(false);
  const restoringUrl = useRef(false);
  const [search, setSearch] = useState(initial.state.search || null);
  const [indexState, setIndexState] = useState(null);
  const [spaces, setSpaces] = useState([]);
  const [space, setSpace] = useState(initial.state.space || "");
  const [catalog, setCatalog] = useState({
    folders: [],
    types: [],
    tags: [],
    definitions: [],
  });
  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [view, setView] = useState(initial.state.view || preferredView);
  const [section, setSection] = useState(initial.state.section || "home");
  const [folder, setFolder] = useState(initial.state.folder || "");
  const [selected, setSelected] = useState(null);
  const [mobileDetail, setMobileDetail] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [page, setPage] = useState(initial.state.page || 1);
  const [sort, setSort] = useState(initial.state.sort || "-imported_at");
  const [type, setType] = useState(initial.state.type || "");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [dialog, setDialog] = useState(null);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef(null);
  const queue = useUploads(api, () => setRefresh((n) => n + 1));
  const [checked, setChecked] = useState(new Map());
  const [selectionMode, setSelectionMode] = useState("explicit");
  const [snapshotBusy, setSnapshotBusy] = useState(false);
  const snapshotRequest = useRef(null);
  const [notice, setNotice] = useState(initial.error || "");
  const [dropTarget, setDropTarget] = useState("");
  const [fileDrag, setFileDrag] = useState(false);
  const dragDepth = useRef(0);
  const internalDrag = useRef(null);
  const operations = useOperations(api, (finished = true) => {
    if (!finished) setChecked(new Map());
    if (finished) setRefresh((n) => n + 1);
  });
  useEffect(() => {
    setChecked(new Map());
    setSelectionMode("explicit");
    snapshotRequest.current?.abort();
    setSnapshotBusy(false);
    internalDrag.current = null;
    return () => snapshotRequest.current?.abort();
  }, [space, page, sort, type, folder, section, search]);
  function context() {
    return {
      spaceId: space,
      spaceName: spaces.find((s) => s.id === space)?.name || "空间",
      catalog,
      mode: selectionMode,
    };
  }
  function prepare(items, operation = "move_folder", payload = null) {
    if (!items.length) return;
    const savedContext = context();
    if (items.length !== checked.size || items.some((i) => !checked.has(i.id)))
      savedContext.mode = "explicit";
    operations.prepare(items, savedContext, operation, payload);
  }
  function toggle(doc, value) {
    if (value && checked.size >= 100 && !checked.has(doc.id)) {
      setNotice("最多选择100份档案，请先缩小范围。");
      return;
    }
    setSelectionMode("explicit");
    setChecked((current) => {
      const next = new Map(current);
      if (value) next.set(doc.id, { ...doc });
      else next.delete(doc.id);
      return next;
    });
  }
  function fetchDocuments(number, size, signal) {
    if (section === 'home') return Promise.resolve({ items: [], total: 0 });
    if (search && section !== "sources") {
      const body = { ...searchBody(search), space_id: space, page: number, page_size: size,
        sort: [{ field: sort.replace(/^-/, ""), order: sort.startsWith("-") ? "desc" : "asc" }] };
      if (folder) body.folder = { id: folder, include_descendants: search.descendants };
      if (type) body.document_type_ids = [type];
      if (section === "inbox") body.triage_status = "needs_review";
      if (section === "favorite") body.is_favorite = true;
      if (section === "trash") body.trash = "only";
      return api.request("/documents/search", { method: "POST", body, signal });
    }
    const params = new URLSearchParams({ space_id: space, page: String(number), page_size: String(size), sort: sort === "-relevance" ? "-imported_at" : sort });
    if (folder) params.set("folder_id", folder);
    if (type) params.set("document_type_id", type);
    if (section === "inbox") params.set("triage_status", "needs_review");
    if (section === "favorite") params.set("is_favorite", "true");
    if (section === "trash") params.set("trash", "only");
    return api.request("/documents?" + params, { signal });
  }
  function applySearch(value) {
    const nextSort = value.text ? "-relevance" : "-imported_at";
    const nextType = value.type_ids?.length ? "" : type;
    encodedState({ space, section, folder, type: nextType, page: 1, sort: nextSort, view, search: value });
    setSearch(value); setType(nextType); setSort(nextSort); setPage(1); setSelected(null); setIndexState(null);
    setRefresh((n) => n + 1);
  }
  function clearSearch() {
    setSearch(null); setSort("-imported_at"); setPage(1); setSelected(null); setIndexState(null);
  }
  useEffect(() => {
    if (!ready || !space) return;
    let hash;
    try { hash = encodedState({ space, section, folder, type, page, sort, view, search }); }
    catch (error) { setNotice(error.message + " 当前状态未保存到链接。"); return; }
    if (location.hash !== hash) history[urlStarted.current && !restoringUrl.current ? "pushState" : "replaceState"](null, "", hash);
    urlStarted.current = true;
    restoringUrl.current = false;
  }, [ready, space, section, folder, type, page, sort, view, search]);
  useEffect(() => {
    function restore() {
      restoringUrl.current = true;
      const saved = readLocation(); const value = saved.state;
      const available = spaces.some((item) => item.id === value.space);
      setNotice(saved.error || (!available && value.space ? "链接中的空间不可用，已回到默认列表并清空检索。" : ""));
      setSpace(available ? value.space : (spaces[0]?.id || ""));
      setSection(available ? value.section : (value.space || saved.error ? "all" : "home")); setFolder(available ? value.folder : ""); setType(available ? value.type : "");
      setPage(available ? value.page : 1); setSort(available ? value.sort : "-imported_at"); setView(available ? value.view : preferredView());
      setSearch(available ? value.search : null); setSelected(null); setMobileDetail(false); setChecked(new Map());
    }
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [spaces]);
  async function selectResults() {
    const controller = new AbortController();
    snapshotRequest.current?.abort();
    snapshotRequest.current = controller;
    setSnapshotBusy(true);
    setNotice("");
    try {
      const result = await fetchDocuments(1, 100, controller.signal);
      if (controller.signal.aborted) return;
      if (result.total > 100) {
        setNotice("当前筛选结果超过100份，请缩小筛选范围或按当前页操作。");
        return;
      }
      setChecked(new Map(result.items.map((doc) => [doc.id, { ...doc }])));
      setSelectionMode("snapshot");
    } catch (e) {
      if (e.name !== "AbortError") setNotice(message(e));
    } finally {
      if (!controller.signal.aborted) setSnapshotBusy(false);
    }
  }
  function dragStart(event, doc) {
    if (doc.deleted_at || operations.pending) {
      event.preventDefault();
      return;
    }
    const items = checked.has(doc.id) ? [...checked.values()] : [doc];
    const token = crypto.randomUUID();
    internalDrag.current = {
      token,
      items: items.map((item) => ({ ...item })),
      context: {
        ...context(),
        mode: checked.has(doc.id) ? selectionMode : "explicit",
      },
    };
    event.dataTransfer.setData("application/x-juanzhan-documents", token);
    event.dataTransfer.effectAllowed = "move";
  }
  function resetDrag() {
    internalDrag.current = null;
    setDropTarget("");
    setFileDrag(false);
    dragDepth.current = 0;
  }
  function accepts(event) {
    return (
      [...event.dataTransfer.types].includes("Files") ||
      (internalDrag.current &&
        [...event.dataTransfer.types].includes(
          "application/x-juanzhan-documents",
        ))
    );
  }
  function dragOver(event, target) {
    if (!accepts(event)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = [...event.dataTransfer.types].includes(
      "Files",
    )
      ? "copy"
      : "move";
    setDropTarget(target);
  }
  function drop(event, kind = "files", target = null) {
    event.preventDefault();
    event.stopPropagation();
    const internal = internalDrag.current;
    const files = [...event.dataTransfer.files];
    const token = event.dataTransfer.getData(
      "application/x-juanzhan-documents",
    );
    resetDrag();
    if (files.length) {
      if (section === "sources" && kind === "files") {
        setNotice("来源为只读。请返回档案列表上传，或将文件拖到逻辑目录。");
        return;
      }
      if (!space) {
        setNotice("请先建立或选择空间。");
        return;
      }
      if (kind === "trash" || kind === "tag") {
        setNotice("原文件请拖入列表或逻辑目录。");
        return;
      }
      if (
        [...event.dataTransfer.items].some(
          (item) => item.webkitGetAsEntry?.()?.isDirectory,
        )
      ) {
        setNotice("暂不支持拖入整个文件夹，请选择具体文件。");
        return;
      }
      queue.enqueue(files, space, kind === "folder" ? target : folder);
      return;
    }
    if (
      !internal ||
      token !== internal.token ||
      internal.context.spaceId !== space
    )
      return;
    if (operations.pending) {
      setNotice("请等待当前操作结束后再拖动档案。");
      return;
    }
    if (kind === "files") {
      setNotice("请将档案拖到逻辑目录、标签或回收站。");
      return;
    }
    operations.prepare(
      internal.items,
      internal.context,
      kind === "trash" ? "trash" : kind === "tag" ? "add_tags" : "move_folder",
      kind === "trash"
        ? {}
        : kind === "tag"
          ? { tag_ids: [target] }
          : { folder_id: target },
    );
  }

  useEffect(() => {
    const controller = new AbortController();
    api
      .request("/spaces", { signal: controller.signal })
      .then((rows) => {
        setSpaces(rows);
        const saved = rows.some((row) => row.id === initial.state.space);
        setSpace(saved ? initial.state.space : (rows[0]?.id || ""));
        if (initial.state.space && !saved) {
          setNotice("链接中的空间不可用，已回到默认列表并清空检索。");
          setSearch(null); setSection("all"); setFolder(""); setType(""); setPage(1); setSort("-imported_at");
        }
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
    if (!ready || !space) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setIndexState(null);
    Promise.all([
      fetchDocuments(page, 30, controller.signal),
      ...["folders", "document-types", "tags", "field-definitions", "sources"].map(
        (path) =>
          api.request("/" + path + "?space_id=" + encodeURIComponent(space), {
            signal: controller.signal,
          }),
      ),
    ])
      .then(([result, folders, types, tags, definitions, sources]) => {
        if (controller.signal.aborted) return;
        if (page > 1 && (page - 1) * 30 >= result.total) {
          restoringUrl.current = true;
          setPage(Math.max(1, Math.ceil(result.total / 30)));
          return;
        }
        setDocuments(result.items);
        setTotal(result.total);
        setIndexState(result.search_index || null);
        setCatalog({ folders, types, tags, definitions, sources });
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
  }, [api, ready, space, page, sort, type, folder, section, refresh, search]);
  function chooseSection(next, nextFolder = "") {
    if (next === 'home') { clearSearch(); setType(''); }
    setSection(next);
    setFolder(nextFolder);
    setPage(1);
    setSelected(null);
    setMobileDetail(false);
    setNavOpen(false);
  }
  function chooseSpace(id) {
    if (id === space) return;
    clearSearch();
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
        await api.request(dialog === "tag" ? "/tags" : "/folders", {
          method: "POST",
          body:
            dialog === "tag"
              ? { space_id: space, name }
              : { space_id: space, parent_id: folder || null, name },
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
    <div
      className="app"
      onDragEnter={(e) => {
        if ([...e.dataTransfer.types].includes("Files")) {
          e.preventDefault();
          dragDepth.current++;
          setFileDrag(true);
        }
      }}
      onDragLeave={(e) => {
        if ([...e.dataTransfer.types].includes("Files")) {
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (!dragDepth.current) {
            setFileDrag(false);
            setDropTarget("");
          }
        }
      }}
      onDragOver={(e) => dragOver(e, "files")}
      onDrop={(e) => drop(e)}
    >
      {fileDrag && section !== "sources" ? (
        <div className="drop-overlay" role="status">
          松开文件，上传至所选空间 /{" "}
          {catalog.folders.find(
            (f) =>
              f.id ===
              (dropTarget.startsWith("folder:") ? dropTarget.slice(7) : folder),
          )?.name || "未分类"}
          ；内部档案拖动只改变逻辑分类。
        </div>
      ) : null}
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
          <span>{section === 'home' ? '全部空间' : spaces.find((s) => s.id === space)?.name || "个人资料"}</span>
          <CaretRight size={15} />
          <span>{title}</span>
        </div>
        <div className="header-actions">
          <button aria-label="系统设置" title="系统设置" onClick={()=>setSettingsOpen(true)}><Gear size={22} /></button>
          {settingsOpen && <Dialog title="系统设置" onClose={()=>setSettingsOpen(false)}><div className="settings-choices"><button onClick={()=>{setSettingsOpen(false);setStorageOpen(true);}}>存储管理</button><button disabled={!space} onClick={()=>{setSettingsOpen(false);setCatalogOpen(true);}}>管理字段与类型</button><button onClick={()=>{setSettingsOpen(false);setBackupOpen(true);}}>备份与恢复</button><button onClick={()=>{setSettingsOpen(false);setAgentOpen(true);}}>Agent 接入</button></div></Dialog>}
          {agentOpen && <AgentManager api={api} spaces={spaces} onClose={()=>setAgentOpen(false)} />}
          {backupOpen && <BackupManager api={api} onClose={()=>setBackupOpen(false)} />}
          {storageOpen && <StorageManager api={api} onClose={()=>setStorageOpen(false)} />}
          {catalogOpen && <CatalogManager key={space} api={api} spaceId={space} spaceName={spaces.find(item=>item.id===space)?.name||'当前空间'} onClose={()=>setCatalogOpen(false)} onChanged={()=>setRefresh(value=>value+1)} />}
          <TaskEntry api={api} onOpen={openTasks} refreshKey={refresh} />
          {tasksOpen && <TaskCenter api={api} initialId={taskId} onClose={() => setTasksOpen(false)} />}
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
      {notice ? (
        <div className="workspace-notice">
          <Notice>{notice}</Notice>
          <button aria-label="关闭提示" onClick={() => setNotice("")}>
            关闭
          </button>
        </div>
      ) : null}
      <main className={[mobileDetail && selected ? 'show-detail' : '', !selected ? 'no-selection' : ''].filter(Boolean).join(' ')}>
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
                  onDragOver={
                    key === "trash" ? (e) => dragOver(e, "trash") : undefined
                  }
                  onDrop={key === "trash" ? (e) => drop(e, "trash") : undefined}
                  data-drop-active={key === "trash" && dropTarget === "trash"}
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
                onDragOver={(e) => dragOver(e, "folder:" + f.id)}
                onDrop={(e) => drop(e, "folder", f.id)}
                data-drop-active={dropTarget === "folder:" + f.id}
              >
                <Folder size={18} />
                <span>{f.name}</span>
              </button>
            ))}
            {!catalog.folders.length ? (
              <small className="folder-empty">尚无逻辑目录</small>
            ) : null}
          </div>
          <div className="nav-heading">
            <span>标签</span>
            <button
              aria-label="新建标签"
              disabled={!space}
              onClick={() => openDialog("tag")}
            >
              <Plus size={17} />
            </button>
          </div>
          <div className="tag-tree">
            {catalog.tags.map((tag) => (
              <button
                key={tag.id}
                aria-label={"标签 " + tag.name}
                onClick={() => {
                  if (checked.size)
                    prepare([...checked.values()], "add_tags", {
                      tag_ids: [tag.id],
                    });
                  else setNotice("先勾选档案，或将档案拖到标签上。");
                }}
                onDragOver={(e) => dragOver(e, "tag:" + tag.id)}
                onDrop={(e) => drop(e, "tag", tag.id)}
                data-drop-active={dropTarget === "tag:" + tag.id}
              >
                {tag.name}
              </button>
            ))}
          </div>
          <div className="nav-bottom">
            {operations.receipt || operations.draft || operations.busy ? (
              <button onClick={() => operations.setOpen(true)}>
                {operations.draft
                  ? "查看当前操作"
                  : operations.pending
                    ? "查看操作进度"
                    : "查看操作结果"}
              </button>
            ) : null}
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
        ) : !ready ? <div className="workspace-empty" role="status">正在读取档案库…</div>
        : section === 'home' && space ? (
          <SystemOverview api={api} spaces={spaces} refreshKey={refresh}
            onBrowse={next => { clearSearch(); setType(''); chooseSection(next); }}
            onTasks={() => openTasks(null)} onImport={importFiles}
            onDocument={doc => { clearSearch(); setType(''); setSpace(doc.space_id); chooseSection('all'); setSelected(doc.id); setMobileDetail(true); }} />
        ) : !space && ready ? (
          <div className="workspace-empty">
            <Empty title="建立你的第一个空间">
              <InfoTip>按工作、项目或生活，将资料归入独立空间。</InfoTip>
              <button className="primary" onClick={() => openDialog("space")}>
                <Folders size={18} />
                新建空间
              </button>
            </Empty>
          </div>
        ) : (
          <>
            <Sources
              key={space}
              api={api}
              space={space}
              folders={catalog.folders}
              catalog={catalog}
              onOperate={(doc) =>
                prepare([doc], doc.deleted_at ? "restore" : "set_triage")
              }
              operationPending={operations.pending}
              refreshKey={refresh}
              active={section === "sources"}
              onRefresh={() => setRefresh((n) => n + 1)}
            />
            {section !== "sources" && (
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
                  setView={value => { rememberView(value); setView(value); }}
                  selected={selected}
                  onSelect={(id) => {
                    setSelected(id);
                    setMobileDetail(true);
                  }}
                  searchPanel={<SearchPanel key={space + JSON.stringify(search)} applied={search} catalog={catalog} onApply={applySearch} onClear={clearSearch} />}
                  searching={!!search}
                  relevanceAvailable={!!search?.text}
                  multiType={!!search?.type_ids?.length}
                  indexState={indexState}
                  title={title}
                  loading={loading}
                  error={error}
                  retry={() => setRefresh((n) => n + 1)}
                  importFiles={importFiles}
                  checked={checked}
                  toggle={toggle}
                  selectPage={(value) => {
                    setSelectionMode("explicit");
                    setChecked(
                      value
                        ? new Map(documents.map((doc) => [doc.id, { ...doc }]))
                        : new Map(),
                    );
                  }}
                  selectResults={selectResults}
                  snapshotBusy={snapshotBusy}
                  clearSelection={() => setChecked(new Map())}
                  operate={() =>
                    prepare(
                      [...checked.values()],
                      section === "trash" ? "restore" : "move_folder",
                    )
                  }
                  operationPending={operations.pending}
                  onDragStart={dragStart}
                  onDragEnd={resetDrag}
                />
                {selected && <Detail
                  key={selected || "empty"}
                  api={api}
                  id={selected}
                  types={catalog.types}
                  folders={catalog.folders}
                  tags={catalog.tags}
                  definitions={catalog.definitions}
                  onBack={() => { setMobileDetail(false); setSelected(null); }}
                  refreshKey={refresh}
                  operationPending={operations.pending}
                  onOperate={(doc) =>
                    prepare([doc], doc.deleted_at ? "restore" : "set_triage")
                  }
                />}
              </>
            )}
          </>
        )}
      </main>
      <Operations state={operations} catalog={catalog} />
      <Uploads queue={queue} api={api} inputRef={inputRef} onOpenTask={openTasks} />
      {dialog ? (
        <Dialog
          title={
            dialog === "space"
              ? "新建空间"
              : dialog === "tag"
                ? "新建标签"
                : "新建目录"
          }
          onClose={() => {
            if (!saving) setDialog(null);
          }}
        >
          <form onSubmit={create}>
            <label>
              {dialog === "space"
                ? "空间名称"
                : dialog === "tag"
                  ? "标签名称"
                  : "目录名称"}
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
