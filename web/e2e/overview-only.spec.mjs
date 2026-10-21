import { test, expect } from '@playwright/test';
import { login, createSpace, api } from './helpers.mjs';

async function upload(page,space,name,buffer,mimeType) {
  const response=await page.request.post('/api/v1/documents/upload',{
    headers:{'X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},
    multipart:{space_id:space,file:{name,mimeType,buffer}},
  });
  expect(response.status()).toBe(201);const doc=await response.json();
  await expect.poll(async()=> (await api(page,`/documents/${doc.document_id}`)).data.processing_status,{timeout:30000}).toBe('completed');
}
async function open(page,name,space) {
  await page.reload();await page.getByLabel('当前空间').selectOption(space);
  await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:name}).click();
}

test('detail shows only source-backed overview and an original entry on desktop and mobile',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const requests=[];page.on('request',r=>requests.push(new URL(r.url()).pathname));
  await login(page);await createSpace(page,'概览专用验收');
  const space=await page.getByLabel('当前空间').inputValue();
  await upload(page,space,'概览验收.md',Buffer.from('# 项目计划\n\n## 进展\n\n已经完成接口迁移。\n\n## 下一步\n\n完成移动端验收。'),'text/markdown');
  requests.length=0;
  await open(page,'概览验收.md',space);
  const detail=page.getByRole('region',{name:'档案详情',exact:true});
  const overview=detail.getByRole('region',{name:'文档概览',exact:true});
  await expect(overview.locator('.summary-points')).toContainText('接口迁移');
  await expect(detail.getByLabel('阅读格式')).toHaveCount(0);
  await expect(detail.getByRole('region',{name:'提取候选',exact:true})).toHaveCount(0);
  await expect(detail.getByRole('region',{name:'解析历史',exact:true})).toHaveCount(0);
  await expect(detail.locator('.reader-diagnostics,.summary-sources,.summary-actions')).toHaveCount(0);
  expect(requests.some(p=>p.endsWith('/candidates') || p.endsWith('/parse-runs'))).toBe(false);
  await detail.locator('.inspector').getByRole('button',{name:'查看源文件',exact:true}).click();
  const original=page.getByRole('dialog',{name:'源文件',exact:true});
  await expect(original).toBeVisible();
  await expect(original.getByText('概览验收.md',{exact:false}).first()).toBeVisible();
  await page.getByRole('button',{name:'关闭源文件',exact:true}).click();
  await page.screenshot({path:'/tmp/juanzhan-overview-only-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await detail.locator('.reader-toolbar').getByRole('button',{name:'查看源文件',exact:true}).click();
  await expect(original).toBeVisible();
  await page.getByRole('button',{name:'关闭源文件',exact:true}).click();
  await page.screenshot({path:'/tmp/juanzhan-overview-only-mobile.png'});
  expect(errors).toEqual([]);
});
