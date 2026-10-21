"""Isolated real Archive + TCP Converter + worker for content browser validation."""
import os
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory
import threading
from contextlib import contextmanager
import subprocess
import time
import urllib.request
import uuid
import signal

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'services'),str(ROOT/'tests')]
from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.conversion_store import ConverterConfig
from juanzhan.database import migrate
from juanzhan.worker import Worker
from test_converter import real_server
import uvicorn

@contextmanager
def converter_server(root,token):
    image=os.environ.get('JUANZHAN_E2E_CONVERTER_IMAGE')
    if not image:
        converter=create_app('converter',Settings(root/'unused',token),converter_config=ConverterConfig(root=root/'converter'))
        with real_server(converter) as base:yield base
        return
    name='juanzhan-reading-converter-'+uuid.uuid4().hex[:12]
    def docker(*args):
        result=subprocess.run(['docker',*args],env={**os.environ,'CONVERTER_SERVICE_TOKEN':token},capture_output=True,text=True,timeout=30,check=True)
        return result.stdout.strip()
    try:
        docker('run','-d','--name',name,'--read-only','--cap-drop=ALL','--security-opt','no-new-privileges:true',
               '--tmpfs','/tmp:size=128m,mode=1777','--memory','512m','--cpus','1','-p','127.0.0.1::8000',
               '-e','CONVERTER_SERVICE_TOKEN',image,'python','-m','uvicorn','juanzhan.converter:app','--host','0.0.0.0','--port','8000')
        base='http://'+docker('port',name,'8000/tcp').splitlines()[0]
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(100):
            try:
                with opener.open(base+'/healthz',timeout=1):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Isolated image Converter did not become healthy')
        yield base
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)


def main():
    def stop_on_signal(signum,frame):raise SystemExit(0)
    # Uvicorn replays captured SIGTERM to the original handler. SystemExit unwinds
    # our worker/context cleanup instead of the OS default terminating immediately.
    signal.signal(signal.SIGTERM,stop_on_signal)
    with TemporaryDirectory(prefix='juanzhan-reading-browser-') as temp:
        root=Path(temp);token=os.environ.get('JUANZHAN_E2E_SERVICE_TOKEN') or secrets.token_urlsafe(32)
        with converter_server(root,token) as base:
            os.environ['CONVERTER_URL']=base
            settings=Settings(root/'archive',token,cookie_secure=False)
            settings.prepare_archive();migrate(settings.database)
            set_password(settings,os.environ['JUANZHAN_E2E_PASSWORD'])
            pointer=os.environ.get('JUANZHAN_E2E_ARCHIVE_POINTER')
            if pointer:
                with open(pointer,'x') as file:
                    os.chmod(pointer,0o600);file.write(str(settings.data_dir))
            stop=threading.Event();worker=Worker(settings,stop=stop)
            def work():
                while not stop.is_set():
                    if os.environ.get("JUANZHAN_E2E_INDEXING") == "1":
                        from juanzhan.indexing import schedule
                        schedule(settings,limit=1)
                    worker.run_once(prefer_index=os.environ.get("JUANZHAN_E2E_INDEXING") == "1");stop.wait(.05)
            thread=threading.Thread(target=work,daemon=True);thread.start()
            try:uvicorn.run(create_app('archive',settings),host='127.0.0.1',port=8767,log_level='warning')
            finally:
                stop.set();thread.join(timeout=15)
                if pointer:Path(pointer).unlink(missing_ok=True)

if __name__=='__main__':main()
