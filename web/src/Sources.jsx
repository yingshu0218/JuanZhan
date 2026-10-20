import { InfoTip } from "./ui.jsx";
import { useEffect, useRef, useState } from "react";
import {
  HardDrives,
  Plus,
  Folder,
  FileText,
  ArrowClockwise,
  CaretRight,
} from "@phosphor-icons/react";
import { Dialog, Notice, Empty, formatSize, formatDate } from "./ui.jsx";
import { Detail } from "./Detail.jsx";
import { SourceWizard } from "./SourceWizard.jsx";
import { SourceSchedule } from "./SourceSchedule.jsx";
import { SourceMatch } from "./SourceMatch.jsx";
import { message } from "./api.js";

const states = {
  available: "原件可用",
  suspected_missing: "待核验失联",
  missing: "已确认失联",
  needs_match: "待人工匹配",
};
const health = {
  ready: "在线 · 只读",
  offline: "来源离线",
  unavailable: "挂载不可用",
};
const jobStates = {
  queued: "等待执行",
  running: "正在执行",
  completed: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
};
const labels = {
  estimated_files: "预计文件",
  estimated_bytes: "预计大小",
  ignored_files: "忽略文件",
  imported_files: "新增档案",
  imported_bytes: "导入大小",
  created_folders: "建立逻辑目录",
  scanned_files: "扫描文件",
  scanned_bytes: "扫描大小",
  updated_files: "更新原件",
  reassociated_files: "重关联",
  recovered_files: "恢复可用",
  unchanged_files: "未变化",
  needs_match: "待匹配总数",
  suspected_missing: "待核验总数",
  missing: "失联总数",
};

