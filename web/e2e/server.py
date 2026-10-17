"""Disposable real API/worker for browser tests; never uses the Compose volume."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'services'))
from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import migrate
from juanzhan.worker import Worker
import uvicorn


def main():
    with TemporaryDirectory(prefix='juanzhan-browser-') as temp:
        settings=Settings(Path(temp),'',cookie_secure=False,upload_max_bytes=32768)
        settings.prepare_archive()
        migrate(settings.database)
        set_password(settings,os.environ['JUANZHAN_E2E_PASSWORD'])
        stop=threading.Event()
        worker=Worker(settings,stop=stop)
        def run_worker():
            while not stop.is_set():
                worker.run_once()
                stop.wait(0.05)
        thread=threading.Thread(target=run_worker,daemon=True)
        thread.start()
        try:uvicorn.run(create_app('archive',settings),host='127.0.0.1',port=8767,log_level='warning')
        finally:
            stop.set()
            thread.join(timeout=10)


if __name__=='__main__':main()
