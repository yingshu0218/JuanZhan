"""Fetch hash-pinned Debian tools/sources or verify and install them offline in an image."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--download',action='store_true');parser.add_argument('--install',action='store_true')
    args=parser.parse_args();lock=json.loads((ROOT/'legacy-tools.lock.json').read_text())
    folder=ROOT/'native-packages';folder.mkdir(exist_ok=True)
    for item in lock['files']:
        name=item['name']
        if Path(name).name!=name:raise ValueError('Invalid locked package name')
        target=folder/name
        if args.download:
            with urllib.request.urlopen(item['url'],timeout=30) as response:
                data=response.read(item['size_bytes']+1)
            if len(data)!=item['size_bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Native package hash mismatch')
            target.write_bytes(data)
        data=target.read_bytes()
        if len(data)!=item['size_bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Native package hash mismatch')
    if args.install:
        if platform.system()!='Linux' or platform.machine()!='x86_64':raise RuntimeError('Locked native binaries currently require Linux x86_64')
        binaries=[str(folder/item['name']) for item in lock['files'] if item['role']=='binary']
        subprocess.run(['dpkg','-i',*binaries],check=True)
        actual=subprocess.check_output(['dpkg-query','-W','-f=${Version}',lock['package']],text=True)
        if actual!=lock['version']:raise ValueError('Installed native package version mismatch')
        source=Path('/usr/share/doc/catdoc/corresponding-source');source.mkdir(exist_ok=True)
        for item in lock['files']:
            if item['role']=='source':shutil.copyfile(folder/item['name'],source/item['name'])
        shutil.copyfile(ROOT/'legacy-tools.lock.json',source/'legacy-tools.lock.json')
    print('Native tools and corresponding sources verified')

if __name__=='__main__':main()
