import {test,expect} from "@playwright/test";
import {execFileSync} from "node:child_process";
import {readFile} from "node:fs/promises";
import {login,createSpace,api} from "./helpers.mjs";
test("real original download, passive preview and return on desktop and mobile",async({page})=>{
  const errors=[];page.on("pageerror",e=>errors.push(e.message));page.on("console",e=>{if(e.type()==="error")errors.push(e.text());});
  await login(page);await createSpace(page,"原件安全验证");
  const space=(await api(page,"/spaces")).data.find(s=>s.name==="原件安全验证").id;
  const buffer=execFileSync("../.venv/bin/python",["-c","import sys;sys.path.insert(0,'../tests');from format_samples import raster_sample;sys.stdout.buffer.write(raster_sample('PDF'))"]);
  const receipt=await page.request.post("/api/v1/documents/upload",{headers:{"X-CSRF-Token":(await api(page,"/auth/session")).data.csrf_token},multipart:{space_id:space,file:{name:"安全原件.pdf",mimeType:"application/pdf",buffer}}});
  expect(receipt.status()).toBe(201);const document=await receipt.json();
  await expect.poll(async()=>(await api(page,`/documents/${document.document_id}`)).data.processing_status,{timeout:30000}).toBe("completed");
  await page.reload();await page.getByLabel("当前空间").selectOption(space);
  await page.getByRole("region",{name:"档案列表",exact:true}).getByRole("button").filter({hasText:"安全原件"}).click();
  await page.getByRole("button",{name:"关联原文件",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"关联原文件",exact:true});
  await expect(dialog.getByRole("img",{name:"原件预览图 1",exact:true})).toBeVisible();
  await expect.poll(()=>dialog.getByRole("img",{name:"原件预览图 1",exact:true}).evaluate(img=>img.complete&&img.naturalWidth>0)).toBe(true);
  const downloadEvent=page.waitForEvent("download");await dialog.getByRole("button",{name:"下载当前原件",exact:true}).click();
  const download=await downloadEvent;expect(download.suggestedFilename()).toBe("安全原件.pdf");expect(await readFile(await download.path())).toEqual(buffer);
  await dialog.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  const pdf=page.getByRole('region',{name:'完整PDF阅读',exact:true});
  await expect(pdf.getByText('第 1 / 1 页',{exact:true})).toBeVisible();
  await expect.poll(()=>pdf.locator('canvas').evaluate(node=>{if(!node.width||!node.height)return false;const data=node.getContext('2d').getImageData(0,0,node.width,node.height).data;let dark=0;for(let i=0;i<data.length;i+=40)if(data[i+3]>0&&data[i]<200&&data[i+1]<200&&data[i+2]<200)dark++;return dark>10;})).toBe(true);
  await dialog.getByRole('button',{name:'关闭完整PDF阅读',exact:true}).click();
  await page.screenshot({path:"/tmp/juanzhan-t32-desktop.png"});
  await page.setViewportSize({width:390,height:844});await expect(dialog).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"/tmp/juanzhan-t32-mobile.png"});
  await dialog.getByRole("button",{name:"关闭关联原文件"}).click();
  await expect(page.getByRole("heading",{name:"内容概览",exact:true})).toBeVisible();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);expect(errors).toEqual([]);
});

test("untrusted HTML stays a download and cannot execute in the original dialog",async({page})=>{
  await login(page);await createSpace(page,"恶意HTML隔离");
  const space=(await api(page,"/spaces")).data.find(s=>s.name==="恶意HTML隔离").id;
  const content='<html><script>window.originalExecuted=true</script><img src="https://invalid.example/track"></html>';
  const requested=[];page.on("request",request=>{if(request.url().includes("invalid.example"))requested.push(request.url());});
  const response=await page.request.post("/api/v1/documents/upload",{headers:{"X-CSRF-Token":(await api(page,"/auth/session")).data.csrf_token},multipart:{space_id:space,file:{name:"隔离原件.html",mimeType:"text/html",buffer:Buffer.from(content)}}});
  expect(response.status()).toBe(201);await page.reload();await page.getByLabel("当前空间").selectOption(space);
  await page.getByRole("region",{name:"档案列表",exact:true}).getByRole("button").filter({hasText:"隔离原件"}).click();
  await page.getByRole("button",{name:"关联原文件",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"关联原文件",exact:true});
  await expect(dialog.getByText("暂无可用缩略图",{exact:false})).toBeVisible();
  await expect(dialog.locator("iframe,object,embed,script")).toHaveCount(0);
  const event=page.waitForEvent("download");await dialog.getByRole("button",{name:"下载当前原件",exact:true}).click();
  const download=await event;expect((await readFile(await download.path())).toString()).toBe(content);
  expect(await page.evaluate(()=>window.originalExecuted)).toBeUndefined();expect(requested).toEqual([]);
});


