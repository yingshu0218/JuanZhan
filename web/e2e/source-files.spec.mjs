import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { login,createSpace,api } from './helpers.mjs';

test('native source opens inside platform and cache cleanup preserves its original',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await login(page);await createSpace(page,'源文件阅读与缓存验收');
  const space=await page.getByLabel('当前空间').inputValue();
  const buffer=await readFile(process.env.JUANZHAN_E2E_NATIVE_FIXTURE);
  const response=await page.request.post('/api/v1/documents/upload',{
    headers:{'X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},
    multipart:{space_id:space,file:{name:'源表.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer}},
  });
  expect(response.status()).toBe(201);const saved=await response.json();
  await expect.poll(async()=>(await api(page,`/documents/${saved.document_id}`)).data.processing_status,{timeout:30000}).toBe('completed');
  const before=(await api(page,`/documents/${saved.document_id}`)).data;
  await page.reload();await page.getByLabel('当前空间').selectOption(space);
  await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:'源表.xlsx'}).click();
  const detail=page.getByRole('region',{name:'档案详情',exact:true});
  await detail.locator('.inspector').getByRole('button',{name:'查看源文件',exact:true}).click();
  const source=page.getByRole('dialog',{name:'源文件',exact:true});
  await expect(source.getByLabel('源文件版本')).toHaveValue(before.current_revision_id);
  await expect(source.locator('canvas')).toBeVisible({timeout:30000});
  await expect(source.getByLabel('PDF页码')).toHaveValue('1');
  await page.screenshot({path:'/tmp/juanzhan-native-source-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(source.locator('canvas')).toBeVisible();
  await page.screenshot({path:'/tmp/juanzhan-native-source-mobile.png'});
  await page.getByRole('button',{name:'关闭源文件',exact:true}).click();
  await page.getByRole('button',{name:'系统设置',exact:true}).click();
  await page.getByRole('button',{name:'存储管理',exact:true}).click();
  const storage=page.getByRole('dialog',{name:'存储管理',exact:true});
  await expect(storage.getByText('可重建阅读预览',{exact:true})).toBeVisible();
  await expect(storage.getByRole('button',{name:'开始清理',exact:true})).toBeDisabled();
  await storage.getByRole('checkbox').check();
  await storage.getByRole('button',{name:'开始清理',exact:true}).click();
  await expect.poll(async()=>(await api(page,'/system/storage')).data.reading_preview_count).toBe(0);
  await expect(storage.locator('dt').filter({hasText:'可重建阅读预览'}).locator('+ dd')).toContainText('0 份');
  const after=(await api(page,`/documents/${saved.document_id}`)).data;
  expect(after.document_version).toBe(before.document_version);
  expect(after.current_revision_id).toBe(before.current_revision_id);
  const original=await page.request.get(`/api/v1/documents/${saved.document_id}/download`);
  expect(await original.body()).toEqual(buffer);
  await page.screenshot({path:'/tmp/juanzhan-storage-mobile.png'});
  expect(errors).toEqual([]);
});
