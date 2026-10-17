import { useEffect, useRef } from "react";
import { X, FileText } from "@phosphor-icons/react";
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
  available: "原件可用",
  missing: "原件缺失",
  suspected_missing: "原件待核验",
  source_offline: "来源离线",
  excluded: "已排除",
  unknown: "原件待核验",
};
