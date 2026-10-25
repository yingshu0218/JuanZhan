import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {login,createSpace,api} from './helpers.mjs';
test('bulk task controls preserve pending files until actual current-version processing completes',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await login(page);await createSpace(page,'任务控制与待处理验收');
 const space=await page.getByLabel('当前空间').inputValue();
 const directory=(await readFile(process.env.JUANZHAN_E2E_ARCHIVE_POINTER,'utf8')).trim();
 const created=JSON.parse(execFileSync('../.venv/bin/python',['-c',`import sys,json,time
from pathlib import Path
from io import BytesIO
sys.path.insert(0,'../services')
from juanzhan.config import Settings
from juanzhan.jobs import JobQueue,JobSpec
from juanzhan.documents import DocumentService,Registration
from juanzhan.storage import ManagedStore
s=Settings(Path(sys.argv[1]),'');store=ManagedStore(s.data_dir/'managed');service=DocumentService(s);queue=JobQueue(s,clock=lambda:time.time()+3600);result=[]
for name in ('task-one.txt','task-two.txt'):
 obj=store.put(BytesIO(('Document text for '+name).encode()),max_bytes=10000);saved={}
 def after(db,doc):saved.update(queue.enqueue(JobSpec(kind='parse',target_type='document',target_id=doc['id'],payload={'revision_id':doc['current_revision_id']},idempotency_key='control-test:'+doc['id']),db=db))
 doc=service.register_managed(obj,Registration(space_id=sys.argv[2],title=name,original_filename=name,mime_type='text/plain'),after_create=after)
 result.append({'document_id':doc['id'],'job_id':saved['id'],'filename':name})
print(json.dumps(result))`,directory,space],{encoding:'utf8'}));
 await page.getByRole('button',{name:'任务中心',exact:true}).click();
 const center=page.getByRole('dialog',{name:'任务中心',exact:true});
 await center.getByLabel('任务状态').selectOption('queued');
 for(const item of created)await center.getByRole('checkbox',{name:'选择任务 '+item.job_id,exact:true}).check();
 await center.getByRole('button',{name:'批量暂停',exact:true}).click();await center.getByLabel('任务状态').selectOption('paused');
 for(const item of created)await expect(center.getByRole('checkbox',{name:'选择任务 '+item.job_id,exact:true})).toBeVisible();
 await page.screenshot({path:'/tmp/juanzhan-controls-paused.png'});
 await center.getByRole('checkbox',{name:'选择任务 '+created[0].job_id,exact:true}).check();await center.getByRole('button',{name:'批量恢复',exact:true}).click();
 await center.getByRole('checkbox',{name:'选择任务 '+created[1].job_id,exact:true}).check();await center.getByRole('button',{name:'批量取消',exact:true}).click();await center.getByRole('button',{name:'确认取消任务',exact:true}).click();
 await center.getByLabel('任务状态').selectOption('cancelled');await center.getByRole('checkbox',{name:'选择任务 '+created[1].job_id,exact:true}).check();await center.getByRole('button',{name:'批量删除记录',exact:true}).click();await center.getByRole('button',{name:'确认删除任务记录',exact:true}).click();
 await expect(center.getByRole('checkbox',{name:'选择任务 '+created[1].job_id,exact:true})).toHaveCount(0);
 await center.getByRole('button',{name:'待处理文件',exact:true}).click();
 const pending=center.getByRole('region',{name:'待处理文件清单',exact:true});await pending.getByLabel('待处理空间').selectOption(space);
 await expect(pending.getByRole('checkbox',{name:'选择文件 task-two.txt',exact:true})).toBeVisible();
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'/tmp/juanzhan-controls-pending-mobile.png'});
 await pending.getByRole('checkbox',{name:'选择文件 task-two.txt',exact:true}).check();await pending.getByRole('button',{name:'重新处理所选（1）',exact:true}).click();
 await expect.poll(async()=>(await api(page,'/pending-documents?space_id='+space)).data.total,{timeout:45000}).toBe(0);
 for(const item of created)expect((await page.request.get('/api/v1/documents/'+item.document_id+'/download')).status()).toBe(200);
 expect(errors).toEqual([]);
});
