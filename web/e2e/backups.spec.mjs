import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {login,createSpace,api} from './helpers.mjs';
async function open(page){await page.getByRole('button',{name:'系统设置',exact:true}).click();await page.getByRole('button',{name:'备份与恢复',exact:true}).click();return page.getByRole('dialog',{name:'备份与恢复',exact:true});}

test('an empty instance can open backup settings and invalid ZIP never appears usable',async({page})=>{
  await login(page);await expect(page.locator('.app-header')).toHaveCSS('display','flex');expect((await api(page,'/spaces')).data).toHaveLength(0);const dialog=await open(page);
  await dialog.getByLabel('上传备份ZIP',{exact:true}).setInputFiles({name:'invalid.zip',mimeType:'application/zip',buffer:Buffer.from('invalid transport')});
  await dialog.getByRole('button',{name:'上传并校验',exact:true}).click();
  const records=dialog.getByRole('region',{name:'备份记录',exact:true});await expect(records).toContainText('上传 · 失败',{timeout:30000});await expect(records.locator('.backup-list>li').filter({hasText:'上传 · 失败'}).getByRole('button',{name:'恢复此备份',exact:true})).toBeDisabled();
  await expect(records).toContainText('BACKUP_INVALID');
});

test('real backup download, ZIP upload and verified recovery remain explicit on desktop and mobile',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',entry=>{if(entry.type()==='error'&&!entry.text().includes('Failed to load resource: the server responded with a status of'))errors.push(entry.text());});await login(page);await createSpace(page,'网页备份验证');
  const space=await page.getByLabel('当前空间').inputValue();
  const upload=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},multipart:{space_id:space,file:{name:'备份原件.txt',mimeType:'text/plain',buffer:Buffer.from('browser backup preserved original')}}});expect(upload.status()).toBe(201);
  const baseline=(await api(page,'/system/backups')).data.total;const dialog=await open(page);await expect(dialog.getByRole('heading',{name:'手动备份',exact:true})).toBeVisible();
  await dialog.getByRole('button',{name:'创建备份',exact:true}).click();
  const records=dialog.getByRole('region',{name:'备份记录',exact:true});
  await expect(records.locator('.backup-list>li')).toHaveCount(baseline+1);
  const manual=records.locator('.backup-list>li').first();await expect(manual.getByText('手动 · 可用',{exact:true})).toBeVisible({timeout:30000});
  const downloaded=page.waitForEvent('download');await manual.getByRole('link',{name:'下载ZIP',exact:true}).click();const download=await downloaded;
  const path='/tmp/juanzhan-backup-browser.zip';await download.saveAs(path);expect((await readFile(path)).subarray(0,2).toString()).toBe('PK');
  await dialog.getByLabel('上传备份ZIP',{exact:true}).setInputFiles(path);await dialog.getByRole('button',{name:'上传并校验',exact:true}).click();
  await expect(records.locator('.backup-list>li')).toHaveCount(baseline+2);
  const imported=records.locator('.backup-list>li').filter({hasText:'上传 · 可用'});await expect(imported).toHaveCount(1,{timeout:30000});
  await imported.getByRole('button',{name:'恢复此备份',exact:true}).click();
  const confirmation=dialog.getByRole('region',{name:'确认恢复',exact:true});await expect(confirmation.getByRole('button',{name:'开始恢复',exact:true})).toBeDisabled();
  await expect(confirmation).toContainText('不覆盖当前实例');await confirmation.getByLabel('我已了解并确认此操作',{exact:true}).check();await confirmation.getByRole('button',{name:'开始恢复',exact:true}).click();
  const recovered=dialog.getByRole('region',{name:'恢复记录',exact:true});await expect(recovered).toContainText('新目录已验证，尚未切换当前实例',{timeout:30000});
  const plan=dialog.getByRole('region',{name:'自动备份计划',exact:true});await plan.getByLabel('备份间隔（分钟，0关闭）',{exact:true}).fill('60');await plan.getByLabel('最多保留自动备份数',{exact:true}).fill('3');await plan.getByLabel('自动备份最长天数',{exact:true}).fill('14');await plan.getByRole('button',{name:'保存备份计划',exact:true}).click();
  await expect(dialog.getByRole('status')).toContainText('自动备份计划已保存');
  expect((await api(page,'/system/backup-schedule')).data).toMatchObject({interval_minutes:60,keep_count:3,max_age_days:14});
  await page.setViewportSize({width:1440,height:1000});await dialog.evaluate(element=>element.scrollTop=0);await page.screenshot({path:'/tmp/juanzhan-backup-desktop.png'});
  await page.setViewportSize({width:390,height:844});await dialog.evaluate(element=>element.scrollTop=0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'/tmp/juanzhan-backup-mobile.png'});
  await dialog.getByRole('button',{name:'关闭备份与恢复',exact:true}).click();await page.reload();
  const reopened=await open(page);await expect(reopened.getByLabel('备份间隔（分钟，0关闭）',{exact:true})).toHaveValue('60');await expect(reopened.getByRole('region',{name:'恢复记录',exact:true})).toContainText('新目录已验证');
  await reopened.getByLabel('备份间隔（分钟，0关闭）',{exact:true}).fill('0');await reopened.getByRole('button',{name:'保存备份计划',exact:true}).click();await expect(reopened.getByRole('status')).toContainText('自动备份已关闭');
  const toDelete=reopened.getByRole('region',{name:'备份记录',exact:true}).locator('.backup-list>li').filter({hasText:'手动 · 可用'});
  await toDelete.getByRole('button',{name:'删除备份文件',exact:true}).click();const deletion=reopened.getByRole('region',{name:'确认删除备份',exact:true});await deletion.getByLabel('我已了解并确认此操作',{exact:true}).check();await deletion.getByRole('button',{name:'确认删除',exact:true}).click();
  await expect(reopened.getByRole('region',{name:'备份记录',exact:true})).toContainText('手动 · 已删除');
  const doc=(await upload.json()).document_id;expect(await (await page.request.get('/api/v1/documents/'+doc+'/download')).text()).toBe('browser backup preserved original');
  expect(errors).toEqual([]);
});


test('a stale backup plan is rejected and explicit reload reads the latest server version',async({page})=>{
  await login(page);const dialog=await open(page);
  const input=dialog.getByLabel('备份间隔（分钟，0关闭）',{exact:true});await expect(input).toHaveValue('0');
  const current=(await api(page,'/system/backup-schedule')).data;
  expect((await api(page,'/system/backup-schedule','PATCH',{expected_version:current.version,interval_minutes:120,keep_count:4,max_age_days:21})).status).toBe(200);
  await input.fill('30');await dialog.getByRole('button',{name:'保存备份计划',exact:true}).click();
  await expect(dialog.getByRole('alert').filter({hasText:'备份计划已被更新'})).toBeVisible();expect((await api(page,'/system/backup-schedule')).data.interval_minutes).toBe(120);
  await dialog.getByRole('button',{name:'重载计划',exact:true}).click();await expect(input).toHaveValue('120');
  await expect(dialog.getByLabel('最多保留自动备份数',{exact:true})).toHaveValue('4');
  await input.fill('0');await dialog.getByRole('button',{name:'保存备份计划',exact:true}).click();
  await expect(dialog.getByRole('status')).toContainText('自动备份已关闭');
});