test("historical managed original downloads exact prior bytes from version list",async({page})=>{
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await login(page);await createSpace(page,"历史原件验证");
  const space=await page.getByLabel("当前空间").inputValue();
  const buffer=Buffer.from("历史原件字节，不应被新版本替代");
  const response=await page.request.post("/api/v1/documents/upload",{headers:{"X-CSRF-Token":(await api(page,"/auth/session")).data.csrf_token},multipart:{space_id:space,file:{name:"历史原件.txt",mimeType:"text/plain",buffer}}});
  expect(response.status()).toBe(201);const receipt=await response.json();
  await expect.poll(async()=>(await api(page,`/documents/${receipt.document_id}`)).data.processing_status).toBe("completed");
  // Use the real revision service against this disposable test server's private store.
  const directory=(await readFile(process.env.JUANZHAN_E2E_ARCHIVE_POINTER,"utf8")).trim();
  execFileSync("../.venv/bin/python",["-c","import sys;from pathlib import Path;sys.path[:0]=['../tests','../services'];from test_parsing import append;from juanzhan.config import Settings;append(Settings(Path(sys.argv[1]),''),sys.argv[2],b'new current bytes')",directory,receipt.document_id]);
  await page.reload();await page.getByLabel("当前空间").selectOption(space);
  await page.getByRole("region",{name:"档案列表",exact:true}).getByRole("button").filter({hasText:"历史原件.txt"}).click();
  await page.getByRole("button",{name:"关联原文件",exact:true}).click();
  const dialog=page.getByRole("dialog",{name:"关联原文件",exact:true});
  await dialog.getByText("已登记原件版本",{exact:true}).click();
  const event=page.waitForEvent("download");await dialog.getByRole("button",{name:"下载版本 1",exact:true}).click();
  const downloaded=await event;expect(downloaded.suggestedFilename()).toBe("历史原件.txt");
  expect(await readFile(await downloaded.path())).toEqual(buffer);
  const currentEvent=page.waitForEvent("download");await dialog.getByRole("button",{name:"下载当前原件",exact:true}).click();
  expect((await readFile(await (await currentEvent).path())).toString()).toBe("new current bytes");
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"/tmp/juanzhan-history-original-mobile.png"});
  expect(errors).toEqual([]);
});

test("complete PDF pages, selection, rotation, zoom and search without executing document actions",async({page})=>{
  await page.addInitScript(()=>Object.defineProperty(window,'devicePixelRatio',{get:()=>4}));
  const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',e=>{if(e.type()==='error')errors.push(e.text());});
  page.on('request',request=>{if(request.url().includes('invalid.example'))external.push(request.url());});
  await login(page);await createSpace(page,'完整PDF验证');
  const space=await page.getByLabel('当前空间').inputValue();
  const buffer=execFileSync('../.venv/bin/python',['-c',"import sys;from io import BytesIO;sys.path.insert(0,'../tests');from format_samples import pdf;from pypdf import PdfReader,PdfWriter;from pypdf.annotations import Link;w=PdfWriter();w.append_pages_from_reader(PdfReader(BytesIO(pdf(pages=8))));w.add_js(\"globalThis.pdfExecuted=true;fetch('https://invalid.example/pdf-script')\");w.add_annotation(0,Link(rect=(72,700,300,730),url='https://invalid.example/pdf-link'));out=BytesIO();w.write(out);sys.stdout.buffer.write(out.getvalue())"]);
  const response=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},multipart:{space_id:space,file:{name:'完整八页.pdf',mimeType:'application/pdf',buffer}}});
  expect(response.status()).toBe(201);const receipt=await response.json();
  await expect.poll(async()=>(await api(page,`/documents/${receipt.document_id}`)).data.processing_status,{timeout:30000}).toBe('completed');
  await page.reload();await page.getByLabel('当前空间').selectOption(space);
  await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:'完整八页.pdf'}).click();
  await page.getByRole('button',{name:'关联原文件',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'关联原文件',exact:true});
  await dialog.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  const reader=page.getByRole('region',{name:'完整PDF阅读',exact:true});
  await expect(reader.getByText('第 1 / 8 页',{exact:true})).toBeVisible();
  await expect(reader.locator('.textLayer')).toContainText('Real PDF page 1');
  await reader.getByLabel('PDF页码',{exact:true}).fill('8');await reader.getByRole('button',{name:'跳转PDF页',exact:true}).click();
  await expect(reader.locator('.textLayer')).toContainText('Real PDF page 8');
  expect(await reader.locator('canvas').evaluate(node=>node.width>100&&node.height>100)).toBe(true);
  const selected=await reader.locator('.textLayer').evaluate(node=>{const range=document.createRange();range.selectNodeContents(node);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);return selection.toString();});
  expect(selected).toContain('Real PDF page 8');
  await reader.getByRole('button',{name:'旋转PDF',exact:true}).click();
  await expect(reader.locator('.textLayer')).toHaveAttribute('data-main-rotation','90');
  const beforeZoom=await reader.locator('canvas').evaluate(node=>parseFloat(node.style.width));
  await reader.getByRole('combobox',{name:'PDF缩放',exact:true}).selectOption('2');
  await expect.poll(()=>reader.locator('canvas').evaluate(node=>parseFloat(node.style.width))).toBeGreaterThan(beforeZoom*1.9);
  await expect.poll(()=>reader.locator('canvas').evaluate(node=>node.width*node.height<=8*1024*1024)).toBe(true);
  await reader.getByLabel('PDF查找文字',{exact:true}).fill('Real PDF page 3');
  await reader.getByRole('button',{name:'查找下一处PDF文字',exact:true}).click();
  await expect(reader.getByText('匹配位于第 3 页',{exact:true})).toBeVisible();
  await expect(reader.locator('.textLayer')).toContainText('Real PDF page 3');
  await expect(reader.locator('iframe,object,embed,a')).toHaveCount(0);
  expect(await page.evaluate(()=>window.pdfExecuted)).toBeUndefined();expect(external).toEqual([]);
  for(let turn=0;turn<3;turn++)await reader.getByRole('button',{name:'旋转PDF',exact:true}).click();
  await reader.getByRole('combobox',{name:'PDF缩放',exact:true}).selectOption('1');
  await expect(reader.locator('.textLayer')).toHaveAttribute('data-main-rotation','0');
  await expect(reader.locator('.textLayer')).toContainText('Real PDF page 3');
  await page.screenshot({path:'/tmp/juanzhan-full-pdf-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>reader.locator('canvas').evaluate(node=>parseFloat(node.style.width))).toBeLessThan(800);
  await expect(reader.locator('.textLayer')).toContainText('Real PDF page 3');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'/tmp/juanzhan-full-pdf-mobile.png'});
  await dialog.getByRole('button',{name:'关闭完整PDF阅读',exact:true}).click();
  await dialog.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  await expect(reader.locator('.textLayer')).toContainText('Real PDF page 1');
  expect(errors).toEqual([]);
});

