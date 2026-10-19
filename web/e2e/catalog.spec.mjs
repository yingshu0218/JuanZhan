import {test,expect} from '@playwright/test';
import {login,createSpace,api} from './helpers.mjs';

async function manager(page){await page.getByRole('button',{name:'管理字段与类型',exact:true}).click();return page.getByRole('dialog',{name:'字段与类型管理',exact:true});}
async function createField(dialog,key,label,type){
  await dialog.getByRole('button',{name:'新增业务字段',exact:true}).click();
  await dialog.getByLabel('字段名称',{exact:true}).fill(label);await dialog.getByLabel('字段标识',{exact:true}).fill(key);
  await dialog.getByRole('combobox',{name:'字段类型',exact:true}).selectOption(type);
}
async function saved(dialog){await dialog.getByRole('button',{name:'保存字段',exact:true}).click();await expect(dialog.getByRole('button',{name:'新增业务字段',exact:true})).toBeVisible();}

test('field and type templates use real APIs, preserve decimal precision and enforce filing',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await login(page);await createSpace(page,'字段与模板管理');const space=await page.getByLabel('当前空间').inputValue();
  const dialog=await manager(page);
  await createField(dialog,'short','简述','text');await dialog.getByLabel('最长长度',{exact:true}).fill('100');await saved(dialog);
  await createField(dialog,'long','详细说明','long_text');await saved(dialog);
  await createField(dialog,'count','数量','integer');await dialog.getByLabel('最小值',{exact:true}).fill('1');await saved(dialog);
  await createField(dialog,'amount','金额','decimal');await dialog.getByLabel('最小值',{exact:true}).fill('0.0001');await dialog.getByLabel('最大值',{exact:true}).fill('900.9999');await dialog.getByLabel('允许条件筛选',{exact:true}).check();await saved(dialog);
  await createField(dialog,'day','日期','date');await dialog.getByLabel('最小值',{exact:true}).fill('2020-01-01');await saved(dialog);
  await createField(dialog,'checked','已复核','boolean');await saved(dialog);
  await createField(dialog,'stage','阶段','single_select');await dialog.getByLabel('选项标识 1',{exact:true}).fill('stable-draft');await dialog.getByLabel('选项名称 1',{exact:true}).fill('待确认');await saved(dialog);
  const fields=(await api(page,`/field-definitions?space_id=${space}`)).data;expect(fields).toHaveLength(7);
  const amount=fields.find(field=>field.key==='amount');expect(amount.constraints).toEqual({min:'0.0001',max:'900.9999'});
  await dialog.getByRole('button',{name:'文档类型与模板',exact:true}).click();await dialog.getByRole('button',{name:'新增文档类型',exact:true}).click();
  await dialog.getByLabel('类型名称',{exact:true}).fill('合同');await dialog.getByLabel('类型标识',{exact:true}).fill('contract');
  await dialog.getByRole('combobox',{name:'添加模板字段',exact:true}).selectOption(amount.id);await dialog.getByRole('button',{name:'加入模板',exact:true}).click();
  const short=fields.find(field=>field.key==='short');await dialog.getByRole('combobox',{name:'添加模板字段',exact:true}).selectOption(short.id);await dialog.getByRole('button',{name:'加入模板',exact:true}).click();
  await dialog.getByRole('button',{name:'上移字段 2',exact:true}).click();
  await dialog.locator('.catalog-template li').filter({hasText:'金额'}).getByLabel('归档时必填',{exact:true}).check();
  await dialog.getByRole('button',{name:'保存类型',exact:true}).click();await expect(dialog.getByRole('button',{name:'编辑合同',exact:true})).toBeVisible();
  const type=(await api(page,`/document-types?space_id=${space}`)).data[0];expect(type.fields.map(field=>field.field_definition_id)).toEqual([short.id,amount.id]);expect(type.fields[1].required_for_filing).toBe(true);
  await dialog.getByRole('button',{name:'编辑合同',exact:true}).click();await expect(dialog.getByLabel('类型标识',{exact:true})).toBeDisabled();await dialog.getByLabel('类型名称',{exact:true}).fill('合同资料');await dialog.getByRole('button',{name:'保存类型',exact:true}).click();
  await dialog.getByRole('button',{name:'关闭字段与类型管理',exact:true}).click();
  const receipt=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},multipart:{space_id:space,file:{name:'模板验证.txt',mimeType:'text/plain',buffer:Buffer.from('template actual bytes')}}});expect(receipt.status()).toBe(201);const doc=await receipt.json();
  const root=`/documents/${doc.document_id}`;let current=(await api(page,root)).data;
  expect((await api(page,root,'PATCH',{expected_document_version:current.document_version,document_type_id:type.id})).status).toBe(200);
  current=(await api(page,root)).data;const filing=await api(page,root+'/triage','POST',{expected_document_version:current.document_version,triage_status:'filed'});expect(filing.status).toBe(422);
  expect((await api(page,root+'/metadata','PATCH',{expected_document_version:current.document_version,values:{amount:'10.0001',checked:false},confirm:true})).status).toBe(200);
  current=(await api(page,root)).data;expect((await api(page,root+'/triage','POST',{expected_document_version:current.document_version,triage_status:'filed'})).status).toBe(200);
  await page.reload();await page.getByLabel('当前空间').selectOption(space);
  await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:'模板验证.txt'}).click();
  const values=page.locator('.business-fields dl > div');await expect(values).toHaveCount(3);
  await expect(values.nth(0).locator('dt')).toContainText('简述');await expect(values.nth(0).locator('dd')).toHaveText('未填写');
  await expect(values.nth(1).locator('dt')).toContainText('金额');await expect(values.nth(1).locator('dt')).toContainText('归档必填');await expect(values.nth(1).locator('dd')).toHaveText('10.0001');
  await expect(values.nth(2).locator('dd')).toHaveText('否');
  const settings=await manager(page);await settings.getByRole('button',{name:'文档类型与模板',exact:true}).click();
  await settings.getByRole('button',{name:'编辑合同资料',exact:true}).click();
  await page.screenshot({path:'/tmp/juanzhan-catalog-template-desktop.png'});
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'/tmp/juanzhan-catalog-template-mobile.png'});
  await settings.getByLabel('启用此类型',{exact:true}).uncheck();await settings.getByRole('button',{name:'保存类型',exact:true}).click();
  await expect(settings.getByRole('button',{name:'编辑合同资料',exact:true})).toBeVisible();
  expect((await api(page,root)).data.document_type_id).toBe(type.id);expect((await api(page,root+'/metadata')).data[0].value).toBe('10.0001');
  expect((await api(page,`/document-types?space_id=${space}`)).data[0].is_active).toBe(false);
  await settings.getByRole('button',{name:'编辑合同资料',exact:true}).click();await settings.getByLabel('启用此类型',{exact:true}).check();await settings.getByRole('button',{name:'保存类型',exact:true}).click();
  await expect(settings.getByRole('button',{name:'编辑合同资料',exact:true})).toBeVisible();
  expect((await api(page,`/document-types?space_id=${space}`)).data[0].is_active).toBe(true);
  expect(errors).toEqual([]);
});

