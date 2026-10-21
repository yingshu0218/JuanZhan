import { useEffect, useState } from 'react';
import { FileText, Tray, Clock, WarningCircle, ArrowRight, ArrowClockwise } from '@phosphor-icons/react';
import { Notice, InfoTip, formatDate, formatSize } from './ui.jsx';
import { message } from './api.js';

export function SystemOverview({ api, spaces, refreshKey, onBrowse, onDocument, onTasks, onImport }) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(''); setData(null);
    Promise.all([
      api.request('/system/summary', { signal: controller.signal }),
      api.request('/documents?page_size=6&sort=-imported_at', { signal: controller.signal }),
      ...['queued', 'running'].map(status => api.request(`/jobs?status=${status}&page_size=1`, { signal: controller.signal })),
    ]).then(([summary, recent, queued, running]) => {
      if (!controller.signal.aborted) setData({ ...summary, recent: recent.items, queued: queued.total, running: running.total });
    }).catch(e => { if (!controller.signal.aborted) setError(message(e)); });
    return () => controller.abort();
  }, [api, refreshKey, attempt]);
  const metrics = data ? [
    { label: '全部档案', value: data.documents_total, icon: FileText },
    { label: '待整理', value: data.inbox_total, icon: Tray },
    { label: '正在处理', value: data.running, icon: Clock, action: onTasks },
    { label: '失败任务', value: data.failed_jobs, icon: WarningCircle, action: onTasks },
  ] : [];
  return <section className="system-overview" aria-label="系统概览">
    <header className="overview-heading"><div><span className="overview-eyebrow">全部空间</span><h1>系统概览</h1></div>
      <div><button aria-label="刷新系统概览" onClick={() => setAttempt(n => n + 1)}><ArrowClockwise size={19} /></button><button className="primary" onClick={() => onBrowse('all')}>进入档案列表 <ArrowRight size={17} /></button></div>
    </header>
    {error ? <Notice error>{error}<button onClick={() => setAttempt(n => n + 1)}>重试</button></Notice> : !data ? <p role="status">正在读取系统概览…</p> : <>
      <div className="overview-metrics">{metrics.map(({ label, value, icon: Icon, action }) => { const Tag = action ? 'button' : 'div'; return <Tag key={label} onClick={action} className="overview-metric"><Icon size={22} /><span>{label}</span><strong>{value}</strong></Tag>; })}</div>
      <div className="overview-layout">
        <section className="overview-recent" aria-label="近期导入"><div className="overview-section-heading"><h2>近期导入</h2><button className="text-action" onClick={() => onBrowse('all')}>当前空间档案 <ArrowRight size={15} /></button></div>
          {data.recent.length ? <div className="overview-recent-list">{data.recent.map(doc => <button key={doc.id} onClick={() => onDocument(doc)} className="overview-document"><FileText size={23} /><div><strong>{doc.title}</strong>{doc.overview_excerpt && <p>{doc.overview_excerpt}</p>}<small>{spaces.find(space => space.id === doc.space_id)?.name || '空间'} · {formatSize(doc.size_bytes)} · {formatDate(doc.imported_at)}</small></div><ArrowRight size={17} /></button>)}</div> : <div className="overview-no-files"><FileText size={32} /><h3>还没有档案</h3><button onClick={onImport}>导入文件</button></div>}
        </section>
        <aside className="overview-side">
          <section><div className="overview-section-heading"><h2>处理任务</h2><button className="text-action" onClick={onTasks}>查看任务</button></div><dl><div><dt>排队中</dt><dd>{data.queued}</dd></div><div><dt>处理中</dt><dd>{data.running}</dd></div><div><dt>失败任务 <InfoTip>包含历史失败任务，具体状态与重试入口请查看任务中心。</InfoTip></dt><dd>{data.failed_jobs}</dd></div></dl></section>
          <section><div className="overview-section-heading"><h2>资料来源</h2><InfoTip>汇总所有空间的有效档案，不含回收站；来源离线状态来自最近扫描记录。</InfoTip></div><dl><div><dt>上传档案</dt><dd>{data.managed_total}</dd></div><div><dt>外部来源档案</dt><dd>{data.external_total}</dd></div><div><dt>离线来源</dt><dd>{data.offline_sources}</dd></div><div><dt>空间</dt><dd>{spaces.length}</dd></div></dl></section>
        </aside>
      </div>
    </>}
  </section>;
}
