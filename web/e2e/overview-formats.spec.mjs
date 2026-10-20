import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { login, createSpace, api } from './helpers.mjs';

let directory;
test.beforeAll(() => {
 directory=mkdtempSync(join(tmpdir(),'juanzhan-overview-types-'));
 execFileSync('../.venv/bin/python',['e2e/overview_samples.py',directory]);
});
test.afterAll(() => { if(directory)rmSync(directory,{recursive:true,force:true}); });

test('seven new office and delimited formats show source-backed overviews on desktop and mobile',async({page})=>{
  test.setTimeout(180000);
  const script="import sys,json,base64;sys.path[:0]=['../tests','../services'];from test_office_formats import workbook,presentation,odf,ODT,ODS,ODP;items=[('budget.xlsx',workbook()),('plan.pptx',presentation()),('report.odt',odf(ODT)),('budget.ods',odf(ODS)),('plan.odp',odf(ODP)),('inventory.csv','设备,状态\\n主机,已验收\\n'.encode()),('inventory.tsv','设备\\t状态\\n主机\\t已验收\\n'.encode())];print(json.dumps([{'name':name,'data':base64.b64encode(data).decode()} for name,data in items]))";
  const cases=JSON.parse(execFileSync('../.venv/bin/python',['-c',script],{encoding:'utf8'}));
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await login(page);await createSpace(page,'Office概要验收');const space=await page.getByLabel('当前空间').inputValue();
  for(const item of cases){
    const session=await api(page,'/auth/session');
    const response=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':session.data.csrf_token},multipart:{space_id:space,file:{name:item.name,mimeType:'application/octet-stream',buffer:Buffer.from(item.data,'base64')}}});
    expect(response.status()).toBe(201);const saved=await response.json();
    await expect.poll(async()=> (await api(page,`/documents/${saved.document_id}`)).data.processing_status,{timeout:30000}).toBe('completed');
    await page.reload();await page.getByLabel('当前空间').selectOption(space);
    await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:item.name}).click();
    const reader=page.getByRole('region',{name:'正文阅读',exact:true});
    await expect(reader.locator('.summary-points > li').first()).toBeVisible();
    await expect(reader.locator('.summary-points')).toContainText(/验收|主机/);
    const source=reader.locator('.summary-points > li').first();await source.locator('summary').click();
    await source.getByRole('button',{name:'查看对应正文',exact:true}).first().click();
    await expect(reader.locator('.content-blocks')).toBeVisible();
    await reader.getByLabel('阅读格式').selectOption('summary');
    await page.screenshot({path:join(tmpdir(),'juanzhan-office-'+item.name+'-desktop.png')});
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),item.name).toBe(true);
    await page.screenshot({path:join(tmpdir(),'juanzhan-office-'+item.name+'-mobile.png')});
    await page.setViewportSize({width:1440,height:1000});
  }
  expect(errors).toEqual([]);
});

test('ten real documents across six formats produce truthful generic overviews', async ({ page }) => {
  test.setTimeout(180000);
  page.setDefaultTimeout(15000);
  const results=[];
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  try {
    const cases=JSON.parse(readFileSync(join(directory,'manifest.json'),'utf8'));
    console.log('Generated sample files');
    await login(page); console.log('Logged in'); await createSpace(page,'多类型概览验收');
    const space=await page.getByLabel('当前空间').inputValue();
    for (const item of cases) {
      console.log("Checking",item.name);
      const session=await api(page,'/auth/session');
      const response=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':session.data.csrf_token},multipart:{space_id:space,file:{name:item.name,mimeType:item.mime,buffer:readFileSync(join(directory,item.name))}}});
      expect(response.status(),item.name).toBe(201); const saved=await response.json();
      await expect.poll(async()=> (await api(page,`/documents/${saved.document_id}`)).data.processing_status,{timeout:30000,message:item.name}).toBe('completed');
      const before=(await api(page,`/documents/${saved.document_id}`)).data;
      console.log("Parsed",item.name);
      await page.reload(); await page.getByLabel('当前空间').selectOption(space);
      await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:item.name}).click();
      const reader=page.getByRole('region',{name:'正文阅读',exact:true});
      await expect(reader.getByLabel('阅读格式')).toHaveValue('summary');
      await expect(reader.locator('.fact-grid,.fact-card,img,script,iframe')).toHaveCount(0);
      if(item.empty) {
        await expect(reader.getByText('暂无可提炼的文本内容。')).toBeVisible();
      } else {
        await expect(reader.locator('.summary-points > li').first()).toBeVisible();
        const text=await reader.locator('.summary-points').innerText();
        for(const expected of item.expected) expect(text,item.name+' includes '+expected).toContain(expected);
        if(item.partial) {
          expect(await reader.locator('.summary-points > li').count()).toBeLessThanOrEqual(8);
          await reader.getByRole('button',{name:'信息说明',exact:true}).last().hover();
          await expect(reader.getByRole('tooltip')).toContainText('并非全文');
          await page.mouse.move(0,0);
        }
        const source=reader.locator('.summary-points > li').first(); await source.locator('summary').click();
        await source.getByRole('button',{name:'查看对应正文',exact:true}).first().click();
        await expect(reader.locator('.content-blocks')).toBeVisible();
        await reader.getByLabel('阅读格式').selectOption('summary');
      }
      await page.screenshot({path:join(tmpdir(),'juanzhan-types-'+item.name.replace(/\..+$/,'')+'-desktop.png')});
      await page.setViewportSize({width:390,height:844});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),item.name).toBe(true);
      await page.screenshot({path:join(tmpdir(),'juanzhan-types-'+item.name.replace(/\..+$/,'')+'-mobile.png')});
      await page.setViewportSize({width:1440,height:1000});
      expect(await page.evaluate(()=>Boolean(window.OVERVIEW_ATTACK))).toBe(false);
      const after=(await api(page,`/documents/${saved.document_id}`)).data;
      for(const key of ['document_version','current_revision_id','current_parse_run_id'])expect(after[key]).toBe(before[key]);
      results.push({name:item.name,status:'passed',id:saved.document_id,empty:!!item.empty,partial:!!item.partial});
    }
    expect(errors).toEqual([]);
  } finally {
    writeFileSync(join(tmpdir(),'juanzhan-overview-types-results.json'),JSON.stringify({results,errors},null,2));
    rmSync(directory,{recursive:true,force:true});
  }
});
