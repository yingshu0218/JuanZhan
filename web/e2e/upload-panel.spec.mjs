import {test,expect} from '@playwright/test';
import {login,createSpace} from './helpers.mjs';
test('empty import panel presents both picker actions and a usable drop zone at desktop and mobile sizes',async({page})=>{
 const errors=[],nativeDialogs=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',dialog=>{nativeDialogs.push(dialog.type());dialog.dismiss();});
 await login(page);await createSpace(page,'导入面板验收');
 await page.getByRole('banner').getByRole('button',{name:'导入文件',exact:true}).click();
 const panel=page.getByRole('region',{name:'上传队列',exact:true});
 for(const [width,height,label] of [[1440,1000,'desktop'],[390,844,'mobile'],[667,375,'short']]){
  await page.setViewportSize({width,height});
  await expect(panel.getByRole('heading',{name:'导入文件',exact:true})).toBeVisible();
  await expect(panel.getByText('将文件或文件夹拖到这里',{exact:true})).toBeVisible();
  for(const name of ['选择文件','选择文件夹']){
   const box=await panel.getByRole('button',{name,exact:true}).boundingBox();
   expect(box.x).toBeGreaterThanOrEqual(0);expect(box.y).toBeGreaterThanOrEqual(0);
   expect(box.x+box.width).toBeLessThanOrEqual(width);expect(box.y+box.height).toBeLessThanOrEqual(height);
  }
  expect(await panel.getByRole('button',{name:'信息说明',exact:true}).count()).toBe(1);
  await page.screenshot({path:`/tmp/juanzhan-upload-panel-${label}.png`});
 }
 await panel.getByRole('button',{name:'收起上传队列'}).click();await expect(panel).toHaveCount(0);
 expect(errors).toEqual([]);expect(nativeDialogs).toEqual([]);expect(page.context().pages()).toHaveLength(1);
});

test('a folder with 512 files and 513 directories enters the queue with separate counts',async({page})=>{
 const {mkdtemp,mkdir,writeFile,rm}=await import('node:fs/promises');
 const root=await mkdtemp('/tmp/juanzhan-count-folder-');
 let release;const gate=new Promise(resolve=>release=resolve);
 try{
  for(let i=0;i<512;i++){const child=root+'/section'+i;await mkdir(child);await writeFile(child+'/note.txt','sample '+i);}
  await login(page);await createSpace(page,'文件目录独立计数');
  // Hold preparation to inspect admission without creating 1025 test records.
  await page.route('**/api/v1/folders',async route=>{if(route.request().method()==='POST'){await gate;await route.abort();}else await route.continue();});
  await page.getByRole('banner').getByRole('button',{name:'导入文件',exact:true}).click();
  await page.getByLabel('上传整个文件夹',{exact:true}).setInputFiles(root);
  const panel=page.getByRole('region',{name:'上传队列',exact:true});
  await expect(panel.getByRole('status').filter({hasText:'文件 512 个 · 目录 513 个'})).toBeVisible();
  await expect(panel.getByText('未加入上传队列',{exact:true})).toHaveCount(0);
  await expect(panel.getByRole('alert')).toHaveCount(0);
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:'/tmp/juanzhan-upload-count-mobile.png'});
 }finally{await page.close();release();await rm(root,{recursive:true,force:true});}
});

test('flat image batch is guided into a named folder before upload, with current-folder and cancel alternatives',async({page})=>{
 const {api}=await import('./helpers.mjs');
 const {execFileSync}=await import('node:child_process');
 const encoded=JSON.parse(execFileSync('../.venv/bin/python',['-c',"import sys,json,base64;sys.path.insert(0,'../tests');from format_samples import raster_sample;print(json.dumps([base64.b64encode(raster_sample(text='Archive picture '+str(i))).decode() for i in range(10)]))"],{encoding:'utf8'}));
 const files=encoded.map((value,i)=>({name:`batch-${i}.png`,mimeType:'image/png',buffer:Buffer.from(value,'base64')}));
 const dialogs=[];page.on('dialog',d=>{dialogs.push(d.type());d.dismiss();});
 await login(page);await createSpace(page,'散图归档引导');const space=await page.getByLabel('当前空间').inputValue();
 const picker=page.getByLabel('选择上传文件',{exact:true});
 await picker.setInputFiles(files);
 const group=page.getByRole('dialog',{name:'批量图片归档',exact:true});await expect(group).toBeVisible();
 expect((await api(page,'/documents?space_id='+space)).data.total).toBe(0);
 await group.getByLabel('图片归档文件夹名称').fill('../bad');await group.getByRole('button',{name:'新建文件夹并导入',exact:true}).click();
 await expect(group.getByRole('alert')).toContainText('有效文件夹名称');
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'/tmp/juanzhan-image-group-mobile.png'});
 await group.getByLabel('图片归档文件夹名称').fill('项目图片');await group.getByRole('button',{name:'新建文件夹并导入',exact:true}).click();
 await expect.poll(async()=>(await api(page,'/documents?space_id='+space)).data.total,{timeout:30000}).toBe(10);
 const folders=(await api(page,'/folders?space_id='+space)).data;const folder=folders.find(f=>f.name==='项目图片');expect(folder).toBeTruthy();
 expect((await api(page,'/documents?space_id='+space)).data.items.every(d=>d.folder_id===folder.id)).toBe(true);
 await picker.setInputFiles([]);await picker.setInputFiles(files);await expect(group).toBeVisible();
 await group.getByRole('button',{name:'取消本批',exact:true}).click();expect((await api(page,'/documents?space_id='+space)).data.total).toBe(10);
 await picker.setInputFiles([]);await picker.setInputFiles(files);await expect(group).toBeVisible();
 // Reject upload requests here to inspect the target choice without intentionally importing duplicate originals.
 const requested=[];await page.route('**/api/v1/documents/upload',async route=>{requested.push(route.request().postData());await route.abort();});
 await group.getByRole('button',{name:'仍放在当前目录',exact:true}).click();
 await expect.poll(()=>requested.length).toBe(10);
 expect(requested.every(body=>!body.includes('name="folder_id"'))).toBe(true);
 expect(dialogs).toEqual([]);
});
