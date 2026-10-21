import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {login,createSpace,api} from './helpers.mjs';

test('legacy Office and RTF show generic overviews, Unicode and source navigation',async({page})=>{
  test.setTimeout(180000);
  test.skip(!process.env.JUANZHAN_E2E_CONVERTER_IMAGE || !process.env.JUANZHAN_EXTRA_FORMAT_FIXTURES,'Requires pinned legacy image and real fixtures');
  const root=process.env.JUANZHAN_EXTRA_FORMAT_FIXTURES;
  const cases=['testWORD_various.doc','testEXCEL_macro.xls','testPPT_various.ppt','testRTFUnicodeGothic.rtf'];
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await login(page);await createSpace(page,'旧Office解析验收');const space=await page.getByLabel('当前空间').inputValue();
  for(const name of cases){
    const session=await api(page,'/auth/session');
    const response=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':session.data.csrf_token},multipart:{space_id:space,file:{name,mimeType:'application/octet-stream',buffer:readFileSync(join(root,name))}}});
    expect(response.status(),name).toBe(201);const saved=await response.json();
    await expect.poll(async()=> (await api(page,`/documents/${saved.document_id}`)).data.processing_status,{timeout:30000,message:name}).toBe('completed');
    await page.reload();await page.getByLabel('当前空间').selectOption(space);
    await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:name}).click();
    const reader=page.getByRole('region',{name:'正文阅读',exact:true});await expect(reader.locator('.summary-points > li').first()).toBeVisible();
    if(name==='testPPT_various.ppt')await expect(reader.locator('.summary-points')).toContainText('Row 1');
    expect(await reader.locator('.summary-points').innerText()).not.toContain('\uFFFD');
    const source=reader.locator('.summary-points > li').first();await source.locator('summary').click();
    await source.getByRole('button',{name:'查看对应正文',exact:true}).first().click();await expect(reader.locator('.content-blocks')).toBeVisible();
    await reader.getByLabel('阅读格式').selectOption('summary');
    await expect(reader.locator('.summary-points > li').first()).toBeVisible();
    await page.screenshot({path:join(tmpdir(),'juanzhan-legacy-'+name+'-desktop.png')});
    await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),name).toBe(true);
    await page.screenshot({path:join(tmpdir(),'juanzhan-legacy-'+name+'-mobile.png')});await page.setViewportSize({width:1440,height:1000});
  }
  expect(errors).toEqual([]);
});