export function Sources({
  api,
  space,
  folders,
  active,
  onRefresh,
  catalog,
  onOperate,
  operationPending,
  refreshKey,
}) {
  const [documentId, setDocumentId] = useState(null);
  const [matching,setMatching]=useState(null);
  useEffect(()=>setMatching(null),[space,active]);
  const [sources, setSources] = useState([]);
  const [mounts, setMounts] = useState([]);
  const [id, setId] = useState("");
  const [prefix, setPrefix] = useState("");
  const [page, setPage] = useState(1);
  const [inventory, setInventory] = useState(null);
  const [rules, setRules] = useState([]);
  const [tab, setTab] = useState("entries");
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [job, setJob] = useState(null);
  const [pollError, setPollError] = useState("");
  const [pollEpoch, setPollEpoch] = useState(0);
  const [notice, setNotice] = useState("");
  const prepareRequest = useRef(null);
  useEffect(() => () => prepareRequest.current?.abort(), [id, active]);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const source = sources.find((s) => s.id === id);
  const pending =
    receipt && (!job || ["queued", "running"].includes(job.status));
  const refresh = () => setRevision((n) => n + 1);
  useEffect(() => {
    if (!active || !space) return;
    const controller = new AbortController();
    setListError("");
    Promise.all([
      api.request("/sources?space_id=" + encodeURIComponent(space), {
        signal: controller.signal,
      }),
      api.request("/source-mounts", { signal: controller.signal }),
    ])
      .then(([rows, aliases]) => {
        if (controller.signal.aborted) return;
        setSources(rows);
        setMounts(aliases.items);
        setId((old) =>
          rows.some((s) => s.id === old) ? old : rows[0]?.id || "",
        );
        setLoading(false);
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setListError(message(e));
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [api, space, active, revision]);
  useEffect(() => {
    if (!id || !active) return;
    const controller = new AbortController();
    setInventory(null);
    setRules([]);
    setError("");
    const query = new URLSearchParams({ page: String(page), page_size: "30" });
    if (prefix) query.set("relative_prefix", prefix);
    Promise.all([
      api.request(`/sources/${id}/entries?${query}`, {
        signal: controller.signal,
      }),
      api.request(`/sources/${id}/exclusions`, { signal: controller.signal }),
    ])
      .then(([rows, exclusions]) => {
        if (controller.signal.aborted) return;
        if (page > 1 && (page - 1) * 30 >= rows.total) {
          setPage(Math.max(1, Math.ceil(rows.total / 30)));
          return;
        }
        setInventory(rows);
        setRules(exclusions);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(message(e));
      });
    return () => controller.abort();
  }, [api, id, prefix, page, active, revision]);
  useEffect(() => {
    if (!receipt) return;
    const controller = new AbortController();
    let timer;
    let count = 0;
    async function poll() {
      try {
        const result = await api.request(`/jobs/${receipt.job_id}`, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setJob(result);
        setPollError("");
        if (!["queued", "running"].includes(result.status)) {
          refresh();
          onRefresh();
          return;
        }
        if (++count >= 300) {
          setPollError("任务仍在后台运行，已暂停自动查询。点击继续查询。");
          return;
        }
        timer = setTimeout(poll, 1000);
      } catch (e) {
        if (!controller.signal.aborted)
          setPollError(
            message(e) + " 任务可能仍在执行，请继续查询，不要重复提交。",
          );
      }
    }
    poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [api, receipt, pollEpoch]); // Receipt captures the source and action at submission.

  function choose(next) {
    setId(next);
    setPrefix("");
    setPage(1);
    setTab("entries");
    setError("");
    setNotice("");
  }
  function navigate(path) {
    setPrefix(path);
    setPage(1);
  }
  function open(value) {
    setError("");
    setDialog(value);
  }
  async function perform(action) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      if (e.name === "AbortError") return;
      if (alive.current)
        setError(
          message(e) +
            (!e.status ? " 请求可能已提交，请刷新核对后再操作。" : ""),
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  function track(result, title, name) {
    setJob(null);
    setPollError("");
    setReceipt({ ...result, title, name });
    setDialog(null);
    refresh();
  }
  async function scan(mode) {
    await perform(async () => {
      const result = await api.request(
        `/sources/${source.id}/${mode === "preview" ? "preview-scan" : "scan"}`,
        { method: "POST", ...(mode !== "preview" ? { body: { mode } } : {}) },
      );
      if (alive.current)
        track(
          result,
          { preview: "预扫描", initial: "首次导入", incremental: "增量扫描" }[
            mode
          ],
          source.name,
        );
    });
  }
  async function prepareExclusion(entry) {
    const controller = new AbortController();
    prepareRequest.current?.abort();
    prepareRequest.current = controller;
    await perform(async () => {
      const document = entry.document_id
        ? await api.request(`/documents/${entry.document_id}`, {
            signal: controller.signal,
          })
        : null;
      if (alive.current && !controller.signal.aborted)
        open({
          kind: "exclude",
          entry,
          version: document?.document_version ?? null,
          sourceId: id,
          sourceName: source.name,
        });
    });
  }
  const excludedPaths = new Set(rules.map((r) => r.relative_path));
  const ready =
    source?.health.mount_status === "ready" && source.status !== "disabled";
  const blocked = busy || pending || source?.status === "scanning";
  return (
    <section className="sources-view" hidden={!active} aria-label="只读来源">
      <div className="sources-heading">
        <div>
          <small>原地索引</small>
          <h1>来源</h1>
          <InfoTip>连接只读目录，保留原文件所在位置。</InfoTip>
        </div>
        <button
          className="primary"
          onClick={() => open({ kind: "create" })}
          disabled={busy}
        >
          <Plus size={18} />
          配置来源
        </button>
      </div>
      {listError && <Notice error>{listError}</Notice>}
      {notice && <Notice>{notice}</Notice>}
      <div className="sources-layout">
        <aside className="source-list" aria-label="来源列表">
          <div className="source-list-heading">
            <strong>{sources.length} 个来源</strong>
            <button aria-label="刷新来源" onClick={refresh}>
              <ArrowClockwise size={18} />
            </button>
          </div>
          {sources.map((s) => (
            <button
              key={s.id}
              className={s.id === id ? "source-card active" : "source-card"}
              aria-pressed={s.id === id}
              onClick={() => choose(s.id)}
            >
              <HardDrives size={22} />
              <span>
                <strong>{s.name}</strong>
                <small>{s.root_alias}</small>
                <small>{health[s.health.mount_status]}</small>
              </span>
            </button>
          ))}
          {!sources.length && (
            <p className="source-hint">
              {loading
                ? "正在读取来源…"
                : "尚未配置来源。只可选择管理员提供的只读挂载别名。"}
            </p>
          )}
        </aside>
        <div className="source-content">
          {!source ? (
            <Empty title="把资料留在原处">
              <InfoTip>
                首次可复制目录层次为逻辑目录，之后的人工整理独立于物理目录。
              </InfoTip>
              <InfoTip>外部原件不会被移动、覆盖或删除。</InfoTip>
            </Empty>
          ) : (
            <>
              <div className="source-summary">
                <div>
                  <h2>{source.name}</h2>
                  <span
                    className={
                      ready ? "source-status" : "source-status warning"
                    }
                  >
                    {health[source.health.mount_status]}
                  </span>
                  <p>
                    挂载别名：{source.root_alias} ·{" "}
                    {source.initial_import_policy === "tree"
                      ? "首次保留目录层次"
                      : "首次平铺归档"}
                  </p>
                </div>
                <div className="source-actions">
                  <button
                    disabled={!ready || blocked}
                    onClick={() => scan("preview")}
                  >
                    预扫描
                  </button>
                  <button
                    className="primary"
                    disabled={!ready || blocked}
                    onClick={() =>
                      open({
                        kind: source.initial_import_completed_at
                          ? "incremental"
                          : "initial",
                      })
                    }
                  >
                    {source.initial_import_completed_at
                      ? "增量扫描"
                      : "首次导入"}
                  </button>
                </div>
              </div>
              <p className="source-hint">
                最近成功扫描：{formatDate(source.last_successful_scan_at)} ·
                {source.scan_interval_minutes>0 ? `每 ${source.scan_interval_minutes} 分钟自动增量扫描` : "自动扫描已关闭"}
              </p>
              <SourceSchedule api={api} source={source} onSaved={refresh} />
              {!ready && (
                <Notice error>
                  {message({ code: source.health.error_code })}{" "}
                  已保存条目仍可浏览；离线不会把整库标记为失联。
                </Notice>
              )}
              {source.status === "error" && ready && (
                <Notice error>
                  上次扫描失败；当前挂载在线，请核对任务结果后重试。
                </Notice>
              )}
              {source.status === "scanning" && (
                <Notice>来源有扫描任务正在执行。刷新可核对状态。</Notice>
              )}
              <div className="source-tabs" role="group" aria-label="来源视图">
                <button
                  aria-pressed={tab === "entries"}
                  onClick={() => setTab("entries")}
                >
                  来源文件
                </button>
                <button
                  aria-pressed={tab === "rules"}
                  onClick={() => setTab("rules")}
                >
                  排除规则（{rules.length}）
                </button>
              </div>
              {error && <Notice error>{error}</Notice>}
              {tab === "entries" ? (
                <>
                  <nav className="source-path" aria-label="物理相对目录">
                    <button onClick={() => navigate("")}>来源根目录</button>
                    {prefix
                      .split("/")
                      .filter(Boolean)
                      .map((part, index, parts) => (
                        <span key={index}>
                          <CaretRight size={13} />
                          <button
                            onClick={() =>
                              navigate(parts.slice(0, index + 1).join("/"))
                            }
                          >
                            {part}
                          </button>
                        </span>
                      ))}
                  </nav>
                  <InfoTip>
                    按路径展示已登记文件；目录按钮可向下筛选。本页最多30项，空目录不在文件库存中。此处不接受拖入文件。
                  </InfoTip>
                  {!inventory ? (
                    <p role="status">
                      {error ? "读取未完成，请刷新重试。" : "正在读取文件…"}
                    </p>
                  ) : (
                    <>
                      <div className="source-entries">
                        {inventory.items.map((entry) => (
                          <article className="source-entry" key={entry.id}>
                            <FileText size={22} />
                            <div className="source-file">
                              <div className="source-file-path">
                                {entry.relative_path
                                  .split("/")
                                  .map((part, index, parts) =>
                                    index < parts.length - 1 ? (
                                      <span key={index}>
                                        <button
                                          onClick={() =>
                                            navigate(
                                              parts
                                                .slice(0, index + 1)
                                                .join("/"),
                                            )
                                          }
                                        >
                                          <Folder size={13} />
                                          {part}
                                        </button>
                                        <span>/</span>
                                      </span>
                                    ) : (
                                      <strong key={index}>{part}</strong>
                                    ),
                                  )}
                              </div>
                              <small>
                                {formatSize(entry.size_bytes)} ·{" "}
                                {excludedPaths.has(entry.relative_path)
                                  ? "已排除"
                                  : !ready
                                    ? "上次库存：" +
                                      (states[entry.status] || "状态未知")
                                    : states[entry.status] || "状态未知"}
                                {!ready ? " · 当前原件未核验，来源不可用" : ""}
                              </small>
                              {entry.status === "needs_match" && (
                                <small>
                                  {entry.document_id ? "原档案待重新关联。请在新发现的待匹配文件中选择此档案，或核对后取消索引。" : "存在匹配歧义，需要明确选择原档案或登记新档案；不会自动合并。"}
                                </small>
                              )}
                            </div>
                            {entry.document_id && (
                              <button
                                onClick={() => setDocumentId(entry.document_id)}
                              >
                                查看档案
                              </button>
                            )}
                            {entry.status==='needs_match' && !entry.document_id && <button disabled={!ready || busy || pending || excludedPaths.has(entry.relative_path)} onClick={()=>setMatching({sourceId:id,entry})}>处理待匹配文件</button>}
                            <button
                              disabled={
                                busy ||
                                pending ||
                                entry.is_managed ||
                                excludedPaths.has(entry.relative_path)
                              }
                              onClick={() => prepareExclusion(entry)}
                            >
                              取消索引
                            </button>
                          </article>
                        ))}
                      </div>
                      {!inventory.total && (
                        <Empty
                          title={
                            source.initial_import_completed_at
                              ? "此目录暂无已登记文件"
                              : "尚未首次导入"
                          }
                        >
                          <p>
                            预扫描仅统计；首次导入成功后，文件才会登记到这里。
                          </p>
                        </Empty>
                      )}
                      <div className="source-pagination">
                        <span>
                          共 {inventory.total} 项 · 第 {page} /{" "}
                          {Math.max(1, Math.ceil(inventory.total / 30))} 页
                        </span>
                        <button
                          disabled={page <= 1}
                          onClick={() => setPage((n) => n - 1)}
                        >
                          上一页
                        </button>
                        <button
                          disabled={page * 30 >= inventory.total}
                          onClick={() => setPage((n) => n + 1)}
                        >
                          下一页
                        </button>
                      </div>
                    </>
                  )}
                  <InfoTip>
                    待核验失联：一次完整在线扫描未找到。已确认失联：另一次独立成功扫描再次未找到。匹配歧义不会自动关联档案。
                  </InfoTip>
                </>
              ) : (
                <>
                  <InfoTip>
                    精确相对路径排除，后续扫描不再导入。移除规则不会自动恢复回收站中的档案。
                  </InfoTip>
                  {rules.map((rule) => (
                    <article className="source-entry" key={rule.id}>
                      <div className="source-file">
                        <strong>{rule.relative_path}</strong>
                        <small>
                          {rule.protected ? "已纳入托管，保留防重导规则" : rule.reason || "未填写原因"} ·{" "}
                          {formatDate(rule.created_at)}
                        </small>
                      </div>
                      <button
                        disabled={busy || pending || rule.protected}
                        onClick={() =>
                          open({ kind: "remove", rule, sourceId: id })
                        }
                      >
                        移除规则
                      </button>
                    </article>
                  ))}
                  {!rules.length && <Empty title="暂无排除规则" />}
                </>
              )}
            </>
          )}
        </div>
      </div>
      {receipt && (
        <div className="source-receipt" aria-label="来源任务结果">
          <strong>
            {receipt.name} · {receipt.title} ·{" "}
            {jobStates[job?.status] || "正在查询"}
          </strong>
          <small>
            任务 {receipt.job_id} ·
            回执保留于当前空间页面；切换空间或刷新后，需用任务ID查询接口。
          </small>
          {job && (
            <small>
              尝试 {job.attempts} / {job.max_attempts} · 进度{" "}
              {job.progress_done ?? 0} / {job.progress_total ?? "未知"}
            </small>
          )}
          {job?.result && (
            <div className="source-stats">
              {Object.entries(labels)
                .filter(([key]) => key in job.result)
                .map(([key, label]) => (
                  <span key={key}>
                    {label}
                    <strong>
                      {key.endsWith("bytes")
                        ? formatSize(job.result[key])
                        : job.result[key]}
                    </strong>
                  </span>
                ))}
            </div>
          )}
          {job?.result?.by_extension && (
            <p>
              {Object.entries(job.result.by_extension)
                .map(([ext, count]) => `${ext}：${count}`)
                .join(" · ") || "没有候选扩展名文件"}
            </p>
          )}
          {receipt.title === "预扫描" && (
            <p>
              候选扩展名统计是估计，不是快照，也不代表可以解析；不会创建档案。
            </p>
          )}
          {job?.result?.external_file_deleted === false && (
            <Notice>已取消索引并保存排除规则，外部原文件未删除。</Notice>
          )}
          {job?.error && (
            <Notice error>
              {message(job.error)}（{job.error.code}）
            </Notice>
          )}
          {pollError && <Notice error>{pollError}</Notice>}
          {pollError && (
            <button onClick={() => setPollEpoch((n) => n + 1)}>继续查询</button>
          )}
          {job?.status === "failed" &&
            job.error?.retryable &&
            job.attempts < job.max_attempts && (
              <button
                disabled={busy}
                onClick={() =>
                  perform(async () => {
                    await api.request(`/jobs/${receipt.job_id}/retry`, {
                      method: "POST",
                    });
                    setJob(null);
                    setPollEpoch((n) => n + 1);
                  })
                }
              >
                重试任务
              </button>
            )}
        </div>
      )}
      {documentId && (
        <Dialog title="来源档案详情" wide onClose={() => setDocumentId(null)}>
          <div className="source-document">
            <Detail
              api={api}
              id={documentId}
              types={catalog.types}
              folders={folders}
              tags={catalog.tags}
              definitions={catalog.definitions}
              onBack={() => setDocumentId(null)}
              refreshKey={`${revision}:${refreshKey}`}
              onOperate={onOperate}
              operationPending={operationPending}
            />
          </div>
        </Dialog>
      )}
      {dialog?.kind === "create" && (
        <SourceWizard
          mounts={mounts}
          folders={folders}
          busy={busy}
          error={error}
          onClose={() => {
            if (!busy) setDialog(null);
          }}
          onCreate={(body) =>
            perform(async () => {
              const result = await api.request("/sources", {
                method: "POST",
                body: { ...body, space_id: space },
              });
              if (alive.current) {
                setSources((rows) => [...rows, result]);
                choose(result.id);
                setDialog(null);
                refresh();
              }
            })
          }
        />
      )}
      {dialog &&
        ["initial", "incremental", "exclude", "remove"].includes(
          dialog.kind,
        ) && (
          <Dialog
            title={
              {
                initial: "确认首次导入",
                incremental: "确认增量扫描",
                exclude: "确认取消索引",
                remove: "确认移除排除规则",
              }[dialog.kind]
            }
            onClose={() => {
              if (!busy) setDialog(null);
            }}
          >
            {dialog.kind === "initial" ? (
              <>
                <p>
                  {source.name}：
                  {source.initial_import_policy === "tree"
                    ? "复制物理目录层次为逻辑目录"
                    : "平铺至所选逻辑目录"}
                  ，首批档案设为
                  {source.initial_triage_status === "filed"
                    ? "已归档"
                    : "待整理"}
                  。
                </p>
                <p>
                  只登记元数据和外部原件引用，不移动或复制原件。完成后不能重复首次导入；后续请使用增量扫描。
                </p>
              </>
            ) : dialog.kind === "incremental" ? (
              <>
                <p>
                  扫描 {source.name}
                  ，新增档案进入待整理；保留已有人工分类和字段，不重建逻辑目录。
                </p>
                <p>本次完整在线扫描可能推进缺失确认。原件不被修改。</p>
              </>
            ) : dialog.kind === "exclude" ? (
              <>
                <p className="source-confirm-path">
                  {dialog.sourceName} · {dialog.entry.relative_path}
                </p>
                <p>
                  将关联档案加入回收站，并按此精确路径排除后续扫描。外部原文件保留；档案版本变化时操作会拒绝。
                </p>
              </>
            ) : (
              <>
                <p className="source-confirm-path">
                  {dialog.rule.relative_path}
                </p>
                <p>
                  允许后续扫描重新发现此路径。此操作不会自动恢复已回收档案。
                </p>
              </>
            )}
            {error && <Notice error>{error}</Notice>}
            <div className="form-actions">
              <button disabled={busy} onClick={() => setDialog(null)}>
                取消
              </button>
              <button
                className="primary"
                disabled={
                  busy ||
                  (pending && ["initial", "incremental"].includes(dialog.kind))
                }
                onClick={() => {
                  if (["initial", "incremental"].includes(dialog.kind))
                    scan(dialog.kind);
                  else if (dialog.kind === "exclude")
                    perform(async () => {
                      const result = await api.request(
                        `/sources/${dialog.sourceId}/exclude-entry`,
                        {
                          method: "POST",
                          body: {
                            source_entry_id: dialog.entry.id,
                            expected_document_version: dialog.version,
                            reason: "用户在来源界面取消索引",
                          },
                        },
                      );
                      if (alive.current)
                        track(result, "取消索引", dialog.sourceName);
                    });
                  else
                    perform(async () => {
                      await api.request(
                        `/sources/${dialog.sourceId}/exclusions/${dialog.rule.id}`,
                        { method: "DELETE" },
                      );
                      if (alive.current) {
                        setDialog(null);
                        refresh();
                        setNotice("排除规则已移除；未自动恢复档案。");
                      }
                    });
                }}
              >
                {busy ? "正在提交…" : "确认执行"}
              </button>
            </div>
          </Dialog>
        )}
      {matching && active && <SourceMatch key={matching.entry.id} api={api} sourceId={matching.sourceId} entry={matching.entry} onClose={()=>setMatching(null)} onDone={()=>{setMatching(null);refresh();}} />}
    </section>
  );
}
