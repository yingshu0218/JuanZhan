import { InfoTip } from "./ui.jsx";
import { useEffect, useRef, useState } from "react";
import { UploadSimple, CheckCircle, XCircle, X } from "@phosphor-icons/react";
import { message } from "./api.js";
import { formatSize, Notice, processing } from "./ui.jsx";
import { selectedFiles, droppedFiles, folderResolver, MAX_UPLOAD_ENTRIES } from './uploadTree.js';
export function useUploads(api, onSaved) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [scanning, setScanning] = useState(null);
  const [skipped, setSkipped] = useState({ total: 0, samples: [] });
  const reader = useRef(null);
  const refreshTimer = useRef(null);
  const controllers = useRef(new Map());
  const alive = useRef(true);
  const saved = useRef(onSaved);
  saved.current = onSaved;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      reader.current?.abort();
      clearTimeout(refreshTimer.current);
      for (const controller of controllers.current.values()) controller.abort();
    };
  }, []);
  const change = (id, patch) => {
    if (alive.current)
      setItems((rows) =>
        rows.map((row) => (row.id === id ? { ...row, ...patch } : row)),
      );
  };
  useEffect(() => {
    if (controllers.current.size || items.some((i) => i.status === "uploading")) return;
    const next = items.find((i) => i.status === "waiting");
    if (!next || controllers.current.has(next.id)) return;
    const controller = new AbortController();
    controllers.current.set(next.id, controller);
    change(next.id, { status: "uploading" });
    Promise.resolve().then(async () => {
      const folderId = await next.ensureFolder(next.kind === 'folder' ? next.path : next.parentPath, controller.signal);
      if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
      if (next.kind === 'folder') return { folder_id: folderId };
      return api.upload({ ...next, folderId }, {
        signal: controller.signal,
        onProgress: (progress) => change(next.id, { progress }),
      });
    })
      .then((result) => {
        change(next.id, { status: "saved", result, progress: 100 });
        if (!refreshTimer.current) refreshTimer.current = setTimeout(() => { refreshTimer.current = null; if (alive.current) saved.current(); }, 500);
      })
      .catch((error) => {
        change(next.id, {
          status:
            error.name === "AbortError"
              ? "cancelled"
              : error.code === "DUPLICATE_DETECTED"
                ? "duplicate"
                : "failed",
          error:
            error.name === "AbortError"
              ? "已停止等待，原件可能已保存，请刷新核对。"
              : error.status === 0
                ? "连接中断，保存结果尚未确认，请先刷新核对。"
                : message(error),
        });
      })
      .finally(() => { controllers.current.delete(next.id); if (alive.current) setItems(rows => [...rows]); });
  }, [items, api]);
  function enqueue(files, spaceId, folderId) {
    if (!spaceId) return;
    try { add(selectedFiles([...files]), spaceId, folderId); }
    catch (error) { report(error.message); }
  }
  function report(error) {
    setOpen(true);
    setItems(rows => [...rows, { id: crypto.randomUUID(), file: { name: '未加入上传队列', size: 0 }, status: 'failed', error }]);
  }
  function add(list, spaceId, folderId) {
    if (list.skipped?.total) {
      setOpen(true);
      setSkipped(current => ({ total: current.total + list.skipped.total, samples: [...list.skipped.samples, ...current.samples].slice(0, 20) }));
    }
    if (!list.length) return;
    const ensureFolder = folderResolver(api, spaceId, folderId);
    const batch = crypto.randomUUID();
    const rows = list.map(entry => ({ ...entry, id: crypto.randomUUID(), batch, ensureFolder, spaceId, folderId, policy: 'reject', status: 'waiting', progress: 0 }));
    setOpen(true);
    setItems((current) => {
      const active = current.filter(i => ['waiting', 'uploading'].includes(i.status)).length;
      if (active + rows.length > MAX_UPLOAD_ENTRIES) return [...current, { id: batch, file: { name: '本批未加入队列', size: 0 }, status: 'failed', error: '同时最多排队1000个文件和目录，请等待队列结束后重试；本批没有部分上传。' }];
      return [...current, ...rows];
    });
  }
  async function enqueueDrop(transfer, spaceId, folderId) {
    if (!spaceId) return;
    if (reader.current) { report('正在读取另一个文件夹，请稍后添加。'); return; }
    const controller = new AbortController(); reader.current = controller;
    setOpen(true); setScanning(0);
    try { const rows = await droppedFiles(transfer, controller.signal, count => { if (alive.current) setScanning(count); }); if (alive.current) add(rows, spaceId, folderId); }
    catch (error) { if (alive.current && error.name !== 'AbortError') report(error.message || '文件夹读取失败，本批尚未上传。'); }
    finally { if (reader.current === controller) reader.current = null; if (alive.current) setScanning(null); }
  }
  function cancel(id) {
    const target = items.find(item => item.id === id);
    const matches = item => item.id === id || (target?.kind === 'folder' && item.batch === target.batch && item.path?.startsWith(target.path + '/'));
    for (const item of items.filter(matches)) controllers.current.get(item.id)?.abort();
    setItems(rows => rows.map(item => matches(item) && ['waiting', 'uploading'].includes(item.status) ? { ...item, status: 'cancelled', error: item.status === 'waiting' ? '已从等待队列移除。' : '已停止等待，原件或目录可能已保存，请刷新核对。' } : item));
  }
  function separate(id) {
    change(id, {
      status: "waiting",
      policy: "keep_separate",
      error: null,
      progress: 0,
    });
  }
  function retry(id) { if (!controllers.current.has(id)) change(id, { status: 'waiting', policy: 'reject', error: null, progress: 0 }); }
  return { items, open, setOpen, enqueue, enqueueDrop, scanning, skipped, stopReading: () => reader.current?.abort(), cancel, separate, retry, busy: id => controllers.current.has(id) };
}
function SavedState({ api, item }) {
  const [job, setJob] = useState(null);
  const [visible, setVisible] = useState(false);
  const label = useRef(null);
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: '100px' });
    observer.observe(label.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return;
    let active = true;
    let timer;
    const controller = new AbortController();
    async function poll() {
      try {
        const data = await api.request("/jobs/" + item.result.job_id, {
          signal: controller.signal,
        });
        if (active) {
          setJob(data);
          if (["queued", "running"].includes(data.status))
            timer = setTimeout(poll, 1500);
        }
      } catch {
        /* Saving remains true even when task status cannot be retrieved. */
      }
    }
    poll();
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [api, item.result.job_id, visible]);
  return (
    <small role="status" ref={label}>
      原件已保存 ·{" "}
      {job
        ? job.error?.code === "HANDLER_NOT_AVAILABLE"
          ? "暂不支持解析"
          : processing[job.status] || "处理状态待核验"
        : "处理状态待核验"}
    </small>
  );
}
export function Uploads({ queue, api, inputRef, folderInputRef, onOpenTask }) {
  if (!queue.open) return null;
  return (
    <section className="upload-panel" aria-label="上传队列">
      <div className="dialog-head">
        <h2>上传队列</h2>
        <button aria-label="收起上传队列" onClick={() => queue.setOpen(false)}>
          <X size={21} />
        </button>
      </div>
      <InfoTip>支持选择或拖入文件、文件夹，保留目录层级并串行上传，单批最多1000个文件和目录、最多32层。同名逻辑目录复用；原件不会覆盖。文件夹选择器不提供空目录，拖入文件夹可保留空目录。原件保存与正文处理分别进行；关闭页面会停止尚未完成的上传。</InfoTip>
      {queue.scanning !== null && <div role="status">正在读取文件夹 · 已发现 {queue.scanning} 项 <button onClick={queue.stopReading}>取消读取</button></div>}
      {queue.items.some(item => item.ensureFolder) && <small role="status">已保存 {queue.items.filter(item => item.kind === 'file' && item.status === 'saved').length} 个文件 · 待处理 {queue.items.filter(item => ['waiting', 'uploading'].includes(item.status)).length} 项</small>}
      <div className="upload-items">
        {queue.skipped.total > 0 && <details className="upload-skipped"><summary>已跳过 {queue.skipped.total} 项系统或临时文件/目录</summary><InfoTip>不上传系统元数据、缓存和临时锁文件；被排除目录不会继续读取。以下显示最近20项，普通隐藏文件及备份文件仍保留。</InfoTip><ul>{queue.skipped.samples.map((item, index) => <li key={index}><strong>{item.path}</strong><small>{item.reason}</small></li>)}</ul></details>}
        {queue.items.length ? (
          queue.items.map((item) => (
            <div className="upload-row" key={item.id}>
              <div className={"upload-symbol " + item.status}>
                {item.status === "saved" ? (
                  <CheckCircle size={23} />
                ) : ["failed", "duplicate", "cancelled"].includes(
                    item.status,
                  ) ? (
                  <XCircle size={23} />
                ) : (
                  <UploadSimple size={23} />
                )}
              </div>
              <div className="upload-info">
                <strong>{item.path || item.file.name}</strong>
                <small>{item.kind === 'folder' ? '文件夹' : formatSize(item.file.size)}</small>
                {item.status === "uploading" ? (
                  <>
                    <progress
                      max="100"
                      value={item.progress ?? undefined}
                      aria-label={item.file.name + "上传进度"}
                    />
                    <small>
                      {item.kind === 'folder' ? '正在准备目录…' : item.progress === 100
                        ? "正在确认保存…"
                        : `正在上传${item.progress === null ? "" : " " + item.progress + "%"}`}
                    </small>
                  </>
                ) : null}
                {item.status === "waiting" ? <small>等待上传</small> : null}
                {item.status === "saved" ? (
                  item.kind === 'folder' ? <small role="status">目录已就绪</small> : <><SavedState api={api} item={item} /><button className="text-action" onClick={() => onOpenTask(item.result.job_id)}>查看解析进度</button></>
                ) : null}
                {item.error ? (
                  <Notice error={item.status !== "cancelled"}>
                    {item.error}
                  </Notice>
                ) : null}
                {item.status === "duplicate" ? (
                  <button
                    className="text-action"
                    onClick={() => queue.separate(item.id)}
                  >
                    仍要另存为独立档案
                  </button>
                ) : null}
                {item.ensureFolder && ['failed', 'cancelled'].includes(item.status) ? <button className="text-action" disabled={queue.busy(item.id)} onClick={() => queue.retry(item.id)}>重试 {item.file.name}</button> : null}
              </div>
              {["waiting", "uploading"].includes(item.status) ? (
                <button
                  aria-label={"取消上传 " + item.file.name}
                  onClick={() => queue.cancel(item.id)}
                >
                  <X size={18} />
                </button>
              ) : null}
            </div>
          ))
        ) : (
          <InfoTip>选择需要导入的原文件。</InfoTip>
        )}
      </div>
      <button className="primary" onClick={() => inputRef.current?.click()}>
        <UploadSimple size={18} />
        选择文件
      </button>
      <button onClick={() => folderInputRef.current?.click()}>选择文件夹</button>
    </section>
  );
}
