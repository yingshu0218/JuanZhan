"""Single-client warm HTTP baseline on synthetic 10k/100k SQLite/FTS corpora.

Does not measure upload/parsing throughput. No user volumes or credentials are used.
"""
import argparse
import hashlib
import http.cookiejar
import json
import math
import os
from pathlib import Path
import platform
import resource
import secrets
import socket
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'services'))
import uvicorn
from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import connect,migrate
from juanzhan.tokenizer import VERSION,indexed


def run(count,samples):
    with tempfile.TemporaryDirectory(prefix='juanzhan-benchmark-') as temp:
        settings=Settings(Path(temp),'',cookie_secure=False);settings.prepare_archive();migrate(settings.database)
        password=secrets.token_urlsafe(24);set_password(settings,password)
        start=time.perf_counter();now='2026-10-18T00:00:00Z'
        with connect(settings.database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO spaces VALUES (?,?,?,?)',('benchmark','Benchmark',now,now))
            for n in range(count):
                id=f'bench-{n:06}';title=f'档案合同 HT2026-{n:06}';text=indexed([title,'采购项目 检索基线 Archive2026'])
                db.execute('INSERT INTO documents(id,space_id,title,document_date,imported_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                           (id,'benchmark',title,'2026-10-18',now,now,now))
                db.execute('INSERT INTO document_search VALUES (?,?)',(id,text))
                db.execute('INSERT INTO document_search_state(document_id,tokenizer_version,content_hash,indexed_at,generation) VALUES (?,?,?,?,1)',
                           (id,VERSION,hashlib.sha256(text.encode()).hexdigest(),now))
            db.execute('UPDATE search_dirty SET scheduled_generation=generation');db.commit()
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        seed=time.perf_counter()-start
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(create_app('archive',settings),log_level='error'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
        try:
            deadline=time.monotonic()+15
            while not server.started:
                if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('Benchmark server did not start')
                time.sleep(.01)
            opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            base=f'http://127.0.0.1:{port}/api/v1'
            def request(path,body=None,csrf=None):
                headers={'Content-Type':'application/json'}
                if csrf:headers['X-CSRF-Token']=csrf
                with opener.open(urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=30) as r:
                    return json.load(r)
            csrf=request('/auth/session')['csrf_token'];request('/auth/login',{'username':'admin','password':password},csrf)
            paths={'list':'/documents?space_id=benchmark&page_size=20',
                'chinese_common':'/documents?space_id=benchmark&q='+urllib.parse.quote('合同')+'&page_size=20',
                'mixed_identifier':'/documents?space_id=benchmark&q='+urllib.parse.quote('HT2026-000001')+'&page_size=20',
                'missing':'/documents?space_id=benchmark&q='+urllib.parse.quote('不存在')+'&page_size=20'}
            results={}
            for name,path in paths.items():
                warm=request(path);assert warm['total']==(0 if name=='missing' else 1 if name=='mixed_identifier' else count),(name,warm['total'])
                timings=[]
                for _ in range(samples):
                    begin=time.perf_counter();value=request(path);timings.append((time.perf_counter()-begin)*1000)
                    assert value['total']==warm['total']
                results[name]={'samples':samples,'p50_ms':round(statistics.median(timings),2),
                    'p95_ms':round(sorted(timings)[math.ceil(.95*samples)-1],2),'matches':warm['total']}
            return {'documents':count,'fixture_seed_seconds':round(seed,2),'db_bytes':settings.database.stat().st_size,
                'sqlite_total_files_bytes':sum(p.stat().st_size for p in settings.database.parent.iterdir() if p.is_file()),
                'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'requests':results}
        finally:
            server.should_exit=True;thread.join(timeout=15);sock.close()
            if thread.is_alive():raise RuntimeError('Benchmark server did not stop')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--counts',type=int,nargs='+',default=[10000,100000]);parser.add_argument('--samples',type=int,default=20)
    args=parser.parse_args()
    if any(n<1 or n>100000 for n in args.counts) or not 5<=args.samples<=100:parser.error('Invalid bounded workload')
    report={'environment':{'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'platform':platform.platform(),
                'logical_cpus':os.cpu_count(),'tokenizer':VERSION},'scope':'Synthetic metadata/FTS, real single-client warm TCP HTTP; no originals, OCR or ingestion throughput',
            'results':[run(n,args.samples) for n in args.counts]}
    output=Path(tempfile.mkdtemp(prefix='juanzhan-performance-'))/'baseline.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(str(output))
if __name__=='__main__':main()
