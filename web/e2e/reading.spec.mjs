import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { login, createSpace, api } from "./helpers.mjs";

async function upload(page, space, name, buffer, mimeType) {
  const response = await page.request.post("/api/v1/documents/upload", {
    headers: { "X-CSRF-Token": (await api(page, "/auth/session")).data.csrf_token },
    multipart: { space_id: space, file: { name, mimeType, buffer } },
  });
  expect(response.status()).toBe(201);
  const doc = await response.json();
  await expect.poll(async () => (await api(page, `/documents/${doc.document_id}`)).data.processing_status, { timeout: 30000 }).toBe("completed");
  return doc.document_id;
}
async function open(page, name, space) {
  await page.reload();
  await page.getByLabel("当前空间").selectOption(space);
  await page.getByRole("region", { name: "档案列表", exact: true }).getByRole("button").filter({ hasText: name }).click();
}

test('overview retains generic bullets and emphasis, with full source in a separate reader',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await login(page);await createSpace(page,'通用概览验证');
  const space=await page.getByLabel('当前空间').inputValue();
  await upload(page,space,'项目样例.html',Buffer.from('<html><body><h1>项目计划</h1><p>本轮聚焦迁移与验收。</p><h2>工作安排</h2><p>交付时间：周五完成接口迁移。</p><h2>资源与风险</h2><p>预算：1980元，分两期支付。</p><p>注意：保留已有原件。</p></body></html>'),'text/html');
  await open(page,'项目样例.html',space);
  const overview=page.getByRole('region',{name:'文档概览',exact:true});
  await expect(overview.locator('.summary-points > li')).toHaveCount(3);
  await expect(overview.locator('.summary-topic')).toHaveText(['项目计划','工作安排','资源与风险']);
  await expect(overview.locator('.summary-label').filter({hasText:'预算：'})).toBeVisible();
  await expect(overview.locator('.summary-points')).toContainText('1980元，分两期支付');
  await expect(overview.locator('.fact-grid,.fact-card,.summary-sources,.summary-actions')).toHaveCount(0);
  const tip=overview.getByRole('button',{name:'信息说明',exact:true}).first();
  await tip.hover();await expect(overview.getByRole('tooltip')).toBeVisible();
  await tip.focus();await tip.press('Escape');await expect(overview.getByRole('tooltip')).toHaveCount(0);
  await page.setViewportSize({width:390,height:844});await tip.click();
  await expect(overview.getByRole('tooltip')).toBeVisible();await tip.press('Escape');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('reprocessing preserves API history without exposing diagnostic panels in overview',async({page})=>{
  await login(page);await createSpace(page,'正文与历史保护');
  const space=await page.getByLabel('当前空间').inputValue();
  const docx=execFileSync('../.venv/bin/python',['-c',"import sys;sys.path.insert(0,'../tests');from format_samples import docx;sys.stdout.buffer.write(docx())"]);
  const id=await upload(page,space,'真实候选.docx',docx,'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
  const original=(await api(page,`/documents/${id}`)).data;
  expect((await api(page,`/documents/${id}/candidates`)).status).toBe(200);
  const requested=await api(page,`/documents/${id}/reprocess`,'POST',{expected_document_version:original.document_version,expected_revision_id:original.current_revision_id,request_id:'browser-history',force:true});
  expect(requested.status).toBe(202);
  await expect.poll(async()=>(await api(page,`/jobs/${requested.data.job_id}`)).data.status,{timeout:30000}).toBe('completed');
  expect((await api(page,`/documents/${id}/parse-runs`)).data.total).toBe(2);
  await open(page,'真实候选.docx',space);
  await expect(page.getByRole('region',{name:'文档概览',exact:true}).locator('.summary-points')).toContainText('项目规划');
  await expect(page.getByRole('region',{name:'提取候选',exact:true})).toHaveCount(0);
  await expect(page.getByRole('region',{name:'解析历史',exact:true})).toHaveCount(0);
  expect((await api(page,`/documents/${id}`)).data.current_revision_id).toBe(original.current_revision_id);
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'返回档案列表',exact:true}).click();
  await expect(page.getByRole('region',{name:'档案列表',exact:true})).toBeVisible();
});

test('long untrusted source text remains literal in platform source reader',async({page})=>{
  await login(page);await createSpace(page,'分页与安全文本');
  const space=await page.getByLabel('当前空间').inputValue();
  const text=Array.from({length:45},(_,i)=>`段落 ${String(i+1).padStart(2,'0')} <img src=x onerror=alert(1)>`).join('\n\n');
  await upload(page,space,'分页.txt',Buffer.from(text),'text/plain');await open(page,'分页.txt',space);
  await expect(page.getByRole('region',{name:'文档概览',exact:true}).locator('.summary-points')).toContainText('段落 01');
  await page.locator('.inspector').getByRole('button',{name:'查看源文件',exact:true}).click();
  const source=page.getByRole('dialog',{name:'源文件',exact:true});
  await expect(source.locator('pre')).toContainText('段落 45 <img src=x onerror=alert(1)>');
  await expect(source.locator('img,script,iframe,object,embed')).toHaveCount(0);
});

test('failed parsing has truthful empty overview and session expiry returns to login',async({page})=>{
  await login(page);await createSpace(page,'失败正文');
  const space=await page.getByLabel('当前空间').inputValue();
  const response=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},multipart:{space_id:space,file:{name:'损坏.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\ninvalid')}}});
  expect(response.status()).toBe(201);const id=(await response.json()).document_id;
  await expect.poll(async()=>(await api(page,`/documents/${id}`)).data.processing_status).toBe('failed');
  await open(page,'损坏.pdf',space);
  await expect(page.getByRole('region',{name:'文档概览',exact:true})).toContainText('暂无内容概览');
  await api(page,'/auth/logout','POST');
  await page.getByRole('button',{name:'刷新档案详情',exact:true}).click();
  await expect(page.getByLabel('密码',{exact:true})).toBeVisible();
});
