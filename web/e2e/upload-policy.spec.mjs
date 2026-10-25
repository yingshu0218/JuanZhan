import {test,expect} from '@playwright/test';
import {login,createSpace,api} from './helpers.mjs';
test('default JSON exclusion is configurable in-page and applies to next upload',async({page})=>{
 const errors=[],uploads=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().endsWith('/documents/upload'))uploads.push(r);});
 await login(page);await createSpace(page,'上传格式规则验收');
 await page.getByRole('banner').getByRole('button',{name:'导入文件',exact:true}).click();
 await page.getByLabel('选择上传文件',{exact:true}).setInputFiles([{name:'metadata.json',mimeType:'application/json',buffer:Buffer.from('{"subject":"sample"}')}]);
 const queue=page.getByRole('region',{name:'上传队列',exact:true});
 await expect(queue.getByText('已跳过 1 项已排除文件/目录')).toBeVisible();expect(uploads).toHaveLength(0);
 await queue.getByRole('button',{name:'收起上传队列'}).click();
 await page.getByRole('button',{name:'系统设置',exact:true}).click();await page.getByRole('button',{name:'上传格式规则',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'上传格式规则',exact:true});
 await expect(dialog.getByRole('checkbox',{name:'JSON及程序数据文件',exact:true})).toBeChecked();
 await expect(dialog.getByRole('checkbox',{name:'源代码与脚本',exact:true})).toBeChecked();
 await dialog.getByRole('checkbox',{name:'JSON及程序数据文件',exact:true}).uncheck();
 await dialog.getByLabel('额外排除的扩展名').fill('psd');await dialog.getByRole('button',{name:'保存上传规则',exact:true}).click();
 await expect(dialog.getByText('上传规则已保存，对之后的上传生效。')).toBeVisible();
 await page.screenshot({path:'/tmp/juanzhan-upload-policy-desktop.png'});
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'/tmp/juanzhan-upload-policy-mobile.png'});
 await dialog.getByRole('button',{name:'关闭上传格式规则'}).click();
 await page.getByRole('banner').getByRole('button',{name:'导入文件',exact:true}).click();
 await page.getByLabel('选择上传文件',{exact:true}).setInputFiles({name:'metadata.json',mimeType:'application/json',buffer:Buffer.from('{"subject":"sample"}')});
 await expect(queue.getByText('原件已保存',{exact:false})).toHaveCount(1);expect(uploads).toHaveLength(1);
 // Restore defaults so the shared disposable server remains deterministic for later files.
 const policy=(await api(page,'/system/upload-policy')).data;
 await api(page,'/system/upload-policy','PUT',{expected_version:policy.version,excluded_groups:policy.groups.filter(g=>g.default_excluded).map(g=>g.id),custom_extensions:[]});
 expect(errors).toEqual([]);
});

test('development dependency and app bundle directories are skipped without traversal',async()=>{
 const {droppedFiles}=await import('../src/uploadTree.js');
 for(const name of ['node_modules','.venv','__pycache__','Example.app']){
  const data={files:[],items:[{kind:'file',getAsFile:()=>null,webkitGetAsEntry:()=>({name,isDirectory:true,createReader(){throw Error('Excluded directory must not be traversed');}})}]};
  const result=await droppedFiles(data,new AbortController().signal);expect(result).toHaveLength(0);expect(result.skipped.total).toBe(1);
 }
});
