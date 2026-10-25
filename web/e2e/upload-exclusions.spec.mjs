import { test, expect } from '@playwright/test';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { login, createSpace, api } from './helpers.mjs';
import { droppedFiles, selectedFiles } from '../src/uploadTree.js';
import { uploadExclusion } from '../src/uploadExclusions.js';

for (const mode of ['picker', 'drop']) test(`auxiliary files are skipped before ${mode} uploads and hidden documents survive`, async ({ page }) => {
  const temp = await mkdtemp('/tmp/juanzhan-upload-exclusions-');
  try {
    const root = path.join(temp, '资料'); await mkdir(path.join(root, '__MACOSX'), { recursive: true });
    const excluded = ['.DS_Store', 'Thumbs.db', '._report.txt', '~$draft.docx', '.~lock.notes.odt#', '.report.swp', '.gitignore', '.gitattributes', '.gitmodules', '.env', 'main.py', 'data.json', 'config.yml'];
    const kept = ['README.md', 'notes.tmp', 'notes.bak', 'report.txt'];
    for (const name of [...excluded, ...kept]) await writeFile(path.join(root, name), mode + '-' + name);
    await writeFile(path.join(root, '__MACOSX', 'hidden.txt'), 'Not a document');
    for (const directory of ['.git', '.svn', '.hg', '.bzr']) { await mkdir(path.join(root, directory)); await writeFile(path.join(root, directory, 'metadata'), 'Ignored repository data'); }
    const skipCount = excluded.length + 5;
    const errors = [], uploads = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', entry => { if (entry.type() === 'error') errors.push(entry.text()); });
    page.on('request', request => { if (request.url().endsWith('/documents/upload')) uploads.push(request); });
    await login(page); await createSpace(page, path.basename(temp));
    const space = await page.getByLabel('当前空间').inputValue();
    if (mode === 'picker') await page.getByLabel('上传整个文件夹', { exact: true }).setInputFiles(root);
    else {
      const cdp = await page.context().newCDPSession(page), box = await page.locator('.file-collection').boundingBox();
      for (const type of ['dragEnter', 'dragOver', 'drop']) await cdp.send('Input.dispatchDragEvent', { type, x: box.x + 60, y: box.y + 60, data: { items: [], files: [root], dragOperationsMask: 1 } });
    }
    const panel = page.getByRole('region', { name: '上传队列', exact: true });
    await expect(panel.getByText('原件已保存', { exact: false })).toHaveCount(kept.length);
    await expect(panel.locator('.upload-skipped summary')).toContainText(`${skipCount} 项`);
    const documents = (await api(page, '/documents?space_id=' + space)).data.items;
    expect(documents.map(doc => doc.title).sort()).toEqual(kept.sort());
    expect((await api(page, '/folders?space_id=' + space)).data.map(folder => folder.name)).toEqual(['资料']);
    expect(uploads).toHaveLength(kept.length);
    await page.getByLabel('选择上传文件', { exact: true }).setInputFiles({ name: '.DS_Store', mimeType: 'application/octet-stream', buffer: Buffer.from('ignored') });
    await expect(panel.locator('.upload-skipped summary')).toContainText(`${skipCount + 1} 项`);
    expect(uploads).toHaveLength(kept.length);
    await panel.locator('.upload-skipped summary').click();
    await expect(panel.locator('.upload-skipped')).toContainText('.DS_Store');
    if (mode === 'drop') await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `/tmp/juanzhan-exclusions-${mode}.png` });
    expect(errors).toEqual([]);
  } finally { await rm(temp, { recursive: true, force: true }); }
});

test('exclusion boundaries are conservative and ignored directories are never read', async () => {
  for (const name of ['.DS_Store', '.ds_store', 'desktop.ini', '._test.pdf', '~$test.xlsx', '.~lock.test.odt#', '.test.swo', '.gitignore', '.git', '.gitmodules', '.gitattributes', '.env', 'main.py', 'data.json', 'config.yml']) expect(uploadExclusion(name)).toBeTruthy();
  for (const name of ['README.md', '.hidden.docx', 'notes.tmp', 'notes.bak', 'notes.docx~', 'Thumbs.db.txt', '~$budget.txt']) expect(uploadExclusion(name)).toBeNull();
  const selected = selectedFiles([{ name: 'notes.txt', webkitRelativePath: 'root/__MACOSX/notes.txt' }]);
  expect(selected).toHaveLength(0); expect(selected.skipped.total).toBe(1);
  const transfer = { files: [], items: [{ kind: 'file', getAsFile: () => null, webkitGetAsEntry: () => ({ name: '__MACOSX', isDirectory: true, createReader() { throw Error('Excluded directory must not be read'); } }) }] };
  const dropped = await droppedFiles(transfer, new AbortController().signal);
  expect(dropped).toHaveLength(0); expect(dropped.skipped.total).toBe(1);
  for (const directory of ['.git', '.svn', '.hg', '.bzr']) {
    const transfer = { files: [], items: [{ kind: 'file', getAsFile: () => null, webkitGetAsEntry: () => ({ name: directory, isDirectory: true, createReader() { throw Error('Repository metadata must not be read'); } }) }] };
    const dropped = await droppedFiles(transfer, new AbortController().signal);
    expect(dropped).toHaveLength(0); expect(dropped.skipped.total).toBe(1);
  }
});
