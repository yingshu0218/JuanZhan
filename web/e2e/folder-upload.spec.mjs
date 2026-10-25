import { test, expect } from '@playwright/test';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { login, createSpace, api } from './helpers.mjs';
import { droppedFiles, selectedFiles } from '../src/uploadTree.js';

test('native folder picker preserves nested files beyond 20 and reuses existing logical folders', async ({ page }) => {
  const temp = await mkdtemp('/tmp/juanzhan-upload-folder-');
  try {
    const root = path.join(temp, '资料包');
    await mkdir(path.join(root, '合同'), { recursive: true });
    for (let i = 0; i < 21; i++) await writeFile(path.join(root, `资料${i}.txt`), '原件内容-' + i);
    await writeFile(path.join(root, '合同', '条款.txt'), '合同条款原件');
    await login(page); await createSpace(page, '文件夹上传-' + path.basename(temp));
    const space = await page.getByLabel('当前空间').inputValue();
    const base = (await api(page, '/folders', 'POST', { space_id: space, name: '目标目录' })).data;
    const existing = (await api(page, '/folders', 'POST', { space_id: space, parent_id: base.id, name: '资料包' })).data;
    await page.reload();
    await page.getByRole('navigation').getByRole('button', { name: '目标目录', exact: true }).click();
    await page.getByRole('button', { name: '导入文件', exact: true }).click();
    await expect(page.getByRole('button', { name: '选择文件夹', exact: true })).toBeVisible();
    const chooserReady=page.waitForEvent('filechooser');
    await page.getByRole('button',{name:'选择文件夹',exact:true}).click();
    await (await chooserReady).setFiles(root);
    const panel = page.getByRole('region', { name: '上传队列', exact: true });
    await expect(panel.getByText('原件已保存', { exact: false })).toHaveCount(22, { timeout: 45000 });
    const folders = (await api(page, '/folders?space_id=' + space)).data;
    expect(folders.filter(f => f.name === '资料包')).toHaveLength(1);
    const child = folders.find(f => f.name === '合同'); expect(child.parent_id).toBe(existing.id);
    const docs = (await api(page, `/documents?space_id=${space}&page_size=100`)).data.items;
    expect(docs).toHaveLength(22);
    expect(docs.find(d => d.title === '条款.txt').folder_id).toBe(child.id);
    expect(docs.filter(d => d.folder_id === existing.id)).toHaveLength(21);
    const file = docs.find(d => d.title === '资料0.txt');
    expect(await (await page.request.get(`/api/v1/documents/${file.id}/download`)).text()).toBe('原件内容-0');
    await page.screenshot({ path: '/tmp/juanzhan-folder-picker.png' });
    // Repeating a directory reuses its logical identity; duplicate content still needs a decision.
    const repeated = path.join(temp, '重复', '资料包'); await mkdir(repeated, { recursive: true });
    await writeFile(path.join(repeated, '资料0.txt'), '原件内容-0');
    await page.getByLabel('上传整个文件夹', { exact: true }).setInputFiles(repeated);
    await expect(panel.getByRole('button', { name: '仍要另存为独立档案' })).toHaveCount(1);
    await panel.getByRole('button', { name: '仍要另存为独立档案' }).click();
    await expect(panel.getByText('原件已保存', { exact: false })).toHaveCount(23);
    expect((await api(page, '/folders?space_id=' + space)).data).toHaveLength(3);
  } finally { await rm(temp, { recursive: true, force: true }); }
});

