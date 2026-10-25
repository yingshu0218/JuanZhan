import formats from '../../services/juanzhan/upload_formats.json' with { type: 'json' };
export const defaultUploadPolicy={excluded_groups:formats.groups.filter(g=>g.default_excluded).map(g=>g.id),custom_extensions:[],groups:formats.groups};
import rules from '../../services/juanzhan/upload_exclusions.json' with { type: 'json' };
const files = new Set(rules.files.map(name => name.toLowerCase()));
const directories = new Set(rules.directories.map(name => name.toLowerCase()));
const patterns = rules.patterns.map(pattern => new RegExp(pattern));
const versionFiles = new Set(rules.version_control_files.map(name => name.toLowerCase()));
const versionDirectories = new Set(rules.version_control_directories.map(name => name.toLowerCase()));
export function uploadExclusion(path, isDirectory = false, policy = defaultUploadPolicy) {
  const names = path.split('/');
  if (names.some((name, index) => (isDirectory || index < names.length - 1) && versionDirectories.has(name.toLowerCase()))) return '版本控制元数据目录及其内容';
  if (!isDirectory && versionFiles.has(names.at(-1).toLowerCase())) return '版本控制配置或元数据文件';
  if (names.some((name, index) => (isDirectory || index < names.length - 1) && directories.has(name.toLowerCase()))) return '系统辅助目录及其内容';
  const name = names.at(-1);
  if (!isDirectory && (files.has(name.toLowerCase()) || patterns.some(pattern => pattern.test(name.toLowerCase())))) return '系统元数据、缓存或临时锁文件';
  const lower=name.toLowerCase();
  for(const group of policy.groups||formats.groups){
    if(!policy.excluded_groups.includes(group.id))continue;
    if(names.some((name,index)=>(isDirectory||index<names.length-1)&&((group.directories||[]).includes(name.toLowerCase())||(group.directory_extensions||[]).some(extension=>name.toLowerCase().endsWith('.'+extension)))))return group.label;
    if(!isDirectory&&((group.extensions||[]).some(extension=>lower.endsWith('.'+extension))||(group.files||[]).some(file=>file.toLowerCase()===lower)||(group.prefixes||[]).some(prefix=>lower.startsWith(prefix))))return group.label;
  }
  if(!isDirectory&&(policy.custom_extensions||[]).some(extension=>lower.endsWith('.'+extension)))return '自定义排除格式';
  return null;
}
