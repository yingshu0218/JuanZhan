// Browser-relative names only. Never send a client filesystem path to the server.
export const MAX_UPLOAD_ENTRIES = 1000;
const abort = signal => { if (signal?.aborted) throw new DOMException('Aborted', 'AbortError'); };
function parts(path) {
  const result = path.split('/');
  if (result.length > 32 || result.some(name => !name.trim() || name === '.' || name === '..' || name.length > 255 || /[\\\u0000-\u001f\u007f]/u.test(name))) throw Error('目录名称或层级不符合要求，最多支持32层目录。');
  return result;
}
function tree() {
  const directories = new Set(), files = [];
  function directory(path) {
    const names = parts(path);
    for (let i = 1; i <= names.length; i++) directories.add(names.slice(0, i).join('/'));
    limit();
  }
  function limit() { if (directories.size + files.length > MAX_UPLOAD_ENTRIES) throw Error('单批最多1000个文件和目录，请拆分后上传；本批尚未上传。'); }
  return {
    directory,
    file(file, path) {
      const names = parts(path);
      if (names.length > 1) directory(names.slice(0, -1).join('/'));
      files.push({ kind: 'file', file, path, parentPath: names.slice(0, -1).join('/') }); limit();
    },
    result() { return [...[...directories].sort((a, b) => a.split('/').length - b.split('/').length).map(path => ({ kind: 'folder', file: { name: path.split('/').at(-1), size: 0 }, path, parentPath: path.split('/').slice(0, -1).join('/') })), ...files]; },
  };
}
export function selectedFiles(files) {
  const result = tree();
  for (const file of files) result.file(file, file.webkitRelativePath || file.name);
  return result.result();
}
function callbackCall(start, signal) {
  return new Promise((resolve, reject) => {
    const stopped = () => { cleanup(); reject(new DOMException('Aborted', 'AbortError')); };
    const cleanup = () => signal?.removeEventListener('abort', stopped);
    if (signal?.aborted) return stopped();
    signal?.addEventListener('abort', stopped, { once: true });
    try { start(value => { cleanup(); resolve(value); }, error => { cleanup(); reject(error); }); }
    catch (error) { cleanup(); reject(error); }
  });
}
export async function droppedFiles(transfer, signal, onCount = () => {}) {
  // Capture entries during the drop event, before its DataTransfer store is protected.
  const items = [...transfer.items].filter(item => item.kind === 'file');
  const roots = items.map(item => ({ entry: item.webkitGetAsEntry?.(), file: item.getAsFile() }));
  const fallback = [...transfer.files];
  const result = tree(); let count = 0;
  async function visit(entry, parent = '') {
    abort(signal);
    const path = parent ? parent + '/' + entry.name : entry.name;
    parts(path);
    if (++count > MAX_UPLOAD_ENTRIES) throw Error('单批最多1000个文件和目录，请拆分后上传；本批尚未上传。');
    onCount(count);
    if (entry.isDirectory) {
      result.directory(path);
      const reader = entry.createReader();
      for (let batches = 0; ; batches++) {
        abort(signal);
        if (batches > MAX_UPLOAD_ENTRIES) throw Error('目录读取异常，请改用选择文件夹。');
        const children = await callbackCall((ok, fail) => reader.readEntries(ok, fail), signal);
        if (!children.length) break;
        for (const child of children) await visit(child, path);
      }
    } else if (entry.isFile) {
      const file = await callbackCall((ok, fail) => entry.file(ok, fail), signal);
      abort(signal); result.file(file, path);
    } else throw Error('无法读取拖入的项目，请改用选择文件或文件夹。');
  }
  if (roots.length) {
    for (const root of roots) {
      if (root.entry) await visit(root.entry);
      else if (root.file) result.file(root.file, root.file.name);
      else throw Error('浏览器无法读取此文件夹，请使用“选择文件夹”。');
    }
  } else for (const file of fallback) { abort(signal); result.file(file, file.name); }
  abort(signal);
  return result.result();
}

export function folderResolver(api, spaceId, baseFolderId) {
  const resolved = new Map([['', baseFolderId || null]]);
  let folders;
  const reload = async signal => { folders = await api.request('/folders?space_id=' + encodeURIComponent(spaceId), { signal }); };
  return async function ensure(path, signal) {
    let prefix = '', parent = baseFolderId || null;
    for (const name of path ? parts(path) : []) {
      abort(signal); prefix = prefix ? prefix + '/' + name : name;
      if (resolved.has(prefix)) { parent = resolved.get(prefix); continue; }
      if (!folders) await reload(signal);
      const match = () => folders.find(folder => folder.parent_id === parent && folder.name === name.trim().normalize('NFC'));
      let folder = match();
      if (!folder) {
        try { folder = await api.request('/folders', { method: 'POST', body: { space_id: spaceId, parent_id: parent, name }, signal }); folders.push(folder); }
        catch (error) {
          if (error.code !== 'CATALOG_CONFLICT') throw error;
          await reload(signal); folder = match();
          if (!folder) throw error; // Do not guess which differently spelled directory to reuse.
        }
      }
      parent = folder.id; resolved.set(prefix, parent);
    }
    return parent;
  };
}
