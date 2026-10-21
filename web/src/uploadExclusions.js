import rules from '../../services/juanzhan/upload_exclusions.json' with { type: 'json' };
const files = new Set(rules.files.map(name => name.toLowerCase()));
const directories = new Set(rules.directories.map(name => name.toLowerCase()));
const patterns = rules.patterns.map(pattern => new RegExp(pattern));
export function uploadExclusion(path, isDirectory = false) {
  const names = path.split('/');
  if (names.some((name, index) => (isDirectory || index < names.length - 1) && directories.has(name.toLowerCase()))) return '系统辅助目录及其内容';
  const name = names.at(-1);
  if (!isDirectory && (files.has(name.toLowerCase()) || patterns.some(pattern => pattern.test(name.toLowerCase())))) return '系统元数据、缓存或临时锁文件';
  return null;
}
