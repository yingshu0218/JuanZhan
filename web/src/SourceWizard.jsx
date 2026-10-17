import { useState } from "react";
import { Dialog, Notice } from "./ui.jsx";

export function SourceWizard({
  mounts,
  folders,
  busy,
  error,
  onClose,
  onCreate,
}) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [alias, setAlias] = useState("");
  const [policy, setPolicy] = useState("tree");
  const [target, setTarget] = useState("");
  const [triage, setTriage] = useState("needs_review");
  const [newTarget, setNewTarget] = useState("");
  const folderOptions = (
    <>
      <option value="">未分类</option>
      {folders.map((folder) => (
        <option value={folder.id} key={folder.id}>
          {folder.name} · {folder.id.slice(0, 6)}
        </option>
      ))}
    </>
  );
  return (
    <Dialog title="配置只读来源" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (step === 1) setStep(2);
          else
            onCreate({
              name: name.trim(),
              kind: "external",
              root_alias: alias,
              initial_import_policy: policy,
              initial_target_folder_id: target || null,
              initial_triage_status: triage,
              new_file_target_folder_id: newTarget || null,
              scan_interval_minutes: null,
            });
        }}
      >
        <p className="source-hint">
          步骤 {step} / 2 ·{" "}
          {step === 1 ? "选择只读挂载" : "确认首次及后续归档方式"}
        </p>
        {step === 1 ? (
          <>
            <label>
              来源名称
              <input
                required
                maxLength={255}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              挂载别名
              <select
                required
                value={alias}
                onChange={(e) => setAlias(e.target.value)}
              >
                <option value="">请选择管理员配置的别名</option>
                {mounts.map((mount) => (
                  <option
                    key={mount.alias}
                    value={mount.alias}
                    disabled={mount.status !== "ready"}
                  >
                    {mount.alias} ·{" "}
                    {
                      {
                        ready: "在线 · 只读",
                        offline: "来源离线",
                        unavailable: "挂载不可用",
                      }[mount.status]
                    }
                  </option>
                ))}
              </select>
            </label>
            <p>
              仅可选择在线只读挂载。不能输入服务器路径；若没有可用项，请管理员配置挂载后刷新来源。
            </p>
          </>
        ) : (
          <>
            <label>
              首次导入方式
              <select
                value={policy}
                onChange={(e) => setPolicy(e.target.value)}
              >
                <option value="tree">保留目录层次（tree）</option>
                <option value="flat">平铺归档（flat）</option>
              </select>
            </label>
            <label>
              首次目标逻辑目录
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                {folderOptions}
              </select>
            </label>
            <label>
              首次整理状态
              <select
                value={triage}
                onChange={(e) => setTriage(e.target.value)}
              >
                <option value="needs_review">待整理</option>
                <option value="filed">已归档</option>
              </select>
            </label>
            <label>
              后续新增文件目标
              <select
                value={newTarget}
                onChange={(e) => setNewTarget(e.target.value)}
              >
                {folderOptions}
              </select>
            </label>
            <p>
              后续新增统一待整理，不复制新物理目录。当前仅手动扫描。配置创建后不可在界面修改；创建不会自动扫描或导入。
            </p>
            <p>
              <strong>{name}</strong> · {alias}
            </p>
          </>
        )}
        {error && <Notice error>{error}</Notice>}
        <div className="form-actions">
          {step === 2 && (
            <button type="button" disabled={busy} onClick={() => setStep(1)}>
              上一步
            </button>
          )}
          <button type="button" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button
            className="primary"
            disabled={busy || (step === 1 && (!name.trim() || !alias))}
          >
            {busy ? "正在创建…" : step === 1 ? "下一步" : "创建来源"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
