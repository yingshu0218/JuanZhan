import { useEffect, useRef, useId, useState } from "react";
import { X, FileText } from "@phosphor-icons/react";
export function InfoTip({ children, label = "信息说明" }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const trigger = useRef(null);
  const [position, setPosition] = useState({});
  function show() {
    const box = trigger.current.getBoundingClientRect();
    setPosition({ left: Math.max(12, Math.min(box.left, window.innerWidth - Math.min(320, window.innerWidth - 24) - 12)),
      ...(box.top > window.innerHeight / 2 ? { bottom: window.innerHeight - box.top + 6 } : { top: box.bottom + 6 }) });
    setOpen(true);
  }
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const outside = event => { if (!trigger.current?.parentElement.contains(event.target)) close(); };
    document.addEventListener("pointerdown", outside);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => { document.removeEventListener("pointerdown", outside); window.removeEventListener("scroll", close, true); window.removeEventListener("resize", close); };
  }, [open]);
  return <span className="info-tip" onMouseEnter={show} onMouseLeave={() => setOpen(false)}>
    <button ref={trigger} type="button" className="info-trigger" aria-label={label} aria-describedby={open ? id : undefined}
      aria-expanded={open} onFocus={show} onBlur={() => setOpen(false)}
      onClick={show} onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setOpen(false); } }}>ⓘ</button>
    {open && <span id={id} role="tooltip" className="info-content" style={position}>{children}</span>}
  </span>;
}
export function Dialog({ title, onClose, children, wide = false }) {
  const ref = useRef();
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = ref.current;
    dialog.showModal();
    return () => {
      dialog.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={wide ? "dialog wide" : "dialog"}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="dialog-head">
        <h2>{title}</h2>
        <button aria-label={"关闭" + title} onClick={onClose}>
          <X size={22} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Notice({ children, error = false }) {
  return (
    <p
      className={"notice" + (error ? " error" : "")}
      role={error ? "alert" : "status"}
    >
      {children}
    </p>
  );
}
export function Empty({ title, children }) {
  return (
    <div className="empty">
      <FileText size={38} weight="thin" />
      <h2>{title}</h2>
      {children}
    </div>
  );
}
export function formatSize(bytes) {
  return bytes >= 1048576
    ? `${(bytes / 1048576).toFixed(1)} MB`
    : bytes >= 1024
      ? `${(bytes / 1024).toFixed(1)} KB`
      : `${bytes} B`;
}
export function formatDate(value) {
  if (!value) return "未设置";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "未知"
    : date.toLocaleDateString("zh-CN");
}
export const processing = {
  not_started: "尚未处理",
  queued: "等待处理",
  running: "正在处理",
  completed: "处理完成",
  failed: "处理失败",
  unsupported: "暂不支持解析",
};
export const availability = {
  needs_match: "待人工匹配",
  available: "原件可用",
  missing: "原件缺失",
  suspected_missing: "原件待核验",
  source_offline: "来源离线",
  excluded: "已排除",
  unknown: "原件待核验",
};
