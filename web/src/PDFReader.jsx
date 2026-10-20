import { InfoTip } from "./ui.jsx";
import {useEffect,useRef,useState} from "react";
import {getDocument,GlobalWorkerOptions,TextLayer,version} from 'pdfjs-dist/legacy/build/pdf.mjs';
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url';
import './pdf-text-layer.css';
import {Notice} from './ui.jsx';
import {ApiError,message} from './api.js';

GlobalWorkerOptions.workerSrc=workerUrl;
const MAX_BYTES=64*1024*1024,MAX_PIXELS=8*1024*1024;
const assets=`/assets/pdfjs/${version}/`;

export default function PDFReader({documentId,revisionId}){
  const [pdf,setPdf]=useState(null),[error,setError]=useState(''),[page,setPage]=useState(1),[draft,setDraft]=useState('1');
  const [zoom,setZoom]=useState(1),[rotation,setRotation]=useState(0),[width,setWidth]=useState(500),[rendering,setRendering]=useState(false);
  const [passwordNeeded,setPasswordNeeded]=useState(false),[password,setPassword]=useState(''),[wrongPassword,setWrongPassword]=useState(false);
  const [pageError,setPageError]=useState(''),[textWarning,setTextWarning]=useState('');
  const [query,setQuery]=useState(''),[finding,setFinding]=useState(false),[findStatus,setFindStatus]=useState('');
  const pane=useRef(null),canvas=useRef(null),text=useRef(null),previous=useRef(null),unlock=useRef(null),searchEpoch=useRef(0);
  useEffect(()=>{
    const observer=new ResizeObserver(items=>setWidth(Math.max(120,items[0].contentRect.width-16)));
    observer.observe(pane.current);return ()=>observer.disconnect();
  },[]);
  useEffect(()=>{
    const abort=new AbortController();let task,timer,live=true,timedOut=false;
    setPdf(null);setError('');setPasswordNeeded(false);setPage(1);setDraft('1');
    const deadline=()=>{clearTimeout(timer);timer=setTimeout(()=>{timedOut=true;abort.abort();task?.destroy();if(live)setError('PDF读取超时，请重试或下载原件。');},45000);};
    deadline();
    (async()=>{
      const response=await fetch(`/api/v1/documents/${documentId}/download?expected_revision_id=${encodeURIComponent(revisionId)}`,{credentials:'same-origin',signal:abort.signal});
      if(!response.ok){const value=await response.json();throw new ApiError(response.status,value.error);}
      if(Number(response.headers.get('content-length'))>MAX_BYTES){await response.body?.cancel();throw Error('PDF_LIMIT');}
      const bytes=await response.arrayBuffer();if(bytes.byteLength>MAX_BYTES)throw Error('PDF_LIMIT');
      if(!live)return;
      task=getDocument({data:new Uint8Array(bytes),cMapUrl:assets+'cmaps/',cMapPacked:true,standardFontDataUrl:assets+'standard_fonts/',
        wasmUrl:assets+'wasm/',iccUrl:assets+'iccs/',enableXfa:false,maxImageSize:64*1024*1024,canvasMaxAreaInBytes:MAX_PIXELS*4,
        disableAutoFetch:true,disableStream:true,disableRange:true});
      task.onPassword=(callback,reason)=>{if(!live)return;clearTimeout(timer);unlock.current=value=>{setPasswordNeeded(false);deadline();callback(value);};setWrongPassword(reason===2);setPasswordNeeded(true);};
      const loaded=await task.promise;
      if(!live)return;
      if(loaded.numPages>10000){await loaded.loadingTask.destroy();throw Error('PDF_PAGE_LIMIT');}
      clearTimeout(timer);setPdf(loaded);
    })().catch(e=>{clearTimeout(timer);task?.destroy().catch(()=>{});if(live && !timedOut && e.name!=='AbortError')setError(e instanceof ApiError ? message(e) : e.message==='PDF_LIMIT' ? 'PDF超过64 MiB阅读上限，请下载原件。' : e.message==='PDF_PAGE_LIMIT' ? 'PDF超过10000页阅读上限，请下载原件。' : '无法读取此PDF，请下载原件核对文件。');});
    return ()=>{live=false;searchEpoch.current++;clearTimeout(timer);abort.abort();unlock.current=null;task?.destroy();};
  },[documentId,revisionId]);
  useEffect(()=>{
    if(!pdf)return;
    let live=true,renderTask,layer,pageObject,timer;
    setRendering(true);setPageError('');setTextWarning('');
    timer=setTimeout(()=>{renderTask?.cancel();pdf.loadingTask.destroy().catch(()=>{});if(live){setError('PDF页面处理超时，请关闭阅读器后重试或下载原件。');setPdf(null);setRendering(false);}},20000);
    (async()=>{
      await previous.current?.promise.catch(()=>{});
      if(!live)return;
      canvas.current.width=0;canvas.current.height=0;text.current.replaceChildren();
      pageObject=await pdf.getPage(page);if(!live)return;
      const angle=(pageObject.rotate+rotation)%360,base=pageObject.getViewport({scale:1,rotation:angle});
      const scale=Math.min(4,width/base.width,32768/Math.max(base.width,base.height))*zoom;
      const viewport=pageObject.getViewport({scale,rotation:angle});
      let output=Math.min(window.devicePixelRatio||1,2,Math.sqrt(MAX_PIXELS/(viewport.width*viewport.height)),8192/Math.max(viewport.width,viewport.height));
      if(!Number.isFinite(output) || output<=0)throw Error('Invalid page dimensions');
      const node=canvas.current;node.width=Math.max(1,Math.floor(viewport.width*output));node.height=Math.max(1,Math.floor(viewport.height*output));
      node.style.width=`${viewport.width}px`;node.style.height=`${viewport.height}px`;
      const parent=node.parentElement;parent.style.width=`${viewport.width}px`;parent.style.height=`${viewport.height}px`;
      text.current.replaceChildren();text.current.style.setProperty('--total-scale-factor',viewport.scale*viewport.userUnit);
      renderTask=pageObject.render({canvasContext:node.getContext('2d'),viewport,transform:[output,0,0,output,0,0]});previous.current=renderTask;
      await renderTask.promise;if(!live)return;
      const content=await pageObject.getTextContent();if(!live)return;
      const chars=content.items.reduce((n,item)=>n+(item.str?.length||0),0);
      if(content.items.length>10000 || chars>1024*1024)setTextWarning('本页文字量较大，仅显示页面图像。');
      else {layer=new TextLayer({textContentSource:content,container:text.current,viewport});await layer.render();}
      clearTimeout(timer);if(live)setRendering(false);
    })().catch(e=>{clearTimeout(timer);if(live && e.name!=='RenderingCancelledException'){setPageError('本页无法完整显示，可切换页面或下载原件。');setRendering(false);}});
    return ()=>{live=false;clearTimeout(timer);renderTask?.cancel();layer?.cancel();pageObject?.cleanup();};
  },[pdf,page,zoom,rotation,width]);
  function go(value){const number=Number(value);if(Number.isInteger(number) && number>=1 && number<=pdf.numPages){setPage(number);setDraft(String(number));}}
  async function find(event){
    event.preventDefault();const term=query.trim().toLocaleLowerCase();if(!term)return;
    const epoch=++searchEpoch.current;setFinding(true);setFindStatus('');const start=performance.now();let timer;
    try {
      for(let count=0;count<pdf.numPages;count++){
        if(searchEpoch.current!==epoch)return;
        if(performance.now()-start>60000){setFindStatus('查找已达一分钟，请缩小范围或使用正文检索。');return;}
        const number=(page+count)%pdf.numPages+1;setFindStatus(`正在查找第 ${number} 页…`);
        timer=setTimeout(()=>{pdf.loadingTask.destroy().catch(()=>{});if(searchEpoch.current===epoch){setPdf(null);setError('PDF文字处理超时，请关闭阅读器后重试或下载原件。');}},20000);
        const target=await pdf.getPage(number),content=await target.getTextContent();
        clearTimeout(timer);
        if(searchEpoch.current!==epoch)return;
        let value='';for(const item of content.items){value+=(item.str||'')+(item.hasEOL ? ' ' : '');if(value.length>2*1024*1024)throw Error('Search limit');}
        if(number!==page)target.cleanup();
        if(value.toLocaleLowerCase().includes(term)){go(number);setFindStatus(`匹配位于第 ${number} 页`);return;}
      }
      setFindStatus('未找到匹配文字；扫描页需要OCR正文才能检索。');
    }catch{if(searchEpoch.current===epoch)setFindStatus('无法完成本次查找，请使用正文检索或下载原件。');}
    finally{clearTimeout(timer);if(searchEpoch.current===epoch)setFinding(false);}
  }
  return <section className="pdf-reader" aria-label="完整PDF阅读">
    <h3>完整 PDF 阅读</h3>
    <InfoTip>逐页显示已核验的原件；不执行PDF脚本、附件或外部链接。最多64 MiB / 10000页，复杂页面可能降低分辨率，超过6400万像素的单幅图像可能省略。</InfoTip>
    {error && <Notice error>{error}</Notice>}
    {passwordNeeded && <form onSubmit={event=>{event.preventDefault();unlock.current?.(password);setPassword('');}}>
      {wrongPassword && <Notice error>密码不正确，请重试。</Notice>}
      <label>PDF密码<input type="password" value={password} autoComplete="off" onChange={event=>setPassword(event.target.value)} required /></label><button>解锁PDF</button>
    </form>}
    {!pdf && !passwordNeeded && !error && <p role="status">正在核验并读取PDF…</p>}
    {pdf && <>
      <div className="pdf-controls">
        <button disabled={page===1} onClick={()=>go(page-1)}>上一页PDF</button><span>第 {page} / {pdf.numPages} 页</span><button disabled={page===pdf.numPages} onClick={()=>go(page+1)}>下一页PDF</button>
        <form onSubmit={event=>{event.preventDefault();go(draft);}}><label>PDF页码<input type="number" min="1" max={pdf.numPages} value={draft} onChange={event=>setDraft(event.target.value)} /></label><button>跳转PDF页</button></form>
        <label>PDF缩放<select value={zoom} onChange={event=>setZoom(Number(event.target.value))}><option value="0.5">50%</option><option value="1">适合宽度</option><option value="1.5">150%</option><option value="2">200%</option></select></label>
        <button onClick={()=>setRotation(value=>(value+90)%360)}>旋转PDF</button>
      </div>
      <form className="pdf-find" onSubmit={find}><label>PDF查找文字<input value={query} maxLength={128} onChange={event=>setQuery(event.target.value)} required /></label><button disabled={finding}>查找下一处PDF文字</button>{finding && <button type="button" onClick={()=>{searchEpoch.current++;setFinding(false);setFindStatus('已停止查找');}}>停止PDF查找</button>}</form>
      {findStatus && <p role="status">{findStatus}</p>}{rendering && <p role="status">正在显示第 {page} 页…</p>}
      {pageError && <Notice error>{pageError}</Notice>}{textWarning && <Notice>{textWarning}</Notice>}
    </>}
    <div className="pdf-pane" ref={pane} hidden={!pdf} aria-busy={rendering}><div className="pdf-page"><canvas ref={canvas} aria-label={`PDF第${page}页`} /><div ref={text} className="textLayer" /></div></div>
  </section>;
}