test('management isolates spaces, handles invalid rules, and deactivation preserves existing values',async({page})=>{
  await login(page);await createSpace(page,'管理隔离甲');const first=await page.getByLabel('当前空间').inputValue();
  const dialog=await manager(page);await createField(dialog,'quantity','数量','integer');await dialog.getByLabel('最小值',{exact:true}).fill('9007199254740993');
  await dialog.getByRole('button',{name:'保存字段',exact:true}).click();await expect(dialog.getByRole('alert')).toContainText('安全整数');
  await dialog.getByLabel('最小值',{exact:true}).fill('10');await dialog.getByLabel('最大值',{exact:true}).fill('1');await dialog.getByRole('button',{name:'保存字段',exact:true}).click();await expect(dialog.getByRole('alert')).toContainText('规则无效');
  await dialog.getByLabel('最大值',{exact:true}).fill('100');await saved(dialog);
  const uploaded=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},multipart:{space_id:first,file:{name:'保留字段.txt',mimeType:'text/plain',buffer:Buffer.from('retain original')}}});expect(uploaded.status()).toBe(201);
  const root='/documents/'+(await uploaded.json()).document_id;const doc=(await api(page,root)).data;
  expect((await api(page,root+'/metadata','PATCH',{expected_document_version:doc.document_version,values:{quantity:42},confirm:true})).status).toBe(200);
  const before=(await api(page,root+'/metadata')).data;
  await dialog.getByRole('button',{name:'编辑数量',exact:true}).click();await expect(dialog.getByRole('combobox',{name:'字段类型',exact:true})).toBeDisabled();await dialog.getByLabel('启用此字段',{exact:true}).uncheck();await saved(dialog);
  expect((await api(page,`/field-definitions?space_id=${first}`)).data[0].is_active).toBe(false);
  expect((await api(page,root+'/metadata')).data).toEqual(before);
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'/tmp/juanzhan-catalog-manager-mobile.png'});
  await dialog.getByRole('button',{name:'关闭字段与类型管理',exact:true}).click();await page.setViewportSize({width:1440,height:1000});await createSpace(page,'管理隔离乙');const second=await page.getByLabel('当前空间').inputValue();
  const empty=await manager(page);await expect(empty.getByText('暂无符合条件的配置。',{exact:true})).toBeVisible();expect((await api(page,`/field-definitions?space_id=${second}`)).data).toEqual([]);
});

