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