test('native OS drag accepts mixed folders and files, retains empty folders and supports failed upload retry', async ({ page }) => {
  const temp = await mkdtemp('/tmp/juanzhan-upload-drag-');
  try {
    const root = path.join(temp, '拖入目录'); await mkdir(path.join(root, '子目录'), { recursive: true }); await mkdir(path.join(root, '空目录'));
    await writeFile(path.join(root, '子目录', '记录.txt'), '拖入子目录原件');
    const loose = path.join(temp, '独立文件.txt'); await writeFile(loose, '混合拖入独立原件');
    await login(page); await createSpace(page, path.basename(temp));
    const space = await page.getByLabel('当前空间').inputValue();
    // CDP delivers real filesystem drag data, not a fabricated FileSystemEntry tree.
    const cdp = await page.context().newCDPSession(page);
    const box = await page.locator('.file-collection').boundingBox();
    const data = { items: [], files: [root, loose], dragOperationsMask: 1 };
    for (const type of ['dragEnter', 'dragOver', 'drop']) await cdp.send('Input.dispatchDragEvent', { type, x: box.x + 60, y: box.y + 60, data });
    const panel = page.getByRole('region', { name: '上传队列', exact: true });
    await expect(panel.getByText('原件已保存', { exact: false })).toHaveCount(2, { timeout: 30000 });
    const folders = (await api(page, '/folders?space_id=' + space)).data;
    const rootFolder = folders.find(f => f.name === '拖入目录');
    expect(folders.find(f => f.name === '空目录').parent_id).toBe(rootFolder.id);
    const child = folders.find(f => f.name === '子目录');
    const docs = (await api(page, '/documents?space_id=' + space)).data.items;
    expect(docs.find(d => d.title === '记录.txt').folder_id).toBe(child.id);
    expect(docs.find(d => d.title === '独立文件.txt').folder_id).toBeNull();
    await page.route('**/api/v1/documents/upload', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'STORAGE_UNAVAILABLE' } }) }), { times: 1 });
    await page.getByLabel('选择上传文件', { exact: true }).setInputFiles({ name: '重试.txt', mimeType: 'text/plain', buffer: Buffer.from('重试原件') });
    await panel.getByRole('button', { name: '重试 重试.txt', exact: true }).click();
    await expect(panel.getByText('原件已保存', { exact: false })).toHaveCount(3);
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: '/tmp/juanzhan-folder-drag-mobile.png' });
  } finally { await rm(temp, { recursive: true, force: true }); }
});

test('directory reader drains multiple batches, rejects unsafe paths and aborts before upload', async () => {
  let reads = 0;
  const files = Array.from({ length: 121 }, (_, i) => ({ name: `file${i}.txt`, isFile: true, file: ok => ok({ name: `file${i}.txt`, size: 1 }) }));
  const entry = { name: 'root', isDirectory: true, createReader: () => ({ readEntries: ok => ok(reads++ === 0 ? files.slice(0, 100) : reads === 2 ? files.slice(100) : []) }) };
  const transfer = { items: [{ kind: 'file', webkitGetAsEntry: () => entry, getAsFile: () => null }], files: [] };
  const result = await droppedFiles(transfer, new AbortController().signal);
  expect(reads).toBe(3); expect(result.filter(row => row.kind === 'file')).toHaveLength(121);
  expect(() => selectedFiles([{ name: 'bad.txt', webkitRelativePath: 'root/../bad.txt' }])).toThrow();
  expect(() => selectedFiles(Array.from({ length: 1001 }, (_, i) => ({ name: `${i}.txt` })))).toThrow(/1000/);
  const controller = new AbortController(); controller.abort();
  await expect(droppedFiles(transfer, controller.signal)).rejects.toHaveProperty('name', 'AbortError');
  const unreadable = { items: [{ kind: 'file', getAsFile: () => null, webkitGetAsEntry: () => ({ name: 'blocked.txt', isFile: true, file: (_ok, fail) => fail(Error('Permission denied')) }) }], files: [] };
  await expect(droppedFiles(unreadable, new AbortController().signal)).rejects.toThrow('Permission denied');
});

test('file quota excludes directories and excluded files',async()=>{
 const entries=Array.from({length:700},(_,i)=>({name:`item${i}.txt`,webkitRelativePath:`root/section${i}/item.txt`}));
 const result=selectedFiles([...entries,...Array.from({length:400},(_,i)=>({name:'.DS_Store',webkitRelativePath:`root/ignored${i}/.DS_Store`}))]);
 expect(result.filter(row=>row.kind==='file')).toHaveLength(700);
 expect(result.filter(row=>row.kind==='folder')).toHaveLength(701);
 expect(result.skipped.total).toBe(400);
 const exact=selectedFiles(Array.from({length:1000},(_,i)=>({name:`${i}.txt`,webkitRelativePath:`root/section${i}/${i}.txt`})));
 expect(exact.filter(row=>row.kind==='file')).toHaveLength(1000);
 expect(()=>selectedFiles(Array.from({length:1001},(_,i)=>({name:`${i}.txt`})))).toThrow(/1001个可上传文件/);
});