async function openPDFOriginal(page,name,buffer,authenticated=false){
  if(!authenticated)await login(page);await createSpace(page,name);
  const space=await page.getByLabel('当前空间').inputValue();
  const response=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},multipart:{space_id:space,file:{name:name+'.pdf',mimeType:'application/pdf',buffer}}});
  expect(response.status()).toBe(201);const receipt=await response.json();
  await page.reload();await page.getByLabel('当前空间').selectOption(space);
  await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:name+'.pdf'}).click();
  await page.getByRole('button',{name:'关联原文件',exact:true}).click();return receipt;
}

test('PDF password stays in browser and wrong password can be corrected',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const buffer=execFileSync('../.venv/bin/python',['-c',"import sys;sys.path.insert(0,'../tests');from format_samples import pdf;sys.stdout.buffer.write(pdf(encrypted=True))"]);
  await openPDFOriginal(page,'加密PDF阅读',buffer);
  await page.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  const reader=page.getByRole('region',{name:'完整PDF阅读',exact:true});
  await reader.getByLabel('PDF密码',{exact:true}).fill('wrong');await reader.getByRole('button',{name:'解锁PDF',exact:true}).click();
  await expect(reader.getByText('密码不正确，请重试。',{exact:true})).toBeVisible();
  await reader.getByLabel('PDF密码',{exact:true}).fill('secret');await reader.getByRole('button',{name:'解锁PDF',exact:true}).click();
  await expect(reader.locator('.textLayer')).toContainText('Real PDF page 1');
  await expect(reader.getByLabel('PDF密码',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'关闭完整PDF阅读',exact:true}).click();
  await page.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  await expect(reader.getByLabel('PDF密码',{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('PDF revision conflicts and corrupt files fail without displaying uncertain content',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const buffer=execFileSync('../.venv/bin/python',['-c',"import sys;sys.path.insert(0,'../tests');from format_samples import pdf;sys.stdout.buffer.write(pdf())"]);
  const receipt=await openPDFOriginal(page,'PDF版本保护',buffer);
  const directory=(await readFile(process.env.JUANZHAN_E2E_ARCHIVE_POINTER,'utf8')).trim();
  execFileSync('../.venv/bin/python',['-c',"import sys;from pathlib import Path;sys.path[:0]=['../tests','../services'];from test_parsing import append;from juanzhan.config import Settings;append(Settings(Path(sys.argv[1]),''),sys.argv[2],b'new current original')",directory,receipt.document_id]);
  await page.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  let reader=page.getByRole('region',{name:'完整PDF阅读',exact:true});
  await expect(reader.getByText('原件版本已改变，请刷新档案。',{exact:true})).toBeVisible();
  await expect(reader.locator('.textLayer')).toBeEmpty();
  await page.getByRole('button',{name:'关闭关联原文件',exact:true}).click();
  await openPDFOriginal(page,'损坏PDF阅读',Buffer.from('%PDF-1.7\nnot a valid PDF document'),true);
  await page.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  reader=page.getByRole('region',{name:'完整PDF阅读',exact:true});
  await expect(reader.getByText('无法读取此PDF，请下载原件核对文件。',{exact:true})).toBeVisible();
  await expect(reader.locator('.textLayer')).toBeEmpty();
  await expect.poll(()=>page.workers().length).toBe(0);expect(errors).toEqual([]);
});

test('rapid PDF reader cancellation does not keep workers or render into closed dialogs',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const buffer=execFileSync('../.venv/bin/python',['-c',"import sys;sys.path.insert(0,'../tests');from format_samples import pdf;sys.stdout.buffer.write(pdf(pages=10))"]);
  await openPDFOriginal(page,'PDF取消与重开',buffer);
  for(let index=0;index<3;index++){
    await page.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
    await page.getByRole('button',{name:'关闭完整PDF阅读',exact:true}).click();
  }
  await page.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  const reader=page.getByRole('region',{name:'完整PDF阅读',exact:true});
  await expect(reader.locator('.textLayer')).toContainText('Real PDF page 1');
  await reader.getByRole('button',{name:'下一页PDF',exact:true}).click();
  await page.getByRole('button',{name:'关闭关联原文件',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect.poll(()=>page.workers().length).toBe(0);expect(errors).toEqual([]);
});

test('PDF page budget rejects oversized page trees',async({page})=>{
  const buffer=execFileSync('../.venv/bin/python',['-c',"import sys;sys.path.insert(0,'../tests');from format_samples import pdf;sys.stdout.buffer.write(pdf(blank=True,pages=10001))"],{maxBuffer:8*1024*1024});
  await openPDFOriginal(page,'PDF页数预算',buffer);
  await page.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  const reader=page.getByRole('region',{name:'完整PDF阅读',exact:true});
  await expect(reader.getByText('PDF超过10000页阅读上限，请下载原件。',{exact:true})).toBeVisible();
  await expect(reader.locator('.textLayer')).toBeEmpty();
  await expect.poll(()=>page.workers().length).toBe(0);
});

test('Chinese PDF text uses bundled local CMaps and stays selectable',async({page})=>{
  const requests=[],errors=[];page.on('request',request=>{if(request.url().includes('/cmaps/'))requests.push(request.url());});page.on('pageerror',error=>errors.push(error.message));
  const script="from pypdf import PdfWriter;from pypdf.generic import DictionaryObject as D,NameObject as N,ArrayObject as A,NumberObject as I,TextStringObject as T,DecodedStreamObject;from io import BytesIO;import sys;w=PdfWriter();p=w.add_blank_page(width=612,height=792);cid=D({N('/Type'):N('/Font'),N('/Subtype'):N('/CIDFontType0'),N('/BaseFont'):N('/STSong-Light'),N('/CIDSystemInfo'):D({N('/Registry'):T('Adobe'),N('/Ordering'):T('GB1'),N('/Supplement'):I(4)})});font=D({N('/Type'):N('/Font'),N('/Subtype'):N('/Type0'),N('/BaseFont'):N('/STSong-Light'),N('/Encoding'):N('/UniGB-UCS2-H'),N('/DescendantFonts'):A([w._add_object(cid)])});p[N('/Resources')]=D({N('/Font'):D({N('/F1'):w._add_object(font)})});s=DecodedStreamObject();s.set_data(b'BT /F1 20 Tf 72 720 Td <'+'中文档案测试'.encode('utf-16-be').hex().encode()+b'> Tj ET');p[N('/Contents')]=w._add_object(s);out=BytesIO();w.write(out);sys.stdout.buffer.write(out.getvalue())";
  const buffer=execFileSync('../.venv/bin/python',['-c',script]);
  await openPDFOriginal(page,'中文PDF映射',buffer);
  await page.getByRole('button',{name:'阅读完整PDF',exact:true}).click();
  const reader=page.getByRole('region',{name:'完整PDF阅读',exact:true});
  await expect(reader.locator('.textLayer')).toContainText('中文档案测试');
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every(url=>url.startsWith('http://127.0.0.1:8767/assets/pdfjs/6.4.299/cmaps/'))).toBe(true);
  expect(errors).toEqual([]);
});
