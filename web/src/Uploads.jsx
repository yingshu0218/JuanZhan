import { Dialog, InfoTip } from "./ui.jsx";
import { useEffect, useRef, useState } from "react";
import { UploadSimple, CheckCircle, XCircle, X } from "@phosphor-icons/react";
import { message } from "./api.js";
import { formatSize, Notice, processing } from "./ui.jsx";
import { selectedFiles, droppedFiles, folderResolver, MAX_UPLOAD_ENTRIES, MAX_UPLOAD_DIRECTORIES } from './uploadTree.js';
export function useUploads(api, onSaved) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [scanning, setScanning] = useState(null);
  const [skipped, setSkipped] = useState({ total: 0, samples: [] });
  const [imageGroup, setImageGroup] = useState(null);
  const imageGroupRef = useRef(null);
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
  async function enqueue(files, spaceId, folderId) {
    if (!spaceId) return;
    const chosen=[...files];if(!chosen.length)return;
    try { const policy=await api.request("/system/upload-policy");if(alive.current)prepare(selectedFiles(chosen,policy), spaceId, folderId); }
    catch (error) { report(error.message); }
  }
  function report(error) {
    setOpen(true);
    setItems(rows => [...rows, { id: crypto.randomUUID(), kind:'notice', file: { name: '未加入上传队列', size: 0 }, status: 'failed', error }]);
  }
  function prepare(list, spaceId, folderId) {
    if (list.length >= 10 && list.every(entry => entry.kind === 'file' && !entry.parentPath && /\.(png|jpe?g|tiff?|webp|gif|bmp|heic|avif)$/i.test(entry.file.name))) {
      if (imageGroupRef.current) { report('请先完成上一批图片的归档选择；本批尚未加入队列。'); return; }
      const proposal = { list, spaceId, folderId };
      imageGroupRef.current = proposal; setImageGroup(proposal); setOpen(true);
    } else add(list, spaceId, folderId);
  }
  function groupImages(name) {
    const proposal = imageGroupRef.current;
    if (!proposal) return;
    const folderName = name?.trim().normalize('NFC');
    if (name !== null && (!folderName || folderName.length > 120 || /[\/\\\u0000-\u001f]/.test(folderName) || ['.', '..'].includes(folderName))) return '请输入有效文件夹名称（最多120字，不能含路径分隔符）。';
    let list = proposal.list;
    if (folderName) list = Object.assign([
      { kind: 'folder', file: { name: folderName, size: 0 }, path: folderName, parentPath: '' },
      ...list.map(entry => ({ ...entry, path: folderName + '/' + entry.path, parentPath: folderName })),
    ], { skipped: list.skipped });
    imageGroupRef.current = null; setImageGroup(null);
    add(list, proposal.spaceId, proposal.folderId);
  }
  function cancelImageGroup() { imageGroupRef.current = null; setImageGroup(null); }
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
      const pending = [...current.filter(i => ['waiting', 'uploading'].includes(i.status)), ...rows];
      const files = pending.filter(i => i.kind !== 'folder').length;
      const directories = pending.filter(i => i.kind === 'folder').length;
      if (files > MAX_UPLOAD_ENTRIES || directories > MAX_UPLOAD_DIRECTORIES) return [...current, { id: batch, kind:'notice', file: { name: '本批未加入队列', size: 0 }, status: 'failed', error: `加入本批后将有${files}个待上传文件、${directories}个待准备目录；同时最多排队1000个文件、5000个目录，目录不占文件名额。请等待队列结束后重试；本批尚未上传。` }];
      return [...current, ...rows];
    });
  }
  async function enqueueDrop(transfer, spaceId, folderId) {
    if (!spaceId) return;
    if (reader.current) { report('正在读取另一个文件夹，请稍后添加。'); return; }
    const controller = new AbortController(); reader.current = controller;
    setOpen(true); setScanning(0);
    try { const rows = await droppedFiles(transfer, controller.signal, count => { if (alive.current) setScanning(count); }, api.request("/system/upload-policy")); if (alive.current) prepare(rows, spaceId, folderId); }
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
  return { items, open, setOpen, enqueue, enqueueDrop, scanning, skipped, imageGroup, groupImages, cancelImageGroup, stopReading: () => reader.current?.abort(), cancel, separate, retry, busy: id => controllers.current.has(id) };
}
function ImageGroupDialog({ queue }) {
  const [name,setName] = useState(() => '图片归档 ' + new Date().toLocaleDateString('sv-SE'));
  const [error,setError] = useState('');
  return <Dialog title="批量图片归档" onClose={queue.cancelImageGroup}>
    <p>本批 {queue.imageGroup.list.length} 张图片</p>
    <label>文件夹名称<input aria-label="图片归档文件夹名称" maxLength={120} value={name} onChange={e=>setName(e.target.value)}/></label>
    <InfoTip>同批10张及以上散图建议归入一个文件夹；已有目录结构时直接保留。归档目录固定为选择这批文件时的位置，同名目录会复用。图片仍是独立档案，默认识别文字，不合并或改写原件。</InfoTip>
    {error&&<Notice error>{error}</Notice>}
    <div className="summary-actions"><button className="primary" onClick={()=>setError(queue.groupImages(name)||'')}>新建文件夹并导入</button><button onClick={()=>queue.groupImages(null)}>仍放在当前目录</button><button onClick={queue.cancelImageGroup}>取消本批</button></div>
  </Dialog>;
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
export function Uploads({ queue, api, inputRef, folderInputRef, onOpenTask, onDropFiles }) {
  if (!queue.open) return null;
  return (
    <section className="upload-panel" aria-label="上传队列">
      {queue.imageGroup && <ImageGroupDialog queue={queue} />}
      <div className="dialog-head">
        <div className="upload-title"><h2>导入文件</h2><InfoTip>支持多个文件或整个文件夹，保留目录层级；每批最多1000个文件，目录独立计数（最多5000个），最多32层。辅助文件会自动跳过。收起面板不取消上传，关闭页面会停止未完成的上传。</InfoTip></div>
        <button aria-label="收起上传队列" onClick={() => queue.setOpen(false)}>
          <X size={21} />
        </button>
      </div>
      <div className="upload-dropzone" aria-label="文件拖放区域"
        onDragOver={event=>{if([...event.dataTransfer.types].includes('Files')){event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect='copy';}}}
        onDrop={onDropFiles}>
        <UploadSimple size={30} aria-hidden="true" />
        <strong>将文件或文件夹拖到这里</strong>
        <div className="upload-actions">
          <button className="primary" onClick={() => inputRef.current?.click()}>选择文件</button>
          <button className="upload-folder-button" onClick={() => folderInputRef.current?.click()}>选择文件夹</button>
        </div>
      </div>
      {queue.scanning !== null && <div role="status">正在读取文件夹 · 已发现 {queue.scanning} 项 <button onClick={queue.stopReading}>取消读取</button></div>}
      {queue.items.some(item => item.ensureFolder) && <small role="status">文件 {queue.items.filter(item => item.kind === 'file').length} 个 · 目录 {queue.items.filter(item => item.kind === 'folder').length} 个 · 已保存 {queue.items.filter(item => item.kind === 'file' && item.status === 'saved').length} 个文件 · 待处理 {queue.items.filter(item => ['waiting', 'uploading'].includes(item.status)).length} 项</small>}
      <div className="upload-items">
        {queue.skipped.total > 0 && <details className="upload-skipped"><summary>已跳过 {queue.skipped.total} 项已排除文件/目录</summary><InfoTip>按后台上传格式规则及固定辅助文件清单跳过；被排除目录不会继续读取。以下显示最近20项；已有档案不受影响。</InfoTip><ul>{queue.skipped.samples.map((item, index) => <li key={index}><strong>{item.path}</strong><small>{item.reason}</small></li>)}</ul></details>}
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
                {item.kind !== 'notice' && <small>{item.kind === 'folder' ? '文件夹' : formatSize(item.file.size)}</small>}
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
        ) : null}
      </div>
    </section>
  );
}
