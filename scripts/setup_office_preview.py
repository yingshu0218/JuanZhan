"""Fetch SHA-256-pinned native Office packages into a project-only build cache."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler

ROOT=Path(__file__).resolve().parents[1]
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def check(path,package):
    if not path.is_file() or path.stat().st_size!=package['size_bytes']:return False
    with path.open('rb') as file:return hashlib.file_digest(file,'sha256').hexdigest()==package['sha256']

def download(package,directory,mirror):
    name=package['filename']
    if Path(name).name!=name or not name.endswith('.deb') or any(ord(c)<33 for c in name):raise ValueError('Invalid package filename')
    target=directory/name
    if check(target,package):return name
    parsed=urlsplit(package['url'])
    if parsed.hostname!='deb.debian.org' or parsed.scheme not in ('http','https') or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('Unexpected package source')
    original='https://deb.debian.org'+parsed.path
    urls=[mirror+parsed.path,original] if mirror else [original]
    for url in dict.fromkeys(urls):
        temporary=None
        try:
            start=time.monotonic();size=0;digest=hashlib.sha256()
            opener=build_opener(ProxyHandler({}),NoRedirect())
            with opener.open(Request(url),timeout=30) as source,tempfile.NamedTemporaryFile(dir=directory,prefix='.office-',delete=False) as output:
                temporary=Path(output.name)
                while chunk:=source.read(131072):
                    size+=len(chunk)
                    if size>package['size_bytes'] or time.monotonic()-start>300:raise ValueError('Package exceeds declared budget')
                    digest.update(chunk);output.write(chunk)
                output.flush();os.fsync(output.fileno())
            if size!=package['size_bytes'] or digest.hexdigest()!=package['sha256']:raise ValueError('Package checksum mismatch')
            os.replace(temporary,target);return name
        except Exception:
            if temporary is not None:temporary.unlink(missing_ok=True)
            if url==urls[-1]:raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--mirror',choices=['https://mirrors.aliyun.com','https://mirrors.tuna.tsinghua.edu.cn'])
    args=parser.parse_args()
    manifest=json.loads((ROOT/'office-preview-tools.lock.json').read_text());packages=manifest['packages']
    if len(packages)>500 or sum(p['size_bytes'] for p in packages)>1024**3 or any(p['size_bytes']>256*1024**2 for p in packages):raise ValueError('Native package budget exceeded')
    directory=ROOT/'office-packages';directory.mkdir(exist_ok=True)
    expected={p['filename'] for p in packages}
    if any(p.name not in expected for p in directory.glob('*.deb')):raise ValueError('Unlisted native package in build cache')
    if args.download:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures=[pool.submit(download,p,directory,args.mirror) for p in packages]
            for future in as_completed(futures):print('Verified '+future.result(),flush=True)
    if not all(check(directory/p['filename'],p) for p in packages):raise SystemExit('Pinned Office packages missing; run --download')
    print('Verified '+str(len(packages))+' native packages; bytes='+str(sum(p['size_bytes'] for p in packages)))

if __name__=='__main__':main()
