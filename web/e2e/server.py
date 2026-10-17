"""Disposable real archive for browser tests; never uses the normal Compose volume."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'services'))
from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import migrate
import uvicorn

with TemporaryDirectory(prefix='juanzhan-browser-') as temp:
    settings=Settings(Path(temp),'',cookie_secure=False,upload_max_bytes=32768)
    settings.prepare_archive()
    migrate(settings.database)
    set_password(settings,os.environ['JUANZHAN_E2E_PASSWORD'])
    uvicorn.run(create_app('archive',settings),host='127.0.0.1',port=8767,log_level='warning')
