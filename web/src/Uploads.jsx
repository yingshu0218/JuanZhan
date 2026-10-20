import { useEffect, useRef, useState } from "react";
import { UploadSimple, CheckCircle, XCircle, X } from "@phosphor-icons/react";
import { message } from "./api.js";
import { formatSize, Notice, processing } from "./ui.jsx";
export function useUploads(api, onSaved) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const controllers = useRef(new Map());
  const alive = useRef(true);
  const saved = useRef(onSaved);
  saved.current = onSaved;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
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
    if (items.some((i) => i.status === "uploading")) return;
    const next = items.find((i) => i.status === "waiting");
    if (!next || controllers.current.has(next.id)) return;
    const controller = new AbortController();
    controllers.current.set(next.id, controller);
    change(next.id, { status: "uploading" });
    api
      .upload(next, {
        signal: controller.signal,
        onProgress: (progress) => change(next.id, { progress }),
      })
      .then((result) => {
        change(next.id, { status: "saved", result, progress: 100 });
        saved.current();
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
      .finally(() => controllers.current.delete(next.id));
  }, [items, api]);
  function enqueue(files, spaceId, folderId) {
    if (!spaceId) return;
    const list = [...files];
    if (!list.length) return;
    setOpen(true);
    setItems((current) => {
      const capacity = Math.max(
        0,
        20 -
          current.filter((i) => ["waiting", "uploading"].includes(i.status))
            .length,
      );
      return [
        ...current,
        ...list.slice(0, capacity).map((file) => ({
          id: crypto.randomUUID(),
          file,
          spaceId,
          folderId,
          policy: "reject",
          status: "waiting",
          progress: 0,
        })),
        ...(list.length > capacity
          ? [
              {
                id: crypto.randomUUID(),
                file: { name: "部分文件未加入队列", size: 0 },
                status: "failed",
                error: "同时最多排队 20 份文件，请等待当前队列结束后再添加。",
              },
            ]
          : []),
      ];
    });
  }
  function cancel(id) {
    const controller = controllers.current.get(id);
    if (controller) controller.abort();
    else change(id, { status: "cancelled", error: "已从等待队列移除。" });
  }
  function separate(id) {
    change(id, {
      status: "waiting",
      policy: "keep_separate",
      error: null,
      progress: 0,
    });
  }
  return { items, open, setOpen, enqueue, cancel, separate };
}
function SavedState({ api, item }) {
  const [job, setJob] = useState(null);
  useEffect(() => {
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
  }, [api, item.result.job_id]);
  return (
    <small role="status">
      原件已保存 ·{" "}
      {job
        ? job.error?.code === "HANDLER_NOT_AVAILABLE"
          ? "暂不支持解析"
          : processing[job.status] || "处理状态待核验"
        : "处理状态待核验"}
    </small>
  );
}
export function Uploads({ queue, api, inputRef, onOpenTask }) {
  if (!queue.open) return null;
  return (
    <section className="upload-panel" aria-label="上传队列">
      <div className="dialog-head">
        <h2>上传队列</h2>
        <button aria-label="收起上传队列" onClick={() => queue.setOpen(false)}>
          <X size={21} />
        </button>
      </div>
      <p className="muted">原件保存与正文处理分别进行。</p>
      <div className="upload-items">
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
                <strong>{item.file.name}</strong>
                <small>{formatSize(item.file.size)}</small>
                {item.status === "uploading" ? (
                  <>
                    <progress
                      max="100"
                      value={item.progress ?? undefined}
                      aria-label={item.file.name + "上传进度"}
                    />
                    <small>
                      {item.progress === 100
                        ? "正在确认保存…"
                        : `正在上传${item.progress === null ? "" : " " + item.progress + "%"}`}
                    </small>
                  </>
                ) : null}
                {item.status === "waiting" ? <small>等待上传</small> : null}
                {item.status === "saved" ? (
                  <><SavedState api={api} item={item} /><button className="text-action" onClick={() => onOpenTask(item.result.job_id)}>查看解析进度</button></>
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
          <p className="muted">选择需要导入的原文件。</p>
        )}
      </div>
      <button className="primary" onClick={() => inputRef.current?.click()}>
        <UploadSimple size={18} />
        选择文件
      </button>
    </section>
  );
}