test('editing a label never rounds existing int64 constraints',async({page})=>{
  await login(page);await createSpace(page,'整数边界保留');const space=await page.getByLabel('当前空间').inputValue();
  const response=await page.request.post('/api/v1/field-definitions',{headers:{'Content-Type':'application/json','X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},data:`{"space_id":"${space}","key":"large","label":"大整数","type":"integer","constraints":{"max":9223372036854775807}}`});
  expect(response.status()).toBe(201);const id=(await response.json()).id;
  const dialog=await manager(page);await dialog.getByRole('button',{name:'编辑大整数',exact:true}).click();
  await expect(dialog.getByText('此字段含旧版未知规则或超出浏览器精度的整数边界。可修改名称/状态，原规则保持；请通过API精确核对和修复规则。',{exact:true})).toBeVisible();
  await dialog.getByLabel('字段名称',{exact:true}).fill('大整数保留');await saved(dialog);
  const fields=await page.request.get(`/api/v1/field-definitions?space_id=${space}`);expect(await fields.text()).toContain('"max":9223372036854775807');
  expect((await api(page,`/field-definitions?space_id=${space}`)).data.find(field=>field.id===id).label).toBe('大整数保留');
  await dialog.getByRole('button',{name:'关闭字段与类型管理',exact:true}).click();
  const uploaded=await page.request.post('/api/v1/documents/upload',{headers:{'X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},multipart:{space_id:space,file:{name:'精确整数.txt',mimeType:'text/plain',buffer:Buffer.from('exact integer bytes')}}});expect(uploaded.status()).toBe(201);
  const root='/documents/'+(await uploaded.json()).document_id,current=(await api(page,root)).data;
  const metadata=await page.request.patch('/api/v1'+root+'/metadata',{headers:{'Content-Type':'application/json','X-CSRF-Token':(await api(page,'/auth/session')).data.csrf_token},data:`{"expected_document_version":${current.document_version},"values":{"large":9223372036854775807},"confirm":true}`});expect(metadata.status()).toBe(200);
  await page.reload();await page.getByLabel('当前空间').selectOption(space);
  await page.getByRole('region',{name:'档案列表',exact:true}).getByRole('button').filter({hasText:'精确整数.txt'}).click();
  await expect(page.locator('.business-fields')).toContainText('超出浏览器安全整数范围，请通过API查看精确值');
  expect(await (await page.request.get('/api/v1'+root+'/metadata')).text()).toContain('"value":9223372036854775807');
});
