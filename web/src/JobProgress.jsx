const labels = { copy: "保存服务器副本", render: "生成源文件阅读预览", validate: "读取并校验原件", submit: "提交转换任务", extract: "提取正文 / OCR（如启用）", assets: "保存派生文件", publish: "写入正文与候选", process: "执行处理" };
const states = { pending: "等待开始", running: "处理中", completed: "已完成", failed: "失败", discarded: "未发布" };

export function JobProgress({ job }) {
  const steps = job.steps || [];
  const completed = steps.filter(step => step.status === "completed").length;
  return <span className="job-progress">
    {job.document_name && <strong className="job-filename">{job.document_name}</strong>}
    {steps.length ? <>
      <span className="job-overall">已完成步骤 {completed} / {steps.length}<progress aria-label="文件总体步骤进度" value={completed} max={steps.length} /></span>
      <span className="job-steps" role="list" aria-label="按顺序排列的处理步骤">{steps.map((step, index) => {
        const known = Number.isSafeInteger(step.done) && Number.isSafeInteger(step.total) && step.total > 0;
        const value = step.status === "completed" ? 1 : known ? Math.min(1, step.done / step.total) : step.status === "running" ? undefined : 0;
        const label = step.code === "publish" && ["document_snapshot","document_reading_preview"].includes(job.target_type) ? "保存并发布结果" : labels[step.code] || "执行处理";
        return <span role="listitem" className={"job-step " + step.status} key={step.code}>
          <span className="job-step-label"><span>{index + 1}. {label}</span><small>{states[step.status] || "未知"}{known ? ` · ${step.done} / ${step.total}` : step.status === "running" ? " · 总量未知" : ""}</small></span>
          <progress aria-label={label + "进度"} value={value} max={1} />
        </span>;
      })}</span>
    </> : <span className="muted">此历史任务未记录分步进度。</span>}
  </span>;
}
