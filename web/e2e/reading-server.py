"""Isolated real Archive + TCP Converter + worker for content browser validation."""
import os
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory
import threading

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


def main():
    with TemporaryDirectory(prefix='juanzhan-reading-browser-') as temp:
        root=Path(temp);token=secrets.token_urlsafe(32)
        converter=create_app('converter',Settings(root/'unused',token),converter_config=ConverterConfig(root=root/'converter'))
        with real_server(converter) as base:
            os.environ['CONVERTER_URL']=base
            settings=Settings(root/'archive',token,cookie_secure=False)
            settings.prepare_archive();migrate(settings.database)
            set_password(settings,os.environ['JUANZHAN_E2E_PASSWORD'])
            stop=threading.Event();worker=Worker(settings,stop=stop)
            def work():
                while not stop.is_set():
                    if os.environ.get("JUANZHAN_E2E_INDEXING") == "1":
                        from juanzhan.indexing import schedule
                        schedule(settings,limit=1)
                    worker.run_once(prefer_index=os.environ.get("JUANZHAN_E2E_INDEXING") == "1");stop.wait(.05)
            thread=threading.Thread(target=work,daemon=True);thread.start()
            try:uvicorn.run(create_app('archive',settings),host='127.0.0.1',port=8767,log_level='warning')
            finally:stop.set();thread.join(timeout=15)

if __name__=='__main__':main()
